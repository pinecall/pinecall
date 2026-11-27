"""Small parsers for the words the API takes: slugs, addresses, phone numbers, JSON."""

import re
import unicodedata
from collections.abc import Mapping
from hashlib import sha256
from typing import Any, TypeIs

from runtime.exceptions import ValidationError

type Json = str | int | float | bool | list["Json"] | dict[str, "Json"] | None
type JsonObject = dict[str, Any]

A_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AN_E164 = re.compile(r"^\+[1-9]\d{1,14}$")
# Whitespace in an address would allow header injection (RFC 5322 §2.2).
AN_EMAIL = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")
# Meta's id of an account (a Facebook Page, an Instagram account), and of a contact on one: digits.
A_META_ID = re.compile(r"^\d{5,32}$")
# A contact Meta names by an id of one account, as a caller is said: `messenger:<PSID>`, `instagram:<IGSID>`.
A_META_CALLER = re.compile(r"^(messenger|instagram):\d{5,32}$")
A_FUNCTION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# A word is letters and digits, with an apostrophe or a hyphen inside it kept: "d'acord", "uh-huh".
A_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def a_mapping(value: object) -> TypeIs[Mapping[str, object]]:
    """Whether the value is a mapping, read with its keys as names."""
    return isinstance(value, Mapping)


def a_list(value: object) -> TypeIs[list[object]]:
    """Whether the value is a list."""
    return isinstance(value, list)


# The one tokeniser: what tells agreement from a turn, an echo from a caller, and two transcripts apart
# reads a text as these words. Until 2026-11 three modules each had their own, each a little different.
def words_of(text: str) -> list[str]:
    """The words of a text, in order, lowered, its punctuation dropped."""
    return [found.group(0).lower() for found in A_WORD.finditer(text)]


# What is kept under the hash of what it holds (a block of a prompt, a recorded line, an uploaded clip) is
# named by this, so the same content is the same name in every process and every release.
def sha256_of(content: str | bytes) -> str:
    """The sha256 of a text or of bytes, in hex."""
    return sha256(content.encode() if isinstance(content, str) else content).hexdigest()


def parse_slug(word: str) -> str:
    """Lowercase words joined by dashes, as an org's and an agent's names are."""
    if not A_SLUG.match(word):
        raise ValidationError(f"a slug is lowercase words joined by dashes, not {word!r}")
    return word


def slug_of(name: str) -> str:
    """The slug a name makes: accents dropped, lowercase words joined by dashes, 63 at most."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:63].rstrip("-")
    if not slug:
        raise ValidationError(f"a name makes a slug out of its letters and digits, and {name!r} has none")
    return slug


def parse_e164(number: str) -> str:
    """A phone number in E.164 form, trimmed."""
    data = number.strip()
    if not AN_E164.match(data):
        raise ValidationError(f"a number is written in E.164 form, like +59829001199, not {data!r}")
    return data


def is_e164(number: str) -> bool:
    """Whether the number is in E.164 form."""
    return AN_E164.match(number) is not None


def parse_email(address: str) -> str:
    """An email address with one @ and a domain, lowercased."""
    data = address.strip().lower()
    if not AN_EMAIL.match(data):
        raise ValidationError(f"an email has one @ and a domain, not {address!r}")
    return data


def parse_meta_id(written: str) -> str:
    """Meta's id of a Page or an Instagram account: digits alone, trimmed."""
    data = written.strip()
    if not A_META_ID.match(data):
        raise ValidationError(f"a Page or an Instagram account is named by Meta's id, digits alone, not {data!r}")
    return data


# Meta's id of an account is digits alone, as a number typed without its + would be: it is taken as one
# only where the channel asked is one whose routes answer at such ids.
def parse_address(written: str, *, by_meta_id: bool = False) -> str:
    """A route's address or a contact: an email, Meta's id of a contact (or an account, asked so), else a number."""
    data = written.strip()
    if A_META_CALLER.match(data) or (by_meta_id and A_META_ID.match(data)):
        return data
    if by_meta_id:
        return parse_meta_id(data)
    return parse_email(data) if "@" in data else parse_e164(data)


# A signed token is three parts between dots.
JWT_PARTS = 3


def is_a_jwt(secret: str) -> bool:
    """Whether the secret is shaped as a signed token rather than an API key (which holds no dots)."""
    return secret.count(".") == JWT_PARTS - 1


# What cuts a text into chunks and what batches the chunks for a vendor measure with the same estimate,
# so a chunk that fits its cap fits a window.
TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    """The tokens a text costs, estimated as its words times 1.3; no tokenizer is loaded."""
    return round(len(text.split()) * TOKENS_PER_WORD)


# A text longer than a channel takes goes out as several, cut where the writing breathes: at a
# paragraph when one ends in the second half of what fits, else at a line, else at a word, and
# mid-word only for a word with no space in it.
def cut_in_parts(text: str, longest: int) -> list[str]:
    """The text as the parts it goes out in, each within the longest a channel takes, in order."""
    parts: list[str] = []
    rest = text.strip()
    while len(rest) > longest:
        cut = _breath_in(rest[:longest])
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return [*parts, rest] if rest else parts


def _breath_in(head: str) -> int:
    breaths = [head.rfind(breath) for breath in ("\n\n", "\n", " ")]
    late = next((cut for cut in breaths if cut >= len(head) // 2), max(breaths))
    return late if late > 0 else len(head)
