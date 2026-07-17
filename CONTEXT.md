# CONTEXT.md — Patient Billing System Domain Reference

## Project Purpose

Zango take-home prototype for a job application at Zelthy (makers of Zango). It demonstrates
multi-module CRUD, workflow-driven claim lifecycles, and concurrent AI agents dispatched as
independent Celery tasks on claim denial. **This is not a production healthcare system** — it
is not HIPAA-compliant, does not implement EDI 837/835, and makes no accounting guarantees.

---

## Domain Glossary

| Term | Definition |
|---|---|
| **Patient** | Person receiving care. Has demographics + insurance fields. |
| **InsurancePayer** | Insurance company. Referenced on Claims. Lives in `backend/payers/`. |
| **Claim** | Insurance billing record linking Patient + Payer. Has ClaimLineItems and AI output fields. |
| **ClaimLineItem** | One billable procedure on a Claim: CPT code, description, qty, unit_price, total_price. |
| **Invoice** | Self-pay billing record for a Patient. Has InvoiceLineItems and Payment records. |
| **InvoiceLineItem** | Itemized charge on an Invoice. |
| **Payment** | Money recorded against an Invoice: amount, method, date. |
| **BillingStaff** | Create/edit patients, claims, invoices; record payments; view AI Insights; appeal claims. |
| **BillingManager** | All BillingStaff permissions + approve/deny claims, void invoices, access dashboard. |

---

## Claim Lifecycle (ClaimWorkflow)

```
Draft ──► Submitted ──► Under Review ──► Approved ──► Closed
                    │                └──► Denied ──► Appealed ──► Closed
                    │                          └──────────────► Closed
                    │
            (submit fires ClaimValidator agent)
            (deny fires DenialAnalyzer + AppealDrafter concurrently)
```

Workflow hooks:
- `submit_done` → `zango_task_executor.delay(..., "run_claim_validator", claim_id=...)`
- `deny_done` → two independent `.delay()` calls: `run_denial_analyzer` AND `run_appeal_drafter`

Target additional transitions (PAT-42):
- `denied → under_review` (Reopen, BillingManager)
- `appealed → approved` (Approve Appeal, BillingManager)

---

## Invoice Lifecycle (InvoiceWorkflow)

```
Draft ──► Sent ──► Partially Paid ──► Paid
              └──► Overdue ──────────► Paid
              └──► Voided
```

---

## AI Agents

| Agent name (in Zango) | Trigger | Output field on Claim | Type |
|---|---|---|---|
| `claim-validator` | Draft → Submitted | `ai_validation_result` | JSONField |
| `denial-analyzer` | → Denied (concurrent) | `ai_denial_analysis` | JSONField |
| `appeal-drafter` | → Denied (concurrent) | `ai_appeal_draft` | TextField |

Output fields start `null`/blank. The frontend AI Insights tab polls every 5s while any field is null.

### Provider Selection (`deploy/scripts/setup_ai.sh`)

| Env var | `provider_slug` | Notes |
|---|---|---|
| `ANTHROPIC_KEY` | `anthropic` | Recommended — Claude Haiku. |
| `OPENAI_KEY` | `openai` | GPT-4o Mini. |
| `GEMINI_KEY` | `gemini` | Requires paid quota. |
| `LOCAL_FAKE_AI=true` | `local_fake` | Offline, deterministic, zero-cost. **Must be set explicitly** — never a fallback when no key is present. No key + no `LOCAL_FAKE_AI=true` → hard error. |

Precedence when multiple are set: `ANTHROPIC_KEY` > `OPENAI_KEY` > `GEMINI_KEY`; `LOCAL_FAKE_AI=true`
takes priority over all of them (explicit opt-in wins). See "AI Provider Safety" in AGENTS.md.

---

## Task Interfaces

Three registered functions in `backend/agents/tasks.py`:

