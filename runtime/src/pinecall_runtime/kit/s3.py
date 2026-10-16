"""An S3-compatible object store: any endpoint that takes AWS's version 4 signature."""

import hashlib
import hmac
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from pinecall_runtime.config import Settings
from pinecall_runtime.exceptions import UpstreamError

ALGORITHM = "AWS4-HMAC-SHA256"
NO_BODY = hashlib.sha256(b"").hexdigest()
UNSIGNED = "UNSIGNED-PAYLOAD"

# What S3 answers for an object that is not there, which `head` and `delete` read as an answer.
NOT_FOUND = 404


@dataclass(frozen=True, slots=True)
class Credentials:
    """What a request is signed with."""

    region: str
    access_key_id: str
    secret_access_key: str


class ObjectStore:
    """An endpoint and the key the box reads and writes it with; path-style addressing."""

    def __init__(self, endpoint: str, credentials: Credentials, http: httpx.AsyncClient) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.credentials = credentials
        self.http = http

    @classmethod
    def from_settings(cls, settings: Settings, http: httpx.AsyncClient) -> "ObjectStore | None":
        """The store the settings name whole; None when any of its four is missing."""
        if not (settings.s3_endpoint and settings.s3_region and settings.s3_access_key_id):
            return None
        if settings.s3_secret_access_key is None:
            return None
        credentials = Credentials(
            settings.s3_region,
            settings.s3_access_key_id,
            settings.s3_secret_access_key.get_secret_value(),
        )
        return cls(settings.s3_endpoint, credentials, http)

    def url_of(self, bucket: str, name: str) -> str:
        """The object's address."""
        return f"{self.endpoint}/{bucket}/{quote(name, safe='/')}"

    async def put(self, bucket: str, name: str, body: bytes, content_type: str) -> None:
        """Write the object whole."""
        url = self.url_of(bucket, name)
        headers = self._signed("PUT", url, {"content-type": content_type}, hashlib.sha256(body).hexdigest())
        answer = await self.http.put(url, content=body, headers=headers, timeout=60.0)
        _checked(answer, f"PUT {bucket}/{name}")

    async def head(self, bucket: str, name: str) -> int | None:
        """The object's size, or None when it is not there."""
        url = self.url_of(bucket, name)
        answer = await self.http.head(url, headers=self._signed("HEAD", url, {}), timeout=15.0)
        if answer.status_code == NOT_FOUND:
            return None
        _checked(answer, f"HEAD {bucket}/{name}")
        return int(answer.headers["content-length"])

    async def read(self, bucket: str, name: str, *, offset: int = 0, length: int | None = None) -> AsyncIterator[bytes]:
        """The object's bytes from the offset, in pieces; a range when a length is given."""
        url = self.url_of(bucket, name)
        headers: dict[str, str] = {}
        if length is not None:
            headers["range"] = f"bytes={offset}-{offset + length - 1}"
        elif offset:
            headers["range"] = f"bytes={offset}-"
        async with self.http.stream("GET", url, headers=self._signed("GET", url, headers), timeout=60.0) as answer:
            _checked(answer, f"GET {bucket}/{name}")
            async for piece in answer.aiter_bytes():
                yield piece

    async def delete(self, bucket: str, name: str) -> None:
        """Remove the object; removing one that is not there is nothing."""
        url = self.url_of(bucket, name)
        answer = await self.http.delete(url, headers=self._signed("DELETE", url, {}), timeout=15.0)
        if answer.status_code != NOT_FOUND:
            _checked(answer, f"DELETE {bucket}/{name}")

    def _signed(
        self, method: str, url: str, headers: Mapping[str, str], payload_sha256: str = NO_BODY
    ) -> dict[str, str]:
        return sign(method, url, headers, self.credentials, payload_sha256, datetime.now(UTC))


# https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html
def sign(
    method: str,
    url: str,
    headers: Mapping[str, str],
    credentials: Credentials,
    payload_sha256: str,
    now: datetime,
) -> dict[str, str]:
    """The headers with the date, the payload's hash and the Authorization that signs them all."""
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    parts = urlsplit(url)
    signed = {
        **{name.lower(): value.strip() for name, value in headers.items()},
        "host": parts.netloc,
        "x-amz-content-sha256": payload_sha256,
        "x-amz-date": stamp,
    }
    names = sorted(signed)
    canonical = "\n".join(
        (
            method,
            parts.path or "/",
            "",
            "".join(f"{name}:{signed[name]}\n" for name in names),
            ";".join(names),
            payload_sha256,
        )
    )
    scope = f"{stamp[:8]}/{credentials.region}/s3/aws4_request"
    to_sign = "\n".join((ALGORITHM, stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()))
    key = f"AWS4{credentials.secret_access_key}".encode()
    for step in (stamp[:8], credentials.region, "s3", "aws4_request"):
        key = hmac.new(key, step.encode(), hashlib.sha256).digest()
    proof = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = (
        f"{ALGORITHM} Credential={credentials.access_key_id}/{scope}, "
        f"SignedHeaders={';'.join(names)}, Signature={proof}"
    )
    return {**signed, "authorization": authorization}


def _checked(answer: httpx.Response, what: str) -> None:
    if answer.status_code >= httpx.codes.BAD_REQUEST:
        raise UpstreamError(f"the object store refused {what}: {answer.status_code}")
