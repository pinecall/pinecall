"""Whose key a vendor runs on for an org: its own runs anything, the box's what the box lends it."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.exceptions import Forbidden, ServiceUnavailable, ValidationError
from runtime.kit.crypto import Vault
from runtime.providers.service import plugins
from runtime.providers.service.credentials import box_credentials, own_credentials
from runtime.providers.service.signatures import takes_a_key
from runtime.providers.stage import Credentials, Running

# A lends entry is a vendor, or `vendor/model`. Model ids carry slashes of their own (`openai/gpt-5`
# on LiveKit Inference): the first ends the vendor.
SEPARATOR = "/"
# What a dated snapshot adds to a model's name: `-20251001`, `-2025-08-07`, `@20240229`.
A_SNAPSHOT = re.compile(r"[-@](\d{8}|\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True, slots=True)
class Keyring:
    """What a call may run on: the org's own credentials, the box's, and what the box lends it."""

    own: Mapping[str, Credentials] = field(default_factory=dict[str, Credentials])
    box: Mapping[str, Credentials] = field(default_factory=dict[str, Credentials])
    # quotas.lends: None lends everything the box holds, empty lends nothing.
    lends: frozenset[str] | None = None

    def may_run(self, vendor: str, model: str) -> bool:
        """Whether the org may run this model: on its own key any, on the box's what is lent."""
        return vendor in self.own or (vendor in self.box and is_lent(self.lends, vendor, model))

    # A vendor lent whole, or by any one of its models: the picker lists those.
    def lends_any_of(self, vendor: str) -> bool:
        """Whether the box lends the org anything of the vendor."""
        under = f"{vendor}{SEPARATOR}"
        return is_lent(self.lends, vendor, None) or any(entry.startswith(under) for entry in self.lends or ())


# Read per call, so a rotated key runs from the next call on.
async def keys_of(session: AsyncSession, vault: Vault, scope: Scope) -> Keyring:
    """What the org's calls in the env may run on."""
    quotas = await billing.get_quotas(session, scope.org, scope.env)
    return Keyring(
        own=await own_credentials(session, vault, scope.org),
        box=await box_credentials(session, vault),
        lends=quotas.lends,
    )


def running_on(keys: Keyring, vendor: str, model: str | None) -> Running:
    """The vendor on the org's own key, else on a key the box lends; refused before the call."""
    own = keys.own.get(vendor)
    if own is not None:
        return Running(vendor=vendor, credentials=own, model=model)
    box = keys.box.get(vendor)
    if box is None:
        if not takes_a_key(vendor):
            return Running(vendor=vendor, credentials="", model=model)
        raise ServiceUnavailable(f"{vendor} has no key: the org brought none and the box holds none")
    if not is_lent(keys.lends, vendor, model):
        raise Forbidden(lending_refusal(keys.lends or frozenset(), vendor, model))
    return Running(vendor=vendor, credentials=box, model=model, lent=True)


# A model entry lends itself and its dated snapshots (`anthropic/claude-haiku-5-5` lends
# `claude-haiku-5-5-20261001`), never a sibling that only starts the same (`openai/gpt-5` lends no
# `gpt-5-pro`); a plugin's own default needs the whole vendor.
def is_lent(lends: frozenset[str] | None, vendor: str, model: str | None) -> bool:
    """Whether the box lends this org its key for this vendor and model."""
    if lends is None or vendor in lends:
        return True
    if model is None:
        return False
    prefix = f"{vendor}{SEPARATOR}"
    named = (entry.removeprefix(prefix) for entry in lends if entry.startswith(prefix))
    return any(model == entry or _is_a_snapshot_of(entry, model) for entry in named)


def lending_refusal(lends: frozenset[str], vendor: str, model: str | None) -> str:
    """The sentence a refused org reads: what it asked, what it may run, and the other way."""
    asked = vendor if model is None else f"{vendor}{SEPARATOR}{model}"
    may = ", ".join(sorted(lends)) if lends else "nothing of the box's"
    return f"{asked} is not lent to this org: it may run on {may}, or on a key of its own"


def parse_lending(entries: Iterable[str]) -> frozenset[str]:
    """The entries an operator lends, each a vendor installed here or `vendor/model`."""
    parsed: set[str] = set()
    for entry in entries:
        named, slash, model = entry.strip().partition(SEPARATOR)
        vendor = named.lower()
        if not plugins.is_installed(vendor):
            raise ValidationError(f"{entry!r} lends no vendor installed here")
        if slash and not model:
            raise ValidationError(f"{entry!r} names a vendor and no model after the slash")
        parsed.add(f"{vendor}{SEPARATOR}{model}" if slash else vendor)
    return frozenset(parsed)


def _is_a_snapshot_of(entry: str, model: str) -> bool:
    return model.startswith(entry) and A_SNAPSHOT.fullmatch(model[len(entry) :]) is not None
