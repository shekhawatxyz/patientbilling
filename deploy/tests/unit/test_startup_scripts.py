import os
import shutil
import subprocess
from pathlib import Path


DEPLOY_DIR = Path(__file__).parents[2]
INIT_SCRIPT = DEPLOY_DIR / "init.sh"
START_SCRIPT = DEPLOY_DIR / "scripts" / "start_demo.sh"
SETUP_AI_SCRIPT = DEPLOY_DIR / "scripts" / "setup_ai.sh"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def test_init_always_initializes_database_before_update_and_runserver(tmp_path):
    fake_root = tmp_path / "zango"
    project = fake_root / "zango_project"
    (project / "zango_project").mkdir(parents=True)
    (fake_root / "scripts").mkdir()
    (fake_root / ".env").write_text(
        """PROJECT_NAME=zango_project
POSTGRES_DB=zango
POSTGRES_USER=zango
POSTGRES_PASSWORD=zango
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
REDIS_HOST=redis
REDIS_PORT=6379
PLATFORM_USERNAME=admin@example.test
PLATFORM_USER_PASSWORD=local-password
UPDATE_APPS_ON_STARTUP=true
""",
        encoding="utf-8",
    )
    trace = tmp_path / "trace"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "zango",
        '#!/usr/bin/env bash\necho "zango $*" >> "$TRACE_FILE"\n',
    )
    _write_executable(
        fake_bin / "single-beat",
        '#!/usr/bin/env bash\necho "single-beat $*" >> "$TRACE_FILE"\n',
    )
    _write_executable(
        fake_bin / "python",
        '#!/usr/bin/env bash\necho "python $*" >> "$TRACE_FILE"\n',
    )
    _write_executable(
        fake_root / "scripts" / "sync_providers.sh",
        '#!/usr/bin/env bash\necho sync-providers >> "$TRACE_FILE"\n',
    )
    harness = tmp_path / "init.sh"
    harness.write_text(
        INIT_SCRIPT.read_text(encoding="utf-8").replace("/zango", str(fake_root)),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["sh", str(harness)],
        cwd=fake_root,
        env=os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "TRACE_FILE": str(trace)},
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    events = trace.read_text(encoding="utf-8").splitlines()
    start = next(i for i, event in enumerate(events) if "zango start-project" in event)
    update = next(i for i, event in enumerate(events) if "zango update-apps" in event)
    workflow_migrate = next(
        i for i, event in enumerate(events)
        if "manage.py ws_migrate patientbilling --package workflow" in event
    )
    appbuilder_migrate = next(
        i for i, event in enumerate(events)
        if "manage.py ws_migrate patientbilling --package appbuilder" in event
    )
    runserver = next(i for i, event in enumerate(events) if "manage.py runserver" in event)
    assert start < update < workflow_migrate < appbuilder_migrate < runserver, events


