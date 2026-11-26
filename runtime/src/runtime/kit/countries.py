"""The country an address is in, from DB-IP's free table, packed once into ranges read by halving."""

import gzip
import ipaddress
import struct
from bisect import bisect_right
from dataclasses import dataclass
from functools import cache
from pathlib import Path

# DB-IP's "IP to Country Lite" (db-ip.com, CC BY 4.0): a line a range, `first,last,country`. Packed
# as two tables, the IPv4 ranges and the IPv6 ones, each its rows' first addresses, last addresses
# and two letters, so a lookup halves one of them and no line is parsed while a visitor waits.
MAGIC = b"PCC1"
V4 = struct.Struct(">II2s")
V6 = struct.Struct(">16s16s2s")
HEAD = struct.Struct(">4sII")
# What DB-IP writes for an address of no country (a private range, a reserved one).
NOWHERE = b"ZZ"


@dataclass(frozen=True, slots=True)
class Table:
    """The packed ranges, each family's first addresses sorted, beside their last address and country."""

    v4_first: tuple[int, ...]
    v4_rows: bytes
    v6_first: tuple[bytes, ...]
    v6_rows: bytes

    def country_of(self, address: str) -> str | None:
        """The two letters of the country the address is in; None for one in none, or no address."""
        try:
            parsed = ipaddress.ip_address(address.strip())
        except ValueError:
            return None
        if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
            parsed = parsed.ipv4_mapped
        if isinstance(parsed, ipaddress.IPv4Address):
            found = bisect_right(self.v4_first, int(parsed)) - 1
            if found < 0:
                return None
            _, last, country = V4.unpack_from(self.v4_rows, found * V4.size)
            return _country_named(country) if int(parsed) <= last else None
        packed = parsed.packed
        found = bisect_right(self.v6_first, packed) - 1
        if found < 0:
            return None
        _, last, country = V6.unpack_from(self.v6_rows, found * V6.size)
        return _country_named(country) if packed <= last else None


def pack(table_gz: Path, out: Path) -> int:
    """Write DB-IP's gzipped table as the packed file this module reads; how many ranges it holds."""
    v4: list[bytes] = []
    v6: list[bytes] = []
    with gzip.open(table_gz, "rt", encoding="ascii") as lines:
        for line in lines:
            first_said, last_said, country = line.strip().split(",")
            first, last = ipaddress.ip_address(first_said), ipaddress.ip_address(last_said)
            code = country.encode("ascii")[:2]
            if isinstance(first, ipaddress.IPv4Address):
                v4.append(V4.pack(int(first), int(last), code))
            else:
                v6.append(V6.pack(first.packed, last.packed, code))
    # DB-IP writes its rows in order; sorted again, so a table from anywhere reads the same.
    v4.sort()
    v6.sort()
    out.write_bytes(HEAD.pack(MAGIC, len(v4), len(v6)) + b"".join(v4) + b"".join(v6))
    return len(v4) + len(v6)


# Read once a process, at its first lookup: thirteen megabytes, no parsing beyond the first addresses.
@cache
def table_at(path: str) -> Table | None:
    """The packed table at the path; None where there is none, or it is not one."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < HEAD.size:
        return None
    magic, v4_count, v6_count = HEAD.unpack_from(data)
    if magic != MAGIC or len(data) != HEAD.size + v4_count * V4.size + v6_count * V6.size:
        return None
    v4_rows = data[HEAD.size : HEAD.size + v4_count * V4.size]
    v6_rows = data[HEAD.size + v4_count * V4.size :]
    v4_first = tuple(first for first, _, _ in V4.iter_unpack(v4_rows))
    v6_first = tuple(first for first, _, _ in V6.iter_unpack(v6_rows))
    return Table(v4_first=v4_first, v4_rows=v4_rows, v6_first=v6_first, v6_rows=v6_rows)


def _country_named(country: bytes) -> str | None:
    return None if country == NOWHERE or not country.isalpha() else country.decode("ascii")
