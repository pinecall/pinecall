"""A plugin's options as a form draws them: read off its constructor, the knobs the settings set left out."""

from runtime.enums import Stage
from runtime.providers.service.plugin_options import form_of
from tests.fakes import acme


def test_the_ears_options_are_the_constructors_arguments_the_settings_do_not_set_and_an_objects_fields() -> None:
    """The key, the model, the language and its hints are knobs; `params` is its dataclass's fields, named inside it."""
    found = form_of(Stage.stt, acme.ACME, None)
    by_name = {(option.inside, option.name): option for option in found.options}
    assert found.builds == "AcmeSTT"
    assert not any(name in {"api_key", "model", "language", "language_hints"} for _, name in by_name)
    assert by_name[(None, "eot_threshold")].kind == "number" and by_name[(None, "eot_threshold")].default is None
    assert by_name[(None, "eot_timeout_ms")].kind == "integer"
    assert by_name[(None, "keyterms")].kind == "boolean" and by_name[(None, "keyterms")].default is False
    assert by_name[("params", "sensitivity")].kind == "number" and by_name[("params", "sensitivity")].default == 0.5
    # A field of an object no form can type (the context's terms) is left out, as any such argument is.
    assert ("params", "context") not in by_name


def test_the_voices_options_leave_out_its_voice_its_key_and_its_model_and_keep_what_a_form_can_draw() -> None:
    """`speech_key`, `voice_name`, `language_code` and `model` are knobs; `channels` and `silent` stay."""
    found = form_of(Stage.tts, acme.ACME, None)
    names = [option.name for option in found.options]
    assert "speech_key" not in names and "voice_name" not in names and "language_code" not in names
    assert "channels" in names and "silent" in names


def test_the_models_temperature_is_the_settings_knob_and_not_an_option() -> None:
    """`temperature` has its own field in the settings; the form never offers it twice."""
    assert "temperature" not in [option.name for option in form_of(Stage.llm, acme.ACME, None).options]
