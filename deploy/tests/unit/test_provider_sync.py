from pathlib import Path


DEPLOY_DIR = Path(__file__).parents[2]


def test_provider_sync_is_shared_by_all_container_startup_paths():
    init_script = (DEPLOY_DIR / "init.sh").read_text()
    dockerfile = (DEPLOY_DIR / "Dockerfile").read_text()

    assert "/zango/scripts/sync_providers.sh" in init_script
    assert "COPY scripts/sync_providers.sh /zango/scripts/sync_providers.sh" in dockerfile

    for compose_name in ("docker_compose.yml", "docker_compose.prod.yml"):
        compose = (DEPLOY_DIR / compose_name).read_text()
        assert "command: /bin/sh -c \"/zango/scripts/sync_providers.sh && cd" in compose
        assert compose.count("/zango/scripts/sync_providers.sh") == 2


def test_provider_sync_copies_and_registers_every_custom_provider():
    sync_script = (DEPLOY_DIR / "scripts" / "sync_providers.sh").read_text()

    assert "/zango/providers/*.py" in sync_script
    assert 'cp "$provider_file" "$destination"' in sync_script
    assert 'from . import %s' in sync_script
