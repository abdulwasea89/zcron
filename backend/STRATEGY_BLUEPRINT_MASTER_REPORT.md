# Acron / Zhilo Master Product Strategy and Implementation Report

## 1. Scope and source documents

This report joins three bodies of information:

1. **AI-Native CRM: Global Product Blueprint V3** — the broad product
   specification for a global, gym-first, AI-native CRM and operating system.
2. **Zhilo Labs AI Business OS Strategy Report** — the later strategic review
   that narrows the launch plan and reframes the product as a trusted business
   execution layer.
3. **The current Acron codebase** — FastAPI backend, Next.js web portal, Expo
   mobile app, workers, integrations, models, migrations, and tests.

The Blueprint row-level implementation matrix is maintained in
[`../BLUEPRINT_AUDIT.md`](../BLUEPRINT_AUDIT.md) and embedded again in Section
21 so this report is independently complete. It contains 152
Blueprint-derived requirements, 18 additional capabilities discovered in the
codebase, and 106 Strategy feature traceability rows. Sections 17–21 of this report provide the
separate Strategy Report traceability matrix, including overlaps, genuinely
new requirements, and non-product execution requirements. The two matrices
together cover both source documents without pretending that the Strategy
Report was already fully represented by the Blueprint audit.

## 2. Executive conclusion

The two PDFs describe the same long-term company, but they serve different
purposes:

- The **Blueprint** is the product universe. It attempts to ensure that sales,
  memberships, finance, retention, marketing, staff, classes, facilities,
  analytics, compliance, member experience, localisation, evidence, and
  expansion are not forgotten.
- The **Strategy Report** is the sequencing and positioning correction. It
  warns that building the entire universe before proving demand would create a
  large product without evidence that customers will pay.

The recommended company direction is therefore:

`Gym-first → one validated operational workflow → trusted execution → measured outcome → repeatable adoption → additional workflows → adjacent industries`

The current codebase is significantly stronger as a traditional gym operations
platform than it is as the execution platform described by the Strategy
Report. It already contains many operational modules, but the strategic core is
still missing: first-class cases, a unified event ledger, reusable workflows,
backend-enforced autonomy policies, real external messaging, and verified
outcomes.

The highest-leverage next move is not another isolated feature. It is to connect
the existing retention, membership, attendance, payment, task, notification,
and analytics capabilities into one complete **membership retention/payment
recovery case workflow** and test it with paying pilot gyms.

## 3. Relationship between the two PDFs

| Question | Blueprint | Strategy Report | Combined interpretation |
|---|---|---|---|
| Product category | AI-native CRM and gym operating platform | Business execution layer | An execution platform that can grow into the operating system |
| Primary object | Lead/member/customer model | Operational case with a measurable resolution | Customer context feeds cases; cases coordinate action and evidence |
| Core data | Say, Do, Pay event streams | Verified facts, estimates, recommendations, and outcomes | Preserve raw evidence and distinguish facts from model inference |
| AI role | Understand, decide, act, learn | Act only through controlled, permissioned workflows | Models propose; validated application tools enforce |
| User promise | Fewer missed leads, dues, renewals, and operational tasks | Identify problems, resolve them, and show what changed | Sell completed outcomes, not AI features |
| Launch scope | Broad MVP across many departments | One or two high-value workflows | Use the blueprint as a backlog, not as the first release scope |
| Commercial model | Full platform subscription | Add-on to existing systems first | Sell improvement before infrastructure replacement |
| Global strategy | Country Packs and global channels/payments | Narrow commercial launch | Global architecture, local launch |
| Defensibility | Customer world model, Evidence Vault, localisation, agents | Workflow expertise, reliability, distribution, measured outcomes | The moat is the combination, not the model or workflow canvas alone |
| Expansion | Gyms to education, salons, clinics, real estate, sales | Expand after repeatable gym success | One vertical at a time, reusing proven core capabilities |

### 3.1 What the Strategy Report keeps

The later strategy explicitly preserves these Blueprint ideas:

- Event-driven customer understanding
- Revenue and retention agents
- Daily owner command center
- Human approvals
- Evidence Vault
- Wins feed and measured outcomes
- Country and Industry Packs
- Expansion through reusable platform capabilities

### 3.2 What the Strategy Report adds

It adds five important ideas that should influence architecture:

1. **Operational cases** rather than disconnected alerts or messages.
2. **Zhilo Flow**, beginning with typed templates and later becoming a visual
   workflow editor.
3. **Zhilo Control**, enforcing autonomy, permissions, budgets, approvals,
   escalation, and emergency stops.
4. **Outcome Lab**, separating correlation from credible incremental impact.
5. **Add-on-first go-to-market**, avoiding a premature requirement to replace
   mature incumbent gym systems.

### 3.3 What the Strategy Report rejects or delays

- Competing through feature count
- Marketing a generic autonomous AI receptionist
- Building a general n8n competitor before customer validation
- Claiming revenue attribution without credible evidence
- Expanding to every country or industry immediately
- Treating ordinary automation, chat, or AI-generated messages as a moat
- Requiring customers to migrate away from existing software during early
  validation

## 4. Unified product architecture

The complete execution loop should be:

`Capture → Understand → Detect → Open case → Decide → Authorize → Execute → Observe → Verify → Learn`

| Layer | Responsibility | Required records | Current state |
|---|---|---|---|
| Capture | Receive messages, forms, calls, attendance, bookings, payments, documents, staff notes, and external webhooks | Immutable source event, source, tenant, subject, timestamp, idempotency identity | ⚠️ Events exist in separate domain tables; no unified business event ledger |
| Understand | Extract intent, goals, objections, sentiment, requested actions, payment details, and risk signals | Structured observation with source links, confidence, model/version metadata | ⚠️ Assistant and some rules exist; inbound communications are not transformed into structured facts |
| Context | Maintain current customer and business state without losing history | Person, relationship, membership, plan, payment, visit baseline, preferences, summary | ⚠️ Strong structured state; weak unified timeline and provenance |
| Detect | Apply deterministic rules and later statistical models | Signal, reason, severity, value at risk, deduplication key | ⚠️ Retention signals exist; no common signal framework across domains |
| Case | Represent a business objective until resolved | Objective, evidence, owner, deadline, allowed actions, state, resolution criteria | ❌ No first-class case model |
| Decide | Recommend a next action and estimate impact | Recommendation, alternatives, explanation, value estimate, policy classification | ⚠️ Assistant proposals exist; no ranked next-best-action engine |
| Authorize | Enforce role, consent, autonomy, budgets, limits, and approvals | Policy decision, approver, expiry, signature, denial reason | ⚠️ RBAC and selected approvals exist; no unified L0–L3 policy engine |
| Execute | Run messages, tasks, bookings, payment links, updates, waits, retries, and escalations | Workflow definition/version, run, step, attempt, checkpoint, external reference | ❌ No shared durable workflow engine |
| Observe | Record replies, visits, bookings, payments, renewals, complaints, and timeouts | Outcome event linked to case and action | ⚠️ Domain events exist but are not linked into a common outcome loop |
| Verify | Determine whether the case resolved and whether evidence is sufficient | Verified outcome, source, value, cost, human confirmation where needed | ❌ No common outcome verification model |
| Learn | Compare workflow performance and improve safely | Cohorts, conversion, cost, complaints, edits, rejections, incremental estimate | ❌ No Outcome Lab or controlled learning loop |

## 5. Strategic platform capability table

| Capability | Intended role | Current implementation | Status | Required next step |
|---|---|---|---|---|
| Acron OS / Zhilo OS | Main operating environment | Broad web/mobile operations suite | ⚠️ Partial | Reorient navigation and dashboards around Today, Cases, Approvals, and Outcomes |
| Intelligence | Unified customer/business context | Membership, attendance, payment, analytics, retention scores, assistant | ⚠️ Partial | Add append-only events, source-linked facts, message understanding, and unified timelines |
| Cases | Durable objective and resolution tracking | Tasks and approval objects only | ❌ Not built | Add case, evidence, assignment, deadline, state transition, and outcome models |
| Flow | Reusable business workflows | Feature-specific workers and services | ❌ Not built | Define typed workflow templates and durable run/step/checkpoint records |
| Control | Safe autonomy and policy enforcement | RBAC, idempotency, audit, selected approvals | ⚠️ Partial | Add L0–L3 policies, consent, caps, expiry, escalation, pause, and kill switch |
| Agents | Permissioned AI capabilities | Owner assistant, tools, retention logic, inbox drafts | ⚠️ Partial | Add Lead Concierge and Compliance Guard; route all writes through Control |
| Outcomes | Verified value and workflow performance | Revenue-at-risk analytics | ❌ Not built | Link actions to replies, visits, payments, renewals, costs, and case resolution |
| Connect | Data/channel/payment integrations | Stripe, email, push, CSV, inbound Stripe webhooks | ⚠️ Partial | Add WhatsApp first, then supported incumbent-system and calendar connectors |
| Evidence Vault | Tamper-evident operational proof | Normal audit table | ❌ Not built | Add versions, soft delete, hash chain, evidence exports, retention, and alerts |
| Country Packs | Local channels, payments, languages, tax, law, and culture | Country/timezone/currency fields | ❌ Not built | Implement one launch-country policy package and enforcement interface |
| Industry Packs | Vertical vocabulary, schema, signals, workflows, and screens | Hard-coded gym, office, and academy metadata | ⚠️ Partial | Stabilize pack contracts only after gym workflow product-market evidence |

## 6. Deep implementation status by department

The exact row-level status and code evidence are in
[`../BLUEPRINT_AUDIT.md`](../BLUEPRINT_AUDIT.md). The following table explains
the practical product meaning of the full matrix.

| Department | Built | Partial / improvement | Not built / broken | Strategic implication |
|---|---|---|---|---|
| Sales and leads | Lead profile, pipeline board/history, referral attribution, validated manual/source-tagged capture, normalized contacts, tenant-scoped duplicate prevention, editable source attribution, trial-class and tour booking, attendance/no-show/cancellation tracking, consent-gated day 0/1/3/7 follow-up emails, controlled lost reasons, explainable lead score | Manual capture remains the only working intake path; follow-up email copy is fixed rather than configurable; booking confirmations/reminders to leads are absent | External channel capture, instant reply, automated qualification, speed-to-lead reporting, missed-call text-back | Trial/tour booking, follow-up, loss analysis, and profile-readiness scoring work in the web lead view; full Lead Concierge automation remains incomplete |
| Memberships | Signup, invitations, approval enrollment, plans with duration/audience/credit rules, family coverage, activation, statuses, member profiles with goals and private notes | Freeze, reminders, segmentation | Promotions, multi-payer billing, member plan changes, transfer, cancellation/save offers | Good operational base; lifecycle completion is still required |
| Front desk | Tasks, walk-ins, guest log, day passes, lockers, status cards | QR/manual check-in and offline check-in sync | Hardware integrations and full offline application behavior | One of the strongest product areas |
| Finance | Cash reconciliation, receipts, Stripe flows | Recurring cards, dunning, tax, revenue views, refunds | Regional payment rails, P&L, credits, chargeback packs, accounting exports | Financial records are useful, but recovery and localisation remain weak |
| Receipt verification | Upload/review/audit pipeline | Threshold routing and review shell | Real OCR, image authenticity, perceptual duplicates | Central behavior is stubbed and cannot be marketed as production AI verification |
| Retention | Onboarding, visit-drop rules, risk reasons, inactivity ladder, win-back, celebrations, NPS | Backend APIs/workers | Dedicated owner/member UX, external delivery, case/outcome integration | Highest existing-code leverage for the first commercial workflow |
| Marketing | Segment resolution, in-app/email campaign records | Limited delivery | Regional channels, seasons, lead ads, ROI attribution, landing/content tools | Do not prioritize broad marketing before one measurable workflow |
| Trainers | Staff records, shifts, payroll, manual client assignment | Profiles and scheduling primitives | PT packages, matching, workouts, progress, retention-based performance | Important replacement features, not first workflow requirements |
| Classes | Sessions, capacity, booking, cancellation | Utilisation analytics | Waitlist, no-show workflow, reminders, substitution | Add after core retention workflow unless pilots require it |
| HR/payroll | Roles, tasks, shifts, attendance, salary components, commissions, payroll | Some mobile/web surface limitations | Staff performance scorecards | Strong differentiating operational module, but not the strategic moat |
| POS/facility | Day-pass payment | Peak-hour analysis | Retail POS, inventory, access devices, equipment maintenance, safety checklists | Defer until full-suite replacement is commercially justified |
| Management | KPIs, analytics, assistant | Today dashboard, owner brief, revenue-at-risk | Ranked cases, Wins, multi-location, franchise controls | Existing dashboard must become an action-and-outcome command center |
| Compliance | RBAC and state-change audit | Sensitive-data control is coarse | Consent, DSAR, erasure, cooling-off, cancellation rules, waivers, residency | Blocks safe external automation and regulated-market claims |
| Member experience | Mobile signup, booking, payments/history, notifications | Branded app and some self-service | Complete renew/freeze/change/cancel, card/QR, concierge, i18n/RTL | Finish only the flows needed by validated cases first |
| Localisation | Currency/country/timezone fields and generic payment methods | Tax rate and generic mobile-wallet/bank-transfer records | Country Packs, regional rails, channels, privacy rules, language/RTL, cultural calendars | Choose one launch country and implement it deeply |
| Evidence | Audit records | Some export/state-change visibility | Versions, Recycle Bin, packs, hash chain, WORM, PITR policy, owner alerts | Trust claim is currently much weaker than the documents describe |
| Expansion | Gym/office/academy configuration | Shared labels/modules/schema patterns | Pack SDK, marketplace, sales-company pack, validated adjacent verticals | Architecture is ahead of commercial validation; pause expansion |

