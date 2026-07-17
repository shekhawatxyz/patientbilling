# AI testing policy

Normal development and CI tests never need an API key and never intentionally
call an external model provider. The offline provider is never selected by
omission: `LOCAL_FAKE_AI=true` must be explicit.

## Three testing brackets

### Unit

Fast tests mock the `agent.run`/tool-call boundary directly in pytest. Use
these for tool logic, task wiring, and ContextVar handling.

### Plumbing (the standard)

`local_fake` is a deterministic provider registered through Zango's
`BaseLLMProvider` extension point. Its outputs are hardcoded and schema-valid:

- validator: `valid=true`, empty issues, completeness score `100`;
- denial analyzer: a fixed `other`-category analysis;
- appeal drafter: a fixed short appeal letter.

The provider still returns tool calls through the normal AgentClient loop. The
tests therefore cover agent registration, tenant-aware task execution, bound
ContextVars, tool execution, and Claim persistence without model inference.

Activate it explicitly, then run the normal AI integration test with:

```bash
LOCAL_FAKE_AI=true bash deploy/scripts/setup_ai.sh
cd deploy/tests && python -m pytest integration/test_ai.py -v --tb=short
```

This exercises agent registration, tenant-aware Celery task execution, bound
ContextVars, tool execution, and Claim persistence through the real loop.
`setup_ai.sh` saves the three agents' real provider wiring before repointing
them. After the plumbing session, restore it with:

```bash
LOCAL_FAKE_AI=restore bash deploy/scripts/setup_ai.sh
```

The state file is `deploy/.ai_provider_state.json` and is gitignored. Do not
delete it until the shared app has been restored.

## Final live smoke test

Only run this after all offline tests pass and only when a real provider has
been intentionally configured in the App Panel:

```bash
AI_LIVE_SMOKE=1 AI_PROVIDER_CONFIGURED=1 \
  python -m pytest deploy/tests/integration/test_ai.py -v --tb=short
```

This command is never part of the normal suite. Do not put API keys in source,
shell history, CI logs, or committed files. Provider-side token and spend
limits are secondary safeguards; they do not replace explicit offline opt-in.
