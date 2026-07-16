"""
Unit test setup: mock all Zango/Django framework modules before the workspace
code is imported, so tests run without a live DB or Django server.

Path layout (same relative structure host and inside container):
  deploy/             -> /zango/
  deploy/tests/       -> /zango/tests/
  deploy/zango_project/workspaces/patientbilling/ -> workspace root
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock


class _ValidationError(Exception):
    pass

# ── workspace path ──────────────────────────────────────────────────────────
TESTS_DIR = Path(__file__).parent.parent          # deploy/tests  or  /zango/tests
DEPLOY_DIR = TESTS_DIR.parent                     # deploy        or  /zango
WORKSPACE = DEPLOY_DIR / "zango_project" / "workspaces" / "patientbilling"

if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

# ── real base class so ClaimWorkflow / InvoiceWorkflow can inherit ───────────
class _WorkflowBase:
    status_transitions = []
    class Meta:
        on_create_status = None
        statuses = {}


# ── @tool decorator: passthrough so decorated functions stay callable ─────────
def _make_tool_mock():
    m = MagicMock()
    # tool(name=..., description=..., safety=...) -> decorator(func) -> func
    m.return_value = lambda f: f
    return m


# ── sys.modules stubs (set before any workspace module is imported) ───────────
_MOCKS = {
    # Django stubs
    "django":                               MagicMock(),
    "django.db":                            MagicMock(),
    "django.db.models":                     MagicMock(),
    "django.core":                           MagicMock(),
    "django.core.exceptions":                MagicMock(ValidationError=_ValidationError),
    # Zango framework
    "zango":                                MagicMock(),
    "zango.apps":                           MagicMock(),
    "zango.apps.dynamic_models":            MagicMock(),
    "zango.apps.dynamic_models.models":     MagicMock(),
    "zango.apps.dynamic_models.fields":     MagicMock(),
    "zango.core":                           MagicMock(),
    "zango.ai":                             MagicMock(),
    "zango.ai.tools":                       MagicMock(
        tool=_make_tool_mock(),
        ToolParam=MagicMock(return_value=None),
        ToolSafety=MagicMock(READ_ONLY="READ_ONLY", WRITE="WRITE"),
    ),
    # Workspace cross-module imports
    "_workspaces":                                          MagicMock(),
    "_workspaces.backend":                                  MagicMock(),
    "_workspaces.backend.claims":                           MagicMock(),
    "_workspaces.backend.claims.models":                    MagicMock(),
    "_workspaces.backend.patients":                         MagicMock(),
    "_workspaces.backend.patients.models":                  MagicMock(),
    "_workspaces.backend.payers":                           MagicMock(),
    "_workspaces.backend.payers.models":                    MagicMock(),
    "_workspaces.packages":                                 MagicMock(),
    "_workspaces.packages.workflow":                        MagicMock(),
    "_workspaces.packages.workflow.base":                   MagicMock(),
    "_workspaces.packages.workflow.base.engine":            MagicMock(WorkflowBase=_WorkflowBase),
    "_workspaces.packages.crud":                            MagicMock(),
    "_workspaces.packages.crud.forms":                      MagicMock(),
    "_workspaces.packages.crud.form_fields":                MagicMock(),
    "_workspaces.packages.crud.base":                       MagicMock(),
    "_workspaces.packages.crud.base.views":                 MagicMock(),
}

for name, mock in _MOCKS.items():
    sys.modules.setdefault(name, mock)
