"""A lexicon's word is said its way as a whole word alone, in a text and in a voice's stream cut anywhere."""

from collections.abc import AsyncIterator

import pytest

from pinecall_runtime.kit.said import holds, said, saying

SAYS = {
    "CLI": "ci el ái",
    "cloud.pinecall.io": "cláud punto Páincol punto ío",
    "Pinecall": "Páincol",
    "Dr. Lee": "Doctor Lee",
}


def test_a_word_is_said_its_way_as_a_whole_word_never_inside_another() -> None:
    assert (
        said("El CLI, en tu terminal. Un cliente hace clic.", SAYS)
        == "El ci el ái, en tu terminal. Un cliente hace clic."
    )
    assert said("contra cloud.pinecall.io y Pinecall's", SAYS) == "contra cláud punto Páincol punto ío y Páincol's"
    assert said("Ask dr. lee today", SAYS) == "Ask Doctor Lee today"
    assert holds("el CLI.", "CLI")
    assert not holds("el cliente", "CLI")


async def _streamed(chunks: list[str]) -> str:
    async def source() -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    return "".join([piece async for piece in saying(SAYS)(source())])


@pytest.mark.parametrize(
    "chunks",
    [
        ["El CLI, y un cliente, contra cloud.pinecall.io con Dr. Lee."],
        ["El C", "LI, y un cli", "ente, contra cloud.pine", "call.io con Dr.", " Lee."],
        list("El CLI, y un cliente, contra cloud.pinecall.io con Dr. Lee."),
    ],
)
async def test_a_voices_stream_is_said_the_same_wherever_its_chunks_are_cut(chunks: list[str]) -> None:
    assert await _streamed(chunks) == "El ci el ái, y un cliente, contra cláud punto Páincol punto ío con Doctor Lee."


async def test_with_no_lexicon_the_stream_goes_by_as_it_comes() -> None:
    async def source() -> AsyncIterator[str]:
        yield "Hola"
        yield " mundo"

    assert [piece async for piece in saying({})(source())] == ["Hola", " mundo"]
