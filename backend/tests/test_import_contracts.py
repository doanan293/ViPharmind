"""The import-linter contracts in pyproject.toml cover what the architecture spec requires."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "src" / "pharma_agent" / "application"


def _contract_modules(name: str, key: str) -> list[str]:
    """The module list `key` of the import-linter contract called `name`."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = config["tool"]["importlinter"]["contracts"]
    contract = next(contract for contract in contracts if contract["name"] == name)
    return list(contract[key])


def test_domain_forbids_every_framework_the_spec_names() -> None:
    forbidden = set(_contract_modules("domain is framework-free", "forbidden_modules"))
    assert {"langchain", "fastembed"} <= forbidden


def test_application_forbids_every_transport_the_spec_names() -> None:
    forbidden = _contract_modules(
        "application reaches databases, SDKs and transports only through domain ports",
        "forbidden_modules",
    )
    assert "uvicorn" in forbidden


def test_every_application_feature_is_in_the_independence_contract() -> None:
    features = sorted(
        f"pharma_agent.application.{path.parent.name}"
        for path in APPLICATION.glob("*/__init__.py")
    )
    assert features
    modules = _contract_modules("application features are independent", "modules")
    assert sorted(modules) == features
