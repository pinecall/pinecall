"""What the alerts' tests raise an alert with: the agents' logs as a record, and a hosted app that went down."""

import os

from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.wire.feed import AppFailed

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])
ADDRESS = "https://cloud.example.test"

A_FAILED_APP = AppFailed(app="support", host="support-r4-e8033b63", release=4, why="secrets: 403\nmore lines")


class WrittenLogs:
    """The agents' logs as the alert sees them: every entry appended, by agent."""

    def __init__(self) -> None:
        self.written: list[tuple[str, str, JsonObject | None]] = []

    def agent(self, slug: str) -> "WrittenLog":
        """The agent's own log."""
        return WrittenLog(self, slug)


class WrittenLog:
    """One agent's log, appending into the record."""

    def __init__(self, logs: WrittenLogs, slug: str) -> None:
        self.logs, self.slug = logs, slug

    async def append(self, kind: str, data: JsonObject | None = None) -> object:
        """One entry kept."""
        self.logs.written.append((self.slug, kind, data))
        return None
