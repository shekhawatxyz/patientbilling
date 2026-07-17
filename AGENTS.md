# AGENTS.md — Patient Billing System Developer Context

## Purpose
Zango take-home prototype demonstrating a concurrent agentic claim lifecycle: three AI agents
triggered by insurance-claim workflow transitions, dispatched as independent Celery tasks.
The primary goal is a credible end-to-end interview demo — not a production healthcare system.

## Source-of-Truth Precedence
1. Notion PRD and ADRs — intended behavior and architecture decisions
2. **This file + CONTEXT.md** — stable domain facts and invariants
3. Linear ticket — scope of the current task only
4. Passing tests — proof of what exists
5. Code — current implementation (may lag behind decisions)

Stop and report if any ticket instruction conflicts with an ADR or CONTEXT.md.

---

## Zango Rules (violations cause silent failures or broken migrations)

| Rule | Correct | Wrong |
|---|---|---|
| Models | extend `DynamicModelBase` | `models.Model` |
| Foreign keys | `ZForeignKey` | `models.ForeignKey` |
| Many-to-many | not allowed | `ManyToManyField` |
| `class Meta` | only inside `WorkflowBase` subclasses | everywhere else |
| Imports inside modules | relative only (`from .models import ...`) | absolute |
| Migrations | `ws_makemigration` then `ws_migrate` | Django `makemigrations`/`migrate` |
| Async dispatch | `zango_task_executor.delay(tenant, "backend.module.tasks.func", **kwargs)` | `@shared_task` / `.delay()` directly |
| Agent run | `agent.run(input=..., system_variables=..., triggered_by="task")` | `agent.run(variables=...)` without `input=` |

---

## Concurrent Agent Architecture — ADR-001 (DO NOT CHANGE)

When a Claim is denied, `deny_done` dispatches **two independent Celery tasks**:

```python
def deny_done(self, request, object_instance, transaction_obj):
    tenant = connection.tenant.name
    zango_task_executor.delay(
        tenant, "backend.agents.tasks.run_denial_analyzer",
        claim_id=str(object_instance.id),
    )
    zango_task_executor.delay(
        tenant, "backend.agents.tasks.run_appeal_drafter",
        claim_id=str(object_instance.id),
    )
```

- Neither task calls the other.
- Do NOT add Celery chains, chords, groups, or any orchestration framework.
- Each task runs on a separate worker process and may complete in any order.
- One task's failure must not prevent the other from completing.

---

## Server-Bound Agent Context — ADR-003

The model (LLM) must never see Claim IDs, Patient IDs, or output-field selectors.

Two `ContextVar`s in `backend/agents/tools.py`, set by the task, not the model:

- `_current_claim_id`: identifies which Claim this task is working on.
- `_current_output_field`: identifies which Claim field this task owns (`ai_validation_result`, `ai_denial_analysis`, or `ai_appeal_draft`).

Task responsibilities:
1. Set both ContextVars before calling `agent.run()`.
2. Reset both in `finally` (success and exception).
3. After `agent.run()` returns, verify the expected field is non-null.

Tool responsibilities:
- `get_claim_details()` — reads from `_current_claim_id`, no model-supplied ID.
- `get_patient_insurance()` — derives Patient from the bound Claim, no model-supplied ID.
- `update_claim_ai_result(value)` — writes only to `_current_output_field`, atomically
  (`Claim.objects.filter(id=...).update(**{field: value})`). No `claim.save()`.

---

## AI Provider Safety (non-negotiable)

The user pays real money for Anthropic API calls. These rules exist because a prior change
silently defaulted to a fake provider when no key was set — that must be structurally impossible
going forward.

1. **No silent provider defaulting, ever.** If no provider is explicitly selected (no key, no
   offline flag), the script/code must hard-error. Never fall through to a provider — real or
   fake — because one wasn't specified.
2. **Offline/fake providers are opt-in only.** `local_fake` (or any future offline provider)
   requires an explicit flag (`LOCAL_FAKE_AI=true`). It must never be reachable by omission.
3. **Every provider-creation call sets `monthly_budget_usd` explicitly.** No unbounded budget,
   ever — including for offline providers (set it to `0.00` there, not left unset).
4. **Print which provider + model is active before the first call that can spend money.** A
   spend-causing run must never be silent about which provider it's using.

---

## AI Testing Standard — the one way to test agent plumbing offline

**The canonical, only sanctioned way to test the agentic pipeline without hitting a real LLM is
a registered fake provider** (`local_fake`, `deploy/providers/local_fake.py`), never premade
response fixtures that bypass the loop. `register_provider`/`BaseLLMProvider` is Zango's actual
extension point for the LLM boundary — a provider implementing that interface exercises the real
`AgentClient` loop, tool execution, ContextVar binding, Celery dispatch, and DB writes. Canned
fixtures injected earlier in the pipeline would skip exactly the plumbing this exists to cover.

Three brackets, one standard, not three peer options:

| Bracket | Mechanism | When |
|---|---|---|
| **Unit** (fast, no Docker round-trip) | mock at the `agent.run`/tool-call boundary directly in the pytest process (`sys.modules` patching — see `deploy/tests/unit/`) | tool logic, task wiring, ContextVar handling |
| **Plumbing** (the standard) | registered `local_fake` provider, opt-in via `LOCAL_FAKE_AI=true` — full Celery+HTTP+DB path, zero cost | every normal test run of the agent pipeline |
| **Live smoke** (opt-in, rare) | real provider, `AI_LIVE_SMOKE=1 AI_PROVIDER_CONFIGURED=1` | only after plumbing tests pass, only when explicitly proving real-provider behavior |

