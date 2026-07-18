import ast
from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "zango_project"
    / "workspaces"
    / "patientbilling"
    / "migrations"
    / "0004_workflowfile_workflowtransaction_and_more.py"
)


def test_framework_models_are_state_only_in_workspace_migration():
    """Package migrations, not the workspace migration, own these tables."""
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    direct_creates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "CreateModel"
        and not any(
            isinstance(parent, ast.Call)
            and isinstance(parent.func, ast.Attribute)
            and parent.func.attr == "SeparateDatabaseAndState"
            and node in ast.walk(parent)
            for parent in ast.walk(tree)
        )
    ]

    assert direct_creates == []
