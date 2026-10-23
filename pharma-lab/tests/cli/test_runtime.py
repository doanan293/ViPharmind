import json

import pytest
import typer

from pharma_lab.cli.runtime import (
    CliState,
    CommandResult,
    CommandStatus,
    result_payload,
    run_handler,
)


def test_a_result_with_an_exit_code_exits_with_it() -> None:
    result = CommandResult(
        "x", CommandStatus.INCOMPLETE, details={"left": 3}, exit_code=10
    )

    with pytest.raises(typer.Exit) as raised:
        run_handler(CliState(), lambda: result)

    assert raised.value.exit_code == 10


def test_without_an_exit_code_incomplete_still_exits_three() -> None:
    with pytest.raises(typer.Exit) as raised:
        run_handler(CliState(), lambda: CommandResult("x", CommandStatus.INCOMPLETE))

    assert raised.value.exit_code == 3


def test_the_exit_code_is_not_part_of_the_json_payload() -> None:
    payload = result_payload(CommandResult("x", CommandStatus.INCOMPLETE, exit_code=11))

    assert "exit_code" not in payload
    assert json.dumps(payload)
