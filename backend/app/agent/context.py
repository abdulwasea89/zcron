"""
Request-scoped context for an assistant run.

Tenant identity — ``org_id``, ``user_id``, ``role`` — and the request's DB
session live here, never in a tool signature. Tools read them through
``current_context()``; the model cannot pass an ``org_id`` argument, so a
confused or prompt-injected model cannot widen its scope (Security Rule #1).

Why a ``ContextVar`` rather than LangGraph runtime context: this works with a
graph compiled once, for every tool, without threading a runtime argument
through each tool. It is the same request-scoped pattern FastAPI uses for
dependencies, and it is set immediately around the graph run by ``service``.

"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Role


@dataclass
class AgentContext:
    """The resolved identity, tenant scope, and DB session for one run."""

    org_id: str
    user_id: str
    role: Role
    session: AsyncSession

    @property
    def is_owner(self) -> bool:
        return self.role is Role.OWNER


_context: ContextVar[AgentContext | None] = ContextVar("acron_agent_context", default=None)


def bind_context(ctx: AgentContext) -> Token:
    """Make ``ctx`` current for the duration of a graph run."""

    return _context.set(ctx)


def clear_context(token: Token) -> None:
    """Restore the previous context (always called in a ``finally``)."""

    _context.reset(token)


def current_context() -> AgentContext:
    """The context for the in-flight run.

    Raises rather than returning ``None``: a tool running without context is a
    programming error, and failing loudly is safer than an unscoped query.
    """

    ctx = _context.get()
    if ctx is None:
        raise RuntimeError("Assistant context is not bound; run the agent through service.run_turn.")
    return ctx
