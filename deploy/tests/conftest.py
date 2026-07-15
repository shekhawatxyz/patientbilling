"""Root conftest — runs before any test is collected."""
import sys
from pathlib import Path

# Make integration/constants.py importable from test_*.py files
_INTEGRATION = Path(__file__).parent / "integration"
if str(_INTEGRATION) not in sys.path:
    sys.path.insert(0, str(_INTEGRATION))
