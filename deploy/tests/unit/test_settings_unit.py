from pathlib import Path


SETTINGS_FILE = (
    Path(__file__).parents[2] / "zango_project" / "zango_project" / "settings.py"
)


def test_production_settings_disable_debug():
    source = SETTINGS_FILE.read_text(encoding="utf-8")

    assert (
        'DEBUG = os.environ.get("ENV", "dev").lower() not in {"prod", "staging"}'
        in source
    )


def test_csrf_trusted_origins_reads_comma_separated_environment_value():
    source = SETTINGS_FILE.read_text(encoding="utf-8")

    assert '"CSRF_TRUSTED_ORIGINS", "http://localhost:3000"' in source
    assert ".split(\",\")" in source
    assert "origin.strip()" in source


def test_csrf_trusted_origins_keeps_localhost_fallback():
    source = SETTINGS_FILE.read_text(encoding="utf-8")

    assert '"http://localhost:3000"' in source
