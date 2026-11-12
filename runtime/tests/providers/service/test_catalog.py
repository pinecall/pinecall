"""What a vendor is told for a stage and model: the row's word, on the class that runs that model."""

from typing import Literal

from runtime.enums import Stage
from runtime.providers.catalog import Catalog
from runtime.providers.service import catalog
from tests.conftest import configured
from tests.fakes.plugins import install_plugin


class _Ears:
    """The plugin's own ears, typing the models they run, as Deepgram's `STT` does."""

    def __init__(self, *, model: Literal["nova-1", "nova-2"] | str = "nova-2") -> None:
        self.model = model


class _Flux:
    """A second class of ears that ends the turn itself, running the models it lists, as Deepgram's `STTv2`."""

    def __init__(self, *, model: Literal["flux-en", "flux-multi"] | str = "flux-en") -> None:
        self.model = model


# A plugin of two classes of ears, as Deepgram's is.
DEEPGRAM_LIKE = install_plugin("deepgram-like", STT=_Ears, STTv2=_Flux)


def test_the_class_the_row_names_runs_the_models_it_lists_and_the_plugins_own_class_runs_the_rest() -> None:
    """Deepgram's `nova-3` was built as `STTv2`, Flux's door, and refused at the socket: it runs on `STT`,
    which ends no turn; a model neither lists is the row's word."""
    row = configured().model_dump(mode="json")
    row["tuning"][f"stt/{DEEPGRAM_LIKE}"] = {"builds": "STTv2", "ends_the_turn": True}
    written = Catalog.model_validate(row)
    flux = catalog.stage_options_of(written, Stage.stt, DEEPGRAM_LIKE, "flux-multi")
    assert flux is not None and flux.builds == "STTv2" and flux.ends_the_turn
    nova = catalog.stage_options_of(written, Stage.stt, DEEPGRAM_LIKE, "nova-1")
    assert nova is not None and nova.builds is None and not nova.ends_the_turn
    unknown = catalog.stage_options_of(written, Stage.stt, DEEPGRAM_LIKE, "whisper-9")
    assert unknown is not None and unknown.builds == "STTv2" and unknown.ends_the_turn
    unnamed = catalog.stage_options_of(written, Stage.stt, DEEPGRAM_LIKE, None)
    assert unnamed is not None and unnamed.builds == "STTv2"
