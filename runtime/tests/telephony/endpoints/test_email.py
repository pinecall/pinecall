"""The org's email layout: the plain one until it writes its own, kept, tried on words, forgotten."""

from tests.conftest import Gateway, Tenant, needs_the_services

DOOR = "/v1/org/email/layout"
OURS = "<html><body><h1>Acme</h1>{{content}}<p>{{subject}}</p></body></html>"


@needs_the_services
async def test_an_org_keeps_its_own_layout_tries_it_on_words_and_goes_back_to_the_plain_one(
    gateway: Gateway, tenant: Tenant
) -> None:
    """Plain until written; refused without {{content}}; the preview sets a reply in it; forgotten, plain again."""
    plain = (await gateway.http.get(DOOR, headers=tenant.person)).json()
    assert plain["own"] is False and "{{content}}" in plain["html"]
    refused = await gateway.http.put(DOOR, json={"html": "<p>nowhere</p>"}, headers=tenant.person)
    assert refused.status_code == 400 and "{{content}}" in refused.text
    kept = await gateway.http.put(DOOR, json={"html": OURS}, headers=tenant.person)
    assert kept.status_code == 200 and kept.json() == {"html": OURS, "own": True, "text_only": False}
    asked = {"text": "Hola **Ana**,\n\n- sábado 10 a 14", "subject": "Horarios"}
    preview = (await gateway.http.post(f"{DOOR}/preview", json=asked, headers=tenant.person)).json()
    assert preview["subject"] == "Re: Horarios"
    assert preview["html"].startswith("<html><body><h1>Acme</h1><p") and "<strong>Ana</strong>" in preview["html"]
    assert "<p>Re: Horarios</p>" in preview["html"] and preview["text"].startswith("Hola Ana,")
    assert (await gateway.http.delete(DOOR, headers=tenant.person)).status_code == 204
    assert (await gateway.http.get(DOOR, headers=tenant.person)).json()["own"] is False
    assert (await gateway.http.delete(DOOR, headers=tenant.person)).status_code == 404


@needs_the_services
async def test_an_org_that_wants_no_template_sends_text_alone_and_takes_a_layout_again(
    gateway: Gateway, tenant: Tenant
) -> None:
    """`text_only`, no HTML: the preview has no HTML part; a layout kept after is HTML again; both or none refused."""
    asked = {"text": "Hola **Ana**", "subject": "Horarios"}
    for wrong in ({}, {"html": OURS, "text_only": True}):
        refused = await gateway.http.put(DOOR, json=wrong, headers=tenant.person)
        assert refused.status_code == 400 and "one of the two" in refused.text
    kept = await gateway.http.put(DOOR, json={"text_only": True}, headers=tenant.person)
    assert kept.status_code == 200 and (kept.json()["own"], kept.json()["text_only"]) == (True, True)
    preview = (await gateway.http.post(f"{DOOR}/preview", json=asked, headers=tenant.person)).json()
    assert (preview["html"], preview["text"], preview["subject"]) == (None, "Hola Ana", "Re: Horarios")
    tried = (await gateway.http.post(f"{DOOR}/preview", json={**asked, "html": OURS}, headers=tenant.person)).json()
    assert tried["html"].startswith("<html><body><h1>Acme</h1>"), "a layout tried is shown, whatever the org keeps"
    plainly = (
        await gateway.http.post(f"{DOOR}/preview", json={**asked, "text_only": False}, headers=tenant.person)
    ).json()
    assert "<strong>Ana</strong>" in plainly["html"]
    again = await gateway.http.put(DOOR, json={"html": OURS}, headers=tenant.person)
    unbranded = (
        await gateway.http.post(f"{DOOR}/preview", json={**asked, "plain": True}, headers=tenant.person)
    ).json()
    assert "<h1>Acme</h1>" not in unbranded["html"] and "<strong>Ana</strong>" in unbranded["html"]
    assert again.json() == {"html": OURS, "own": True, "text_only": False}
    asked_as_text = {**asked, "text_only": True}
    assert (await gateway.http.post(f"{DOOR}/preview", json=asked_as_text, headers=tenant.person)).json()[
        "html"
    ] is None
    assert (await gateway.http.delete(DOOR, headers=tenant.person)).status_code == 204
