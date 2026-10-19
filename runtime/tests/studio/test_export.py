"""A Studio agent exported as a TypeScript project: the class a developer edits and `pinecall deploy` runs."""

import io
import zipfile

from pinecall_runtime.studio.service import export
from tests.studio.test_definition import clinic


def test_the_class_declares_the_greeting_a_method_per_tool_and_data_collection() -> None:
    """The greeting as words, the lookup as a fetch with its path encoded and its secret from the environment."""
    written = export.class_of("clinica-norte", 3, clinic())
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


def test_instructions_that_name_nothing_are_the_classs_docstring() -> None:
    """No placeholder: the instructions are the static identity, cached, and render() says nothing."""
    plain = clinic(instructions="You take messages for the shop.", collect=None, greeting=None, tools=[])
    written = export.class_of("shop", 1, plain)
    assert " * You take messages for the shop." in written
    assert 'return "";' in written
    assert "improvise" not in written


def test_a_backtick_or_a_dollar_in_the_instructions_is_escaped_in_the_template() -> None:
    """The model reads what the person wrote, never code they did not mean."""
    tricky = clinic(instructions="Prices in $ and `code`, from {{call.from}}.", collect=None)
    written = export.class_of("shop", 1, tricky)
    assert "Prices in $ and \\`code\\`, from ${this.call.from" in written


def test_the_project_is_a_zip_of_the_framework_s_layout() -> None:
    """package.json on this release's framework, the class under agents/, and AGENTS.md naming the secret."""
    zipped = zipfile.ZipFile(io.BytesIO(export.project_of("clinica-norte", 3, clinic(), "^0.13.0")))
    names = set(zipped.namelist())
    assert {
        "clinica-norte/package.json",
        "clinica-norte/tsconfig.json",
        "clinica-norte/agents/clinica-norte/agent.tsx",
        "clinica-norte/AGENTS.md",
    } <= names
    assert '"@pinecall/agents": "^0.13.0"' in zipped.read("clinica-norte/package.json").decode()
    assert "`AGENDA_KEY`" in zipped.read("clinica-norte/AGENTS.md").decode()
