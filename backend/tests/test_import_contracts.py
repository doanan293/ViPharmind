"""The import-linter contracts in pyproject.toml cover what the architecture spec requires."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "src" / "pharma_agent" / "application"


def _contract(name: str) -> dict:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = config["tool"]["importlinter"]["contracts"]
    return next(contract for contract in contracts if contract["name"] == name)


def test_domain_forbids_every_framework_the_spec_names() -> None:
    forbidden = set(_contract("domain is framework-free")["forbidden_modules"])
    assert {"langchain", "fastembed"} <= forbidden


def test_application_forbids_every_transport_the_spec_names() -> None:
    contract = _contract(
        "application reaches databases, SDKs and transports only through domain ports"
    )
    assert "uvicorn" in contract["forbidden_modules"]


def test_every_application_feature_is_in_the_independence_contract() -> None:
    features = sorted(
        f"pharma_agent.application.{path.parent.name}"
        for path in APPLICATION.glob("*/__init__.py")
    )
    assert features
    assert sorted(_contract("application features are independent")["modules"]) == (
        features
    )
