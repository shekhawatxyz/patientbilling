# Patient Billing System — Session Handoff

**Deadline:** 2026-07-18 | **Repo:** https://github.com/shekhawatxyz/patientbilling | **Branch:** main

---

## Session Start Checklist (mandatory — run these before touching any code)

Every new Claude Code session must complete all four steps before writing a single line:

### Step 1 — Load skills
Run these three slash commands in order:
```
/zango-app-developer:zango-app-developer
/tdd
/plan
```

### Step 2 — Read Notion workspace
Fetch the project root and read all sub-pages:
- Project root: https://app.notion.com/p/39ecbcdf8f20819a8a63f40ff20af215
- PRD: https://app.notion.com/p/39ecbcdf8f2081bea536e8843e1612c9
- Technical Design: https://app.notion.com/p/39ecbcdf8f208158ae99d48372638c9c
- Domain Model: https://app.notion.com/p/39ecbcdf8f208163a815cb9494474801
- ADRs: https://app.notion.com/p/39ecbcdf8f2081b38ce9e7e463b5f450

### Step 3 — Check Linear
```
mcp__linear__list_issues  (team: Patientbilling — see current status of all PAT tickets)
mcp__linear__get_issue PAT-<N>  (for any In Progress or Todo ticket)
```

### Step 4 — Verify stack health
```bash
sg docker -c "docker compose -f deploy/docker_compose.yml ps"
```
Must show 5 containers: app (healthy :8000), celery, celery_beat, postgres (healthy), redis (healthy).
If any container is down: `sg docker -c "docker compose -f deploy/docker_compose.yml up -d"`.

---

## Per-Ticket Workflow (hardcoded — never skip any step)

After completing each Linear ticket, run all four steps in order:

```bash
# STEP 1 — Full test suite (unit + integration, inside Docker)
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/ integration/ -v --tb=short 2>&1'"
# Expected: all tests pass (2 AI tests skip without provider — that is correct)
# Never commit with failing tests.

# STEP 2 — Frontend build (always, even if no frontend changes)
cd /home/parakram/src/patientbilling/deploy/zango_project/workspaces/patientbilling/frontend
npm run build:zango
# If bundle hash changed: cp zango-build/zango-app.*.min.js ../static/js/
# and update the filename in backend/app/templates/app.html + run sync_static + collectstatic

# STEP 3 — Commit (specific files only, never git add -A, no Co-Authored-By lines)
git add <file1> <file2> ...
git commit -m "PAT-XX: <description>"

# STEP 4 — Push to GitHub
git push origin main
```

---

## Zango Docs Reference

| Topic | URL |
|-------|-----|
| Zango Docs (main) | https://docs.zango.dev |
| Models (DynamicModelBase, ZForeignKey) | https://docs.zango.dev/docs/core/models |
| Modules + policies | https://docs.zango.dev/docs/core/modules |
| CRUD views | https://docs.zango.dev/docs/packages/crud/views |
| CRUD tables | https://docs.zango.dev/docs/packages/crud/tables |
| CRUD forms | https://docs.zango.dev/docs/packages/crud/forms |
| Workflow package | https://docs.zango.dev/docs/packages/workflow/overview |
| Async tasks (Celery) | https://docs.zango.dev/docs/core/async-tasks |
| AI agents + tools | https://docs.zango.dev/docs/ai-agents |
| AppBuilder frontend | https://docs.zango.dev/docs/frontend/appbuilder |
| AppBuilder API config (routes/menus) | https://docs.zango.dev/docs/packages/appbuilder/api-configuration |
| Frontend CRUD components | https://docs.zango.dev/docs/frontend/crud |
| App Panel REST API | https://docs.zango.dev/docs/app-panel-api |
| Secrets / encrypted fields | https://docs.zango.dev/docs/core/secrets |
| App module (serve React SPA) | plugin skill: `references/templates/app-module/README.md` |

---

## Stack

```
billing-dev-app-1         Healthy  :8000    (Django + Zango)
billing-dev-celery-1      Started           (Celery worker)
billing-dev-celery_beat-1 Started           (Celery beat)
billing-dev-postgres-1    Healthy
billing-dev-redis-1       Healthy
```

Start/restart: `sg docker -c "docker compose -f deploy/docker_compose.yml up -d"`

| Resource | Value |
|---|---|
| Platform admin | http://localhost:8000/platform |
| Platform creds | `platform_admin@zango.dev` / `Zango@123` |
| App (React SPA) | http://patientbilling.localhost:8000/app |
| App UUID | `496d3013-cdd0-4531-92fd-3646714463c1` |
| Staff user | `staff@billing.local` / `Billing@123` (BillingStaff role) |
| Manager user | `manager@billing.local` / `Billing@123` (BillingManager role) |

---

## Project State (as of 2026-07-16)

### Done
- PAT-5 through PAT-27 — backend, AI agents, frontend, test suite
- PAT-28 — E2E tests, workflow transitions, role-gate tests, dashboard API

### Remaining
- **PAT-15**: Add Gemini provider (user action required — API key entered in UI only)
- **PAT-17 + PAT-18**: Sync tools + create prompts + agent records (blocked on PAT-15)

When ready to do PAT-15/17/18:
1. Open http://localhost:8000/platform → AI Providers → Add Provider → select Google Gemini → enter API key → save
2. Then run: `GEMINI_KEY="AIza..." bash deploy/scripts/setup_ai.sh`
3. Verify: `curl -s -b /tmp/zt_ai_setup "http://localhost:8000/api/v1/apps/496d3013-cdd0-4531-92fd-3646714463c1/ai/agents/" | python3 -m json.tool`
   Must return: `claim-validator`, `denial-analyzer`, `appeal-drafter`

