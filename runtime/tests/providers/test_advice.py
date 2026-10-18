"""What a host advises: an open model it serves, then what it lends, then the org's own key, else one to bring."""

from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service import Advised, Keyring, Served, advise, served_by
from tests.conftest import configured
from tests.fakes import acme

THE_30B = "nemotron-3.5-lightning:30b-a3b"


def served_row() -> Catalog:
    """Every stage on acme, its thinking at a server of this host's, as the local stack writes it."""
    row = configured().model_dump(mode="json")
    row["tuning"][f"llm/{acme.ACME}"] = {"options": {"base_url": "http://127.0.0.1:11434/v1"}}
    return Catalog.model_validate(row)


def stage_of(advised: list[Advised], stage: str) -> Advised:
    return next(one for one in advised if one.stage == stage)


async def test_the_servers_of_the_row_are_asked_and_the_best_measured_model_they_hold_is_advised() -> None:
    """The thinking's server lists its models; the best of the measured ones it holds is the choice, on no key."""
    asked: list[str] = []

    async def listed(url: str) -> tuple[str, ...]:
        asked.append(url)
        return ("bge-m3", "gemma4:12b", THE_30B)

    served = await served_by(served_row(), listed)
    assert asked == ["http://127.0.0.1:11434/v1"] and served.on_this_host
    thinking = stage_of(advise(served_row(), Keyring(), served), "llm")
    assert (thinking.choice, thinking.runs_on) == (f"{acme.ACME}/{THE_30B}", "served here")
    assert thinking.served == ("bge-m3", "gemma4:12b", THE_30B)


async def test_a_server_that_does_not_answer_serves_nothing() -> None:
    """A row whose server is down advises as if it served nothing: the next rule decides."""

    async def silent(_url: str) -> tuple[str, ...]:
        return ()

    served = await served_by(served_row(), silent)
    thinking = stage_of(advise(served_row(), Keyring(), served), "llm")
    assert thinking.runs_on == "needs a key"


def test_what_the_host_lends_comes_before_the_orgs_own_key_and_a_key_to_bring_comes_last() -> None:
    """Lent by the host, the org runs it on nothing of its own; else on its own key; else it must bring one."""
    nothing_served = Served()
    lent = advise(configured(), Keyring(box={acme.ACME: "box-key"}, lends=None), nothing_served)
    assert {one.runs_on for one in lent} == {"lent by the host"}
    assert stage_of(lent, "llm").choice == f"{acme.ACME}/{acme.MODEL}"
    not_lent = Keyring(box={acme.ACME: "box-key"}, own={acme.ACME: "own-key"}, lends=frozenset())
    assert {one.runs_on for one in advise(configured(), not_lent, nothing_served)} == {"your org's key"}
    bring = advise(configured(), Keyring(box={acme.ACME: "box-key"}, lends=frozenset()), nothing_served)
    assert {one.runs_on for one in bring} == {"needs a key"}
    assert stage_of(bring, "tts").choice == f"{acme.ACME}/{acme.VOICE}"
