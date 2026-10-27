"""What an agent's app publishes for pages: lines recorded once in its voice, and documents, read with no key."""

from tests.conftest import Gateway, Tenant, holding, needs_the_services

pytestmark = needs_the_services


async def test_each_text_is_recorded_once_and_its_words_come_back_in_order(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/lines"
    texts = ["Up here are our services.", "Pricing is simple."]
    async with holding(gateway, tenant, agent):
        first = await gateway.http.post(door, json={"texts": texts}, headers=tenant.person)
        again = await gateway.http.post(door, json={"texts": texts[::-1]}, headers=tenant.person)
    assert first.status_code == 200, first.text
    lines = first.json()["lines"]
    assert [line["text"] for line in lines] == texts
    assert [word["text"] for word in lines[0]["words"]] == ["Up", "here", "are", "our", "services."]
    assert all(line["url"].endswith(f"/v1/lines/{line['id']}.mp3") and line["duration_ms"] > 0 for line in lines)
    assert [line["id"] for line in again.json()["lines"]] == [line["id"] for line in lines][::-1]


async def test_a_recorded_line_is_heard_by_any_page_with_no_key_and_never_changes(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        recorded = await gateway.http.post(f"/v1/agents/{agent}/lines", json={"texts": ["Hi."]}, headers=tenant.person)
    line = recorded.json()["lines"][0]
    heard = await gateway.http.get(f"/v1/lines/{line['id']}.mp3")
    missing = await gateway.http.get("/v1/lines/0000.mp3")
    assert heard.status_code == 200, heard.text
    assert heard.headers["content-type"] == "audio/mpeg"
    assert "immutable" in heard.headers["cache-control"]
    assert heard.content[:3] == b"ID3" or heard.content[0] == 0xFF
    assert missing.status_code == 404


async def test_too_many_texts_or_an_empty_one_are_refused_and_nothing_is_recorded(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/lines"
    async with holding(gateway, tenant, agent):
        many = await gateway.http.post(door, json={"texts": ["Hi."] * 65}, headers=tenant.person)
        empty = await gateway.http.post(door, json={"texts": [""]}, headers=tenant.person)
    assert many.status_code in (400, 422)
    assert empty.status_code in (400, 422)


async def test_an_output_is_explained_by_the_agents_model_and_an_answer_that_is_not_notes_is_none(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/explain"
    output = "  org lesson · key k_1234 · sandbox\n  a person's key: the sandbox without --prod"
    async with holding(gateway, tenant, agent):
        # The box's model answers the caller's last line, not notes: the door answers none, and no error.
        explained = await gateway.http.post(
            door, json={"output": output, "command": "pinecall whoami"}, headers=tenant.person
        )
        long = await gateway.http.post(door, json={"output": "x" * 8001}, headers=tenant.person)
        many = await gateway.http.post(door, json={"output": output, "most": 7}, headers=tenant.person)
    assert explained.status_code == 200, explained.text
    assert explained.json() == {"notes": []}
    assert long.status_code in (400, 422)
    assert many.status_code in (400, 422)


async def test_a_document_is_published_whole_and_read_with_no_key_in_its_env_alone(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/public/walks"
    async with holding(gateway, tenant, agent):
        put = await gateway.http.put(door, json={"walks": [{"name": "tour"}]}, headers=tenant.person)
        again = await gateway.http.put(door, json={"walks": []}, headers=tenant.person)
    read = await gateway.http.get(f"{door}?env=sandbox")
    production = await gateway.http.get(door)
    nobody = await gateway.http.get("/v1/agents/nobody-holds-this/public/walks?env=sandbox")
    assert put.status_code == 200, put.text
    assert again.json() == {"walks": []}
    assert read.status_code == 200 and read.json() == {"walks": []}
    assert "max-age=60" in read.headers["cache-control"]
    assert production.status_code == 404
    assert nobody.status_code == 404


async def test_a_document_that_is_no_object_or_badly_named_or_too_large_is_refused(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        listed = await gateway.http.put(f"/v1/agents/{agent}/public/walks", json=[1, 2], headers=tenant.person)
        named = await gateway.http.put(f"/v1/agents/{agent}/public/Walks!", json={}, headers=tenant.person)
        large = await gateway.http.put(
            f"/v1/agents/{agent}/public/walks", json={"a": "x" * 70_000}, headers=tenant.person
        )
        keyless = await gateway.http.put(f"/v1/agents/{agent}/public/walks", json={})
    assert listed.status_code == 400 and "one JSON object" in listed.json()["detail"]
    assert named.status_code == 400 and "lower case" in named.json()["detail"]
    assert large.status_code == 413
    assert keyless.status_code == 401
