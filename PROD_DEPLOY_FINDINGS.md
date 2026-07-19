# Production Deploy Findings — AWS Lightsail, 2026-07-19

Found while doing the first live deploy to `https://patientbilling.shekhawat.site` (AWS Lightsail,
Ubuntu 22.04). Each of these is a real bug in this repo's prod deploy path, currently only
worked around live on the running instance (not committed). Filing as tickets below.

---

## 1. `DEBUG = True` in production settings

**File:** `deploy/zango_project/zango_project/settings.py`

Prod is running with Django's debug page active — a bare 404 on `/` dumps the full URLconf,
file paths, and a "you have DEBUG=True" notice to any visitor. Security exposure, not just
cosmetic (stack traces on any unhandled exception would also leak internals).

**Fix:** `DEBUG` should be `False` whenever `ENV=prod`/`staging`, driven from settings rather than
left at its development default. Confirm `ALLOWED_HOSTS` is still permissive enough once DEBUG
flips (Django's own 400 "DisallowedHost" page is also verbose in DEBUG mode but generic without
it — verify the intended errors are still legible in a real incident).

## 2. `CSRF_TRUSTED_ORIGINS` is hardcoded, ignores the env var

**File:** `deploy/zango_project/zango_project/settings.py:40`

```python
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]
```

`deploy/.env.prod` / `.env.prod.example` both define `CSRF_TRUSTED_ORIGINS`, but nothing in
`settings.py` reads it — the value is silently ignored. Every prod domain will need this line
hand-edited (or worse, silently rejected) unless this is fixed. Confirmed by the live symptom:
platform login POSTs 403'd with `Forbidden (Origin checking failed - https://<domain> does not
match any trusted origins.)` until this line was patched live on the box.

**Fix:** read from `os.environ["CSRF_TRUSTED_ORIGINS"]` (comma-separated) the same way other prod
settings do, falling back to the current dev default for local use.

## 3. `INTERNAL_IPS` is never actually assigned — platform admin is unreachable in prod, from anywhere

**File:** `deploy/zango_project/zango_project/settings.py:42-43`

There's a comment describing `INTERNAL_IPS` but no actual assignment anywhere in the codebase.
Django's own default is an empty list. `zango/core/decorators.py::internal_access_only` — which
gates `/platform/` and `/auth/login/` whenever `settings.ENV in ["staging", "prod"]` — checks the
client IP against `settings.INTERNAL_IPS`. With an empty list, **every** request from **every** IP
is rejected with `PermissionDenied`, unconditionally, in prod. There is no way to reach the
platform admin panel in production as this repo currently ships, regardless of who's asking or
from where.

This is not "IP allowlisting working as designed" — it's a config value that was never wired up,
making the feature it's supposed to gate (admin access) completely absent instead of restricted.

**Live workaround used (not committed):** manually added the deploying admin's static IP and the
Docker bridge subnet to `INTERNAL_IPS` directly in `settings.py` on the box, restarted the app
container, completed one-time bootstrap over HTTP, left the IP in place for now.

**Fix:** populate `INTERNAL_IPS` from an env var (e.g. `PLATFORM_ADMIN_ALLOWED_IPS`, comma
separated, supporting CIDR), document that it must be set for `ENV=prod`/`staging`, and fail
loudly (not silently allow-nothing) if it's unset in those environments — an empty allowlist that
means "block everyone forever" is a footgun; better to raise at startup so this is caught in code
review, not discovered live during a deploy.

## 4. `init.sh` sources `/zango/.env`, but prod compose only ships `.env.prod`

**File:** `deploy/init.sh:6`, `deploy/docker_compose.prod.yml`

```sh
set -a
. /zango/.env
set +a
```

The prod compose file's `env_file:` directive points at `.env.prod` for every service, but
`init.sh` (which the `app`/`celery`/`celery_beat` containers all run) hardcodes sourcing
`/zango/.env`. Since `volumes: - .:/zango/` bind-mounts `deploy/` into the container, this works
if and only if a literal file named `deploy/.env` also exists — which nothing in the prod path
creates. Fresh prod containers crash-loop with `init.sh: 6: .: cannot open /zango/.env: No such
file` until this file is manually created.

**Live workaround used (not committed):** `cp deploy/.env.prod deploy/.env` on the box (both
gitignored, no secrets committed).

**Fix:** either have `init.sh` source `.env.prod` directly when `ENV=prod` (matching whichever env
file the compose file actually declared), or have the prod runbook/compose explicitly produce a
plain `.env` from `.env.prod` as a documented first step. Prefer the former — one source of truth
for "which env file are we actually running with" avoids this class of drift entirely.

## 5. Platform admin user creation is gated on first-ever tenant creation — unrecoverable if that run aborts partway

**File:** `zango/cli/start_project.py` (installed package, not this repo — but the failure mode
is directly caused by how this repo's `init.sh` invokes it)

```python
created = create_public_tenant(platform_domain_url=platform_domain_url)
if created:
    # ...create_platform_user(...) only happens here...