def test_real_provider_secret_never_reaches_output_or_process_arguments(tmp_path):
    sentinel = "sentinel-" + "anthropic-key-never-leak"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    argument_log = tmp_path / "arguments"
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
if [[ "${1:-}" == info ]]; then exit 0; fi
exit 0
""",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
printf '%q ' "$@" >> "$ARGUMENT_LOG"
printf '\n' >> "$ARGUMENT_LOG"
cookie=''
previous=''
for argument in "$@"; do
  if [[ "$previous" == '-c' ]]; then cookie="$argument"; fi
  previous="$argument"
done
if [[ -n "$cookie" ]]; then printf 'localhost FALSE / FALSE 0 csrftoken test-csrf\n' > "$cookie"; fi
args=" $* "
if [[ "$args" == *'/auth/login/'* && "$args" != *' -X POST '* ]]; then
  printf '<input name="csrfmiddlewaretoken" value="login-csrf">\n'
elif [[ "$args" == *'/ai/providers/'* && "$args" == *' -X POST '* ]]; then
  printf '{"response":{"id":1,"config":{"api_key":"%s"}}}\n' "$SENTINEL"
elif [[ "$args" == *'/ai/providers/'* ]]; then
  printf '{"response":{"providers":{"records":[]}}}\n'
elif [[ "$args" == *'/ai/prompts/'* ]]; then
  printf '{"response":{"prompts":{"records":[]}},"names":"claim-validator-prompt denial-analyzer-prompt appeal-drafter-prompt"}\n'
elif [[ "$args" == *'/ai/agents/'* ]]; then
  if [[ "$args" == *' -X PUT '* ]]; then
    printf '{}\n'
  else
    printf '{"response":{"agents":{"records":[{"id":101,"name":"claim-validator"},{"id":102,"name":"denial-analyzer"},{"id":103,"name":"appeal-drafter"}]}}}\n'
  fi
else
  printf '{}\n'
fi
""",
    )
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "ANTHROPIC_KEY": sentinel,
        "ARGUMENT_LOG": str(argument_log),
        "SENTINEL": sentinel,
    }

    result = subprocess.run(
        ["bash", str(SETUP_AI_SCRIPT)],
        env=environment,
        text=True,
        capture_output=True,
    )

    captured = result.stdout + result.stderr + argument_log.read_text(encoding="utf-8")
    assert result.returncode == 0, captured
    assert sentinel not in captured
    assert captured.count("-X PUT") == 3, captured


def test_offline_startup_does_not_read_or_expose_real_provider_key(tmp_path):
    sentinel = "sentinel-" + "offline-key-never-leak"
    repo = tmp_path / "repo"
    scripts = repo / "deploy" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(START_SCRIPT, scripts / "start_demo.sh")
    shutil.copy2(DEPLOY_DIR / ".env.example", repo / "deploy" / ".env.example")
    shutil.copy2(DEPLOY_DIR / "docker_compose.yml", repo / "deploy" / "docker_compose.yml")
    (repo / "deploy" / ".env").write_text(f"ANTHROPIC_KEY={sentinel}\n", encoding="utf-8")
    trace = tmp_path / "arguments"
    trace.write_text("", encoding="utf-8")
    _write_executable(scripts / "build_frontend.sh", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        scripts / "bootstrap_demo.sh",
        '#!/usr/bin/env bash\nprintf "%s\\n" "${LOCAL_FAKE_AI:-}" >> "$TRACE_FILE"\n',
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
printf '%q ' "$@" >> "$TRACE_FILE"; printf '\n' >> "$TRACE_FILE"
if [[ "${1:-}" == info ]]; then exit 0; fi
if [[ " $* " == *' ps -q '* ]]; then printf 'fake-container\n'; fi
if [[ "${1:-}" == inspect && "$*" == *'.State.Status'* ]]; then printf 'running\n'; fi
if [[ "${1:-}" == inspect && "$*" == *'.State.Health'* ]]; then printf 'healthy\n'; fi
exit 0
""",
    )
    _write_executable(
        fake_bin / "node",
        """#!/usr/bin/env bash
if [[ "${1:-}" == '-p' ]]; then printf '18\n'; fi
exit 0
""",
    )
    for name in ("npm", "curl"):
        _write_executable(fake_bin / name, "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_bin / "getent",
        "#!/usr/bin/env bash\nprintf '127.0.0.1 STREAM patientbilling.localhost\\n'\n",
    )
    _write_executable(
        fake_bin / "sleep",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "TRACE_FILE": str(trace),
    }

    result = subprocess.run(
        ["bash", str(scripts / "start_demo.sh")],
        env=environment,
        text=True,
        capture_output=True,
    )

    captured = result.stdout + result.stderr + trace.read_text(encoding="utf-8")
    assert result.returncode == 0, captured
    assert sentinel not in captured
    assert "true" in trace.read_text(encoding="utf-8").splitlines()
    for generated_path in repo.rglob("*"):
        if generated_path.is_file() and generated_path.name != ".env":
            assert sentinel not in generated_path.read_text(encoding="utf-8")