### 6.1 Sales and Leads partial-feature improvement

This section covers improvements to the existing manual/source-tagged capture
path. Lead follow-up emails are implemented separately and are sent only when
staff records the prospect's explicit permission.

| Existing capability | Improvement completed | Result |
|---|---|---|
| Lead source attribution | Replaced arbitrary source strings on create/update with a controlled source vocabulary covering staff entry, web form, phone, walk-in, referral, WhatsApp, SMS, Instagram, Facebook, LINE, WeChat, and other | Reporting and future connector mapping receive predictable source values without pretending those connectors exist |
| Contact entry | Trims names and profile text, lowercases email addresses, converts blank optional values to null, and normalizes phone formatting | Search, comparison, export, and later integration matching receive cleaner data |
| Duplicate handling | Rejects matching email or normalized phone inside the same organization while allowing the same contact in another tenant | Staff receive an explicit conflict instead of silently fragmenting one prospect into multiple records |
| Source correction | The lead update contract now permits a validated source correction | Incorrect manual attribution can be repaired without direct database work |
| Audit evidence | Lead updates now record both previous and new values | Source/contact corrections become explainable in the existing audit trail |
| API replay safety | Idempotency hashing now uses JSON-mode schema output for enum-backed source values | Controlled sources remain stable under request replay |

Trial and tour booking is implemented for leads: staff can choose an available
class slot or set a tour time, then track attendance, no-show, or cancellation.
Lead follow-up emails now send on days 0, 1, 3, and 7 when explicit email
permission is recorded, with delivery status, staff reminders, completion/skip
tracking, and outcome notes. Copy is currently fixed. Booking
confirmations/reminders remain absent. Lost leads require a controlled reason;
the visible 0–100 score explains profile completeness and is not presented as a
conversion prediction. Remaining gaps include provider-driven capture, instant
first response, qualification automation, speed-to-lead analytics, and
missed-call text-back.

## 7. Blueprint and code-only feature totals

| Status | Blueprint-derived items | Code-only items | Total |
|---|---:|---:|---:|
| Built | 20 | 15 | 35 |
| Improvement | 4 | 0 | 4 |
| Partial | 68 | 3 | 71 |
| Broken / stubbed | 1 | 0 | 1 |
| Not built | 59 | 0 | 59 |
| **Total** | **152** | **18** | **170** |

These totals are row-level classifications rather than estimates of percentage
completion. A small but critical feature, such as consent enforcement, counts
as one row just as a broad feature, such as payroll, counts as one row.

## 8. Features already stronger than the PDFs explicitly require

| Capability | Existing implementation |
|---|---|
| Authentication | Registration, verification, login, refresh, reset, magic link, MFA, recovery codes |
| Session security | Session inventory and immediate revocation |
| Enrollment variants | Open signup, invite-only redemption, and approval queue |
| SaaS operations | Registration, tier lifecycle, invoices, Connect onboarding, organization checklist |
| Realtime | Ticketed WebSocket synchronization across clients |
| Idempotency | Server key claim, request hash, completion/failure state, payment/class/invoice/membership usage |
| Multi-industry base | Gym, office, and academy labels, modules, plans, and client navigation |
| Payroll | Fixed, hourly, per-class, commission, deductions, runs, and staff shifts |
| Cash controls | Cash payments, digital receipt generation, reconciliation, discrepancy tracking |
| Referral program | Codes, attribution, qualification, rewards, admin tracking, mobile sharing |

These capabilities are valuable, but they should support the execution-layer
strategy rather than pull development toward additional unrelated modules.

## 9. Most important gaps

### 9.1 Operational case model

An alert says something may be wrong. A task says someone should do something.
A case represents the complete business objective until its resolution is
verified.

A minimum case should contain:

- Tenant and subject/customer
- Case type and objective
- Source signals and immutable evidence references
- Observed facts, model estimates, and recommendations as separate fields
- Value at risk and confidence
- Owner, collaborators, deadline, and escalation policy
- Allowed actions and required autonomy level
- Current workflow/run
- State transition history
- Resolution criteria
- Verified outcome, cost, and resulting value

### 9.2 Unified event ledger and transactional outbox

The code currently stores domain state and ordinary audit logs. The proposed
system needs a source-of-truth stream that can safely trigger workflows and be
replayed.

Minimum properties:

- Append-only events
- Tenant, subject, source, schema version, occurred time, received time
- Stable external and internal idempotency identities
- Transactional creation with domain state changes
- Outbox delivery state and retry metadata
- PII classification and retention policy
- Links to original messages, documents, payments, and provider events
- Explicit correction/supersession rather than silent overwrite

### 9.3 Typed workflow engine before visual Flow Studio

The first workflow format should support:

- Trigger
- Deterministic data lookup
- Conditions and policy gates
- AI extraction/drafting with structured output
- Human approval
- External action
- Wait for event or timeout
- Retry and error branch
- Escalation
- Measurement and case closure
- Definition version and immutable run version
- Per-run action, time, model-token, messaging-cost, and money limits

Only after real customers repeatedly configure these templates should the
visual canvas be built.

### 9.4 Control and compliance

Backend policy—not the model—must determine:

| Level | Behavior | Example |
|---|---|---|
| L0 | Observe only | Compute risk and open a case |
| L1 | Preauthorized safe action | Send an approved reminder template within consent and frequency limits |
| L2 | Human approval required | Offer a discount, freeze membership, send complaint response |
| L3 | Human only | Refund, medical issue, legal dispute, exceptional cash discrepancy |

Every external action should check tenant, role, case state, workflow version,
consent, quiet hours, channel preference, frequency cap, budget, approval,
idempotency key, and emergency-stop state.

### 9.5 Outcome verification

The platform should not claim a member was saved merely because a message was
sent. Outcome records should distinguish:

- Message accepted by provider
- Message delivered
- Customer replied
- Customer returned
- Customer paid
- Customer renewed
- Case was resolved by staff
- Customer complained or opted out
- Intervention cost
- Gross and contribution value
- Attributed value versus estimated incremental value

Control groups and advanced causal analysis can come later. The first release
still needs honest wording and source-linked verification.

### 9.6 Evidence Vault

The Evidence Vault should be built in stages:

1. Version sensitive records and add soft deletion.
2. Add Recycle Bin and restoration.
3. Hash-chain audit entries and sign external checkpoints.
4. Generate evidence exports for payments, deletes, merges, and bulk changes.
5. Store protected objects under retention controls.
6. Add owner alerts for high-risk actions.
7. Support privacy-aware erasure while preserving non-identifying chain proofs.

## 10. Recommended first commercial workflow

### Membership retention and payment recovery

| Step | Behavior | Existing asset | Missing work |
|---:|---|---|---|
| 1 | Detect attendance decline, upcoming renewal, expiry, or failed payment | Retention scoring, membership dates, payments | Common signal/event contract |
| 2 | Open one deduplicated case | None | Case model and deduplication policy |
| 3 | Load membership, visits, dues, recent messages, open tasks, consent | Most structured data exists | Unified case context and consent records |
| 4 | Calculate value at risk and recommend action | Revenue/risk data partial | Recommendation/value policy |
| 5 | Classify autonomy level | Selected approvals | L0–L3 policy engine |
| 6 | Draft approved message or staff task | AI drafts and tasks exist | Template registry and real channel integration |
| 7 | Send, wait, retry, or escalate | Feature workers exist | Durable workflow run/checkpoint engine |
| 8 | Observe reply, visit, payment, or timeout | Domain events exist | Outcome links and provider reply ingestion |
| 9 | Close only when resolution criteria are met | None | Verified closure rules |
| 10 | Report cost, result, human effort, and verified value | Analytics partial | Wins feed and workflow performance report |

### Why this workflow should come first

- The backend already implements most detection logic.
- The workflow uses high-quality first-party data: attendance, membership, and
  payments.
- The result can be verified through actual return visits or settlement.
- It has direct economic meaning to an owner.
- It exercises the strategic platform primitives needed by later workflows.
- It avoids competing directly with mature AI receptionist products.

## 11. Full ordered delivery table