```

`create_platform_user` only runs if `create_public_tenant` reports it just created the `public`
tenant for the first time. If the very first `zango start-project` run gets partway through
(schema migrated, `public` tenant row created) and then aborts — e.g. because of bug #2/#3 above,
or any other mid-flight failure — every subsequent retry sees `public` already exists, reports
"skipping creation", and **never creates the admin user**, silently. There's no error, no
idempotent recovery path, and no obvious symptom until you try to log in and every credential is
rejected by axes as a genuine auth failure (looks exactly like a wrong password, not like "the
user was never created").

**Live workaround used (not committed):** called
`zango.cli.start_project.create_platform_user(username, password)` directly via `manage.py shell`.

**Fix:** make `create_platform_user`'s idempotency check independent of the tenant-creation check
— i.e. always attempt user creation (it already internally checks
`PlatformUserModel.objects.filter(email=...).exists()` and no-ops safely), regardless of whether
`create_public_tenant` returned `True` or `False`. This one-line change (removing the `if created:`
gate, or gating on "does the platform user already exist" instead) makes a partial-failure retry
actually self-heal instead of silently wedging.

## 6. No supported way to register an app/workspace whose code already exists on disk

**File:** `zango/apps/shared/tenancy/tasks.py::initialize_workspace` (installed package)

The public `POST /api/v1/apps/` API always takes the cookiecutter/greenfield path
(`initialize_workspace(tenant_uuid, app_template_path=None, ...)`), which fails with
`cookiecutter.exceptions.OutputDirExistsException` whenever the target workspace directory already
exists — which is **always true for this repo**, since `workspaces/patientbilling/` is checked
into git and present in every fresh clone/deploy. There is no documented, API-exposed way to say
"the code is already here, just create the DB-side tenant/schema/domain records for it."

**Live workaround used (not committed):** called `initialize_workspace()` directly via
`manage.py shell`, passing a **temporary copy** of the workspace dir as `app_template_path` (never
the real `workspaces/patientbilling` path — that branch calls `shutil.rmtree(app_template_path)`
at the end, which would delete the real, committed workspace code if pointed at it directly).

**Fix:** this is upstream Zango framework behavior, not something this repo can fix directly —
worth raising with Zango/Zelthy as a framework gap (a deploy runbook needs a "register existing
workspace" path that skips file generation entirely, since redeploying already-shipped code is a
completely normal case, not an edge case). Short-term, document the temp-copy workaround in this
repo's own deploy runbook so the next person doesn't have to rediscover it live.

## 7. Undocumented platform-user password complexity rule (and it differs from the app-user rule)

**File:** `zango/apps/shared/platformauth/models.py::validate_password` (installed package)

```python
reg = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!#%*?&]{8,18}$"
```

Platform-user (not app-user — that's a separate, tenant-configurable policy) passwords must be
**8-18 characters** (note the max!) and may only use `@$!#%*?&` as special characters. Nothing in
`.env.prod.example` or any doc mentions this. A naively generated random password (e.g. via
`openssl rand -base64 N`) will often fail this silently until you read the Zango source directly.

**Fix:** document this regex (or at least "8-18 chars, needs upper/lower/digit/one of `@$!#%*?&`")
directly next to `PLATFORM_USER_PASSWORD` in `.env.prod.example`, so whoever runs the deploy
generates a compliant value up front instead of discovering the rule via a failed API call.

## 8. One domain = one tenant; `PLATFORM_DOMAIN_URL` silently claims the prod domain for `public`

**File:** `zango/apps/shared/tenancy/models.py::Domain` (installed package, `DomainMixin`'s unique
constraint on `domain`), interacting with this repo's `deploy/init.sh`/runbook

`PLATFORM_DOMAIN_URL` (passed to `zango start-project`) registers that domain against the `public`
tenant via `create_public_tenant`. For a deploy with only one real domain (the common case for a
small/demo deploy — one A record, one TLS cert), that domain is now bound to `public`, and
`/api/v1/apps/` (needed to create the app-level tenant/domain/policies) is only resolvable via a
domain that maps to `public`. Once the app's own tenant is created, the *same* domain needs to be
re-pointed from `public` to the app tenant (`tenancy_domain_domain_key` is a hard unique
constraint — a domain cannot map to both at once), at which point the App Panel/platform API
becomes unreachable again over HTTP (by design — see bug #3 also gating this at the IP layer).

DEPLOY_HANDOFF.md already flagged "register the production domain as a tenant domain" as an
easy-to-miss step; this finding is more specific: **for a single-domain deploy, platform-API access
and the live app are mutually exclusive over HTTP on that domain**, and every one-time
platform-API operation (policy sync, role/user creation) has to happen either before the domain is
re-pointed to the app tenant, or via a second internal-only domain / direct ORM calls thereafter.

**Fix:** document this explicitly in the deploy runbook: either (a) provision two subdomains up
front (e.g. `admin.<domain>` → `public`, `<domain>` → app tenant) so platform access remains
available post-deploy, or (b) explicitly note that post-bootstrap platform operations must go
through direct Django shell/ORM access, not the HTTP API, once the domain has been re-pointed.

---

## Not yet fixed / still open after this deploy

- **1GB Lightsail instance live-locked** (not OOM-killed — `nc` showed open sockets with no
  application response, `sshd` itself unresponsive) running the full stack
  (Postgres+Redis+Django+2×Celery+Caddy) simultaneously. Currently mitigated by dropping
  `celery_beat` from the running set and capping `celery --concurrency` to 1 (both live edits to
  `docker_compose.prod.yml`, not yet reconciled with the committed version). The account's 2GB
  Lightsail-plan upgrade is currently blocked by an AWS new-account anti-fraud throttle
  (`"your account cannot create an instance using this Lightsail plan size"`) — expected to clear
  within 24-48h of account history. Once it clears, re-provision at 2GB (the runbook's own stated
  floor) and restore `celery_beat` + `--concurrency=2`.
- Frontend build (`vite build`) OOM-kills without a swapfile even on the 1GB instance during the
  build step alone (separate from the live-lock above, and confirmed via `dmesg`) — a swapfile is
  a reasonable permanent mitigation for the build step regardless of final instance size.
