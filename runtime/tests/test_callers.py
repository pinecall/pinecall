"""The callers service: how many processes it runs, how many callers each plays, and who plays them without it."""

import os

import pytest

from runtime.callers import count_processes
from runtime.config import Settings

REQUIRED = {"PINECALL_VAULT_KEY": "x", "PINECALL_TOKEN_KEY": "y"}


def settings(**named: str) -> Settings:
    return Settings.model_validate({**REQUIRED, **named})


# A caller's process and the worker that answers it share the machine, 0.18 and 0.22 of a core a call:
# a process a core would leave the workers none.
def test_the_service_runs_the_processes_it_is_told_or_half_the_cores_it_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert count_processes(settings(PINECALL_CALLER_PROCESSES="5")) == 5
    for cores, processes in ((16, 8), (8, 4), (3, 1), (1, 1)):
        monkeypatch.setattr(os, "process_cpu_count", lambda cores=cores: cores)
        assert count_processes(settings()) == processes


def test_a_process_plays_three_callers_at_once_and_a_gateway_plays_callers_unless_a_service_does() -> None:
    assert settings().callers_per_process == 2
    assert settings(PINECALL_CALLERS_PER_PROCESS="5").callers_per_process == 5
    # The suite's own gateways are told a service plays them (`tests/conftest.py`): the default is the field's.
    assert Settings.model_fields["callers_service"].default is False
    assert settings(PINECALL_CALLERS_SERVICE="0").callers_service is False
    assert settings(PINECALL_CALLERS_SERVICE="1").callers_service is True