| Order | Phase | Deliverable | Current state | Dependencies | Definition of done |
|---:|---|---|---|---|---|
| 1 | Validation | Interview 10–20 gym operators | Not a code feature | Founder access | Repeated expensive workflow, current process, buyer, baseline, alternatives, and willingness to pay are documented |
| 2 | Validation | Select ICP and paid pilot workflow | Not formalized | Interviews | One segment and one workflow with explicit inclusion/exclusion criteria |
| 3 | Validation | Define measurement plan | Not built | Pilot workflow | Baseline, success metric, cost metric, complaint metric, and decision date agreed before launch |
| 4 | Foundation | Business event ledger | Partial domain/audit events | Data classification | Domain changes emit append-only versioned events transactionally |
| 5 | Foundation | Transactional outbox | Not built | Event ledger | External delivery retries without losing events or duplicating effects |
| 6 | Foundation | Case domain | Not built | Event identity | Cases contain objective, evidence, owner, deadline, status, allowed actions, and resolution criteria |
| 7 | Foundation | Outcome domain | Not built | Cases/events | Outcomes link to observed provider/domain evidence and case closure |
| 8 | Workflow | Retention signal-to-case adapter | Detection logic built | Cases | Risk signals create/update one deduplicated case |
| 9 | Product | Today/Cases queue | Dashboard partial | Cases | Ranked list shows reason, value, deadline, owner, evidence, and action |
| 10 | Product | Case detail timeline | No unified timeline | Events/cases | One scroll shows messages, visits, payments, tasks, approvals, workflow steps, and outcomes |
| 11 | Connect | WhatsApp provider integration | Not built | Provider account | Send templates, ingest replies/status, verify signatures, retry, and store provider references |
| 12 | Safety | Consent and communication preferences | Not built | Identity/channel model | Purpose/channel consent and opt-out suppress actions globally |
| 13 | Safety | Quiet hours and frequency limits | Not built | Country/timezone | Outbound actions defer or reject predictably and visibly |
| 14 | Control | L0–L3 autonomy policy | Partial approvals | Cases/actions | Every action receives an enforceable policy decision |
| 15 | Control | Approval lifecycle | Partial | Autonomy policy | Approval records actor, scope, payload hash, expiry, decision, and reason |
| 16 | Control | Workflow/action budgets | Not built | Workflow run | Time, attempts, messages, model calls, spend, and money limits fail closed |
| 17 | Control | Pause and kill switch | Not built | Workflow/action registry | Workflow, organization, and platform scopes can stop new external actions immediately |
| 18 | Workflow | Typed retention workflow template | Feature workers only | Cases/control/connect | Trigger, gate, draft, approve, send, wait, escalate, measure, and close execute durably |
| 19 | Workflow | Versioned run/checkpoint model | Not built | Template format | Runs resume after restart and preserve their starting definition version |
| 20 | Reliability | Retry/error/escalation handling | Scattered | Durable runs | Safe failures retry; unsafe or exhausted failures create human work |
| 21 | Product | Approval inbox | Partial | Policy/approval model | Owner can inspect evidence, edit, approve, reject, or expire actions |
| 22 | Product | Wins feed | Not built | Outcomes | Feed reports source-linked verified results without overstating causality |
| 23 | Analytics | Workflow performance report | Not built | Runs/outcomes/cost | Completion, intervention, error, complaint, cost, time, and value metrics are visible |
| 24 | Evidence | Record versioning and soft delete | Not built | Event ledger | Sensitive changes preserve prior state and deletes are recoverable |
| 25 | Evidence | Audit hash chain/checkpoint | Not built | Stable audit serialization | Hidden modification is detectable and checkpoints leave the primary database |
| 26 | Evidence | Evidence export and alerts | Not built | Versioning/audit | Payment edits, deletes, merges, bulk actions, and exports produce proof and owner alerts |
| 27 | Pilot | Launch three live customers | Not started | Steps 1–26 minimum subset | Each pilot has scoped permissions, support owner, measurement, and decision date |
| 28 | Pilot | Fix top recurring failures | Unknown until pilots | Live runs | Highest-frequency trust/reliability failures decline week over week |
| 29 | Repeatability | Guided integration/onboarding | Manual | Pilot learning | New customer launches from documented configuration without custom code |
| 30 | Commercial | Convert five to ten paying customers | Not started | Repeatable outcome | Customers pay and continue using the workflow |
| 31 | P1 | Real OCR and perceptual duplicate detection | Stubbed | Storage/model provider | Tests prove image-derived fields, duplicate sensitivity, calibration, and safe fallback |
| 32 | P1 | Lead Concierge end-to-end | CRM partial | Connect/Flow/Control | Inbound lead to booked trial to verified purchase is one measurable workflow |
| 33 | P1 | Member lifecycle completion | Partial | Payments/policies | Renew, change, freeze, cancel, and save flows work across admin/member surfaces |
| 34 | P1 | Pre-expiry and member dunning | Partial | Messaging/control | T-7/T-3/T-1 and overdue escalation stop on verified settlement |
| 35 | P1 | Waitlist/no-show workflow | Partial classes | Events/Flow | Capacity release, promotion, reminders, and no-show risk operate automatically |
| 36 | P1 | Workflow simulation/replay | Not built | Versioned runs/events | Historical dry runs cause no external side effects and explain each decision |
| 37 | P1 | Country Pack v1 | Not built | Policy contracts | One country has channels, payments, language, tax, consent, cancellation, disclosure, and retention rules |
| 38 | P1 | Multi-location foundation | Not built | Tenant/location decision | Data and policies scope correctly to location with consolidated owner reporting |
| 39 | P2 | Visual Flow Studio | Not built | Proven template format | Canvas edits validated workflow definitions and displays live execution traces |
| 40 | P2 | Outcome Lab | Not built | Sufficient volume/outcomes | Cohort comparisons estimate incremental results and monitor adverse effects |
| 41 | P2 | Pack SDK and additional industries | Hard-coded verticals | Repeatable gym business | New packs reuse the core without forking it |

## 12. Ninety-day operating plan

| Period | Product work | Customer work | Exit criterion |
|---|---|---|---|
| Days 1–15 | Finalize event/case/outcome contracts | Interview 20 operators and select pilot workflow | Three operators confirm the pain, baseline, and willingness to pilot |
| Days 16–30 | Build ledger/outbox, case model, one signal adapter, and basic Today queue | Configure pilot data and permissions | Historical or imported events create correct deduplicated cases |
| Days 31–45 | Add WhatsApp, consent, policy decisions, approvals, and outcome capture | Launch three live pilots | Real cases execute with owner visibility and no uncontrolled actions |
| Days 46–60 | Add checkpoints, retries, limits, kill switch, case timeline, and evidence basics | Weekly owner reviews and incident analysis | Workflow completion and trust failures are measured and improving |
| Days 61–75 | Add template configuration, guided onboarding, cost and performance dashboards | Identify strongest segment and workflow configuration | New pilot setup no longer requires code changes |
| Days 76–90 | Add Wins reporting and commercial controls | Convert pilots; target five to ten paying customers | Continued paid usage or a documented decision to change workflow/segment |

## 13. Weekly metrics

| Metric | Why it matters |
|---|---|
| Paying businesses and MRR | Demonstrates actual demand |
| Weekly active businesses | Shows whether the workflow becomes operational habit |
| Time to onboard | Determines whether growth is repeatable |
| Cases opened, deduplicated, resolved, and overdue | Measures operational usefulness |
| Workflow completion rate | Measures execution reliability |
| Human intervention rate | Shows where automation is not yet trustworthy or economical |
| Approval/edit/rejection rates | Measures AI recommendation quality and owner trust |
| Duplicate or erroneous actions | Must remain near zero |
| Lead conversion or retained/renewed members | Measures workflow-specific business result |
| Verified recovered payments | Measures direct financial result |
| Complaints, opt-outs, and policy violations | Safety metrics; violations should be zero |
| Messaging and AI cost per resolved case | Measures unit economics |
| Gross margin after variable costs | Determines whether the model scales |
| Customer logo churn | Shows whether the product remains valuable |

## 14. Explicitly deferred work

The following should not delay the first commercial workflow:

- General-purpose visual workflow canvas
- Workflow marketplace
- Pack SDK
- Inventory and retail POS
- Equipment maintenance
- Door and turnstile hardware
- Advanced franchise royalties
- Broad multi-country launch
- ML churn models before sufficient labeled outcome data
- Clinics and regulated health workflows
- Workout and diet planning
- Rewards/gamification UI
- Full incumbent replacement migration suite

These remain valid backlog items. They are deferred because they do not answer
the immediate commercial question: whether a gym will pay for one reliably
completed and measurably valuable workflow.

## 15. Branding decision

The strategy documents use **Zhilo Labs** and **Zhilo OS**. The repository and
current user interface use **Acron**. Before pilots, choose one explicit brand
architecture:

1. **Zhilo Labs** is the company and **Acron** is the product; or
2. **Zhilo** is both the company and the product, requiring a controlled rename.

Do not allow customer-facing copy, domains, analytics, app-store metadata,
support material, and contracts to use inconsistent names.

## 16. Final decision rule

Continue investing in the execution platform when pilots demonstrate all of the
following:

- The workflow solves a repeated and expensive problem.
- Customers pay and continue using it.
- Onboarding becomes repeatable.
- Workflow completion is reliable.
- Duplicate and unauthorized actions remain effectively zero.
- Verified benefit exceeds messaging, AI, support, and adoption costs.

If owners repeatedly decline to pay because existing systems solve the problem
well enough, change the workflow or target segment. Do not respond by adding
more agents or unrelated features.

The long-term product thesis remains strong:

> Determine what needs attention, safely perform the authorized work, and
> prove what changed.

The immediate execution discipline is equally important:

> Prove one workflow before building the whole operating system.

## 17. Rechecked coverage of both documents

The earlier 146-row audit was complete for the **AI-Native CRM Blueprint** and
code-only discoveries, but it was not a row-by-row inventory of the **Zhilo
Strategy Report**. That gap is now corrected below.

Use the documents as one traceability set:

| Source set | Where it is inventoried | Rows | Purpose |
|---|---|---:|---|
| AI-Native CRM Blueprint V3 | Section 21 and [`../BLUEPRINT_AUDIT.md`](../BLUEPRINT_AUDIT.md), Part A | 152 | Detailed product-universe requirements and implementation evidence |
| Code-only capabilities | [`../BLUEPRINT_AUDIT.md`](../BLUEPRINT_AUDIT.md), Part B | 18 | Existing capabilities not itemized in the Blueprint |
| Zhilo Strategy Report product/platform requirements | Section 18 below | 106 | Strategy requirements, Blueprint overlap, implementation status, and next gap |
| Zhilo Strategy Report company/GTM requirements | Section 19 below | 25 | Validation, pricing, positioning, distribution, rollout, and decision rules |

The 106 Strategy rows must **not** simply be added to the 152 Blueprint rows to
claim 258 unique product features. Many Strategy rows deliberately restate,
narrow, or strengthen Blueprint requirements. The `Relation` column makes that
overlap explicit. The safe statement is: **all material requirements from both
PDFs are now traceable; deduplicated completion remains measured against the
underlying capability, not the number of times it appears in the documents.**

## 18. Strategy Report product and platform matrix

Status meanings remain the same as the Blueprint audit: `Built` is usable
end-to-end, `Partial` has meaningful implementation but an incomplete flow or
surface, and `Not built` has no production-capable implementation. `Deferred`
means the Strategy Report itself says not to build it before validation.

### 18.1 Cases, context, control, evidence, and outcomes

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S001 | First-class operational case with a measurable business objective | P0 | Strategy-only | Not built | Tasks, approvals, and alerts exist, but there is no case aggregate |
| S002 | Case stores source evidence, owner/agent, allowed actions, deadline, resolution criteria, and outcome | P0 | Strategy-only | Not built | No shared case schema or lifecycle exists |
| S003 | Case shows situation and value at risk | P0 | Both: B64/B122 | Partial | Retention and revenue-at-risk data exist but are not attached to cases |
| S004 | Close a case only after evidence verifies its resolution | P0 | Strategy-only | Not built | Existing tasks can complete without verified business outcome evidence |
| S005 | Simple Mode creates workflows from plain-language intent | P1 | Strategy-only | Not built | Assistant can answer and propose selected writes, not define workflows |
| S006 | Advanced Mode provides a connected visual workflow canvas | P2 | Both: B121 | Not built | No Flow Studio or workflow graph editor exists |
| S007 | Owner reviews recipients, conditions, messages, budgets, and approvals before activation | P1 | Strategy-only | Not built | No workflow draft/review/publish lifecycle exists |
| S008 | Simulate workflows on historical data with no side effects | P1 | Strategy-only | Not built | No replay-safe simulation runtime exists |
| S009 | Inspect workflow execution history and troubleshoot failed nodes | P1 | Both: B76 | Not built | Feature logs exist, but no shared run/step trace exists |
| S010 | Business context links customer, membership, attendance, trainer, messages, and payments | P0 | Both: B56/B125 | Partial | Structured records exist but no unified source-linked context graph/timeline |
| S011 | Store observed facts, model estimates, and recommendations as different evidence classes | P0 | Strategy-only | Not built | No common provenance/confidence model enforces this distinction |
| S012 | Policy-aware next-best-action recommendation | P1 | Both: B78 | Partial | Assistant and retention rules suggest actions, but do not rank through one policy layer |
| S013 | Formal L0 observe, L1 safe auto-act, L2 approval, and L3 human-only levels | P0 | Both: B87–B91 | Partial | Some automatic and approval-gated paths exist; no common autonomy classification |
| S014 | Enforce autonomy permissions in backend services, not in prompts | P0 | Strategy-only | Partial | RBAC and write tools enforce selected paths, but not every automated action |
| S015 | Workflow-wide emergency stop | P0 | Strategy-only | Not built | No workflow/agent kill switch exists |
| S016 | Per-customer and workflow message-frequency limits | P0 | Both: B91/B103 | Not built | No cross-channel frequency policy exists |
| S017 | Spending, action, tool-call, time, and execution-deadline caps | P0 | Strategy-only | Not built | No finite run-budget model exists |
| S018 | Approval expiry and fail-closed timeout | P0 | Strategy-only | Not built | Selected approvals exist without a shared expiry policy |
| S019 | Pause actions for one workflow, organization, or location | P0 | Strategy-only | Not built | No common pause scope exists |
| S020 | Tamper-evident audit events | P1 | Both: B112 | Not built | Audit rows are not hash-chained or externally checkpointed |
| S021 | Preserve workflow definitions and versions used for every action | P1 | Strategy-only | Not built | No workflow definition/version records exist |
| S022 | Cryptographically attributable approval signatures | P1 | Strategy-only | Not built | Approver IDs may exist on domain approvals, but no signed approval evidence |
| S023 | Configurable financial evidence exports | P1 | Both: B111/B115 | Partial | Invoice/report exports exist; no case/workflow evidence export package |
| S024 | Evidence retention schedules, redaction, lawful erasure, and scoped access | P0 | Both: B69–B73/B118 | Partial | RBAC exists; retention, redaction, DSAR, and lawful erasure workflows do not |
| S025 | Outcome comparison against baseline or suitable control group | P1 | Strategy-only | Not built | No counterfactual or control-group analysis exists |
| S026 | Track conversion, retention, contribution margin, time saved, complaints, and message costs | P0 | Both: B64/B66/B86 | Partial | Some conversion/revenue/NPS data exists; no workflow-linked cost/outcome model |
| S027 | Country Pack as the deployable localization unit | P1 | Both: B99 | Not built | Country, currency, and timezone are fields, not an enforceable pack |
| S028 | Country Pack binds language, providers, gateways, currency, timezone, policies, and local workflows | P1 | Both: B99–B108 | Not built | No pack contract or runtime enforcement exists |

