"""A test room's own voice and models lie over the settings for its call alone, and ask for nothing else."""

import pytest

from pinecall_runtime.agents.declaration import Tuning
from pinecall_runtime.agents.service import settings
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Forbidden, ValidationError


def test_the_values_a_room_asked_for_win_knob_by_knob_and_the_rest_stay() -> None:
    standing = Tuning(llm="acme/acme-1", voice="ana", language="es", temperature=0.4)
    tried = settings.overlay_tuning(standing, {"voice": "lucia", "temperature": 0.9})
    assert (tried.voice, tried.temperature) == ("lucia", 0.9)
    assert (tried.llm, tried.language) == ("acme/acme-1", "es")


def test_no_values_leave_the_settings_as_they_are() -> None:
    standing = Tuning(voice="ana")
    assert settings.overlay_tuning(standing, None) is standing
    assert settings.overlay_tuning(standing, {}) is standing


def test_the_sandbox_takes_a_voice_and_the_models_and_hands_back_what_it_checked() -> None:
    asked = {"tts": "acme", "voice": "lucia", "stt": "acme/nova", "llm": "acme/acme-2"}
    assert settings.check_test_values(asked, env=Env.sandbox) == asked


def test_production_refuses_them_and_says_whose_they_are() -> None:
    with pytest.raises(Forbidden, match="sandbox"):
        settings.check_test_values({"voice": "lucia"}, env=Env.production)


def test_a_room_changes_the_voice_and_the_models_and_nothing_else() -> None:
    with pytest.raises(ValidationError, match="record"):
        settings.check_test_values({"voice": "lucia", "record": False}, env=Env.sandbox)


def test_a_value_the_settings_would_refuse_is_refused_here_too() -> None:
    with pytest.raises(ValidationError):
        settings.check_test_values({"temperature": -1}, env=Env.sandbox)
