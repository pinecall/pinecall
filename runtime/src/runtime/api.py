"""Every router of the gateway, mounted on its app in the order a path is matched."""

from fastapi import FastAPI

from runtime.accounts import endpoints as accounts
from runtime.agents import endpoints as agents
from runtime.alerts import endpoints as alerts
from runtime.billing import endpoints as billing
from runtime.compliance import endpoints as compliance
from runtime.fleet import endpoints as fleet
from runtime.knowledge import endpoints as knowledge
from runtime.mail import endpoints as mail
from runtime.platform import endpoints as platform
from runtime.providers import endpoints as providers
from runtime.signin import endpoints as signin
from runtime.telephony import endpoints as telephony
from runtime.whatsapp import endpoints as whatsapp


# A domain's router enters here in the commit that builds the domain. The box's pages go last: their
# last route takes any path.
def mount(app: FastAPI) -> None:
    """Mount every domain's router on the app."""
    app.include_router(platform.router)
    app.include_router(billing.router)
    app.include_router(mail.router)
    app.include_router(accounts.router)
    app.include_router(signin.router)
    app.include_router(compliance.router)
    app.include_router(providers.router)
    app.include_router(agents.router)
    app.include_router(knowledge.router)
    app.include_router(whatsapp.router)
    app.include_router(fleet.router)
    app.include_router(telephony.router)
    app.include_router(alerts.router)
    app.include_router(platform.pages_router)
