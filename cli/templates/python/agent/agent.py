"""{{Title}}: the class is the agent — its state, its tools, and beside it in views/ its prompt."""

import re
from typing import Literal

from pinecall import Agent, tool

# What a model in a hurry writes where the caller said nothing: never a message.
NOTHING_SAID = re.compile(r"^(n/?a|none|unknown|unspecified|not (specified|given|provided|said)|tbd|-)?$", re.IGNORECASE)


class {{Class}}(Agent):
    """You answer the phone for the business. Short sentences: everything you say is read aloud.
    You answer what the business's documents say. For anything else you take a message: who is calling
    and what it is about. You never promise when they will hear back.
    """

    stage: Literal["ask", "done"] = "ask"
    message: dict[str, str] | None = None

    @tool(stage="ask", pii=("name",))
    def take_message(self, name: str, about: str) -> dict[str, str]:
        """Writes down the caller's message. Call it as soon as the caller has said their name and what the call is
        about, in that same turn and without reading it back first; never with a blank or a guess.
        """
        if any(NOTHING_SAID.match(said.strip()) for said in (name, about)):
            raise ValueError("Nothing was written down: ask the caller for what they have not said yet, their name or what the call is about.")
        self.message = {"name": name, "about": about}
        self.stage = "done"
        return self.message
