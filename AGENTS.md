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

## Per-Ticket Workflow

```
1. Read AGENTS.md and CONTEXT.md
2. Fetch the one assigned Linear ticket
3. Inspect only the files the ticket names and their direct tests
4. Write the failing test first (red)
5. Make the minimal change to pass (green)
6. Run focused tests → green
7. Run full suite → green (2 AI tests skip without provider — correct)
8. git add <specific files> (never -A)
9. git commit -m "PAT-XX: <description>"
10. git push origin main
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

## Prohibitions

- Do not edit installed Zango package code (anything under the container's site-packages).
- Do not commit `static/js/*.min.js` bundles or `node_modules/`.
- Do not add orchestration frameworks, event buses, or generalized agent-run models.
- Do not replace the Claim/Invoice data model wholesale.
- Do not expand scope beyond the named ticket.
- Do not add secrets or API keys to any committed file.
- Do not batch multiple tickets into one session without running the full suite between them.
