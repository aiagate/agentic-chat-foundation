"""Architecture fitness tests for presentation layer dependencies."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "app"


def _iter_presentation_files() -> list[Path]:
    return sorted(SRC_ROOT.joinpath("presentation").rglob("*.py"))


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


def test_presentation_support_modules_do_not_depend_on_infrastructure() -> None:
    """Presentation support modules must stay independent of runtime layers."""

    support_modules = [
        path for path in _iter_presentation_files() if path.name != "__main__.py"
    ]
    violations = _find_forbidden_imports(
        support_modules,
        ("app.bootstrap", "app.domain", "app.infrastructure"),
    )

    assert not violations, _render_violation_message(violations)


def _render_violation_message(
    violations: list[tuple[Path, str]],
) -> str:
    if not violations:
        return "presentation: no violations"

    lines = ["presentation architecture violations:"]
    for path, module in violations:
        lines.append(f"- {path}: {module}")
    return "\n".join(lines)
