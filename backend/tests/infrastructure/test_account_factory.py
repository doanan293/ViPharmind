import pytest

from pharma_agent.infrastructure.account_factory import account_policy
from pharma_agent.infrastructure.settings import Settings

OTP_SECRET = "o" * 32


def test_policy_keeps_the_per_ip_send_limit_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_AUTH__OTP_SECRET", OTP_SECRET)
    policy = account_policy(Settings(_env_file=None))
    assert policy.sends_per_ip_per_hour == 20


def test_policy_takes_the_per_ip_send_limit_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A local demo sends every account's codes from one address (the machine running it).
    monkeypatch.setenv("PHARMA_AUTH__OTP_SECRET", OTP_SECRET)
    monkeypatch.setenv("PHARMA_AUTH__CODE_SENDS_PER_IP_PER_HOUR", "500")
    policy = account_policy(Settings(_env_file=None))
    assert policy.sends_per_ip_per_hour == 500


def test_per_ip_send_limit_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_AUTH__CODE_SENDS_PER_IP_PER_HOUR", "0")
    with pytest.raises(ValueError, match="code_sends_per_ip_per_hour"):
        Settings(_env_file=None)


def test_policy_takes_the_login_failure_limit_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMA_AUTH__OTP_SECRET", OTP_SECRET)
    assert account_policy(Settings(_env_file=None)).login_failures_per_window == 10
    monkeypatch.setenv("PHARMA_AUTH__LOGIN_FAILURES_PER_WINDOW", "500")
    assert account_policy(Settings(_env_file=None)).login_failures_per_window == 500
