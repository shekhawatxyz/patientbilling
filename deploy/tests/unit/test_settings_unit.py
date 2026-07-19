from pathlib import Path


SETTINGS_FILE = (
    Path(__file__).parents[2] / "zango_project" / "zango_project" / "settings.py"
)


def test_production_settings_disable_debug():
    source = SETTINGS_FILE.read_text(encoding="utf-8")

    assert "DEBUG = os.environ.get(\"ENV\", \"dev\").lower() not in {\"prod\", \"staging\"}" in source
