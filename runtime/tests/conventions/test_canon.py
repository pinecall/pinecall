"""Rule 1, the canon: a domain folder holds the canon's files and nothing else; the tree holds the canon's folders."""

from tests.conventions.canon import CANON_FILES, DOMAINS, ENGINE_MODULES, ENTRYPOINTS, FOUNDATIONS, SRC

# What a domain folder may hold beside the canon's files.
HOUSEKEEPING = frozenset({"__init__.py", "__pycache__"})


def test_every_domain_folder_holds_the_canon_files() -> None:
    """Each domain holds the canon's six files (module or package) and its engine modules, nothing else."""
    wrong: list[str] = []
    for domain in DOMAINS:
        allowed = CANON_FILES | ENGINE_MODULES.get(domain, frozenset())
        for child in sorted((SRC / domain).iterdir()):
            if child.name in HOUSEKEEPING:
                continue
            stem = child.name.removesuffix(".py")
            if stem not in allowed:
                wrong.append(f"{domain}/{child.name}: not one of the canon's files")
            if child.is_dir() and not (child / "__init__.py").is_file() and stem != "library":
                wrong.append(f"{domain}/{child.name}: a package names what others use in its __init__.py")
    assert not wrong, "\n".join(wrong)


def test_the_tree_holds_the_canons_folders() -> None:
    """Under the package: the domains, the foundations, the entrypoints, and nothing else."""
    expected = set(DOMAINS) | FOUNDATIONS | ENTRYPOINTS
    found = {child.name.removesuffix(".py") for child in SRC.iterdir() if child.name not in HOUSEKEEPING | {"public"}}
    unexpected = sorted(found - expected)
    missing = sorted(expected - found)
    assert not unexpected and not missing, f"not in the canon: {unexpected}; missing: {missing}"


def test_a_package_of_a_canon_file_names_what_others_use() -> None:
    """A `service/` or `endpoints/` package exports through `__init__.py`: `__all__` or the router."""
    wrong: list[str] = []
    for domain in DOMAINS:
        for name in ("service", "endpoints"):
            package = SRC / domain / name
            if not package.is_dir():
                continue
            text = (package / "__init__.py").read_text(encoding="utf-8")
            if "__all__" not in text and "router" not in text:
                wrong.append(f"{domain}/{name}/__init__.py names nothing")
    assert not wrong, "\n".join(wrong)
