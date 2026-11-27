"""Design rules lint-imports cannot see (docs/engineering-guide.md, "Backend rules").

- Every application feature exposes its use cases on a class whose dependencies come in
  through the constructor (no use case written as free functions over global objects).
- No module-level state in domain, application or infrastructure: a module-level value is a
  named constant (UPPER_CASE), a type alias, a logger or `__all__`, never a lowercase global
  built by a call or a mutable literal (clients, caches, registries).
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "pharma_agent"
STATE_FREE_LAYERS = ("domain", "application", "infrastructure")
# Module-level calls allowed under a lowercase name: they hold no mutable state.
STATELESS_FACTORIES = frozenset({"logging.getLogger", "getLogger"})


def _features() -> list[Path]:
    root = PACKAGE / "application"
    return sorted(
        p for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    )


def _injected_classes(feature: Path) -> list[str]:
    """Public classes in the feature whose __init__ takes at least one dependency."""
    found: list[str] = []
    for module in feature.rglob("*.py"):
        for node in ast.parse(module.read_text()).body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            found.extend(
                f"{module.name}:{node.name}"
                for item in node.body
                if isinstance(item, ast.FunctionDef)
                and item.name == "__init__"
                and len(item.args.args) + len(item.args.kwonlyargs) > 1
            )
    return found


def test_every_application_feature_has_a_use_case_class_with_injected_dependencies() -> (
    None
):
    missing = [f.name for f in _features() if not _injected_classes(f)]
    assert missing == []


def _module_state(module: Path, root: Path = PACKAGE) -> list[str]:
    """Lowercase module-level names bound to a call result or a mutable literal."""
    bad = []
    for node in ast.parse(module.read_text()).body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not names or all(n.isupper() or n.startswith("__") for n in names):
            continue
        if any(
            n[:1].isupper() for n in names
        ):  # type aliases (`UserId = Annotated[...]`)
            continue
        built = (
            isinstance(value, ast.Call)
            and ast.unparse(value.func) not in STATELESS_FACTORIES
        )
        mutable = isinstance(value, (ast.List, ast.Dict, ast.Set))
        if built or mutable:
            bad.append(f"{module.relative_to(root)}:{node.lineno} {', '.join(names)}")
    return bad


def test_no_module_level_state_in_domain_application_or_infrastructure() -> None:
    found = [
        entry
        for layer in STATE_FREE_LAYERS
        for module in sorted((PACKAGE / layer).rglob("*.py"))
        if "migrations" not in module.parts
        for entry in _module_state(module)
    ]
    assert found == []


def test_module_state_check_catches_globals(tmp_path: Path) -> None:
    module = tmp_path / "probe.py"
    module.write_text(
        "import logging\n"
        "from openai import OpenAI\n"
        "logger = logging.getLogger(__name__)\n"
        "LIMIT = 5\n"
        "ROLES = {'owner': 2}\n"
        "client = OpenAI()\n"
        "cache = {}\n"
    )
    found = _module_state(module, root=tmp_path)
    assert [entry.split(" ")[1] for entry in found] == ["client", "cache"]
