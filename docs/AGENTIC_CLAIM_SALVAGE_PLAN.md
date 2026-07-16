# Patient Billing Agentic Claim Salvage Plan

**Status:** Planning only  
**Branch:** `planning/agentic-claim-salvage`  
**Purpose:** Prepare the existing Zango take-home for focused implementation by small/cheap coding models without rewriting the application.

## 1. Objective and Evaluation Context

This is a backend take-home for a fresher Zango role. The objective is not to build a production healthcare billing platform. The objective is to demonstrate that the candidate can build and explain a coherent agentic application end to end using Zango.

The strongest demonstration is the insurance Claim lifecycle:

1. Staff creates Patients, Insurance Payers, Claims, and Claim Line Items.
2. Submitting a Claim triggers ClaimValidator asynchronously.
3. A manager moves the Claim through review and may deny it with a recorded reason.
4. Denial independently triggers DenialAnalyzer and AppealDrafter.
5. Both results are stored on the Claim and displayed in AI Insights.
6. Zango supplies the models, multi-tenant context, policies, workflows, async tasks, agents, tools, and invocation history.

The project should be described as an end-to-end take-home prototype. It must not claim production healthcare, HIPAA, EDI, or accounting readiness.

## 2. Current Assessment

Approximate readiness:

- Credible interview demonstration: 65–70% complete.
- Core CRUD and Zango foundation: 85–90% complete.
- Claim and Invoice workflow behavior: 65–70% complete.
- Frontend experience: 60–70% complete.
- Real AI pipeline: 35–45% complete because the provider-backed path is not genuinely tested and the current Zango invocation can fail before an LLM call.
- Production healthcare system: 20–30% complete, but production is out of scope.

The repository is not meaningfully bloated in owned application code:

- Roughly 2,357 lines across the billing backend, custom frontend, and tests.
- Roughly 64 tracked application/test files.
- 103 tracked files in the repository at the time of review.
- Most local disk usage comes from `node_modules` and installed/generated Zango packages.
- One generated minified JavaScript bundle of approximately 4.3 MB is tracked unnecessarily.

The correct strategy is surgical completion and documentation reconciliation, not a rewrite.

## 3. Sources of Truth

Use these sources with explicit precedence:

1. **Notion PRD and ADRs:** intended product behavior and architectural decisions.
2. **Linear:** implementation work, priority, and acceptance state.
3. **Code and passing tests:** proof of what currently exists.
4. **HANDOFF.md:** temporary session context and raw review material, not authoritative product truth.

If HANDOFF or a Linear ticket contradicts an accepted ADR, stop and resolve the contradiction explicitly. Do not silently change the architecture.

## 4. Zango Findings

### 4.1 Zango supports the intended concurrent architecture

Zango does not force DenialAnalyzer and AppealDrafter to run sequentially.

- A Zango workflow `<transition>_done` hook is called after the Workflow State is updated.
- `zango_task_executor` is a normal Celery shared task.
- Each `.delay()` call creates an independent Celery message.
- The executor establishes the tenant context, loads the registered workspace function, and calls it.
- There is no Zango lock, implicit task chain, or per-tenant serialization in that executor.
- `agent.run()` is synchronous inside one worker process, but separate Celery worker processes can run separate agents concurrently.
- The current local Celery worker was observed with eight child worker processes.

Relevant primary sources:

- Zango async task documentation: <https://github.com/Healthlane-Technologies/Zango/blob/main/docs/docs/documentation/async-tasks/manually-triggering-async-tasks.mdx>
- Zango agent execution documentation: <https://github.com/Healthlane-Technologies/Zango/blob/main/docs/docs/documentation/ai-agents/running-agents.mdx>
- Zango task executor source: <https://github.com/Healthlane-Technologies/Zango/blob/main/backend/src/zango/core/tasks.py>
- Celery worker/concurrency documentation: <https://docs.celeryq.dev/en/stable/userguide/workers.html>

The accurate documentation claim is:

> DenialAnalyzer and AppealDrafter are independently dispatched and can execute concurrently on separate Celery worker processes.

Do not claim guaranteed identical start times. Worker availability and provider rate limits may affect actual start time.

### 4.2 Why the current implementation stopped matching the diagrams

The original implementation matched Notion and ADR-001 by making two independent `zango_task_executor.delay()` calls.

