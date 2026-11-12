"""The clinic's front desk as Studio holds it: the definition the studio tests build on."""

from runtime.wire.studio import Definition


def clinic(**changes: object) -> Definition:
    """The clinic's front desk: one lookup by phone, and the patient's name and reason collected."""
    raw: dict[str, object] = {
        "instructions": "You answer the phone for Clínica Norte. The caller dials from {{call.from}}.",
        "greeting": {"say": "Clínica Norte, buen día."},
        "tools": [
            {
                "name": "findPatient",
                "description": "Finds the patient by phone.",
                "url": "https://agenda.example.com/patients/{phone}",
                "headers": [{"name": "Authorization", "value": "Bearer {{secrets.AGENDA_KEY}}"}],
                "params": [{"name": "phone", "description": "the caller's number"}],
            }
        ],
        "collect": {
            "fields": [
                {"name": "name", "description": "the patient's full name"},
                {"name": "reason", "required": False},
            ],
            "send_to": "https://agenda.example.com/calls",
        },
    }
    raw.update(changes)
    return Definition.model_validate(raw)


def a_tool(**changes: object) -> dict[str, object]:
    """A tool with a header's secret, the way a definition holds one, with these fields changed."""
    return {"name": "a", "description": "x", "url": "https://a.example.com", **changes}
