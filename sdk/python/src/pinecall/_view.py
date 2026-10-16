"""The view: a Jinja template beside the class, rendered with the state in scope."""

import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template

from pinecall import _config

SUFFIX = ".jinja"

# Where a class keeps its compiled view, once looked for; NOWHERE when it has none.
CACHE = "_pinecall_view"
NOWHERE = "nowhere"


def environment(folder: Path | None) -> Environment:
    """Jinja as a prompt wants it: a tag's own line leaves no line; an unknown name raises."""
    return Environment(
        loader=None if folder is None else FileSystemLoader(folder),
        undefined=StrictUndefined,
        # A prompt is text for a model, not HTML: there is nothing to escape.
        autoescape=False,  # noqa: S701
        trim_blocks=True,
        lstrip_blocks=True,
        # An included file keeps its last newline, or its last line runs into the next one.
        keep_trailing_newline=True,
    )


def beside(cls: type) -> Path | None:
    """Where the class's view would be: `views/<slug>.jinja` beside the file that defines it."""
    module = sys.modules.get(cls.__module__)
    file = getattr(module, "__file__", None)
    if not isinstance(file, str):
        return None
    return Path(file).parent / "views" / f"{_config.slug_of(cls)}{SUFFIX}"


def template_of(cls: type) -> Template | None:
    """The class's view: its own `view_template`, else its file, else its parent's; read once."""
    cached: object = vars(cls).get(CACHE)
    if isinstance(cached, Template):
        return cached
    if cached == NOWHERE:
        return None
    found = found_for(cls)
    setattr(cls, CACHE, NOWHERE if found is None else found)
    return found


def found_for(cls: type) -> Template | None:
    """The first view along the class and its parents."""
    for step in cls.__mro__:
        inline: object = vars(step).get("view_template")
        if isinstance(inline, str):
            return environment(None).from_string(inline)
        path = beside(step)
        if path is not None and path.is_file():
            return environment(path.parent).get_template(path.name)
    return None


def rendered(
    cls: type,
    state: Mapping[str, object],
    call: object,
    *,
    resumed: bool,
    remembered: Sequence[str],
) -> str:
    """The view's text for this state: every field by its name, `call`, `resumed`, `remembers`."""
    template = template_of(cls)
    if template is None:
        return ""

    def remembers(text: str) -> bool:
        return any(text in fact for fact in remembered)

    scope = {**state, "call": call, "resumed": resumed, "remembers": remembers}
    return tidy(template.render(scope))


def tidy(text: str) -> str:
    """A template is laid out for a person: the trailing spaces and the blank-line runs come off."""
    lines = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", lines).strip()
