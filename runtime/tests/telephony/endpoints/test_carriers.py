"""The carriers' doors: the catalog says the SIP name of the key's env, which a portal or a PBX is pointed at."""

from runtime.config import load_settings
from runtime.enums import Env
from tests.conftest import Gateway, Tenant, needs_the_services


@needs_the_services
async def test_the_carriers_catalog_says_the_sip_name_of_the_keys_environment(gateway: Gateway, tenant: Tenant) -> None:
    """A portal or a PBX is pointed at it, so the console has to be able to say it."""
    said = await gateway.http.get("/v1/carriers/catalog", headers=tenant.person)
    assert said.status_code == 200, said.text
    assert said.json()["sip_domain"] == load_settings().sip_domain_of(Env.sandbox)
