import os
import subprocess
from pathlib import Path


SCRIPTS = (
    Path(__file__).parents[2] / "scripts" / "bootstrap_demo.sh",
    Path(__file__).parents[2] / "scripts" / "setup_ai.sh",
)
SCRIPT = SCRIPTS[0]


def test_bootstrap_demo_contains_idempotent_zero_key_flow():
    source = SCRIPT.read_text(encoding="utf-8")

    for expected in (
        "api/v1/apps/$APP_UUID/packages/",
        "action=config_url",
        "action=sync_policies",
        "BillingStaff",
        "BillingManager",
        "ws_migrate",
        "Package migrations did not create required tables",
        "--fake dynamic_models 0004_workflowfile_workflowtransaction_and_more",
        "action=get_routes",
        "action=save_routes",
        "action=get_configs",
        "action=create_config",
        '"name":"Dashboard"',
        '"name":"Insurance Payers"',
        "staff@billing.local",
        "manager@billing.local",
        "LOCAL_FAKE_AI=true bash",
    ):
        assert expected in source

    assert '"name": "claim-validator"' not in source
    assert "setup_ai.sh" in source


def test_compose_sg_fallback_preserves_container_command_arguments(tmp_path):
    """Exercise the fallback, including the nested bash -lc payload."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    container_marker = tmp_path / "container.marker"
    host_marker = tmp_path / "host.marker"
    expected_payload = "cd /zango && zango start-project demo --flag='value with spaces'"

    (fake_bin / "docker").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == info ]]; then
  exit 1
fi
[[ "${1:-}" == compose ]] || exit 2
shift
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[i]}" == bash && "${args[i + 1]:-}" == -lc ]]; then
    [[ "${args[i + 2]:-}" == "$EXPECTED_PAYLOAD" ]] || exit 3
    EXECUTION_SIDE=container "$FAKE_ZANGO" start-project
    exit 0
  fi
done
exit 4
"""
    )
    (fake_bin / "sg").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == docker && "${2:-}" == -c ]] || exit 2
bash -c "$3"
"""
    )
    (fake_bin / "zango").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${EXECUTION_SIDE:-host}" == container ]]; then
  : > "$CONTAINER_MARKER"
else
  : > "$HOST_MARKER"
fi
"""
    )
    for executable in ("docker", "sg", "zango"):
        (fake_bin / executable).chmod(0o755)

    for script in SCRIPTS:
        function = script.read_text(encoding="utf-8").split("compose() {\n", 1)[1].split(
            "\n}\n", 1
        )[0]
        harness = tmp_path / f"{script.stem}.sh"
        harness.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
COMPOSE_FILE=/tmp/docker-compose.yml
compose() {{
{function}
}}
compose exec -T app bash -lc "{expected_payload}"
"""
        )
        harness.chmod(0o755)
        environment = os.environ | {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "EXPECTED_PAYLOAD": expected_payload,
            "FAKE_ZANGO": str(fake_bin / "zango"),
            "CONTAINER_MARKER": str(container_marker),
            "HOST_MARKER": str(host_marker),
        }
        result = subprocess.run(
            ["bash", str(harness)], env=environment, text=True, capture_output=True
        )
        assert result.returncode == 0, result.stderr
        assert container_marker.exists(), result.stderr
        assert not host_marker.exists(), result.stderr
        container_marker.unlink()
