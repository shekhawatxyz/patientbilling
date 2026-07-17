# Patient Billing System

Zango take-home prototype demonstrating a concurrent insurance-claim lifecycle with three independent AI agents.

## Architecture

Claims move through a workflow-driven lifecycle:

```text
Draft -> Submitted -> Under Review -> Approved -> Closed
                         |
                         v
                       Denied -> Appealed -> Closed
```

- Submitting a claim dispatches the `claim-validator` agent.
- Denying a claim dispatches `denial-analyzer` and `appeal-drafter` as two independent Celery tasks.
- The denial agents are deliberately not chained. They run on separate workers and may finish in either order.
- Agent tools read server-bound claim context and atomically write each agent's owned Claim output field.

## Stack

| Layer | Technology |
|---|---|
| Application framework | Zango / Django |
| Frontend | React |
| Background jobs | Celery |
| Database | PostgreSQL |
| Broker | Redis |

## Prerequisites

- Docker and Docker Compose
- An `/etc/hosts` entry for `patientbilling.localhost`:

  ```text
  127.0.0.1 patientbilling.localhost
  ```

## Quick start

From a fresh clone:

```bash
cd patientbilling
cp deploy/.env.example deploy/.env
sg docker -c "docker compose -f deploy/docker_compose.yml up -d"
```

Open the app at <http://patientbilling.localhost:8000/app>.

The platform admin panel is at <http://localhost:8000/platform>.

## Test credentials

| User | Password | Role |
|---|---|---|
| `staff@billing.local` | `Billing@123` | BillingStaff |
| `manager@billing.local` | `Billing@123` | BillingManager |

Platform admin: `platform_admin@zango.dev` / `Zango@123`.

## AI setup and testing

Normal tests use the deterministic `local_fake` provider and do not need an API key:

```bash
bash deploy/scripts/setup_ai.sh
bash deploy/tests/run_ai_tests.sh
```

The fake provider returns hardcoded, schema-valid outputs while exercising the same agent registration, task, tool, ContextVar, and Claim persistence plumbing. The full suite is safe to run without provider credentials:

```bash
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/ integration/ -v --tb=short 2>&1'"
```

Real-provider testing is a separate, final smoke test only. Store the key in the local App Panel configuration; never commit or print it. For Anthropic setup:

```bash
ANTHROPIC_KEY="sk-ant-..." bash deploy/scripts/setup_ai.sh
AI_LIVE_SMOKE=1 AI_PROVIDER_CONFIGURED=1 bash deploy/tests/run_ai_live_smoke.sh
```

Do not run the live smoke command as part of normal development or CI.

## Demo walkthrough

1. Sign in as `staff@billing.local`.
2. Create a patient with insurance details.
3. Create a payer and a claim with diagnosis codes and a total amount.
4. Submit the claim and observe the validator output in AI Insights.
5. Sign in as `manager@billing.local`.
6. Deny a claim with a denial reason.
7. Observe denial analysis and the appeal draft populate independently.
8. Appeal the claim and complete the workflow.

[SCREENSHOT: Claims list showing a submitted claim]

[SCREENSHOT: AI Insights showing validator output]

[SCREENSHOT: AI Insights showing denial analysis and appeal draft]

## Known limitations and future work

- No audit trail
- No HIPAA encryption at rest
- No EDI 837/835 exchange
- No real-time insurance eligibility verification
- No automatic agent retry on failure
- No role-based field masking
- No multi-practice tenancy
- No reverse proxy or TLS termination in the development stack

## Production Deployment

The production Compose file is a starting point, not a complete production deployment.

```bash
cp deploy/.env.prod.example deploy/.env.prod
# Edit deploy/.env.prod and fill in real secrets and hostnames.
docker compose --env-file deploy/.env.prod -f deploy/docker_compose.prod.yml up -d
```

On the first deployment, run the Zango migration command inside the app container:

```bash
docker compose --env-file deploy/.env.prod -f deploy/docker_compose.prod.yml \
  exec app bash -c 'cd /zango/zango_project && python manage.py ws_migrate'
```

Do not use Django's standalone `migrate` command. This scaffold does not include a reverse proxy or TLS termination, wildcard DNS for Zango's subdomain-based multi-tenant routing, or a PostgreSQL backup strategy. A real self-hosted deployment must add those separately.

## Project structure

```text
deploy/
├── docker_compose.yml
├── scripts/setup_ai.sh
├── tests/
└── zango_project/workspaces/patientbilling/
    ├── backend/
    │   ├── agents/
    │   ├── claims/
    │   ├── invoices/
    │   ├── patients/
    │   └── payers/
    └── frontend/
```

Backend modules contain the domain models, CRUD views, workflow transitions, and agent tasks. The React frontend contains the app shell and custom patient-billing pages.
