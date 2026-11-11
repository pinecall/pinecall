"""Every router of the gateway, mounted on its app in the order a path is matched."""

from fastapi import FastAPI


# A domain's router enters here in the commit that builds the domain.
def mount(app: FastAPI) -> None:
    """Mount every domain's router on the app."""
