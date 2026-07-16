# Skill: patientbilling-ticket-worker

Procedure for implementing one Linear ticket on the Patient Billing System.
No domain knowledge here — that lives in AGENTS.md and CONTEXT.md.

## Step-by-Step Procedure

### 1. Load context (required before any code action)
- Read `/AGENTS.md` in full.
- Read `/CONTEXT.md` in full.
- Do not read other files yet.

### 2. Fetch the ticket
- Call `mcp__linear__get_issue` with the assigned PAT-XX identifier.
- Read the description in full. Note the exact files, functions, tests, and acceptance criteria.

### 3. Inspect only named files
- Open only the files the ticket explicitly names.
- Open only the test files the ticket explicitly names.
- Do not read adjacent modules, unrelated tests, or historical tickets.

### 4. Identify the test seam
- The ticket names which seam is being tested (workflow HTTP, task entry, tool schema, CRUD/form, or real provider).
- Confirm the test seam before writing any code.

### 5. Write the failing test first (red)
- Add or update the tests the ticket specifies.
- Run focused tests and confirm they fail for the expected reason.
- If tests already pass without a code change, stop and report — the code may already implement the behavior or the test may be wrong.

### 6. Make the minimal change (green)
- Change only the files the ticket names.
- Do not fix unrelated issues, refactor, or expand scope.

### 7. Verify green
```bash
# Focused tests:
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/<test_file.py> -v --tb=short 2>&1'"

# Full suite:
sg docker -c "docker compose -f deploy/docker_compose.yml exec -T app bash -c \
  'cd /zango/tests && python -m pytest unit/ integration/ -v --tb=short 2>&1'"
```
Expected: all tests pass; 2 AI tests skip (correct without a configured provider).

### 8. Commit and push
```bash
git add <only the files changed>
git commit -m "PAT-XX: <description>"
git push origin main
```
- Never `git add -A` or `git add .`
- Never include Co-Authored-By lines for Claude
- Never commit `*.min.js` bundles, `node_modules/`, or secret/API key files

### 9. Report acceptance evidence
State: which tests were red, which are now green, what the full suite result is.

---

## Stop Conditions

Stop immediately and report if:
- The ticket instruction conflicts with CONTEXT.md or an ADR.
- The required test seam does not exist (may need a prior ticket first).
- A migration is required — run `ws_makemigration` and `ws_migrate`, not Django's tools.
- The test suite shows failures unrelated to this ticket.
- You are unsure which file to change — read CONTEXT.md again before expanding search.