Commit `c0195be` changed that behavior while implementing PAT-30 and PAT-31:

- The AppealDrafter dispatch was removed from the Claim denial hook.
- `run_denial_analyzer()` began calling `run_appeal_drafter()` directly after the analyzer returned.

That is not a Celery chain. It is an ordinary Python function call inside one Celery task and one worker process.

The commit recorded this as a partial PAT-33 change based on review feedback claiming that the appeal logically depended on the denial analysis. However:

- AppealDrafter's prompt does not request `ai_denial_analysis`.
- `get_claim_details()` does not return `ai_denial_analysis`.
- The two agents therefore remain logically independent in the current design.

Sequencing currently adds latency and failure coupling without giving AppealDrafter any additional information.

### 4.3 The review identified a real race but proposed the wrong remedy

The genuine risk in parallel execution is not the absence of ordering. The risk is that both agents may load the same Claim and call unrestricted `claim.save()`. Two stale model instances could overwrite one another's fields.

The correct fix is:

- retain independent task dispatch;
- bind the Claim and owned output field server-side;
- update only the task-owned field atomically;
- never save a stale full Claim instance from the tool.

### 4.4 Zango 1.2 agent invocation incompatibility

The running environment uses Zango `1.2.0b6`.

In that version:

- `variables=` renders a configured user prompt;
- `system_variables=` renders a configured system prompt;
- `input=` supplies a direct user message;
- `agent.run()` raises an error if no user message can be constructed.

The current setup creates system prompts containing `{{claim_id}}`, while tasks call `agent.run(variables={...})` without a user prompt or `input=`. The agents can therefore fail with a “no input” error before making an LLM request.

The minimum compatible correction is:

- supply a non-empty `input=` for every agent run;
- supply `system_variables={"claim_id": ...}` for the current system-prompt templates;
- keep `triggered_by="task"` as documented by Zango.

This is independent of the concurrency decision.

## 5. Authoritative Architecture Decision

Return to independent parallel denial agents.

```text
Claim denied
├── Zango/Celery task → DenialAnalyzer → ai_denial_analysis
└── Zango/Celery task → AppealDrafter  → ai_appeal_draft
```

Reasons:

- It is faithful to the Notion PRD and accepted ADR-001.
- Zango supports it directly.
- The agents consume the same source facts but produce independent outputs.
- It reduces wall-clock latency when worker capacity is available.
- One agent can succeed if the other fails.
- Zango records separate invocations and costs.
- It is the project's clearest agentic differentiator.

Sequential execution would only be appropriate after an intentional redesign in which AppealDrafter explicitly consumes a validated DenialAnalyzer result. That is not the present design and is not required for this take-home.

## 6. Agent Module Interface and Invariants

Do not introduce a generalized orchestration framework. Keep the existing `agents` module and its three task entry points:

- `run_claim_validator(claim_id)`
- `run_denial_analyzer(claim_id)`
- `run_appeal_drafter(claim_id)`

The implementation must enforce these invariants:

1. The server chooses the Claim.
2. The server chooses the output field owned by the task.
3. The model chooses neither a Claim ID, a Patient ID, nor an output field.
4. Read tools operate only on the bound Claim.
5. Patient insurance is derived from the bound Claim's Patient.
6. Each task writes only its owned result field.
7. Concurrent writes preserve unrelated fields.
8. Context is reset after success and failure.
9. An agent that returns without writing its expected result is treated as failed.
10. Invalid JSON never replaces a JSON output field.

Recommended task bindings:

| Task | Bound output field |
|---|---|
| ClaimValidator | `ai_validation_result` |
| DenialAnalyzer | `ai_denial_analysis` |
| AppealDrafter | `ai_appeal_draft` |

The write tool's model-facing interface should accept only the result value. Claim and destination-field selection remain server-side.

## 7. LLM-Executable Repository Context

A cheap coding model should not have to read every source file, Notion page, handoff note, or historical Linear ticket.

Before delegating implementation, create three concise artifacts.

### 7.1 Root `AGENTS.md`

Target: fewer than 150 lines.

Include:

- Project purpose in two sentences.
- Source-of-truth precedence.
- Zango model, foreign-key, policy, workflow, task, migration, and import rules.
- The concurrent-agent architectural decision.
- Server-bound agent-context rules.
- Required red → green workflow.
- Focused and full verification commands.
- Prohibitions on unrelated cleanup, generated bundles, secrets, and installed Zango package edits.
- Instruction to stop if a ticket conflicts with an ADR.