**Provider-lifecycle rule (non-negotiable):** the dev stack is a single shared app — running the
plumbing bracket with `LOCAL_FAKE_AI=true` repoints the three agent records' `provider_id` to
`local_fake`. Any script/tooling that does this **must restore the agents to the previously-active
real provider afterward** (in a `finally`/trap, not just on the happy path) — a plumbing-test run
must never silently leave the live app wired to the fake provider. `setup_ai.sh` must not be the
only way to flip this; provide a explicit `restore` mode or equivalent that re-points agents back.

**Fail-loud rule:** if neither `local_fake` nor a real provider is configured, an AI plumbing test
must **fail**, not skip. Skipping silently degrades the standard run into "nothing was verified."
Reserve `pytest.skip` only for a clearly-labeled context where AI testing is explicitly out of
scope (e.g. a non-AI ticket's unrelated test file).

---

## Per-Ticket Workflow

**Ownership split (non-negotiable): codex never commits to `main` directly.** Claude owns `main`
— docs, standards, ticket state, and merges. Codex works on a branch per ticket and opens a PR;
Claude reviews against the PR Acceptance Checklist below and merges. This exists because a direct
push to `main` once let codex's local checkout silently drift out of sync with standards Claude
had committed on a separate branch — a PR forces a rebase/fetch and a review gate before anything
lands on `main`, so that can't happen silently again.

```
1. Pull latest main: git checkout main && git pull origin main
2. Read AGENTS.md and CONTEXT.md (freshly, from the pulled main — never trust a stale local copy)
3. Fetch the one assigned Linear ticket (or, if Linear/MCP isn't available in this session,
   read the full ticket spec from CODEX_TICKETS.md — do not proceed on a guess or a stale
   cached summary; ask/stop if neither source has the current spec)
4. Create a ticket branch: git checkout -b pat-XX-<short-slug>
5. Inspect only the files the ticket names and their direct tests
6. Write the failing test first (red)
7. Make the minimal change to pass (green)
8. Run focused tests → green
9. Run full suite → green (2 AI tests skip without provider — correct)
10. git add <specific files> (never -A)
11. git commit -m "PAT-XX: <description>"
12. git push origin pat-XX-<short-slug>
13. gh pr create --draft --title "PAT-XX: <description>" --body "<summary + test plan>"
14. Report the PR to Claude for review — do not merge it yourself, and do not start the next
    ticket on top of an unmerged one (single shared dev DB/Celery stack — no parallel tickets).
```

---

## Verification Commands

```bash
# Full suite (run inside container):
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/ integration/ -v --tb=short 2>&1'"

# Unit tests only:
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/ -v --tb=short 2>&1'"

# Single test file:
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/test_tasks_unit.py -v --tb=short 2>&1'"
```

Expected baseline: all tests pass; 2 AI tests skip (correct without a configured provider).

---

## PR Acceptance Checklist

Every PR is checked against this list before merge. Not "looks fine" — each item is a specific,
testable condition.

1. **Cost safety** — if the PR touches `setup_ai.sh`, providers, or agent dispatch: confirm no
   silent fallback to a paid provider, confirm every provider path sets an explicit budget,
   confirm offline/fake paths stay opt-in-only (see AI Provider Safety above).
2. **DB correctness** — `DynamicModelBase`/`ZForeignKey` used, never raw `models.Model`/
   `ForeignKey`; no `ManyToManyField`; migrations generated via `ws_makemigration`/`ws_migrate`
   and present in the diff whenever models changed.
3. **Async wiring** — dispatch goes through `zango_task_executor.delay(tenant,
   "backend.module.tasks.func", **kwargs)`, never `@shared_task`/`.delay()` directly; ContextVars
   (`_current_claim_id`, `_current_output_field`) set before `agent.run()` and reset in `finally`
   on both success and exception paths; task verifies its owned output field is non-null after
   `agent.run()` returns and **raises/logs loudly** if it isn't — never silently returns.
4. **Agent/tool contracts** — `agent.run(input=..., system_variables=..., triggered_by="task")`
   shape; tools read Claim/Patient/output-field only from ContextVars, never from model-supplied
   params; `update_claim_ai_result` writes via `.filter().update()`, never `.save()`.
5. **Fail-loud audit** — grep the diff for bare `except:` / `except Exception: pass`,
   `.get(..., <fallback>)` masking missing config, and any `if not X: return` that should raise
   instead. Flag every instance found.
6. **Modularity** — change stays scoped to the files the ticket names; no new orchestration
   frameworks, event buses, or shared "utils" dumping grounds; provider/task/tool code stays in
   its existing module boundaries.
7. **Tests** — full suite green per Verification Commands below; the ticket's own new/changed
   test is read closely enough to confirm it actually fails without the fix, not just trusted
   because the PR description says "tests pass."

---

## Prohibitions

- Do not edit installed Zango package code (anything under the container's site-packages).
- Do not commit `static/js/*.min.js` bundles or `node_modules/`.
- Do not add orchestration frameworks, event buses, or generalized agent-run models.
- Do not replace the Claim/Invoice data model wholesale.
- Do not expand scope beyond the named ticket.
- Do not add secrets or API keys to any committed file.
- Do not batch multiple tickets into one session without running the full suite between them.