### Test suite (current)
- 19 unit tests (no DB, sys.modules mock)
- 24 integration tests (CRUD, workflow transitions, role gates, dashboard)
- 2 AI integration tests (auto-skip without provider — activated by setup_ai.sh)
- **Total: 43 pass, 2 skip**

Run: `bash deploy/tests/run_tests.sh`

---

## Key Code Locations

| Area | Path |
|---|---|
| Backend modules | `deploy/zango_project/workspaces/patientbilling/backend/` |
| Claim workflow | `backend/claims/workflows.py` |
| Invoice workflow | `backend/invoices/workflows.py` |
| AI tasks | `backend/agents/tasks.py` |
| AI tools | `backend/agents/tools.py` |
| Dashboard API | `backend/app/views.py` (DashboardAPIView) |
| Frontend pages | `frontend/src/custom/pages/` |
| Built JS bundle | `static/js/zango-app.*.min.js` |
| Tests | `deploy/tests/` (unit/ + integration/) |
| Gemini provider | `deploy/providers/gemini.py` |
| AI setup script | `deploy/scripts/setup_ai.sh` |
| App UUID constant | `deploy/tests/integration/constants.py` |

---

## Zango Critical Rules (must follow in all module code)

```python
# Models — ALWAYS DynamicModelBase, NEVER models.Model
from zango.apps.dynamic_models.models import DynamicModelBase
class MyModel(DynamicModelBase): ...

# FKs — ALWAYS ZForeignKey, NEVER ForeignKey or string ref
from zango.apps.dynamic_models.fields import ZForeignKey
patient = ZForeignKey(Patient, null=True, on_delete=models.SET_NULL)

# NO class Meta, NO ManyToManyField on models

# Migrations — ALWAYS ws_makemigration / ws_migrate, NEVER django makemigrations
# docker exec into app container, then:
cd /zango/zango_project
python manage.py ws_makemigration <module_name>
python manage.py ws_migrate <module_name>

# Celery dispatch — always zango_task_executor
from zango.core.tasks import zango_task_executor
zango_task_executor.delay(connection.tenant.name, "backend.agents.tasks.run_claim_validator", claim_id=str(claim.id))

# Policies — must be dict with "policies" key, permissions use dot path to view class
{"policies": [{"name": "...", "statement": {"permissions": [{"name": "backend.module.views.MyView", "type": "view"}]}, "roles": ["BillingStaff"]}]}

# Imports — relative only, count dots from app root
from .models import MyModel           # same module
from ..other.models import Other      # sibling module
from ...packages.crud.forms import BaseForm  # packages (3 dots)

# Workflow Meta — ALWAYS include model = <ModelClass> so transitions can resolve the instance
class Meta:
    model = Claim  # required — workflow engine uses this to look up the object by UUID
    on_create_status = "draft"
    statuses = {...}

# Sync after any policy/task change
curl -s -b /tmp/zango_cookies -X POST \
  "http://localhost:8000/api/v1/apps/$APP_UUID/policies/?action=sync_policies" \
  -H "X-CSRFToken: $CSRF" -H "Referer: http://localhost:8000/platform/"
```

---

## Architecture: Why This Project Matters

This is an AI-agent-first billing platform built on Zango for Zelthy. The primary technical differentiator is **concurrent multi-agent dispatch**:

1. When a claim is **submitted** → `ClaimValidator` fires (completeness check, code suggestions)
2. When a claim is **denied** → `DenialAnalyzer` AND `AppealDrafter` fire **simultaneously** as independent Celery tasks
   - This is two `zango_task_executor.delay()` calls in `deny_done()` — not sequential
   - Both results land on the Claim model: `ai_denial_analysis` (JSON) + `ai_appeal_draft` (text)
3. Frontend AI Insights tab polls every 5s, stops when all three AI fields are non-null

The concurrent architecture avoids sequential latency — engineers reviewing this should see both analysis + draft appear within seconds of each other after a denial.

---

## Platform Admin Auth Snippet (reuse in scripts)

```bash
CSRF=$(curl -s -c /tmp/zt http://localhost:8000/auth/login/ \
  | grep -o 'csrfmiddlewaretoken" value="[^"]*"' \
  | grep -o 'value="[^"]*"' | cut -d'"' -f2)
curl -s -c /tmp/zt -b /tmp/zt -X POST http://localhost:8000/auth/login/ \
  -H "X-CSRFToken: $CSRF" -H "Referer: http://localhost:8000/auth/login/" \
  -F "username=platform_admin@zango.dev" -F "password=Zango@123" \
  -F "csrfmiddlewaretoken=$CSRF" -o /dev/null
CSRF2=$(grep csrftoken /tmp/zt | awk '{print $NF}')
APP_UUID="496d3013-cdd0-4531-92fd-3646714463c1"
```

---

## Frontend Rebuild (after changes to frontend/src/)

```bash
cd deploy/zango_project/workspaces/patientbilling/frontend
npm run build:zango
cp zango-build/zango-app.*.min.js ../static/js/
# Update filename in backend/app/templates/app.html if hash changed

sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/zango_project && python manage.py sync_static patientbilling && python manage.py collectstatic --noinput'"
```