### 7.2 Root `CONTEXT.md`

Target: approximately 2,000–3,000 tokens.

Include only stable facts:

- Domain glossary.
- Claim and Invoice lifecycles.
- Role capabilities.
- Agent triggers, inputs, and owned outputs.
- Task interfaces and context invariants.
- Independent parallel-dispatch decision.
- Testing seams.
- Short architecture/navigation map.
- Explicit out-of-scope list.

Do not duplicate detailed Notion prose.

### 7.3 Linear implementation ticket template

Every ticket must contain:

- Problem statement.
- Observable outcome.
- Required context documents.
- Modules and interfaces in scope.
- Explicit out of scope.
- Red → green behavioral tests.
- Acceptance criteria.
- Verification commands.
- Documentation impact.
- “Do not change” guardrails.

### 7.4 Optional local skill: `patientbilling-ticket-worker`

The skill should enforce procedure, not duplicate domain knowledge:

1. Read `AGENTS.md`.
2. Read `CONTEXT.md`.
3. Fetch exactly one Linear ticket.
4. Inspect only the modules named by that ticket and directly related tests.
5. Confirm the test seam.
6. Execute one red → green vertical slice at a time.
7. Run focused tests and then the complete suite.
8. Stop instead of expanding scope.
9. Report acceptance evidence.

Forward-test the skill with a fresh agent on one small ticket before relying on cheap models for urgent work.

## 8. Ticket Priority and Execution Order

### Urgent: required to prove the take-home

| Order | Ticket | Why urgent |
|---:|---|---|
| 1 | PAT-37 — LLM development context | Every delegated ticket depends on concise, reliable project context |
| 2 | PAT-32 — Portable and repeatable AI setup | An evaluator must be able to configure the project outside the original laptop |
| 3 | PAT-38 — Zango 1.2 agent invocation | The agents may currently fail before an LLM call |
| 4 | PAT-39 — Complete server binding and atomic writes | Required for prompt-injection safety and correct parallel persistence |
| 5 | PAT-40 — Restore independent denial dispatch | Restores the accepted architecture and differentiator |
| 6 | PAT-41 — Real provider-backed pipeline test | Proves the advertised flow rather than merely testing registration |
| 7 | PAT-44 — Reconcile Notion and ADRs | Documentation must describe tested behavior |
| 8 | PAT-34 — Root README and walkthrough | The evaluator needs a reproducible demonstration path |

### High: valuable backend correctness

| Ticket | Why |
|---|---|
| PAT-42 — Workflow and dashboard corrections | Closes visible lifecycle gaps and fixes a misleading KPI |
| PAT-43 — Minimal financial invariants | Demonstrates backend validation without creating a production ledger |

### Medium: inexpensive polish

| Ticket | Why |
|---|---|
| PAT-29 — Development credential comments | Prevents local credentials from appearing to be production practice |
| PAT-35 — Frontend and bundle cleanup | Removes obvious review distractions and repository weight |

### Deferred

- PAT-36 production deployment support.
- EDI 837/835 exchange.
- Real-time eligibility verification.
- HIPAA certification work.
- Generalized accounting ledger.
- Historical AI-result model.
- Multi-practice support.

## 9. Detailed Ticket Specifications

### PAT-37 — Create the LLM Development Context

**Priority:** Urgent

Create the `AGENTS.md`, `CONTEXT.md`, Linear ticket template, and optional procedural skill described above.

Acceptance:

- A fresh agent can correctly explain the architecture after reading only `AGENTS.md` and `CONTEXT.md`.
- A forward-test agent can plan PAT-38 without scanning unrelated modules.
- Stable facts are not duplicated across new documents.
- No implementation behavior changes.

### PAT-32 — Make AI Setup Portable and Repeatable

**Priority:** Urgent

Scope:

- Derive repository and Compose paths from the script location.
- Support Docker with and without `sg`.
- Make provider, prompt, and agent setup safe to rerun without duplicates.
- Retain the provider budget cap.
- Label development credentials clearly.

Acceptance:

- Setup works from a different clone path.
- Running setup twice leaves one intended provider configuration and one record per prompt/agent name.
- All three agents are enabled and retrievable through the Zango API.

### PAT-38 — Correct Zango 1.2 Agent Invocation

**Priority:** Urgent

Scope:

- Every task supplies non-empty `input=`.
- Existing system-prompt variables are passed through `system_variables`.
- Preserve `triggered_by="task"`.
- Preserve current agent names, output fields, and workflow behavior.

Behavioral tests:

- Validator receives valid input and Claim context.
- Analyzer receives valid input and Claim context.
- Drafter receives valid input and Claim context.
- Context is reset after success and exceptions.

Acceptance:

- None of the three tasks can raise Zango's “agent has no input” error.
- No concurrency change is included in this ticket.

### PAT-39 — Bind Claim, Patient, and Output Ownership Server-Side

**Priority:** Urgent

Scope:

- Bind the current Claim and expected output field in task context.
- Remove Claim ID from the model-facing details tool.
- Remove Patient ID from the model-facing insurance tool.
- Derive Patient through the bound Claim.
- Remove the output-field selector from the write tool's model-facing interface.
- Update only the task-owned field atomically.
- Reject invalid structured output.
- Verify the expected field was populated after `agent.run()`.

Behavioral tests:

- Tool schemas expose no record IDs or destination-field selector.
- A malicious note cannot redirect reads or writes.
- Analyzer and drafter writes in either order preserve both outputs.
- Invalid JSON leaves the Claim unchanged.
- An agent that returns without writing fails clearly.

Acceptance:

- PAT-31 protects reads and output ownership, not only the Claim write target.
- Parallel tasks cannot lose unrelated Claim fields.

### PAT-40 — Restore Independent Concurrent Denial Agents

**Priority:** Urgent

Scope:

- The denial workflow independently queues DenialAnalyzer and AppealDrafter.
- DenialAnalyzer never calls AppealDrafter directly.
- Development Celery configuration supplies at least two worker slots.
- Re-denial clears stale denial outputs before dispatching new tasks.
- Do not add Celery chains, chords, groups, or a new orchestration framework.

Behavioral tests:

- Denial submits exactly one analyzer task and one drafter task.
- Either task may complete first without data loss.
- One task's failure does not prevent the other from completing.
- Re-denial does not initially display stale results.

Acceptance:

- Implementation matches ADR-001.
- The HTTP transition does not wait for either model.
- Zango records separate invocations for the two agents.

### PAT-41 — Prove the Core Pipeline with a Real Provider

**Priority:** Urgent

Replace the placeholder AI integration test with a real opt-in smoke test:

1. Create a Patient and Insurance Payer.
2. Create a Claim and line items.
3. Submit the Claim.
4. Wait for ClaimValidator output.
5. Move the Claim to Under Review.
6. Deny the Claim with a reason.
7. Wait independently for DenialAnalyzer and AppealDrafter outputs.
8. Verify documented output shapes.
9. Verify two separate Zango invocation records.

Provider-less test runs may continue to skip this test. Before declaring the take-home ready, run it successfully with one cheap configured provider and record the evidence.

After this ticket passes, reconcile and close PAT-15, PAT-17, and PAT-18.

### PAT-42 — Workflow and Dashboard Corrections

**Priority:** High

Scope:

- Add Appealed → Approved for BillingManager.
- Add Denied → Under Review for BillingManager.
- Calculate denial rate from adjudicated Claims rather than Draft Claims.
- Do not add Claim Partially Paid.

Tests:

- Allowed roles can perform the transitions.
- BillingStaff cannot perform manager-only transitions.
- A worked KPI example proves that Draft Claims do not affect denial rate.

### PAT-43 — Minimal Financial Invariants

**Priority:** High

Scope:

- Line total equals quantity × unit price.
- Claim total matches existing line items at submission.
- Payment amount is positive.
- Invoice paid amount cannot exceed total amount.
- Mark Paid requires recorded payments covering the Invoice.

Test through user-facing form and workflow interfaces. Do not create a ledger module or redesign Invoice storage.

### PAT-44 — Reconcile Notion and Review Feedback

**Priority:** Urgent after PAT-41

Notion changes:

- Preserve the existing PRD structure.
- Keep concurrent agents authoritative.
- Describe ClaimValidator as submission-time validation, not a blocking pre-payer check.
- Remove unimplemented Claim Partially Paid states.
- Describe independent dispatch precisely.
- Update ADR-001 with atomic-write mitigation.
- Expand ADR-003 to include server-bound reads and output ownership.
- Add a separate Review page containing the Friend + Opus text unchanged.
- Add a disposition table that accepts the race concern, rejects chaining as the remedy, and records atomic writes as the resolution.

Do not rewrite the product or domain model.

### PAT-34 — Root README and Evaluator Walkthrough

**Priority:** Urgent after PAT-41

Include:

- Project purpose and Zango concepts demonstrated.
- Stack and prerequisites.
- Portable quick start using the verified setup script.
- Clearly labeled development credentials.
- A five-minute evaluator walkthrough.
- Expected AI results.
- A step showing separate Zango invocation records.
- Screenshots captured from the verified flow.
- Honest known limitations and future work.

### Existing Ticket Disposition

- **PAT-29:** retain and implement after core correctness.
- **PAT-33:** close as superseded by PAT-40, PAT-42, and PAT-43; do not preserve its chaining instruction.
- **PAT-35:** retain and implement after README/build instructions stabilize.
- **PAT-36:** defer.
- **PAT-15/17/18:** mark Done only after PAT-41 proves the live provider, prompts, and agents.

## 10. Testing Seams and TDD Rules

Tests should verify behavior through agreed interfaces rather than internal implementation details.

Agreed seams:

1. **Workflow HTTP interface:** legal transitions, role gates, and observable Claim state.
2. **Task entry interface:** behavior of the three registered app task functions, with the external LLM boundary substituted.
3. **Agent tool interface:** model-visible tool schemas and Claim-bound results.
4. **CRUD/form interface:** amount validation through the same paths users exercise.
5. **Real provider seam:** one opt-in end-to-end smoke test.

Rules:

- Work one red → green vertical slice at a time.
- Mock only genuine external boundaries such as the LLM provider or Celery submission.
- Prefer the test database for owned persistence behavior.
- Do not test private helpers or duplicate implementation calculations in assertions.
- Each completed commit must leave the test suite green.
- Run focused tests, then the complete unit/integration suite.

## 11. Cheap-Model Execution Contract

Assign one ticket to one model. Never ask a cheap model to implement the entire backlog in one session.

Use this instruction:

```text
Use the patientbilling-ticket-worker skill if it exists.

Read only:
1. AGENTS.md
2. CONTEXT.md
3. Linear PAT-XX

Then inspect the modules named by PAT-XX and their directly related tests.
Do not implement adjacent tickets or perform opportunistic cleanup.
Use one red → green vertical slice at a time.
Run focused tests, then the full suite.
Stop and report if the ticket conflicts with CONTEXT.md or an ADR.
```

Every ticket assigned to a cheap model must be decision-complete. It must not ask the model to choose architecture, persistence ownership, output shapes, workflow states, role policy, or scope.

## 12. Notion and Handoff Reconciliation

The current Notion structure is good and should remain:

```text
Patient Billing System
├── PRD
├── Domain Model
├── Technical Design
├── System Diagrams
├── ADRs
│   ├── Concurrent Denial Agents
│   ├── AI Output Storage
│   └── Server-Bound Agent Context
└── Reviews
    └── Friend + Opus Feedback — Verbatim
        ├── Disposition table
        └── Original unedited feedback
```

The review strengthens the project, but its recommendations are not automatically requirements.

Recommended disposition:

| Feedback | Decision |
|---|---|
| Dashboard anonymous PHI leak | Accepted and fixed in PAT-30 |
| Server-bind the write target | Accepted and fixed in PAT-31 |
| Bind read targets and output ownership | Additional accepted follow-up |
| Make setup portable | Accepted; PAT-32 |
| Add root README | Accepted; PAT-34 |
| Chain denial agents | Rejected |
| Prevent lost concurrent writes | Accepted through atomic field updates |
| Clarify development credentials | Accepted; PAT-29 |
| Financial checks | Accepted at take-home scope; PAT-43 |
| Appeal/reopen transitions | Accepted; PAT-42 |
| Correct denial-rate denominator | Accepted; PAT-42 |
| Add known limitations | Accepted; PAT-34 |
| Frontend dependency cleanup | Accepted; PAT-35 |
| Remove committed generated bundle | Accepted; PAT-35 |
| Production Compose support | Deferred |

