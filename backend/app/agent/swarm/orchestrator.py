"""Swarm orchestration: plan, fan out, distil, summarise (ADR 019).

The whole multi-agent turn lives here, in one function the graph node calls. Four
phases:

1. **Plan** — one model call. The roster is the menu; the model decides how many
   agents the question needs and which ones, and writes each a sub-question. The
   size is the planner's, not a constant: one specialist is the right answer to
   "how many members do I have", forty to "how is the business doing". This also
   doubles as the gate — a question no specialist can help with plans ``direct``
   and the turn falls back to the ordinary ReAct path without spending anything
   further.
2. **Fan out** — every chosen specialist runs concurrently. Forty agents take as
   long as the slowest one, not the sum, which is the entire point.
3. **Distil** — one model call per domain that actually ran, concurrently. The
   orchestrator reads only its own specialists' findings and writes a digest.
   This is what makes it an orchestrator rather than a ``gather``: forty raw
   findings do not fit in a prompt, five digests do.
4. **Summarise** — one model call over the five digests, streamed to the client
   as ``delta`` frames so the answer types out exactly as it does on the direct
   path.

A swarm turn is therefore ~7 model calls plus whichever judgement specialists
were dispatched — not forty, which is what makes running forty defensible.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agent.context import AgentContext
from app.agent.model import build_chat_model
from app.core.permissions import Capability, role_has
from app.services.audit_service import record_audit
from app.agent.swarm.roster import BY_ID, DOMAIN_NAMES, DOMAINS, roster_brief
from app.agent.swarm.types import (
    DETAIL_MAX,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_SKIPPED,
    AskFn,
    Assignment,
    Finding,
    AgentPlan,
    Specialist,
)

# Concurrent specialists. The bound is not about CPU — it is about the shared
# ``AsyncSession``: every deterministic agent reads through the one session bound
# to the run, and its connection pool is finite. See queries.py.
MAX_CONCURRENT = 8

# How long the planner may deliberate. It chooses from a fixed menu, so a slow
# plan is a sign of trouble, not of thinking.
PLAN_TIMEOUT = 30.0


def _reasoning(chunk: Any) -> str | None:
    """Reasoning text from a chunk, across the keys providers use.

    The same helper as ``graph._reasoning``, and deliberately duplicated rather
    than imported: ``graph`` imports the swarm, so reaching back the other way
    would close a cycle. gpt-oss emits a reasoning trace before its answer, and
    the swarm's summariser was dropping it — which is why a swarm turn had no
    thinking of its own while a direct turn had plenty.
    """

    extra = getattr(chunk, "additional_kwargs", None) or {}
    return extra.get("reasoning_content") or extra.get("reasoning")


def _clip(text: str) -> str:
    """Bound evidence at the frame boundary, so the column cannot grow unbounded.

    Applied where the frame is built rather than where the finding is made: the
    raw ``Finding`` keeps its full detail for callers that want it, and only what
    travels to the client and the database is capped.
    """

    if len(text) <= DETAIL_MAX:
        return text
    return text[:DETAIL_MAX] + "\n… (truncated)"


@dataclass
class _Tally:
    """What the turn cost, counted as it is spent rather than estimated.

    Emitted to the client so the panel can answer "was that worth it?" with real
    numbers — the difference between a swarm that ran eight queries and one that
    ran eight model calls is the whole cost argument for this design.
    """

    model_calls: int = 0
    findings: dict[str, int] = field(default_factory=dict)

    def count(self, finding: Finding) -> None:
        self.findings[finding.status] = self.findings.get(finding.status, 0) + 1

    def stats(self, *, agents: int, domains: int, fanout_ms: int, turn_ms: int) -> dict:
        return {
            "agents": agents,
            "domains": domains,
            # The orchestrators are agents too, and the header counts them.
            "total": agents + domains,
            "model_calls": self.model_calls,
            "done": self.findings.get(STATUS_DONE, 0),
            "skipped": self.findings.get(STATUS_SKIPPED, 0),
            "failed": self.findings.get(STATUS_FAILED, 0),
            "fanout_ms": fanout_ms,
            # Plan to answer, including the planner. This is the "Worked for"
            # number, and it is persisted with the turn so a reloaded thread can
            # still say how long it took — the client's own stopwatch survives
            # only until the page is refreshed.
            "turn_ms": turn_ms,
        }


def _ask_fn(model, tally: _Tally) -> AskFn:
    """Adapt a chat model to the ``(system, user) -> text`` shape specialists see.

    The call is counted here rather than at the call sites because this is the
    one funnel every judgement specialist's model call goes through.
    """

    async def ask(system: str, user: str) -> str:
        tally.model_calls += 1
        reply = await model.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        return str(reply.content or "")

    return ask


def _plan_prompt() -> str:
    """The planner's instructions: how many agents, and which ones.

    The size of the dispatch is the planner's main decision, and it is deliberately
    open-ended. "How many members do I have" is one specialist's entire remit, so
    it gets one; "why did revenue drop" is four; a full review is all forty. A
    floor would be the wrong answer to the only question that matters here — how
    many agents this particular question actually needs — and it would show in the
    UI, because every agent that runs is a row the user reads.
    """

    menu = "\n".join(f"- {b['id']} ({b['domain']}): {b['specialization']}" for b in roster_brief())
    return (
        "You are a routing planner for a multi-tenant venue-operations assistant. "
        "You choose which specialist analysts should investigate a question, and how many.\n\n"
        f"Available specialists:\n{menu}\n\n"
        "Reply with JSON only, no prose and no code fence:\n"
        '{"mode": "direct" | "swarm", "reason": "<why, one sentence>", "agents": '
        '[{"id": "<specialist id>", "question": "<what to find out>"}]}\n\n'
        'Choose "direct" only when no specialist has anything to add — a greeting, a question '
        'about your own capabilities, or something the assistant\'s own tools already answer.\n\n'
        'Choose "swarm" for anything that needs this gym\'s data, and size the dispatch to the '
        'question: exactly as many specialists as it takes, from one to forty. One specialist '
        'answers "how many members do I have". Two or three answer a comparison. A full review '
        'or an open "how is the business doing" takes everything that bears on it. Do not pad '
        'the list to look thorough — every agent you dispatch is shown to the user as a row and '
        'costs a lookup — and do not trim it to look fast. Give each one a specific '
        "sub-question. The reason is shown to the user, so make it a real justification for "
        "this choice and for this size."
    )


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_plan(raw: str) -> AgentPlan:
    """A planner reply as a plan, degrading to ``direct`` on anything unreadable.

    Failing to ``direct`` rather than raising is deliberate: an unparseable plan
    should cost the user a swarm, not their answer.
    """

    match = _JSON_BLOCK.search(raw or "")
    if not match:
        return AgentPlan(mode="direct")
    try:
        payload = json.loads(match.group(0))
    except (ValueError, TypeError):
        return AgentPlan(mode="direct")
    if not isinstance(payload, dict):
        return AgentPlan(mode="direct")

    mode = str(payload.get("mode") or "direct").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    agents: list[Assignment] = []
    seen: set[str] = set()
    raw_agents = payload.get("agents")
    for entry in raw_agents if isinstance(raw_agents, list) else []:
        if not isinstance(entry, dict):
            continue
        agent_id = str(entry.get("id") or "").strip()
        # Drop anything the planner invented. The model picks from a menu, but a
        # hallucinated id must not become a KeyError three phases later.
        if agent_id not in BY_ID or agent_id in seen:
            continue
        seen.add(agent_id)
        agents.append(
            Assignment(
                agent_id=agent_id,
                question=str(entry.get("question") or "").strip() or "What stands out here?",
            )
        )
    if mode != "swarm":
        return AgentPlan(mode="direct")
    return AgentPlan(mode="swarm", agents=agents[: len(BY_ID)], reason=reason)


async def plan_turn(question: str, model) -> AgentPlan:
    """Ask the planner how this turn should be answered."""

    try:
        reply = await asyncio.wait_for(
            model.ainvoke(
                [
                    {"role": "system", "content": _plan_prompt()},
                    {"role": "user", "content": question},
                ]
            ),
            timeout=PLAN_TIMEOUT,
        )
    except Exception:  # noqa: BLE001
        # A planner that fails is a planner with no opinion — which is exactly
        # what "direct" means. The turn still gets answered.
        return AgentPlan(mode="direct")
    return parse_plan(str(getattr(reply, "content", "") or ""))


async def _run_one(
    specialist: Specialist,
    assignment: Assignment,
    ctx: AgentContext,
    ask: AskFn,
    writer: Callable[[dict], None],
) -> Finding:
    """Run one specialist, converting any failure into a finding.

    One agent raising must not take the turn down — a swarm that dies because
    one of forty queries hit a missing column is worse than a swarm that reports
    39 findings and one failure, and the UI has a row for exactly that.

    The ``agent_done`` frame is written here, the moment this agent settles, so
    rows fill in as they arrive rather than all at once when the slowest one
    finishes. That is also what makes the reported ``ms`` this agent's own.
    """

    started = time.monotonic()
    try:
        allowed = role_has(ctx.role, Capability.USE_ASSISTANT) and (
            specialist.domain != "payroll" or role_has(ctx.role, Capability.RUN_PAYROLL)
        )
        if allowed:
            finding = await specialist.run(ctx, ask, assignment.question)
            await record_audit(ctx.session, action="privacy.data_accessed", organization_id=ctx.org_id,
                               actor_user_id=ctx.user_id, entity_type=specialist.domain,
                               metadata={"source": "assistant", "specialist": specialist.id, "role": ctx.role.value})
        else:
            finding = Finding(agent_id=specialist.id, status=STATUS_SKIPPED,
                              summary="Your role does not have access to this information.")
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("Assistant specialist failed: %s", specialist.id)
        finding = Finding(
            agent_id=specialist.id,
            status=STATUS_FAILED,
            summary="This analysis could not complete. Please try again.",
        )
    writer(
        {
            "agent_done": {
                "id": finding.agent_id,
                "status": finding.status,
                "summary": finding.summary,
                "detail": _clip(finding.detail),
                "ms": int((time.monotonic() - started) * 1000),
            }
        }
    )
    return finding


async def _run_domain(
    domain_id: str,
    assignments: list[Assignment],
    ctx: AgentContext,
    ask: AskFn,
    writer: Callable[[dict], None],
    gate: asyncio.Semaphore,
) -> tuple[str, list[Finding]]:
    """Fan out one domain's specialists, then distil their findings.

    The orchestrator is announced with the same ``agent_start``/``agent_done``
    frames the specialists use, so the UI renders one shape for both — it is one
    of the agents in the picture, it just starts after its team has finished.
    """

    name = DOMAIN_NAMES.get(domain_id, domain_id)
    writer(
        {
            "agent_start": {
                "id": f"orchestrator:{domain_id}",
                "name": f"{name} orchestrator",
                "domain": domain_id,
                "role": "orchestrator",
                "specialization": f"Distils the {name.lower()} specialists into one finding",
                "why": "Someone has to turn eight findings into something that fits in a prompt.",
                "tool": f"distil_{domain_id}",
            }
        }
    )
    orch_started = time.monotonic()

    async def guarded(specialist: Specialist, assignment: Assignment) -> Finding:
        async with gate:
            return await _run_one(specialist, assignment, ctx, ask, writer)

    findings = await asyncio.gather(
        *(guarded(BY_ID[a.agent_id], a) for a in assignments if a.agent_id in BY_ID)
    )

    digest = _digest_text(name, findings)
    if findings:
        digest = await _distil(ask, name, findings) or digest

    writer(
        {
            "agent_done": {
                "id": f"orchestrator:{domain_id}",
                "status": "done",
                "summary": digest,
                # The orchestrator's digest is a conclusion about its team, so it
                # carries the team's raw findings too — expanding it shows what
                # the digest was built from, not just what it says.
                "detail": _clip(
                    "\n".join(
                        f"{BY_ID[f.agent_id].name if f.agent_id in BY_ID else f.agent_id} "
                        f"[{f.status}]: {f.summary}"
                        for f in findings
                    )
                ),
                "ms": int((time.monotonic() - orch_started) * 1000),
            }
        }
    )
    return domain_id, findings


def _digest_text(name: str, findings: list[Finding]) -> str:
    """A digest that does not need a model — the fallback, and the honest floor."""

    done = [f for f in findings if f.status == "done"]
    return f"{name}: {len(done)} of {len(findings)} specialists reported."


async def _distil(ask: AskFn, name: str, findings: list[Finding]) -> str:
    """One orchestrator's read of its own team's findings."""

    body = "\n".join(f"- {f.agent_id} [{f.status}]: {f.summary}" for f in findings)
    try:
        answer = await ask(
            f"You are the {name} orchestrator for a venue-operations assistant. Distil your "
            "specialists' findings into at most four sentences: what matters, what is wrong, "
            "and what it implies. Do not list the agents. Do not repeat every number — keep "
            "the ones a decision would turn on.",
            body,
        )
    except Exception:  # noqa: BLE001 — a failed digest falls back to the count
        return _digest_text(name, findings)
    return answer.strip() or _digest_text(name, findings)


async def run_swarm(
    *,
    ctx: AgentContext,
    question: str,
    plan: AgentPlan,
    writer: Callable[[dict], None],
    model=None,
    started: float | None = None,
) -> str:
    """Run a planned swarm and return the summarised answer.

    ``writer`` is the stream writer; every frame it receives is forwarded to the
    client verbatim by ``service.stream_run``. ``started`` is the turn's
    ``time.monotonic()`` origin, passed down from the graph so the reported
    duration includes the planner's call rather than starting after it.
    """

    model = model or build_chat_model()
    t0 = time.monotonic()
    # Seed the count with the planner's call — but only when one was made. Under
    # "always" the dispatch list is built without asking a model, and reporting a
    # call that did not happen would make the one number this is meant to be
    # trusted about the one number that is wrong.
    tally = _Tally(model_calls=1 if plan.planned else 0)
    ask = _ask_fn(model, tally)
    gate = asyncio.Semaphore(MAX_CONCURRENT)
    grouped = plan.by_domain(BY_ID)

    # The planner's rationale, before anything it dispatched. It is the only
    # reasoning the turn has about *why this shape* — "forty agents ran" is not
    # self-justifying, and without this step the choice appears to have been made
    # by nobody.
    if plan.reason:
        writer({"thinking": f"Dispatch: {plan.reason}\n"})

    # Every specialist is announced before any of them starts, so the UI draws
    # the whole tree at once and then fills it in — a fan-out that appeared row
    # by row as each agent got scheduled would read as hesitation. Rows settle
    # individually as they finish (see _run_one).
    agents = 0
    for domain in DOMAINS:
        for assignment in grouped.get(domain.id, []):
            writer({"agent_start": BY_ID[assignment.agent_id].as_frame()})
            agents += 1

    fanout_started = time.monotonic()
    results = await asyncio.gather(
        *(
            _run_domain(domain_id, assignments, ctx, ask, writer, gate)
            for domain_id, assignments in grouped.items()
        )
    )
    fanout_ms = int((time.monotonic() - fanout_started) * 1000)

    for _, findings in results:
        for finding in findings:
            tally.count(finding)

    stats_agents, stats_domains, stats_fanout = agents, len(results), fanout_ms
    digests = "\n\n".join(
        f"## {DOMAIN_NAMES.get(domain_id, domain_id)}\n"
        + "\n".join(f"- {f.summary}" for f in findings if f.status == "done")
        for domain_id, findings in results
    )

    answer = await _summarise(model, question, digests, writer)

    # Emitted last, after the answer, because the number the header shows is the
    # whole turn and it does not exist until the summariser has finished. It is
    # stored with the turn, so a reloaded thread keeps its duration — the
    # client's own stopwatch dies with the page.
    stats = tally.stats(
        agents=stats_agents,
        domains=stats_domains,
        fanout_ms=stats_fanout,
        turn_ms=int((time.monotonic() - (started if started is not None else t0)) * 1000),
    )
    stats["model_calls"] += 1  # the summariser
    writer({"swarm_stats": stats})
    return answer


async def _summarise(model, question: str, digests: str, writer: Callable[[dict], None]) -> str:
    """The main agent: five digests in, one streamed answer out.

    Reasoning and answer are split the way the direct path splits them: the
    trace goes out as ``thinking`` (a step in the activity panel) and the answer
    as ``delta`` (the reply bubble). Forwarding only ``content`` — which is what
    this did — is why a swarm turn showed no thinking at all even though the
    model was reasoning for the whole summarise step.
    """

    messages = [
        {
            "role": "system",
            "content": (
                "You are the lead analyst for a venue-operations platform. Five teams of "
                "specialists investigated the user's question and their orchestrators wrote the "
                "digests below. Answer the question directly and concretely, leading with the "
                "answer itself. Use only what the digests support; if they do not cover "
                "something asked, say so rather than filling the gap. Markdown, no preamble."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nTeam digests:\n{digests}",
        },
    ]

    answer = ""
    async for chunk in model.astream(messages):
        if reasoning := _reasoning(chunk):
            writer({"thinking": str(reasoning)})
        text = str(getattr(chunk, "content", "") or "")
        if text:
            answer += text
            writer({"delta": text})
    return answer
