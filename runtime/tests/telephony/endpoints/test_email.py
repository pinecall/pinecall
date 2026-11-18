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
    assert kept.status_code == 200 and kept.json() == {"html": OURS, "own": True}
    asked = {"text": "Hola **Ana**,\n\n- sábado 10 a 14", "subject": "Horarios"}
    preview = (await gateway.http.post(f"{DOOR}/preview", json=asked, headers=tenant.person)).json()
    assert preview["subject"] == "Re: Horarios"
    assert preview["html"].startswith("<html><body><h1>Acme</h1><p") and "<strong>Ana</strong>" in preview["html"]
    assert "<p>Re: Horarios</p>" in preview["html"] and preview["text"].startswith("Hola Ana,")
    assert (await gateway.http.delete(DOOR, headers=tenant.person)).status_code == 204
    assert (await gateway.http.get(DOOR, headers=tenant.person)).json()["own"] is False
    assert (await gateway.http.delete(DOOR, headers=tenant.person)).status_code == 404