### 18.2 Commercial product scope and platform expansion

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S029 | Core CRM: leads, contacts, membership status, searchable history | P0 | Both: B1/B56 | Partial | Core records and search exist; customer history remains fragmented |
| S030 | Unified timeline of conversations, visits, billing events, and staff actions | P0 | Both: B125 | Partial | Member views show visits/payments but not one complete timeline |
| S031 | Integration layer with webhooks, CSV import, and one or two supported incumbent systems | P0 | Both: B2/B100 | Partial | Webhooks/CSV exist; no supported incumbent gym-system connector |
| S032 | Shared inbox, authorized outbound follow-up, and reply tracking | P0 | Both: B123 | Partial | Inbox stores conversations/drafts; no production external provider loop |
| S033 | Five configurable workflow templates | P0 | Strategy-only | Not built | Feature-specific workers are not reusable configurable templates |
| S034 | AI summaries, drafts, classification, and action suggestions | P0 | Both: B77–B83 | Partial | Drafts/assistant/some classification exist; source-grounding is inconsistent |
| S035 | Owner Today dashboard, staff tasks, and approval inbox | P0 | Both: B59/B122 | Partial | Dashboard/tasks/approvals exist but are not one ranked case queue |
| S036 | Deduplication, retries, message limits, and execution logs | P0 | Both: B76 | Partial | Idempotency and some retries/logs exist; shared message/run controls do not |
| S037 | Roles, channel consent, workflow permissions, and human handoffs | P0 | Both: B67–B71/B89 | Partial | RBAC and selected approvals exist; consent and workflow policy are missing |
| S038 | Lead conversion, renewal outcomes, hours saved, and estimated financial impact | P0 | Both: B8/B64/B66 | Partial | Some conversion/revenue metrics exist; time saved and credible impact do not |
| S039 | Flow Studio branching, reusable steps, and versioning | P1 | Strategy-only | Not built | No shared workflow definition format or editor exists |
| S040 | AI Workflow Copilot creates and debugs workflows in natural language | P1 | Strategy-only | Not built | Current assistant does not author or debug workflow definitions |
| S041 | Long-running, resumable workflows with approvals and checkpoints | P1 | Strategy-only | Not built | Scheduled workers do not preserve durable run checkpoints |
| S042 | Advanced cancellation prevention, failed-payment handling, and retention cases | P1 | Both: B31–B37/B93 | Partial | Rules and reminders exist; no case-based recovery loop |
| S043 | Staff work queues, deadlines, escalation, and performance tracking | P1 | Both: B47/B50/B53 | Partial | Tasks and payroll/attendance metrics exist; common escalation/performance loop does not |
| S044 | Multi-location permissions, policy inheritance, and standardized workflows | P1 | Both: B63 | Not built | Organization switching is not location hierarchy or policy inheritance |
| S045 | Marketplace of verified industry workflow templates/modules | P2 | Both: B121 | Deferred | No marketplace; Strategy says it must follow validated workflows |
| S046 | Industry Pack SDK for fitness, salons, education, and home services | P2 | Both: B119–B121 | Deferred | Three hard-coded industries exist; no installable pack SDK |
| S047 | Developer platform with APIs, SDKs, signed webhooks, and integrations | P2 | Strategy-only | Partial | REST API and verified inbound Stripe webhooks exist; no public SDK/integration platform |
| S048 | Delegated AI staff interface across specialized permissioned agents | P2 | Both: B77–B85 | Partial | Specialized assistant graph exists; durable delegated work and uniform policy do not |
| S049 | Predictive retention and demand optimization after sufficient data | P2 | Both: B33/B45 | Deferred | Current risk logic is deterministic; Strategy delays predictive models until evidence exists |
| S050 | Franchise management with central policy, regional oversight, and branch analytics | P2 | Both: B63 | Deferred | No franchise hierarchy exists |
| S051 | Region-specific deployments and enterprise controls | P2 | Strategy-only | Deferred | No data-residency deployment/control plane exists |

### 18.3 Workflow engine contract and lifecycle

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S052 | Strict typed input/output contract for every workflow node | P0 | Strategy-only | Not built | Service schemas exist, but there is no workflow-node contract system |
| S053 | Trigger nodes: lead, payment failure, expiry, check-in, schedule, webhook | P0 | Both | Partial | Domain events/workers cover several triggers but not through one engine |
| S054 | Data nodes: customer, membership, history, and availability lookup | P0 | Strategy-only | Not built | Services can query data; no reusable workflow data nodes exist |
| S055 | Condition nodes: branch, compare, filter, consent, duplicate | P0 | Strategy-only | Partial | Business rules exist; consent and reusable typed condition nodes do not |
| S056 | AI nodes: classify, summarize, draft, structured extraction | P0 | Both: B77–B85 | Partial | Several AI functions exist but are not reusable workflow nodes |
| S057 | Action nodes: message, task, booking, CRM update, payment-link request | P0 | Both: B85 | Partial | Tasks/bookings/updates exist; external messaging/payment-link action set is incomplete |
| S058 | Control nodes: wait, retry, approval, stop, escalation, error branch | P0 | Strategy-only | Partial | Workers retry and approvals exist in places; no common control-node runtime |
| S059 | Measurement nodes: outcome, baseline, expense, and report | P0 | Strategy-only | Not built | No workflow-linked measurement node contract exists |
| S060 | Parse natural language into a structured workflow specification | P1 | Strategy-only | Not built | No workflow specification generator exists |
| S061 | Identify required events and integrations during workflow creation | P1 | Strategy-only | Not built | No workflow dependency resolver exists |
| S062 | Present proposed workflow with editable conditions | P1 | Strategy-only | Not built | No workflow draft UI exists |
| S063 | Detect missing permissions and unsupported actions before publication | P1 | Strategy-only | Partial | Route/tool authorization exists, but no workflow preflight validator |
| S064 | Run dry-run simulation before activation | P1 | Strategy-only | Not built | No side-effect-free workflow simulator exists |
| S065 | Require explicit approval before workflow activation | P1 | Strategy-only | Not built | No draft-to-active workflow lifecycle exists |
| S066 | Publish an immutable versioned workflow | P1 | Strategy-only | Not built | No workflow records or immutable versions exist |
| S067 | Explain any node using its inputs, decision, and outcome | P1 | Strategy-only | Not built | No shared execution trace exists |
| S068 | Pin active runs to their starting version unless explicitly migrated | P1 | Strategy-only | Not built | No run/version model exists |
| S069 | Dedicated manager approval inbox outside the editor | P0 | Both: B89 | Partial | Approval screens exist, but not a unified workflow action inbox |
| S070 | Run limits for actions, costs, deadlines, and customer frequency | P0 | Strategy-only | Not built | No workflow budget/limit policy exists |
| S071 | Retry safe failures and route exhausted/unsafe failures to a human | P0 | Strategy-only | Partial | Some jobs retry; no common failure classification and escalation path |
| S072 | Business-specific templates instead of an empty canvas | P0 | Strategy-only | Partial | Fixed domain workers embody workflows but are not configurable templates |
| S073 | Kill switch prevents new workflow or agent actions immediately | P0 | Strategy-only | Not built | No workflow/agent action circuit breaker exists |

### 18.4 Seven showcase workflows

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S074 | Trial-to-paid: capture, qualify, schedule, confirm, attend, follow up, verify purchase | P0 | Both: B1–B8 | Partial | Trial/tour scheduling, attendance tracking, and consent-gated day 0/1/3/7 follow-up emails exist; instant capture, qualification, booking confirmations, and verified purchase loop remain absent |
| S075 | Retention: detect baseline decline, review context, intervene, observe return | P0 | Both: B31–B37 | Partial | Detection and messages/tasks exist; case, provider replies, and verified incremental result do not |
| S076 | Payment recovery: verified failure, permitted outreach/link, provider verification, closure | P0 | Both: B23/B25/B93 | Partial | Payment events and dunning pieces exist; member recovery workflow is incomplete |
| S077 | Complaint resolution: classify, gather policy/context, assign, respond, track, request feedback | P1 | Both: B44/B97 | Partial | NPS/theme clustering and tasks exist; no complaint case lifecycle |
| S078 | Staff accountability: assign, monitor deadline, remind once, escalate, record completion | P1 | Both: B47/B50 | Partial | Tasks/deadlines exist; deduplicated reminder/escalation workflow does not |
| S079 | Campaign optimization: source to booking/purchase, spend, conversion, and recommendations | P1 | Both: B38–B41 | Partial | Campaign/segment data exists; spend-to-confirmed-outcome optimization is incomplete |
| S080 | Multi-location operations: aggregate authorized branch signals and route exceptions | P1 | Both: B63 | Not built | No branch hierarchy, scoped aggregation, or location-manager routing exists |

