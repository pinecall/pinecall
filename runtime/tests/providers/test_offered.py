"""A models file read: what a picker offers by stage and vendor, named, the recommended marked; bad rows refused."""

import pytest

from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers.service.offered import models_from_csv, offered_changed

FILE = """# a note
vendor,stage,model,name,as_of,source
cartesia,stt,ink-2,ink-2,2026-10-19,https://docs.cartesia.ai/stt
cartesia,stt,ink-whisper,ink-whisper,2026-10-19,https://docs.cartesia.ai/stt
cartesia,tts,sonic-3,"Sonic 3, turbo",2026-10-19,https://docs.cartesia.ai/tts
"""

MARKED = """vendor,stage,model,name,as_of,source,recommended
cartesia,tts,sonic-3,Sonic 3,2026-10-19,u,
cartesia,tts,sonic-3.6,Sonic 3.6,2026-10-19,u,yes
cartesia,stt,ink-2,ink-2,2026-10-19,u,YES
"""


def test_a_file_is_read_by_stage_and_vendor_in_its_order_and_its_notes_passed_by() -> None:
    read = models_from_csv(FILE)
    assert read.offered == {"stt/cartesia": ("ink-2", "ink-whisper"), "tts/cartesia": ("sonic-3",)}
    # A name is kept where the vendor gives one; a model named by its id alone has none to keep.
    assert read.names == {"cartesia/sonic-3": "Sonic 3, turbo"}
    assert read.recommended == {}


def test_a_file_may_mark_the_models_a_picker_leads_with() -> None:
    read = models_from_csv(MARKED)
    assert read.offered["tts/cartesia"] == ("sonic-3", "sonic-3.6")
    assert read.recommended == {"tts/cartesia": ("sonic-3.6",), "stt/cartesia": ("ink-2",)}


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("vendor,model\nacme,x\n", "columns vendor,stage,model,name,as_of,source"),
        ("vendor,stage,model,name,as_of,source,notes\nacme,stt,x,x,2026-10-19,u,n\n", "recommended after them or not"),
        ("vendor,stage,model,name,as_of,source\nacme,s2s,x,x,2026-10-19,u\n", "'s2s' is not a stage"),
        ("vendor,stage,model,name,as_of,source\nacme,stt,x,x,2026-10-19,u\nacme,stt,x,x,2026-10-19,u\n", "twice"),
        ("vendor,stage,model,name,as_of,source\n,stt,x,x,2026-10-19,u\n", "names its vendor and its model"),
    ],
)
def test_what_is_not_a_models_file_is_refused_with_its_line(text: str, said: str) -> None:
    with pytest.raises(ValidationError, match=said):
        models_from_csv(text)


def test_the_change_names_what_is_new_changed_the_same_and_only_on_the_box() -> None:
    box = {"stt/acme": ("a",), "tts/acme": ("v",), "llm/acme": ("m",)}
    change = offered_changed(box, {"stt/acme": ("a", "b"), "tts/acme": ("v",), "stt/other": ("o",)})
    assert (change.added, change.changed, change.unchanged, change.only_on_the_box) == (
        ("stt/other",),
        ("stt/acme",),
        ("tts/acme",),
        ("llm/acme",),
    )
