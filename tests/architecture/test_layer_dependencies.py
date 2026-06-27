"""Architecture fitness tests for layer dependency boundaries.

These tests keep the dependency direction explicit:
- domain and contracts must not depend on outer implementation layers
- usecases must not depend on infrastructure implementation modules
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "app"

FORBIDDEN_OUTER_LAYER_PREFIXES = (
    "app.bootstrap",
    "app.infrastructure",
    "app.presentation",
    "app.usecases",
)


def _iter_python_files(*parts: str) -> list[Path]:
    return sorted((SRC_ROOT.joinpath(*parts)).rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or node.module is None:
                continue
            imported_modules.add(node.module)
    return imported_modules


def _find_forbidden_imports(
    files: Iterable[Path],
    forbidden_prefixes: tuple[str, ...],
) -> list[tuple[Path, str]]:
    violations: list[tuple[Path, str]] = []
    for path in files:
        for module in _imported_modules(path):
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            ):
                violations.append((path.relative_to(PROJECT_ROOT), module))
    return violations


@pytest.mark.parametrize(
    ("layer_name", "relative_parts"),
    [
        ("domain", ("domain",)),
        ("contracts", ("contracts",)),
    ],
)
def test_core_layers_do_not_depend_on_outer_layers(
    layer_name: str,
    relative_parts: tuple[str, ...],
) -> None:
    """Core layers must not import implementation-only outer layers."""
    violations = _find_forbidden_imports(
        _iter_python_files(*relative_parts),
        FORBIDDEN_OUTER_LAYER_PREFIXES,
    )
    assert not violations, _render_violation_message(layer_name, violations)


def test_usecases_keep_legacy_infrastructure_imports_bounded() -> None:
    """Use cases must not import infrastructure implementation modules."""
    violations = _find_forbidden_imports(
        _iter_python_files("usecases"),
        ("app.infrastructure",),
    )

    assert not violations, _render_violation_message("usecases", violations)


def _render_violation_message(
    layer_name: str,
    violations: list[tuple[Path, str]],
) -> str:
    if not violations:
        return f"{layer_name}: no violations"

    lines = [f"{layer_name} architecture violations:"]
    for path, module in violations:
        lines.append(f"- {path}: {module}")
    return "\n".join(lines)