### 18.5 Architecture, safety rules, evaluation, and owner UX

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S081 | Append-only business event ledger with transactional outbox | P0 | Both: B109 | Not built | Domain/audit rows exist; no unified ledger/outbox transaction exists |
| S082 | Durable engine for schedules, waits, retries, approvals, and checkpoints | P0 | Strategy-only | Not built | Background jobs exist without durable workflow state |
| S083 | Central policy/tool gateway for authorization, validation, approvals, limits, and idempotency | P0 | Strategy-only | Partial | Dependencies, RBAC, tool wrappers, and idempotency exist but are not one gateway |
| S084 | Typed AI tools with explicit state and checkpoints | P0 | Strategy-only | Partial | Typed assistant tools exist; resumable state/checkpoints do not |
| S085 | Semantic retrieval with PostgreSQL/pgvector only when justified | P2 | Strategy-only | Deferred | Correctly absent until a validated retrieval requirement exists |
| S086 | Retention-controlled object storage for files and evidence | P1 | Both: B113/B114 | Partial | File/storage abstractions exist; WORM and enforceable retention do not |
| S087 | Structured logs, traces, execution metrics, and alerting | P0 | Both: B76 | Partial | Application logs/metrics exist; workflow-level traces and alerts do not |
| S088 | Approved external integrations for gym systems, messaging, payments, and calendars | P0 | Both: B2/B100/B101 | Partial | Stripe/email/push exist; gym-system, two-way messaging, and calendar connectors are missing |
| S089 | LLMs mutate state only through validated application tools | P0 | Strategy-only | Built | Assistant write actions route through typed application tools and approval gates |
| S090 | Every external/state-changing action is idempotent | P0 | Both: A17 | Partial | Framework is strong but is not uniformly required on every state-changing endpoint |
| S091 | Financial settlement comes only from verified payment records | P0 | Both: B23/B84 | Partial | Stripe flows verify provider events; receipt interpretation remains stubbed and must not confirm settlement alone |
| S092 | Every workflow is versioned and reconstructable | P0 | Strategy-only | Not built | No workflow version/execution provenance model exists |
| S093 | Tenant isolation at database, service, and tool layers | P0 | Both | Partial | Service/JWT scoping is broad; complete RLS/tool-layer proof is not established |
| S094 | Every agent has finite tool-call, time, money, and action budgets | P0 | Strategy-only | Not built | No agent budget object or enforcement exists |
| S095 | Automated adversarial evaluations for wrong customer, discount, injection, hallucination, opt-out, webhook, and conflict failures | P0 | Strategy-only | Not built | Normal tests exist; no dedicated safety/evaluation suite covers this matrix |
| S096 | Navigation centered on Today, Customers, Cases, Flows, Approvals, and Evidence | P1 | Strategy-only | Partial | Customers and approvals exist; cases, flows, evidence, and ranked Today are incomplete |
| S097 | Role-specific owner, manager, and automation-specialist workspaces | P1 | Strategy-only | Partial | Role-based navigation exists, but not the three Strategy workspaces |
| S098 | Ask interface returns filtered, source-linked operational lists | P0 | Both: B127 | Partial | Ask is capable, but evidence links and uniform source grounding are incomplete |
| S099 | Ask interface prepares a reviewable action batch | P0 | Both: B127 | Partial | Selected proposal actions exist; general batch review does not |
| S100 | Ask executes only authorized, consent-checked actions and returns a result summary | P0 | Both: B127 | Partial | Authorization/approval exists for selected tools; consent and uniform execution summaries do not |
| S101 | Native management suite covering complete scheduling, billing, attendance, and facility operations | P2 | Both: B42–B58 | Partial | Broad native operations exist, but scheduling depth, POS/inventory, access hardware, and facility maintenance remain incomplete |
| S102 | Production Flow Studio nodes have configuration panels, connection handles, schemas, validation, and execution traces | P1 | Strategy-only | Not built | No production visual workflow editor or node-inspection experience exists |
| S103 | Complex cross-system workflows coordinate messaging, attendance, CRM, booking, and verified payment data | P0 | Strategy-only | Partial | Each domain exists in varying depth, but no shared workflow engine coordinates them end-to-end |
| S104 | AI analytics answers natural-language questions grounded in live business data | P1 | Both: B65/B127 | Partial | Ask-anything analytics exists; production grounding, evidence links, and complete live-domain coverage remain incomplete |
| S105 | Mistaken automated actions have defined rollback or remediation procedures | P0 | Strategy-only | Not built | Selected domain reversals exist, but no platform-wide remediation contract or operator flow exists |
| S106 | Payment workflow nodes validate amounts against billing records and authorized rules, never arbitrary model output | P0 | Strategy-only | Partial | Payment services validate structured records, but no typed workflow payment node or uniform AI boundary exists |

## 19. Strategy Report company, GTM, and operating matrix

These are required by the Strategy Report but should not be counted as software
features. Their status describes company execution, not code completion.

| ID | Requirement / decision | Order | Status | Required evidence or action |
|---|---|---:|---|---|
| O001 | Sell an add-on to existing gym software before demanding replacement | 1 | Adopt now | Position pilots as one measurable workflow beside incumbent tools |
| O002 | Validate one costly unresolved workflow with 20 gym operators | 1 | Not evidenced | Record interviews, current process, cost, alternatives, buyer, and willingness to pay |
| O003 | Start with independent gyms/small chains, roughly 150–1,000 members and 1–5 sites | 1 | Hypothesis | Confirm or revise the ICP through interviews and paid pilots |
| O004 | Target owner, GM, or operations manager as economic buyer | 1 | Hypothesis | Track who owns pain, budget, approval, and renewal decision |
| O005 | Select one primary workflow and explicit success/baseline metrics | 1 | Not evidenced | Prefer retention/payment recovery unless discovery disproves it |
| O006 | Launch three live pilots with permissions, costs, success criteria, and decision dates | 2 | Not evidenced | Use real operations and documented data-access boundaries |
| O007 | Convert five to ten pilots/users into continuing paid customers | 3 | Not evidenced | Measure paid retention, not verbal interest |
| O008 | Test Starter at $79–$99/month | 3 | Hypothesis | Validate workflow/case limits and gross margin |
| O009 | Test Growth at $199–$299/month | 3 | Hypothesis | Validate approvals, integrations, and outcome-report value |
| O010 | Test Multi-location from $499/month | Later | Hypothesis | Do not sell before location controls exist |
| O011 | Use fixed subscription plus reasonable usage allowances | 3 | Recommended | Price variable messaging/voice/payment costs transparently |
| O012 | Test outcome-based pricing only after attribution is credible | Later | Deferred | Requires trustworthy Outcome Lab and contractual clarity |
| O013 | Lead messaging with expensive problem, buyer, and measurable result—not “fully autonomous AI” | 1 | Adopt now | Keep claims specific and evidence-backed |
| O014 | Offer a workflow review rather than a generic software demo | 1 | Adopt now | Review one real process and estimate a measurable opportunity |
| O015 | Use founder-led LinkedIn, Instagram, email, introductions, and direct research | 1 | Not evidenced | Track conversations, qualified opportunities, pilots, and conversion |
| O016 | Demonstrate a real case, approval, execution, and verified outcome | 2 | Blocked by product | Build the first complete case workflow before polished demos |
| O017 | Publish case studies with results, costs, limitations, and exact workflow changes | 3 | Blocked by pilots | Use verified data and customer permission |
| O018 | Develop agency and gym-operations consultant partnerships | Later | Not started | Pursue after onboarding and workflow delivery are repeatable |
| O019 | Avoid unsupported revenue-lift claims | Always | Required | Claims need attributable evidence and stated limitations |
| O020 | Build moat through vertical workflow expertise, reliable execution, distribution, learning, and adoption | Always | In progress | Prioritize repeatable outcomes over model/agent count |
| O021 | Respect privacy, contractual permission, minimization, and separation in cross-customer learning | Always | Required | No pooled training or analysis without a lawful, explicit basis |
| O022 | Expand gyms → boutique fitness → salons/spas or education → home services → healthcare later | Later | Deferred | Enter one adjacent vertical only after expansion gates pass |
| O023 | Require repeatable sales/retention, low-custom onboarding, reliable engine, adjacent demand, and real reuse before expansion | Later | Not met | Treat all five conditions as release gates |
| O024 | Track MRR, weekly active businesses, workflow completion, intervention/error rates, conversion/retention, margin, onboarding, and churn weekly | 2 | Partial | Product metrics exist in pieces; company operating scorecard is not evidenced |
| O025 | If meaningful pilots do not produce willingness to pay, change workflow or segment instead of adding features | Decision gate | Required | Pre-commit the pilot review date and pivot criteria |

## 20. Recheck result and corrected totals

The reconciliation now has two distinct views:

| View | Built | Partial | Not built | Deferred | Total |
|---|---:|---:|---:|---:|---:|
| Blueprint-derived product rows | 15 | 74 including four improvement rows | 63 including one broken/stubbed row | 0 | 152 |
| Code-only rows | 15 | 3 | 0 | 0 | 18 |
| Strategy product/platform rows | 1 | 53 | 46 | 6 | 106 |
| Strategy company/GTM rows | Not comparable | Not comparable | Not comparable | Not comparable | 25 |

These rows answer different questions. The Blueprint count measures breadth of
the proposed operating system. The Strategy count measures whether the current
system supports the narrower execution-platform thesis. A requirement appearing
in both tables is one underlying capability, not two completed features.

### What should happen first after the recheck

| Order | Work | Why first |
|---:|---|---|
| 1 | Validate the retention/payment-recovery pain and paid pilot | Prevents building an unproven platform |
| 2 | Add event ledger/outbox, case, and verified outcome primitives | Creates the minimum execution loop shared by both PDFs |
| 3 | Add consent, L0–L3 policy, limits, approvals, pause, and kill switch | Makes external automation safe enough for pilots |
| 4 | Add one real two-way messaging connector and provider evidence | Turns stored drafts into observable execution |
| 5 | Implement one typed, versioned, resumable retention/payment workflow | Proves end-to-end case completion before Flow Studio |
| 6 | Add Today/Cases/Approvals/Wins surfaces and workflow metrics | Makes the value visible and operable to owners |
| 7 | Improve reliability from pilot failures and convert paying customers | Establishes repeatability and willingness to pay |
| 8 | Only then build simulation, visual Flow Studio, marketplace, packs, and expansion | Prevents P2 work from delaying evidence |

## 21. Complete Blueprint feature matrix

This section embeds the complete Blueprint feature inventory so this report is independently complete. The same rows are maintained in `../BLUEPRINT_AUDIT.md`; rows 1–79 are the printed department table and rows 80–152 expand the Blueprint's architecture, autonomy, agents, localisation, Evidence Vault, UX, expansion, and Sales Pack requirements.


