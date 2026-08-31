"""The layering, enforced.

A rule in AGENTS.md that nothing checks is a rule that decays. These walk the
imports and fail on the arrows that must not exist, so the first commit that
reaches from a use case into an adapter fails here rather than at review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "upnext"

# Each layer, and what it is allowed to import from within the package.
ALLOWED = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "config": {"config"},
    "adapters": {"domain", "application", "config", "adapters"},
    # The composition root exists to name concrete implementations, so it is
    # the one module allowed to see everything. `__main__` is the console entry
    # point and does nothing but call into an inbound adapter.
    "bootstrap": {"domain", "application", "config", "adapters", "bootstrap"},
    "__main__": {"adapters"},
}


def modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if p.name != "__init__.py")


def layer_of(path: Path) -> str:
    relative = path.relative_to(SRC)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def upnext_imports(path: Path) -> set[str]:
    """Every `upnext.<layer>` this module imports, as layer names."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("upnext."):
            found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[1] for alias in node.names if alias.name.startswith("upnext."))
    return found


@pytest.mark.parametrize("module", modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_a_module_imports_only_from_the_layers_below_it(module: Path) -> None:
    layer = layer_of(module)
    allowed = ALLOWED.get(layer, set())
    forbidden = upnext_imports(module) - allowed
    assert not forbidden, f"{module.relative_to(SRC)} is in {layer!r} and may not import {sorted(forbidden)}"


def test_the_domain_depends_on_nothing_else_in_the_package() -> None:
    """The arrow that matters most: everything points at the domain, never out."""
    for module in modules():
        if layer_of(module) == "domain":
            assert upnext_imports(module) <= {"domain"}, module


def test_only_inbound_adapters_write_to_a_stream() -> None:
    """`print` and `sys.exit` outside inbound take down a request mid-flight."""
    offenders = []
    for module in modules():
        relative = module.relative_to(SRC)
        if relative.parts[:2] == ("adapters", "inbound"):
            continue
        source = module.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{relative}:{node.lineno} print")
    assert not offenders, offenders
