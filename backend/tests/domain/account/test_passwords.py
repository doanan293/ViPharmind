from pharma_agent.domain.account.passwords import password_problem


def test_password_length_rule() -> None:
    assert password_problem("a" * 7) == "password must be at least 8 characters"
    assert password_problem("a" * 8) is None
    assert password_problem("a" * 128) is None
    assert password_problem("a" * 129) == "password must be at most 128 characters"
