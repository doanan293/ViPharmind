import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pharma_agent"
FORBIDDEN_IN_DOMAIN = {
    "langgraph",
    "langchain",
    "langchain_core",
    "openai",
    "qdrant_client",
    "sqlalchemy",
    "fastapi",
    "langfuse",
    "httpx",
    "fastembed",
}
OUTER_LAYERS = {
    "pharma_agent.application",
    "pharma_agent.infrastructure",
    "pharma_agent.api",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _py_files(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.py")) if folder.exists() else []


def test_domain_is_framework_free() -> None:
    for file in _py_files(SRC / "domain"):
        for name in _imports(file):
            root = name.split(".")[0]
            assert root not in FORBIDDEN_IN_DOMAIN, (
                f"{file.relative_to(SRC)} imports {name}"
            )


def test_domain_does_not_import_outer_layers() -> None:
    for file in _py_files(SRC / "domain"):
        for name in _imports(file):
            assert not any(name.startswith(layer) for layer in OUTER_LAYERS), (
                f"{file.relative_to(SRC)} imports outer layer {name}"
            )


def test_api_does_not_import_domain_directly() -> None:
    for file in _py_files(SRC / "api"):
        for name in _imports(file):
            assert not name.startswith("pharma_agent.domain"), (
                f"{file.relative_to(SRC)} must go through application, not domain: {name}"
            )


# The application layer orchestrates with LangGraph but reaches every other framework,
# database, SDK and transport through domain ports implemented in infrastructure.
FORBIDDEN_IN_APPLICATION = {
    "openai",
    "qdrant_client",
    "sqlalchemy",
    "psycopg",
    "alembic",
    "fastapi",
    "fastapi_users",
    "starlette",
    "langfuse",
    "httpx",
    "typer",
    "uvicorn",
}
APPLICATION = SRC / "application"


def _application_features() -> list[str]:
    return sorted(
        path.name
        for path in APPLICATION.iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    )


def test_application_does_not_import_infrastructure_or_api() -> None:
    for file in _py_files(APPLICATION):
        for name in _imports(file):
            assert not name.startswith(
                ("pharma_agent.infrastructure", "pharma_agent.api")
            ), f"{file.relative_to(SRC)} imports outer layer {name}"


def test_application_reaches_frameworks_only_through_ports() -> None:
    for file in _py_files(APPLICATION):
        for name in _imports(file):
            root = name.split(".")[0]
            assert root not in FORBIDDEN_IN_APPLICATION, (
                f"{file.relative_to(SRC)} imports {name}; add a domain port instead"
            )


def test_application_features_do_not_import_each_other() -> None:
    """A feature imports itself and the shared modules at the application root only.

    Use cases of different features are composed in api or infrastructure.
    """
    features = _application_features()
    assert features
    for feature in features:
        others = {
            f"pharma_agent.application.{other}"
            for other in features
            if other != feature
        }
        for file in _py_files(APPLICATION / feature):
            for name in _imports(file):
                assert not any(
                    name == other or name.startswith(f"{other}.") for other in others
                ), f"{file.relative_to(SRC)} imports another feature: {name}"


def test_infrastructure_does_not_import_api() -> None:
    for file in _py_files(SRC / "infrastructure"):
        for name in _imports(file):
            assert not name.startswith("pharma_agent.api"), (
                f"{file.relative_to(SRC)} imports the api layer: {name}"
            )


def test_routers_reach_infrastructure_only_through_api_deps() -> None:
    """Routers call application services; api/deps.py and api/app.py do the wiring."""
    for file in _py_files(SRC / "api" / "routers"):
        for name in _imports(file):
            assert not name.startswith("pharma_agent.infrastructure"), (
                f"{file.relative_to(SRC)} imports infrastructure directly: {name}"
            )
