"""Every domain's endpoints on the gateway's app, the box's pages last since they take any path."""

from fastapi import FastAPI

from pinecall_runtime.accounts import endpoints as accounts
from pinecall_runtime.agents import endpoints as agents
from pinecall_runtime.alerts import endpoints as alerts
from pinecall_runtime.billing import endpoints as billing
from pinecall_runtime.calls import endpoints as calls
from pinecall_runtime.channels import endpoints as channels
from pinecall_runtime.compliance import endpoints as compliance
from pinecall_runtime.evals import endpoints as evals
from pinecall_runtime.fleet import endpoints as fleet
from pinecall_runtime.hosting import endpoints as hosting
from pinecall_runtime.knowledge import endpoints as knowledge
from pinecall_runtime.platform import endpoints as platform
from pinecall_runtime.providers import endpoints as providers
from pinecall_runtime.retention import endpoints as retention
from pinecall_runtime.studio import endpoints as studio
from pinecall_runtime.telephony import endpoints as telephony

# In the canon's order, bottom up; `platform` is mounted apart, after them all.
DOMAINS = (
    billing,
    accounts,
    compliance,
    providers,
    agents,
    knowledge,
    channels,
    fleet,
    telephony,
    alerts,
    calls,
    evals,
    hosting,
    studio,
    retention,
)


def mount(app: FastAPI) -> None:
    """Mount every domain's router on the app, then the widget and the console."""
    for domain in DOMAINS:
        app.include_router(domain.router)
    app.include_router(platform.router)
