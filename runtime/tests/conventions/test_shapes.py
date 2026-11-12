"""Shapes at home: pydantic is imported by the wire and the bodies, and by nothing else that is not named here."""

import dataclasses

from runtime.providers.stage import Running
from runtime.wire.worker import RunningStage
from tests.conventions.canon import Module

# Where pydantic is imported outside `wire/` and a `schemas` module, each for one reason. A vendor's
# client that parses that vendor's answers keeps its shapes beside it, and is named here when it is built.
ALLOWED: dict[str, str] = {
    "config": "the settings are read with pydantic-settings",
    "kit.schemas": "the bases every body is built on",
    "signin.service.oidc": "the OpenID client parses a provider's discovery, grant and id_token",
    "providers.catalog": "the providers row is a document the box keeps, and this module its one shape",
    "whatsapp.service": "Meta's client parses Meta's webhook bodies and its Graph answers",
    "knowledge.service.embedder": "the embedder's client parses a vendor's rows and its refusal",
    "telephony.service.twilio": "Twilio's client parses Twilio's answers",
    "hosts.service.cluster": "the cluster's client parses what Kubernetes lists of a pod",
    "cli.client": "the operator's client reads a gateway's answer as the schema its endpoint answers with",
    "cli.output": "a verb prints a schema as JSON, as the endpoint that answers it would",
}


def test_pydantic_lives_in_the_wire_and_the_bodies(modules: dict[str, Module]) -> None:
    """A module that imports pydantic is in `wire/`, is a `schemas` module, or is named with its reason."""
    wrong: list[str] = []
    for module in modules.values():
        if module.parts[0] == "wire" or "schemas" in module.parts or module.name in ALLOWED:
            continue
        for target, _names, line in module.imports():
            if target.split(".")[0] in ("pydantic", "pydantic_settings"):
                wrong.append(f"{module.shown}:{line}: imports {target} outside the wire and the bodies")
    assert not wrong, "\n".join(wrong)


# The gateway fills the wire's stage from the value by its attributes, and a worker reads the value
# back by its field names (`Running.read`): neither maps a field by hand, so the two lists are one.
def test_a_stage_is_one_shape_on_the_wire_and_in_the_package() -> None:
    """`wire.worker.RunningStage` carries the fields of `providers.stage.Running`, under the same names."""
    assert set(RunningStage.model_fields) == {one.name for one in dataclasses.fields(Running)}