```python
def run_claim_validator(claim_id: str) -> None
def run_denial_analyzer(claim_id: str) -> None
def run_appeal_drafter(claim_id: str) -> None
```

**Each task must enforce all of these invariants:**

1. Import `_current_claim_id` and `_current_output_field` from `backend.agents.tools`.
2. Set `_current_claim_id` to `str(claim_id)` before `agent.run()`.
3. Set `_current_output_field` to the task's owned field name before `agent.run()`.
4. Reset both ContextVars in `finally` (on success and exception).
5. Call `agent.run(input="Process claim.", system_variables={"claim_id": str(claim_id)}, triggered_by="task")`.
6. After `agent.run()` returns, verify the expected field is non-null on the Claim.

Task → owned output field mapping:

| Task | `_current_output_field` value |
|---|---|
| `run_claim_validator` | `"ai_validation_result"` |
| `run_denial_analyzer` | `"ai_denial_analysis"` |
| `run_appeal_drafter` | `"ai_appeal_draft"` |

---

## Tool Interfaces (target shape after PAT-39)

All tools in `backend/agents/tools.py`. Two ContextVars defined here:

```python
_current_claim_id: ContextVar[str | None]     # set by task before agent.run()
_current_output_field: ContextVar[str | None] # set by task before agent.run()
```

**`get_claim_details()`** — no model-supplied params
- Reads Claim from `_current_claim_id`. Raises RuntimeError if not set.
- Returns: `claim_number`, `date_of_service`, `diagnosis_codes`, `total_amount`,
  `denial_reason_code`, `denial_reason_description`, `notes`, `line_items[]`.

**`get_patient_insurance()`** — no model-supplied params
- Reads Claim from `_current_claim_id`, then accesses `claim.patient`.
- Returns: `first_name`, `last_name`, `insurance_provider`, `insurance_policy_number`, `insurance_group_number`.

**`update_claim_ai_result(value: str)`** — no field param, no Claim ID param
- Reads field from `_current_output_field`. Reads Claim ID from `_current_claim_id`.
- For JSON fields: parses `value`; rejects and leaves field unchanged on invalid JSON.
- Writes atomically: `Claim.objects.filter(id=...).update(**{field: parsed_value})`.
- Never calls `claim.save()` (avoids full-instance race with concurrent tasks).

---

## File Map

| Purpose | Path (relative to workspace root `backend/`) |
|---|---|
| Agent task entry points | `agents/tasks.py` |
| Agent tools + ContextVars | `agents/tools.py` |
| Claim model | `claims/models.py` |
| Claim workflow | `claims/workflows.py` |
| Invoice model | `invoices/models.py` |
| Patient model | `patients/models.py` |
| Dashboard API view | `app/views.py` |
| Unit tests | `deploy/tests/unit/` |
| Integration tests | `deploy/tests/integration/` |
| AI setup script | `deploy/scripts/setup_ai.sh` |

Workspace root (inside container): `/zango/`
Workspace root (on host): `deploy/zango_project/workspaces/patientbilling/`

---

## Testing Seams

1. **Workflow HTTP interface** — legal transitions, role gates, observable Claim state via HTTP.
2. **Task entry interface** — the three registered task functions with the LLM boundary mocked.
3. **Agent tool interface** — model-visible tool schemas and ContextVar-bound behavior.
4. **CRUD/form interface** — amount validation through the same paths users exercise.
5. **Real provider seam** — one opt-in end-to-end smoke test (skipped without `AI_PROVIDER_CONFIGURED` env var).

Rules: mock only genuine external boundaries (LLM provider, Celery submission). Use the test database for owned persistence behavior.

---

## Out of Scope

- Production deployment (no Kubernetes, no SSL termination, no secrets management)
- HIPAA compliance or audit trail
- EDI 837/835 file exchange with payers
- Real-time insurance eligibility verification
- Prior authorization management
- Multi-facility or multi-practice support
- Billing-code lookup from external databases
- Generalized accounting ledger or double-entry bookkeeping
