"""A vendor key is tried as a call would run it before it is kept: a key the vendor turns away is never kept."""

from tests.conftest import Gateway, Tenant, needs_the_services
from tests.fakes import acme


@needs_the_services
async def test_a_key_the_vendor_refuses_is_refused_in_its_words_and_never_kept(
    gateway: Gateway, tenant: Tenant
) -> None:
    """The vendor's 401 is the answer's 400, and the org's vendors stay as they were."""
    refused = await gateway.http.put(
        f"/v1/provider-keys/{acme.ACME}", json={"key": acme.A_REFUSED_KEY}, headers=tenant.person
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"].startswith(f"{acme.ACME} refused this key: invalid api key")
    vendors = await gateway.http.get("/v1/provider-keys", headers=tenant.person)
    assert acme.ACME not in vendors.json()["vendors"]


@needs_the_services
async def test_a_key_the_vendor_answers_on_is_kept(gateway: Gateway, tenant: Tenant) -> None:
    """One small request answered, and the key is the org's from the next call."""
    kept = await gateway.http.put(
        f"/v1/provider-keys/{acme.ACME}", json={"key": "acme-good-key"}, headers=tenant.person
    )
    assert kept.status_code == 204, kept.text
    vendors = await gateway.http.get("/v1/provider-keys", headers=tenant.person)
    assert acme.ACME in vendors.json()["vendors"]


@needs_the_services
async def test_a_key_one_job_of_the_vendor_answers_on_is_kept(gateway: Gateway, tenant: Tenant) -> None:
    """A speech-to-text plan of a vendor that also thinks and speaks: its model and voice refuse the
    key, its ears answer, and the key is kept for the ears."""
    kept = await gateway.http.put(
        f"/v1/provider-keys/{acme.ACME}", json={"key": acme.AN_EARS_ONLY_KEY}, headers=tenant.person
    )
    assert kept.status_code == 204, kept.text
    vendors = await gateway.http.get("/v1/provider-keys", headers=tenant.person)
    assert acme.ACME in vendors.json()["vendors"]
