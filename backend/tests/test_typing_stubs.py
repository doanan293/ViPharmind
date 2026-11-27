import fastapi_users

# typings/fastapi_users-stubs restates two modules for the type checker (fastapi_users.py:
# FastAPIUsers without the alias pyrefly misreads; models.py: UserOAuthProtocol as a real
# Protocol). It must follow the installed library: on an upgrade, compare both stubs with the
# library's modules, update them, then update this version.
STUBBED_VERSION = "15.0.5"


def test_fastapi_users_stub_matches_the_installed_version() -> None:
    assert fastapi_users.__version__ == STUBBED_VERSION
