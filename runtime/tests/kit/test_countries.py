"""Tests for the country of an address: DB-IP's table packed, then halved for IPv4, IPv6 and a mapped address."""

import gzip
from pathlib import Path

from runtime.kit import countries

TABLE = """0.0.0.0,0.255.255.255,ZZ
10.0.0.0,10.255.255.255,ZZ
181.47.0.0,181.47.255.255,AR
83.45.0.0,83.45.255.255,ES
2800:810::,2800:810:ffff:ffff:ffff:ffff:ffff:ffff,AR
2a02:9130::,2a02:9130:ffff:ffff:ffff:ffff:ffff:ffff,ES
"""


def a_table(tmp_path: Path) -> countries.Table:
    """The table above, as DB-IP ships it and packed as the image packs it."""
    shipped = tmp_path / "dbip.csv.gz"
    shipped.write_bytes(gzip.compress(TABLE.encode("ascii")))
    packed = tmp_path / "countries.bin"
    assert countries.pack(shipped, packed) == 6
    table = countries.table_at(str(packed))
    assert table is not None
    return table


def test_an_address_is_in_the_country_of_its_range_in_both_families(tmp_path: Path) -> None:
    table = a_table(tmp_path)
    assert table.country_of("181.47.10.5") == "AR"
    assert table.country_of("83.45.0.1") == "ES"
    assert table.country_of("2800:810:4c3::1") == "AR"
    assert table.country_of("2a02:9130::1") == "ES"
    assert table.country_of("::ffff:181.47.10.5") == "AR", "an IPv4 address an IPv6 socket names is read as IPv4"


def test_an_address_in_no_country_in_no_range_or_none_at_all_is_in_none(tmp_path: Path) -> None:
    table = a_table(tmp_path)
    assert table.country_of("10.1.2.3") is None, "DB-IP's ZZ is no country"
    assert table.country_of("8.8.8.8") is None, "between two ranges"
    assert table.country_of("2001:db8::1") is None
    assert table.country_of("not an address") is None


def test_a_file_that_is_missing_or_not_a_table_is_no_table(tmp_path: Path) -> None:
    assert countries.table_at(str(tmp_path / "nothing.bin")) is None
    broken = tmp_path / "broken.bin"
    broken.write_bytes(b"PCC1" + b"\x00" * 3)
    assert countries.table_at(str(broken)) is None
