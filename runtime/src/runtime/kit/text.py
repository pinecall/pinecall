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
A_FUNCTION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def a_mapping(value: object) -> TypeIs[Mapping[str, object]]:
    """Whether the value is a mapping, read with its keys as names."""
    return isinstance(value, Mapping)


def a_list(value: object) -> TypeIs[list[object]]:
    """Whether the value is a list."""
    return isinstance(value, list)


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


# A signed token is three parts between dots.
JWT_PARTS = 3


def is_a_jwt(secret: str) -> bool:
    """Whether the secret is shaped as a signed token rather than an API key (which holds no dots)."""
    return secret.count(".") == JWT_PARTS - 1
