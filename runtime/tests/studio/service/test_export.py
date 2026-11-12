"""A Studio agent exported as a TypeScript project: the class a developer edits and `pinecall deploy` runs."""

import io
import zipfile

from runtime.studio.service import export
from runtime.wire.studio import FixedField, Param
from tests.studio.factories import clinic


def test_the_class_declares_the_greeting_a_method_per_tool_and_data_collection() -> None:
    """The greeting as words, the lookup as a fetch with its path encoded and its secret from the environment."""
    written = export.write_class("clinica-norte", 3, clinic())
    assert "release 3" in written
    assert "export default class ClinicaNorte extends Agent {" in written
    assert 'static override greeting = "Clínica Norte, buen día.";' in written
    assert "async findPatient(phone: string): Promise<unknown> {" in written
    assert '`https://agenda.example.com/patients/${encodeURIComponent(String(phone ?? ""))}`' in written
    assert '"Authorization": `Bearer ${process.env.AGENDA_KEY ?? ""}`' in written
    assert "async collect(name?: string, reason?: string)" in written
    assert "override async onEnd()" in written
    # The instructions name the call's number, so they are the view, rendered for each call.
    assert '${this.call.from ?? ""}' in written


def test_a_closed_list_is_a_union_the_fixed_fields_are_literals_and_the_other_lines_a_comment() -> None:
    """`site` takes the two words; `source` and the caller travel in the query; what the class cannot say is said."""
    talkative = clinic(collect=None)
    talkative.tools[0].params.append(Param(name="site", required=False, enum=["centro", "norte"]))
    talkative.tools[0].fixed = [
        FixedField(name="source", value="phone"),
        FixedField(name="from", value="{{call.from}}"),
    ]
    talkative.tools[0].delayed = "Still looking."
    talkative.tools[0].failed = "The agenda is down."
    written = export.write_class("clinica-norte", 3, talkative)
    assert 'async findPatient(phone: string, site?: "centro" | "norte"): Promise<unknown> {' in written
    assert 'query: { site, source: `phone`, from: `${this.call.from ?? ""}` },' in written
    assert '// Studio said after 5s: "Still looking.", and when it failed: "The agenda is down."; the' in written


def test_instructions_that_name_nothing_are_the_classs_docstring() -> None:
    """No placeholder: the instructions are the static identity, cached, and render() says nothing."""
    plain = clinic(instructions="You take messages for the shop.", collect=None, greeting=None, tools=[])
    written = export.write_class("shop", 1, plain)
    assert " * You take messages for the shop." in written
    assert 'return "";' in written
    assert "improvise" not in written


def test_a_backtick_or_a_dollar_in_the_instructions_is_escaped_in_the_template() -> None:
    """The model reads what the person wrote, never code they did not mean."""
    tricky = clinic(instructions="Prices in $ and `code`, from {{call.from}}.", collect=None)
    written = export.write_class("shop", 1, tricky)
    assert "Prices in $ and \\`code\\`, from ${this.call.from" in written


def test_the_project_is_a_zip_of_the_framework_s_layout() -> None:
    """package.json on this release's framework, the class under agents/, and AGENTS.md naming the secret."""
    zipped = zipfile.ZipFile(io.BytesIO(export.zip_project("clinica-norte", 3, clinic(), "^0.13.0")))
    names = set(zipped.namelist())
    assert {
        "clinica-norte/package.json",
        "clinica-norte/tsconfig.json",
        "clinica-norte/agents/clinica-norte/agent.tsx",
        "clinica-norte/AGENTS.md",
    } <= names
    assert '"@pinecall/agents": "^0.13.0"' in zipped.read("clinica-norte/package.json").decode()
    assert "`AGENDA_KEY`" in zipped.read("clinica-norte/AGENTS.md").decode()


def test_every_call_value_studio_fills_that_this_call_carries_is_an_expression() -> None:
    """The number called, the direction, the caller's name, phone and email, and a key of the metadata."""
    asking = clinic(
        instructions=(
            "From {{call.from}} to {{call.to}}, {{call.direction}}: {{caller.name}} {{caller.phone}}"
            " {{caller.email}}, order {{metadata.order}}."
        )
    )
    written = export.write_class("clinica-norte", 3, asking)
    assert (
        '${this.call.from ?? ""} to ${this.call.to ?? ""}, ${this.call.direction ?? ""}: '
        '${this.call.caller?.name ?? ""} ${this.call.caller?.phone ?? ""} ${this.call.caller?.email ?? ""}, '
        'order ${this.call.metadata["order"] ?? ""}.'
    ) in written
    assert "Studio filled" not in written


def test_a_call_value_this_call_does_not_carry_is_said_in_the_class_instead_of_lost() -> None:
    """`{{metadata.order.id}}` is deeper than a key of `this.call.metadata`: empty, and the class says so."""
    asking = clinic(instructions="Order {{metadata.order.id}} on {{call.channel}}.")
    written = export.write_class("clinica-norte", 3, asking)
    assert 'Order  on ${this.call.channel ?? ""}.' in written
    assert (
        "// Studio filled {{metadata.order.id}} from the call; the class reads no such value, so each is empty below."
    ) in written


def test_a_class_whose_values_all_exist_on_the_call_says_nothing_of_the_ones_it_lacks() -> None:
    """The clinic names `{{call.from}}` and a secret in a header: nothing is left empty."""
    assert "Studio filled" not in export.write_class("clinica-norte", 3, clinic())