| # | Feature | Pri | PDF | API | Web | Mobile | Status | Evidence / gap |
|---|---|---|---|---|---|---|---|---|
| 1 | Lead capture from WhatsApp, SMS, Instagram, Facebook, LINE, WeChat, web forms, calls, walk-ins | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Manual/source-tagged intake at `/app/leads` now uses a controlled source vocabulary, normalized email/phone data, tenant-scoped duplicate rejection, editable attribution, and previous/new audit values. No provider-driven public form, WhatsApp, SMS, or social channel connectors are implemented. |
| 2 | Lead profile: goal, budget, preferred times, preferences | P0 | ✓ | ✓ | — | — | ✅ Built | Tenant-scoped profile fields editable in `/app/leads`, with field provenance, searchable prospects, and pipeline stage tracking; does not include AI extraction or conversation linking |
| 3 | Pipeline: New → Contacted → Trial booked → Visited → Joined / Lost | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Board/list views, six stages, search/filter/counts, accessible stage controls, and paginated actor/timestamp history at `/app/leads` and `GET /leads/{id}/history`. Referral conversions share audited transitions; legacy unknown previous stages are labeled. Trial/visit automation remains separate. |
| 4 | Instant first reply 24/7 | P0 | ✓ | — | — | — | ❌ Not built | No auto-reply, no FAQ knowledge base |
| 5 | Trial and tour booking | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Lead booking panel at `/app/leads`: available class slots for trials and custom tour times; tenant-scoped reservations, capacity enforcement, duplicate-active-booking prevention, and attended/no-show/cancel transitions (`GET /leads/trial-slots`, `POST /leads/{id}/bookings`, `PATCH /leads/{id}/bookings/{booking_id}`). No automated confirmation/reminders |
| 6 | Follow-up sequences (day 0, 1, 3, 7) | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Consent-gated day 0/1/3/7 email sequence, scheduled worker, per-step delivery tracking, staff due notifications, completion/skip controls, and outcome notes; copy is currently fixed |
| 7 | Lost-reason tracking and lead scoring | P1 | ✓ | ✓ | ✓ | — | ✅ Built | Marking a lead Lost requires a controlled reason; `/app/leads` shows a 0–100 explainable profile-completeness score with per-factor breakdown, not a predictive conversion claim |
| 8 | Speed-to-lead reporting; missed-call text-back | P1 | ✓ | — | — | — | ❌ Not built | — |
| 9 | Corporate and group memberships; referral tracking | P1–P2 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Corporate contracts/invoices and team seat management exist (`models/company.py`, `company_contract.py`, `invoices_service.py`, `/app/companies`). Referral program supports member codes, signup attribution, qualification after successful payment, dual rewards, admin tracking/manual fulfillment, mobile share/status, and joined Lead attribution (`services/referrals_service.py`, `/app/referrals`, mobile dashboard). Rewards are recorded and manually delivered; no automatic wallet credit/discount. Not available for office B2B tenants or invite-only enrollment. |
| 10 | Member profile: photo, ID (where legal), contact, emergency contact, goals, health notes | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Organization-scoped photo URL, contact, emergency contact, goals, private health notes, optional ID type/final four, and a deterministic profile summary. Owner/manager edit via `/members/{id}/profile` and `/app/members`; members edit their own profile on mobile. Health notes and ID metadata are hidden from front desk. Audit records changed field names without sensitive values; archive clears private fields. Photo is linked by HTTPS URL; full ID numbers and document images are intentionally not stored. |
| 11 | Plans: daily to yearly, family, student, off-peak, class packs, credits | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Owner plan builder exposes day/week/month/year cycles, student/family audience, family capacity, local off-peak window, class-pack size/validity, and optional recurring visit credits. Purchase snapshots the allowance; check-in consumes one credit atomically and flags out-of-window or exhausted visits while still logging attendance. Owner/manager can link same-org members to an active family plan; they share the payer's entitlement and credits. Student status is a plan label and is not automatically verified. Visit credits are separate from account/payment credits in row 30. |
| 12 | Joining fees, discounts, promo codes | P0 | ✓ | — | — | — | ❌ Not built | 0 matches for `discount\|coupon\|promo\|joining_fee` in `backend/app`. No promotion engine at all |
| 13 | Freeze/pause (travel, illness, seasonal) | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | `MemberStatus.FROZEN`; `members_service.py:83 freeze` / `:85 unfreeze` — staff actions only. Missing: member-requested freeze, approve flow, auto-detect from messages |
| 14 | Renewals and expiry reminders | P0 | ✓ | ✓ | — | — | ⚠️ Partial | Post-expiry grace reminders only (`workers/notifications.py:33`, days 1/2/3). Missing: pre-expiry T-7/T-3/T-1 cadence |
| 15 | Upgrades, downgrades, transfers, cancellation with save offer | P1 | ✓ | — | — | — | ❌ Not built | `saas_billing_service.py:74 upgrade` / `:90 downgrade` / `:116 cancel` are **SaaS-tier only**. `memberships_service.py` is signup/activation — no member plan change, transfer, save offer (verified: no such function exists) |
| 16 | Family and multi-payer accounts; segmentation and tags | P1–P2 | ✓ | ✓ | — | — | ⚠️ Partial | Segments are dynamic and computed: `campaign_service.py:82 _resolve_segment` (status, plan, days-since-visit). Missing: family accounts, multi-payer, tags |
| 17 | Check-in by QR, card/RFID, app, biometric or manual | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | **QR is fully working end-to-end**: member QR issued (`MemberDetailSheet.tsx:602` — `QRCodeSVG value={acron:member:{member_id}}`), webcam scanner (`components/attendance/QrScanner.tsx`, `@zxing/browser`), decode → `checkIn(memberId, "", "qr")` (`attendance/page.tsx:377-386`). Manual ✅ (inline in `attendance/page.tsx:318`, offline localStorage queue). All 5 values in `AttendanceMethod` (`core/constants.py:208`). Missing: card/RFID reader, biometric hardware, member self-check-in in mobile app |
| 18 | Status on check-in: expired, dues, birthday, at-risk | P0 | ✓ | ✓ | ✓ | — | ✅ Built | `services/attendance_service.py:142` renewal line, `:43 _RISK_DAYS = 14`, `:184` status payload |
| 19 | Shared team inbox for all channels | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Inbox fully built: conversations, assignment, status, AI draft; `Channel` enum has 12 values (`core/constants.py:227` — WHATSAPP, SMS, EMAIL, INSTAGRAM, MESSENGER, LINE, WECHAT, TELEGRAM, WEB_CHAT, PHONE, WALK_IN, OTHER). **The inbox never sends** — `inbox_service.py` stores only; `integrations/` has no sms/whatsapp/telegram module at all (email + push are the only transports, used by notifications/campaigns, not the inbox) |
| 20 | Staff "Today" task list | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/staff.py:28 class Task`, `staff_service.py:272-348` CRUD, `frontend/app/app/tasks`, `mobileapp/src/app/(admin)/tasks.tsx` |
| 21 | Walk-ins, day passes, guest log, lockers | P1–P2 | ✓ | ✓ | ✓ | — | ✅ Built | `models/visitor.py`, `visitor_service.py:130` day pass → `Payment(kind=DAY_PASS)`, `routes/front_desk.py` |
| 22 | Offline mode with sync | P1 | ✓ | ✓ | ✓ | — | 🔧 Improvement | `routes/attendance.py:62 POST /sync` — idempotent offline-queued check-in flush; `:56` offline roster |
| 23 | Local payment methods per country | P0 | ✓ | — | — | — | ❌ Not built | `PaymentMethod` = CARD, CASH, BANK_TRANSFER, MOBILE_WALLET, OTHER — generic only. No SEPA / iDEAL / Pix / UPI / M-Pesa / JazzCash |
| 24 | Recurring billing: cards, direct debit, mandates | P0 | ✓ | ✓ | — | — | ⚠️ Partial | Stripe card recurring built; 0 matches for `direct_debit` / `mandate`. No card-updater, no smart retry |
| 25 | Failed-payment and overdue recovery (dunning) | P0 | ✓ | ✓ | — | — | ⚠️ Partial | SaaS has the full escalation ladder (`saas_billing_service.py`). Members get grace reminders days 1/2/3 (`notifications.py:33`, email + push + in-app). Missing: escalating ladder to staff call, smart retry |
| 26 | Cash and manual payments with digital receipts | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/cash.py`, `cash_service.py`, `routes/cash.py:63` receipt PDF, `CashReconciliation` |
| 27 | Payment-proof verification (bank-transfer or wallet screenshots) | P1 | ✓ | ✓ | — | — | 🧨 Broken / stubbed | The upload, review, routing, and audit workflow exists, but the core image-reading behavior does not: `_real_extract()` returns `None`, fallback fields are derived from request inputs, and `_phash()` is SHA-256 rather than a perceptual hash. The system cannot verify receipt content or detect image fraud |
| 28 | Invoices with local tax (VAT, GST, sales tax) | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | `plan.tax_rate` end-to-end incl. inclusive-tax: `invoices_service.py:83`, `memberships_service.py:345 _amount_with_tax()`. Missing: country/region rule packs |
| 29 | Expenses, P&L, revenue by plan, branch or trainer | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Revenue by plan/trainer ✅ (swarm specialists `rev_by_plan`, `payroll_commissions`). 0 matches for `expense`. No P&L, no branch dimension |
| 30 | Refunds, credits, chargeback evidence; accounting export | P1 | ✓ | ✓ | — | — | ⚠️ Partial | Refunds ✅ approval-gated (`agent/tools/write.py refund_payment` via `_proposal()`). Missing: account credits, chargeback evidence assembly, accounting export |
| 31 | 90-day onboarding journey (day 1, days 2–7, weeks 2–4) | P0 | ✓ | ✓ | — | — | ⚠️ Partial | `models/onboarding.py`, `onboarding_service.py:203` ("not visited in 7 days"), `routes/onboarding.py`, `workers/onboarding.py`. Missing: UI |
| 32 | Attendance-drop detection vs each member's own baseline | P0 | ✓ | ✓ | — | — | ⚠️ Partial | `retention_service.py:41-44` — 14-day window vs prior 56-day baseline, `DROP_RATIO=0.5`, `SEVERE_RATIO=0.25`, `MIN_TENURE_DAYS=21`. Missing: UI |
| 33 | Churn-risk score with reasons | P0 | ✓ | ✓ | — | — | ⚠️ Partial | `retention_service.py:166-245 compute_risk` — 0-100 score, `HIGH_BAND=70`/`MEDIUM_BAND=40`, weighted `RiskReason` objects with human text, 5 signal families, loyalty cushion (−10). Missing: UI |
| 34 | Inactivity ladder: 5 days message, 10 days staff check-in, 14–21 days call | P0 | ✓ | ✓ | — | — | ⚠️ Partial | `inactivity_ladder_service.py:95` rungs incl. "Win-back"; `routes/ladder.py`, daily worker. Missing: UI |
| 35 | Win-back campaigns; milestones; birthdays | P1 | ✓ | ✓ | — | — | ⚠️ Partial | `models/winback.py`, `models/celebration.py`, both services + workers. Missing: UI |
| 36 | NPS at day 7, 30, 90; complaint clustering | P1 | ✓ | ✓ | — | — | ⚠️ Partial | `nps_service.py:435 _nps()`, theme taxonomy at `:75`; day-7/30/90 daily sweep, `routes/nps.py`. Missing: UI |
| 37 | Challenges, streaks, leaderboards | P2 | ✓ | ✓ | — | — | ⚠️ Partial | `models/gamification.py` — `GymChallenge`, `MemberChallengeProgress`, `MemberStreak`; `routes/challenges.py`, daily worker. Missing: UI |
| 38 | Segmented campaigns by channel (WhatsApp, SMS, email, LINE, and others) | P1 | ✓ | ✓ | — | — | ⚠️ Partial | Segment resolution real (`campaign_service.py:82 _resolve_segment`); `CampaignChannel` = **IN_APP, EMAIL, BOTH** — not WhatsApp/SMS/LINE. `routes/campaigns.py` exists. Missing: the named channels, and UI |
| 39 | Seasonal offers (New Year, summer, Ramadan, Diwali, Lunar New Year, and more) | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `seasonal`. No local calendar |
| 40 | Referral programme; review requests after positive moments | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `review_request`. Referral *attribution* exists (row 9); no programme, no rewards, no review requests |
| 41 | Lead-ad integrations (Meta, Google, TikTok) | P1 | ✓ | — | — | — | ❌ Not built | — |
| 42 | Campaign ROI: leads → trials → members → revenue | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `roi` in campaign context. No funnel attribution |
| 43 | Landing pages; content ideas | P2 | ✓ | — | — | — | ❌ Not built | — |
| 44 | Trainer profiles, schedules, availability | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Staff model + `Shift` (`models/staff.py:13`) + payroll rates. Missing: availability model, public profile |
| 45 | PT package sales and session tracking | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `pt_package` / `session_credit`. `member_trainer.py` is a coach link only |
| 46 | Trainer–client matching | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Manual assignment only: `member_trainer.py`, `routes/members.py:245-283 assign_trainer/unassign`. Missing: goal/preference/timing matching |
| 47 | Workout and diet plans; progress tracking | P2 | ✓ | — | — | — | ❌ Not built | No routine/program/exercise model |
| 48 | Trainer performance by client retention | P1 | ✓ | — | — | — | ❌ Not built | No retention ranking per trainer |
| 49 | Timetable, booking, capacity, waitlist | P1 | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | `class_session.py:30 capacity: int = 20`, booking + cancel built (`classes_service.py:174`), member booking in web + mobile (`mobileapp/(member)/classes.tsx:60-140` idempotent). **0 matches for `waitlist`/`wait_list`** |
| 50 | No-show tracking and reminders | P1 | ✓ | — | — | — | ❌ Not built | `BookingStatus.NO_SHOW` exists (`core/constants.py:205`) and is in the DB enum, but is **never assigned anywhere** — 0 matches for `BookingStatus.NO_SHOW` outside the definition. No no-show detection, no reminder logic, no risk signal |
| 51 | Utilisation analytics; instructor substitution | P2 | ✓ | ✓ | — | — | ⚠️ Partial | Swarm specialists `ops_class_fill`, `ops_space_use`, `ops_peak_hours`. Missing: instructor substitution (0 matches for `substitut`) |
| 52 | Roles and permissions: owner, manager, front desk, trainer | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `Role` enum + `Capability` enum (incl. `TAKE_ATTENDANCE`), enforced in API deps |
| 53 | Activity and audit log | P0 | ✓ | ✓ | ✓ | — | ✅ Built | `models/audit_log.py`, `audit_service.py`, `routes/audit.py`, `record_audit()` called from services |
| 54 | Shifts, attendance, salaries, commissions, per-session pay | P1 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/staff.py:13 Shift` + `:221/:246 check_in/check_out`; `payroll_service.py` fixed+hourly+per-class+commission; `workers/payroll_runner.py:93` 12-month commission window; `frontend/app/app/payroll`, `mobileapp/(staff)/shift.tsx` |
| 55 | Staff performance: response time, conversions, collections | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for staff KPI/performance aggregation (`performance\|kpi\|response_time\|conversion`) |
| 56 | POS for supplements, merchandise, day passes | P1 | ✓ | ✓ | — | — | ⚠️ Partial | Day passes write real payments (`visitor_service.py:130`). 0 matches for `sale/retail/merch/stock` — no retail POS |
| 57 | Inventory and low-stock alerts | P2 | ✓ | — | — | — | ❌ Not built | 0 matches for `inventory` |
| 58 | Door and turnstile access tied to membership status | P2 | ✓ | — | — | — | ❌ Not built | No device integration |
| 59 | Equipment register and maintenance | P2 | ✓ | — | — | — | ❌ Not built | 0 matches for `asset` / `maintenance` |
| 60 | Peak-hour tracking; safety checklists | P2 | ✓ | ✓ | — | — | ⚠️ Partial | `ops_peak_hours` specialist. Missing: safety checklists |
| 61 | "Today" command centre | P0 | ✓ | — | ✓ | — | ⚠️ Partial | `frontend/app/app/page.tsx` (494 lines) with KPI strip + headline metrics. A dashboard, not the blueprint's ranked action list ("8 people need you today; USD 1,240 at stake" with Send/Edit/Skip/Call) |
| 62 | Daily owner brief on the owner's preferred channel | P0 | ✓ | ✓ | — | — | 🔧 Improvement | `routes/assistant.py:331 POST /briefing` → `workflows.weekly_briefing`. **Weekly, not daily**; **in-app only**, not on preferred channel |
| 63 | KPIs: active members, joins, churn, MRR, collections, conversion | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `analytics_service.py`, `routes/analytics.py`, KPI strip `frontend/app/app/page.tsx:196` |
| 64 | Revenue-at-risk panel; Wins feed (money recovered) | P0 | ✓ | ✓ | — | — | ⚠️ Partial | `revenue_at_risk` computed and returned (`retention_service.py:383-409`). **Wins feed absent** — 0 matches for `wins` feed in backend/frontend/mobileapp |
| 65 | Ask-anything analytics | P1 | ✓ | ✓ | ✓ | — | 🔧 Improvement | `routes/assistant.py`, `agent/` LangGraph graph, 40-specialist swarm, `ChatGroq` live when `GROQ_API_KEY` set (`agent/model.py:32`) with documented offline stub; web `frontend/app/app/assistant` + streaming API |
| 66 | Multi-branch, multi-currency, franchise royalties | P1–P2 | ✓ | — | — | — | ❌ Not built | 0 matches for `branch_id\|location_id\|site_id\|royalty\|franchise` in models. "venue" hits are the industry vertical. `default_currency` on org only |
| 67 | Waivers, health forms (PAR-Q), contracts with e-signature | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `waiver` / `parq`. All `esignature` hits are `Stripe-Signature` webhook headers |
| 68 | Consent management per channel and purpose (opt-in, opt-out) | P0 | ✓ | — | — | — | ❌ Not built | 0 matches for `opt_in\|opt_out\|consent\|unsubscribe`. The `SUPPRESSED` delivery status is **not** consent — `campaign_service.py:276` derives `wants_email` from the campaign's channel; the only suppression is `email_verified == False` |
| 69 | Data-subject requests: access, export, correction, erasure | P0 | ✓ | — | — | — | ❌ Not built | 0 matches for `gdpr\|dsar\|erasure` |
| 70 | Auto-renewal disclosures, cooling-off and online cancellation | P0 | ✓ | — | — | — | ❌ Not built | 0 matches for `cooling_off\|auto_renewal` |
| 71 | Role-based access to sensitive data | P0 | ✓ | ✓ | — | — | ⚠️ Partial | RBAC roles + capabilities enforced in deps. Missing: field-level sensitivity |
| 72 | Evidence Vault (section 8) | P0 | ✓ | — | — | — | ❌ Not built | Audit log exists but is editable — no hash chain (`prev_hash: 0`), no soft delete (`deleted_at: 0`), no packs, no WORM, no residency. See rows 109–118 |
| 73 | Data residency options (EU, India, Gulf, and others) | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `storage_region` |
| 74 | Messaging-first member self-service: renew, pay, freeze, book | P0 | ✓ | ✓ | — | ✓ | ⚠️ Partial | Member app can **book** (`mobileapp/(member)/classes.tsx:60-140` — idempotent `POST /classes/book`, `DEL /classes/bookings/{id}`) and **view dues/history** (`payments.tsx` → `GET /payments/my`). Missing: renew, freeze self-service (freeze is staff-only, `members_service.py:83`), messaging/AI concierge |
| 75 | Web portal or PWA: card, QR, dues, history | P1 | ✓ | ✓ | — | ✓ | ⚠️ Partial | Earlier audit said "No `mobile/` directory" — **`mobileapp/` exists**: Expo app, 44 screens under `mobileapp/src/app/`, member dues + payment history real (`payments.tsx`). Missing: digital member card, QR code (0 matches for `qr`/`member_card` in mobileapp) |
| 76 | Branded app, workout log, streaks, rewards | P2 | ✓ | ✓ | — | ✓ | ⚠️ Partial | Branded Expo app exists (`mobileapp/app.json`, industry-aware tabs in `(member)/_layout.tsx:31-70`). Backend streaks/challenges complete. Missing: workout log, streak/reward UI (0 matches in mobileapp screens) |
| 77 | Import from spreadsheets and competitor exports | P0 | ✓ | ✓ | — | — | ⚠️ Partial | Backend only: `routes/members.py:331 POST /members/import` → `members_service.py:324 bulk_import_csv`. **No UI in web or mobile** (0 matches for import/CSV in `frontend/app` or `mobileapp/src`). No competitor-format importer (0 matches for `competitor`) |
| 78 | Multilingual UI, right-to-left support, local date and number formats | P0 | ✓ | — | — | — | ❌ Not built | `org.country/timezone/default_currency` fields only. 0 matches for `i18n`/`translation`; the "locale" frontend hits are `toLocaleDateString` |
| 79 | Public API and webhooks; usage and cost meter | P1–P2 | ✓ | ✓ | — | — | ⚠️ Partial | Inbound Stripe webhooks ✅ signature-verified, two endpoints (`routes/webhooks.py:1-60` — `/webhooks/stripe`, `/webhooks/stripe-connect`). Missing: outbound public API, API keys, usage/cost meter |
| 80 | L1 Event ledger: append-only timeline per person, nothing overwritten | — | ✓ | ✓ | — | — | ⚠️ Partial | `AuditLog` + append-only attendance records. No per-person raw event stream (messages, notes, calls) as source of truth |
| 81 | L2 Understanding: LLM + rules extract intent, goal, objection, sentiment, payment details, freeze requests, any language | — | ✓ | ✓ | — | — | ⚠️ Partial | LLM live in assistant (`agent/model.py:32 ChatGroq`). No inbound-message extraction pipeline — messages are never parsed into structured facts |
| 82 | L3 Customer model: structured state + history — plan, expiry, dues, visit baseline, risk, goal, trainer, summary | — | ✓ | ✓ | — | — | ✅ Built | Snapshot + `plan_summaries.py` one-paragraph summary; risk from `retention_service.py`; visit baseline computed |
| 83 | L4 Signal engine: deterministic triggers + ML risk scoring (expiry, absence, visit drop, unpaid dues, unanswered lead) | — | ✓ | ✓ | — | — | ⚠️ Partial | Deterministic triggers (workers) + weighted score (`retention_service.py:166-245`). **No ML**; no unanswered-lead signal (no leads) |
| 84 | L5 Decision layer: next best action, draft, value estimate, owner assignment, autonomy level | — | ✓ | ✓ | — | — | ⚠️ Partial | Assistant proposes writes via `_proposal()` with draft text. No ranked next-best-action engine, no value estimate, no owner assignment, no autonomy level |
| 85 | L6 Action layer: auto-send · approve-then-send · staff task · call | — | ✓ | ✓ | — | — | ⚠️ Partial | Auto / approve / task all exist but scattered across workers and features. No call action; sends limited to email + push |
| 86 | L7 Outcome loop: did they reply, return, pay, renew? Model learns; Wins feed shows money recovered | — | ✓ | — | — | — | ❌ Not built | No learning loop, no outcome attribution, no Wins feed (`wins: 0`) |
| 87 | L0 Observe: update summary, compute risk, tag lead — always automatic | — | ✓ | ✓ | — | — | ⚠️ Partial | Risk computation and summaries run automatically in workers. No lead tagging (no leads) |
| 88 | L1 Auto-act (safe): FAQ reply, receipt, renewal reminder, class reminder, first lead reply — automatic, template-bound, reversible | — | ✓ | ✓ | — | — | ⚠️ Partial | Grace reminders, onboarding messages, celebration messages auto-send on schedule. No FAQ reply, no first-lead reply |
| 89 | L2 Approve first: discounts, win-back offers, complaint replies, freezes, bulk campaigns — one-tap approval | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Real human-in-the-loop gate: `agent/tools/write.py` 8 approval-gated writes via `_proposal()` / `_rejected()`. No one-tap approval UI for the full set |
| 90 | L3 Human only: refunds, price changes, medical topics, angry customers, cash mismatches — AI briefs a human | — | ✓ | — | — | — | ❌ Not built | Not distinguished from L2. No risk classification, no fail-closed timeout |
| 91 | Owner trust ladder: move any action type between levels; promote to L1 after seeing results; AI-disclosure setting per country | — | ✓ | — | — | — | ❌ Not built | No L0–L3 tiers, no owner-controlled promotion dial, no AI-disclosure setting (`AI Act Art. 50`) |
| 92 | Lead Concierge — instant reply, qualification, trial booking, follow-up | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Lead pipeline, trial/tour booking, consent-gated follow-up emails, controlled lost reasons, and profile score exist; instant reply and automated qualification remain absent |
| 93 | Renewal & Collections — expiry reminders, dunning, payment links, proof matching | — | ✓ | ✓ | — | — | ⚠️ Partial | Grace reminders (days 1/2/3), payment-proof pipeline, SaaS dunning ladder. Missing: payment links to members, member escalation ladder |
| 94 | Retention Coach — onboarding, absence check-ins, milestones, save offers | — | ✓ | ✓ | — | — | ✅ Built | Onboarding journey + inactivity ladder + win-back + celebrations all built with routes and daily workers |
| 95 | Front-Desk Copilot — check-in context, draft replies | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Check-in status card (row 18) + inbox AI draft (`inbox_service.py`). Missing: context summary at check-in beyond status flags |
| 96 | Owner Analyst — morning brief, Q&A, explanations | — | ✓ | ✓ | ✓ | — | ✅ Built | `POST /assistant/briefing` + ask-anything with 40 specialists (`routes/assistant.py:331`) |
| 97 | Reputation Agent — review requests, complaint clustering | — | ✓ | ✓ | — | — | ⚠️ Partial | NPS + complaint clustering built (`nps_service.py:75` theme taxonomy). Missing: review requests (0 matches for `review_request`) |
| 98 | Compliance Guard — checks consent, quiet hours, disclosures, cancellation rules per country | — | ✓ | — | — | — | ❌ Not built | No consent model, no country rule packs, no quiet hours — nothing to check against |
| 99 | Country Pack container: quiet hours, consent types, reminder schedules, cooling-off, cancellation channels, AI-disclosure text, retention defaults | — | ✓ | — | — | — | ❌ Not built | 0 matches for `country_pack`. `org.country/timezone/default_currency` are bare fields |
| 100 | Messaging channels by region (WhatsApp, SMS, LINE, WeChat, Telegram; email fallback) | — | ✓ | — | — | — | ❌ Not built | 12-value `Channel` enum (`core/constants.py:227`) but `integrations/` contains only `email.py`, `push.py`, `llm.py`, `ocr.py`, `hibp.py`, `stripe_*` — no sms/whatsapp/line/wechat/telegram module exists. `inbox_service.py` stores conversations without sending |
| 101 | Local payment methods by region (SEPA, Pix, UPI AutoPay, M-Pesa, JazzCash, cards/ACH, Stripe/Adyen gateway) | — | ✓ | ✓ | — | — | ⚠️ Partial | Stripe + cash + bank_transfer + mobile_wallet generic. No regional rails (0 matches for `pix\|upi\|m_pesa\|sepa\|jazzcash`) |
| 102 | Privacy-law rule packs (GDPR, AI Act, CCPA, LGPD, DPDP, PDPL) with deadline tracking | — | ✓ | — | — | — | ❌ Not built | 0 matches for `gdpr\|privacy_rule\|deadline` tracking |
| 103 | Membership and messaging rules (US state auto-renewal, UK DMCC cooling-off, opt-in/STOP, quiet hours 8am–9pm) | — | ✓ | — | — | — | ❌ Not built | 0 matches for `quiet_hours\|cooling_off\|stop_keyword` |
| 104 | Languages and RTL (major languages, Hinglish/Roman Urdu/Spanglish/Arabizi, Arabic/Urdu/Hebrew layouts) | — | ✓ | — | — | — | ❌ Not built | 0 matches for `i18n` / `translation` / `rtl` |
| 105 | Currency: multi-currency pricing, reports, multi-branch consolidation | — | ✓ | ✓ | — | — | ⚠️ Partial | `org.default_currency` only. No multi-currency pricing or consolidation |
| 106 | Tax: VAT, GST, sales tax on invoices by country and region | — | ✓ | ✓ | — | — | ⚠️ Partial | `plan.tax_rate` incl. inclusive-tax handling (`memberships_service.py:345`). No country/region rule packs |
| 107 | Culture: local holidays/seasons, women-only hours, tone per country, local names and formats | — | ✓ | — | — | — | ❌ Not built | 0 matches for `holiday\|women_only\|tone` |
| 108 | Pricing: tiers adjusted for purchasing power (PPP) | — | ✓ | — | — | — | ❌ Not built | 0 matches for `ppp\|purchasing_power` |
| 109 | Append-only ledger: old versions kept on every edit | — | ✓ | — | — | — | ❌ Not built | `AuditLog` records changes but rows are editable/deletable. No version history |
| 110 | Soft delete + Recycle Bin: 90-day restorable, one-click undo | — | ✓ | — | — | — | ❌ Not built | 0 matches for `deleted_at` / `recycle`. Hard deletes only (`members_service.py:417 delete_member`) |
| 111 | Automatic Evidence Packs: PDF + Excel snapshot before delete, merge, bulk edit or payment change | — | ✓ | — | — | — | ❌ Not built | 0 matches for evidence pack generation |
| 112 | Tamper-evident audit chain: hash-chained entries + signed daily checkpoints outside the DB | — | ✓ | — | — | — | ❌ Not built | 0 matches for `prev_hash` / checkpoint signing |
| 113 | WORM storage: object lock blocks deletion/overwrite during retention | — | ✓ | — | — | — | ❌ Not built | 0 matches for `worm` / object lock |
| 114 | Point-in-time recovery + 3-2-1 backups (three copies, two media, one off-site) | — | ✓ | — | — | — | ❌ Not built | No PITR/backup config in codebase |
| 115 | Owner-held daily exports: daily Excel to email/cloud, monthly PDF statement | — | ✓ | — | — | — | ❌ Not built | 0 matches for daily export worker |
| 116 | Access and export log: records who viewed or exported what | — | ✓ | ✓ | — | — | ⚠️ Partial | Partial via `AuditLog` (record_audit covers state changes). No dedicated view/export logging |
| 117 | Owner alerts: bulk deletes, payment edits, large exports, after-hours changes | — | ✓ | — | — | — | ❌ Not built | No alert rules on audit events |
| 118 | Erasure with hash-only stub: personal fields erased, hash keeps chain valid | — | ✓ | — | — | — | ❌ Not built | No erasure path at all |
| 119 | Generic engine: Person / Event / Payment / "Say-Do-Pay" core | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | **Multi-industry built** — `org.industry ∈ {gym, office, academy}` (`models/organization.py:29`), `core/industry.py` per-industry labels/modules/checklist/nouns, schema-driven plan builder, `routes/industries.py`, industry-aware mobile tabs (`(member)/_layout.tsx:31-70`). Missing: clinic/salon/real-estate/B2B verticals |
| 120 | Sales-company pack (contacts, deals, meetings, quotes, lead ownership) | — | ✓ | — | — | — | ❌ Not built | 0 matches for sales-company pack |
| 121 | Pack builder / vertical marketplace | — | ✓ | — | — | — | ❌ Not built | Industry schemas are hardcoded, not installable packs |
| 122 | Today: one ranked list ("8 people need you today; USD 1,240 at stake") with Send / Edit / Skip / Call per card | — | ✓ | — | ✓ | — | ⚠️ Partial | `frontend/app/app/page.tsx` (494 lines) has KPI strip + headline metrics but no ranked action list, no value-at-stake cards, no per-item actions |
| 123 | Inbox: all channels in one place, member summary alongside, AI drafts | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Inbox UI, assignment/status, member linking, and AI drafts exist. `inbox_service.py` explicitly has no channel provider; replies are stored but not delivered externally. Email/push transports are used by other notification flows, not by this inbox. |
| 124 | Desk: check-in scanner with a status card for each arrival | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Both halves exist: scanner (`QrScanner.tsx` @zxing webcam reader, wired at `attendance/page.tsx:657`) + status card (`attendance_service.py:184`, shown in attendance page). Missing: RFID/biometric hardware paths |
| 125 | People: one scrollable timeline of messages, visits and payments per person | — | ✓ | ✓ | ✓ | — | 🔧 Improvement | Member detail sheet shows visits + payments (`member_detail`, `frontend/app/app/members/[memberId]`). No unified message timeline |
| 126 | Money: collections, dues, cash drawer, P&L, recovered this month | — | ✓ | — | ✓ | — | ⚠️ Partial | Collections/dues/cash drawer ✅ (`frontend/app/app/cash`, `payments`, `analytics`). No P&L (row 29), no "recovered this month" |
| 127 | Ask: natural-language questions in any language, action buttons in the answer | — | ✓ | ✓ | ✓ | — | ✅ Built | Assistant with LangGraph + 40 specialists, streaming (`frontend/app/api/assistant/stream`), approval-gated write actions |
| 128 | Wins: feed of members saved, money recovered, leads converted | — | ✓ | — | — | — | ❌ Not built | 0 matches for wins feed. Shares root cause with row 64 and layer 86 |
| 129 | Paper-register photo import with immediate expired-member and unpaid-dues opportunity scan | — | ✓ | — | — | — | ❌ Not built | Spreadsheet/CSV import exists, but no paper-register image import or instant opportunity analysis |
| 130 | Explain every AI suggestion with a visible “Why?” line, source evidence, and value at stake | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Retention risks expose reasons and some assistant answers explain results; no uniform source-linked explanation contract |
| 131 | Undo everywhere with a clear owner-controlled autonomy dial | — | ✓ | ✓ | — | — | ⚠️ Partial | Selected actions can be reversed and approvals exist; there is no universal undo or configurable trust dial |
| 132 | Learn the gym's voice from past conversations and owner edits, including culture-specific tone | — | ✓ | — | — | — | ❌ Not built | Tone is not learned from approved edits or historical conversations |
| 133 | Zero-inbox completion state showing “All done for today” | — | ✓ | — | — | — | ❌ Not built | Inbox/task states exist, but no unified daily completion state is implemented |
| 134 | Front-desk UX for inexpensive tablets/old desktops, large controls, sub-second check-in, and instant Today loading | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | Responsive check-in surfaces exist; device/performance budgets and measured sub-second guarantees do not |
| 135 | Messaging economics controls: consolidate replies, classify utility/marketing templates, pace sends, and estimate broadcast cost | — | ✓ | ✓ | — | — | ⚠️ Partial | Campaign records and generic limits exist; no provider-aware template category, consolidation, pacing, or reliable cost estimator |
| 136 | Guided import with AI-assisted cleaning, duplicate merge, and low-quality-data handling | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | CSV import and lead duplicate rejection exist; guided cleaning and merge workflows are incomplete |
| 137 | Mask personally identifiable information before sending prompts to AI providers | — | ✓ | — | — | — | ❌ Not built | No central prompt-redaction/PII-masking gateway was found |
| 138 | Evidence Vault UX: per-record History, Download Evidence, Recycle Bin, safety score, and deletion receipts | — | ✓ | ✓ | — | — | ⚠️ Partial | Audit history and selected exports exist; the complete user-facing evidence suite does not |
| 139 | Block bulk deletes until owner approval and generate an Evidence Pack for every affected record | — | ✓ | — | — | — | ❌ Not built | No bulk-delete approval threshold or per-record evidence-pack workflow exists |
| 140 | Preserve signed-document evidence, renewal/cancellation delivery proof, removed-staff ownership snapshots, and daily signed checkpoints | — | ✓ | — | — | — | ❌ Not built | These automatic evidence events and proofs are not implemented |
| 141 | Sales Pack intake from official messaging numbers, SMS, email, forms, ads, calls, imports, and listing portals | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Manual lead intake/import and source fields exist; official provider and listing-portal ingestion do not |
| 142 | Sales Pack routing by round robin, territory, product, or language with SLA timers and no-response reassignment | — | ✓ | — | — | — | ❌ Not built | No configurable sales routing or SLA engine exists |
| 143 | Sales Pack pipeline with custom stages, value, close date, and conversation-driven AI stage updates | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | A fixed lead pipeline and audited transitions exist; custom stages/value/close date/AI updates do not |
| 144 | Sales Pack AI for call/meeting summaries, multilingual voice transcription, follow-up drafts, deal risk, and “who to call today” | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | General assistant and inbox drafts exist; call ingestion, transcription, deal risk, and ranked sales queue are incomplete |
| 145 | Sales Pack quotes, invoices, deposits, payment links, and multi-currency handling | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Membership invoices/payments exist; sales quotes/deposits and true multi-currency deal flows do not |
| 146 | Sales Pack team targets, leaderboards, activity, commissions, and coaching insights | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Staff activity/payroll commissions exist; sales targets, leaderboards, and coaching insights are incomplete |
| 147 | Field-sales location check-ins, voice visit notes, and route planning | — | ✓ | — | — | — | ❌ Not built | Attendance check-ins are not field-sales visits; no route planning or voice visit-note flow exists |
| 148 | Sales lead ownership history and conversations locked in Evidence Vault, retained when representatives leave | — | ✓ | ✓ | — | — | ⚠️ Partial | Lead source/history and user audit records exist; immutable rep ownership/conversation preservation does not |
| 149 | Sales manager daily brief for new, untouched, and stalled leads with forecast | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | General owner briefing and lead stages exist; no complete sales-specific forecast brief |
| 150 | Configurable Industry Pack contract for vocabulary, schema, signals, playbooks, dashboards, integrations, and compliance | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | Industry labels/modules/schemas exist for hard-coded verticals; installable configuration-only packs do not |
| 151 | Front-desk voice notes transformed by AI into clean outbound messages | — | ✓ | — | — | — | ❌ Not built | No voice-note capture, transcription, cleanup, and review/send flow exists |
| 152 | Messaging-native lead/member self-service in the customer's usual app without requiring an app download | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | Native mobile self-service and an internal inbox exist; no complete WhatsApp/SMS/LINE/WeChat self-service flow |

*Blueprint matrix total: 152 rows. Strategy matrix total in Section 18: 106 rows. Together they provide direct feature coverage for both source PDFs inside this report.*
