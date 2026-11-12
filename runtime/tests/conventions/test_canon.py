"""The canon: a domain folder holds its files and nothing else, the tree its folders, and a domain is one context."""

from tests.conventions.canon import (
    CANON_FILES,
    DOMAINS,
    ENGINE_MODULES,
    ENTRYPOINTS,
    FOLDERS_OF_FILES,
    FOUNDATIONS,
    MOST_SERVICE_MODULES,
    ONE_CONTEXT,
    SRC,
    WHOLE,
)

# What a domain folder may hold beside the canon's files.
HOUSEKEEPING = frozenset({"__init__.py", "__pycache__"})


def test_every_domain_folder_holds_the_canon_files() -> None:
    """Each domain holds the canon's six files (module or package) and its engine modules, nothing else."""
    wrong: list[str] = []
    for domain in DOMAINS:
        allowed = CANON_FILES | ENGINE_MODULES.get(domain, frozenset())
        if not (SRC / domain).is_dir():
            continue
        for child in sorted((SRC / domain).iterdir()):
            if child.name in HOUSEKEEPING:
                continue
            stem = child.name.removesuffix(".py")
            if stem not in allowed:
                wrong.append(f"{domain}/{child.name}: not one of the canon's files")
            holds_files = f"{domain}.{stem}" in FOLDERS_OF_FILES
            if child.is_dir() and not (child / "__init__.py").is_file() and not holds_files:
                wrong.append(f"{domain}/{child.name}: a package names what others use in its __init__.py")
    assert not wrong, "\n".join(wrong)


def test_the_tree_holds_the_canons_folders() -> None:
    """Under the package: the domains, the foundations, the entrypoints, and nothing else."""
    expected = set(DOMAINS) | FOUNDATIONS | ENTRYPOINTS
    found = {child.name.removesuffix(".py") for child in SRC.iterdir() if child.name not in HOUSEKEEPING | {"public"}}
    unexpected = sorted(found - expected)
    missing = sorted(expected - found)
    assert not unexpected, f"not in the canon: {unexpected}"
    assert not (WHOLE and missing), f"missing: {missing}"


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


def test_a_domain_is_one_context() -> None:
    """A `service/` package past sixteen modules is several contexts, unless CONTRIBUTING.md says why it is one."""
    wrong: list[str] = []
    for domain in DOMAINS:
        package = SRC / domain / "service"
        if not package.is_dir() or domain in ONE_CONTEXT:
            continue
        count = sum(1 for child in package.glob("*.py") if child.name != "__init__.py")
        if count > MOST_SERVICE_MODULES:
            wrong.append(f"{domain}/service: {count} modules, over {MOST_SERVICE_MODULES}: cut the domain, or say why")
    assert not wrong, "\n".join(wrong)
