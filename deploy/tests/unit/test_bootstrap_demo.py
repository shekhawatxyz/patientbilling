from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "bootstrap_demo.sh"


def test_bootstrap_demo_contains_idempotent_zero_key_flow():
    source = SCRIPT.read_text(encoding="utf-8")

    for expected in (
        "api/v1/apps/$APP_UUID/packages/",
        "action=config_url",
        "action=sync_policies",
        "BillingStaff",
        "BillingManager",
        "ws_migrate",
        "action=get_routes",
        "action=save_routes",
        "action=get_configs",
        "action=create_config",
        '"name": "Dashboard"',
        '"name": "Insurance Payers"',
        "staff@billing.local",
        "manager@billing.local",
        "LOCAL_FAKE_AI=true bash",
    ):
        assert expected in source

    assert '"name": "claim-validator"' not in source
    assert "setup_ai.sh" in source