## 13. Verbatim Friend + Opus Review

The following text must remain unchanged when transferred to the Notion Review page:

> Fixes I + Opus recommend in order of priority, high:
> - The dashboard API is open to anonymous users. backend/app/policies.json grants DashboardAPIView to "AnonymousUsers" alongside the SPA shell. That endpoint returns patient names, claim numbers, and dollar amounts. On a billing app, that's a PHI leak reachable by anyone who can hit /api/dashboard/. Split the policy: AppView/RedirectAppView can stay anonymous, DashboardAPIView cannot.
> - Prompt injection → cross-claim write. update_claim_ai_result takes claim_id as a model-supplied parameter, and the agent reads claim.notes (free text a user controls) via get_claim_details. Someone types instructions into a claim note and the agent can be steered into writing to a different claim. Bind claim_id server-side from the task context and drop it from the tool schema. Show you know how to mitigate prompt injection.
> - setup_ai.sh hardcodes /home/parakram/src/patientbilling in five places, plus sg docker -c. The script only runs on one laptop. Derive the compose path relative to the script so the interviewer or whoever can actually run it.
> - Similarly, no root README. There's a 325-line frontend README but nothing at top level saying what this is or how to start it, and the GitHub description is empty. Interviewer needs to know how to run locally. Include screenshots too, so they know how to go through the app. Suggest things for them to try.
> Minor nits:
> - Race between the denial agents. deny_done fires run_denial_analyzer and run_appeal_drafter as two independent .delay() calls, but the appeal draft logically depends on the denial analysis. Chain them.
> - Zango@123 / platform_admin@zango.dev in setup_ai.sh, and the hardcoded SECRET_KEY with # Shift this to .env next to it. I would adapt the comment that this is just for testing so you know better than to leak credentials lol
> - No financial integrity checks. Payment rows and Invoice.paid_amount are independent fields; mark_paid is role-gated but never verifies sum(payments) >= total_amount. Same gap on ClaimLineItem.total_price vs quantity × unit_price, and Claim.total_amount vs the sum of its line items. Derive or validate in clean().
> - Workflow gaps: appealed only transitions to closed — a successful appeal can't reach approved. denied has no path back to under_review.
> - denial_rate divides by all claims including drafts. The denominator should be adjudicated claims.
> Follow-ups:
> - A next steps or known limitations section, ofc this is a project but given more time or resources how would you productize it? things like audit trail, better security, compliance, encryption, etc. Just throw some ideas here so you show you've thought about stuff
> - Once you feel things are done, have Claude do a cleanup pass to remove any leftover things that may not be used, for eg these two:
> - Frontend inconsistency: Tailwind v4 + tailwind.config.ts + @tailwindcss/vite are all installed, and every page uses inline style objects instead. Also @types/react ^19 against react@18.3.1, and an eslintConfig block with no eslint dependency.
> - * A 4.3 MB minified bundle is committed (static/js/zango-app.*.min.js). .gitignore catches zango-build/ but not this.

## 14. Final Take-Home Acceptance

The project is ready when:

- A fresh evaluator can start the stack from the root README.
- A real Claim submission produces ClaimValidator output.
- A denial independently queues DenialAnalyzer and AppealDrafter.
- Either denial agent may finish first without losing data.
- Failure of one agent does not suppress the other result.
- Prompt content cannot redirect an agent to another Claim, Patient, or output field.
- Zango invocation history shows separate agent runs.
- Workflow roles and dashboard access match the documentation.
- The provider-backed smoke test has passed at least once.
- Notion, Linear, code, tests, diagrams, and README tell the same story.
- Known limitations explicitly state that production healthcare readiness is out of scope.

## 15. Guardrails

- Salvage existing modules; do not rewrite the application.
- Do not modify installed Zango package code.
- Do not introduce an orchestration framework, event bus, or generalized agent-run model.
- Do not replace the current Claim/Invoice data model wholesale.
- Do not turn this into a production deployment or compliance project.
- Do not let raw review feedback silently override accepted ADRs.
- Do not declare an AI ticket complete based only on registration or skipped tests.
- Do not assign multiple urgent tickets to one cheap-model session.
- Keep every implementation ticket decision-complete and independently verifiable.
