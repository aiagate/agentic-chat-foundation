"""Architecture fitness tests for use case entrypoint structure."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USECASES_ROOT = PROJECT_ROOT / "src" / "app" / "usecases"
INFRASTRUCTURE_ROOT = PROJECT_ROOT / "src" / "app" / "infrastructure"

_ALLOWED_CLASS_SUFFIXES = ("Command", "Query", "Result", "Handler")
_ALLOWED_HANDLER_METHODS = {"__init__", "handle"}


@dataclass(frozen=True)
class _Violation:
    path: Path
    line: int
    message: str


def _usecase_modules() -> list[tuple[Path, ast.Module]]:
    modules: list[tuple[Path, ast.Module]] = []
    for path in sorted(USECASES_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules.append((path, tree))
    return modules


def _find_violations(path: Path, tree: ast.Module) -> list[_Violation]:
    violations: list[_Violation] = []
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    handlers = [node for node in classes if node.name.endswith("Handler")]
    requests = [
        node
        for node in classes
        if node.name.endswith("Command") or node.name.endswith("Query")
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "app.usecases."
        ):
            violations.append(
                _Violation(
                    path=path,
                    line=node.lineno,
                    message=f"use case must not import another use case: {node.module}",
                )
            )
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "send_async"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "Mediator"
        ):
            violations.append(
                _Violation(
                    path=path,
                    line=node.lineno,
                    message="use case must not dispatch another use case via Mediator",
                )
            )
        if isinstance(node.func, ast.Name) and node.func.id.endswith("Handler"):
            violations.append(
                _Violation(
                    path=path,
                    line=node.lineno,
                    message=f"use case must not instantiate handler {node.func.id!r}",
                )
            )

    if len(handlers) != 1:
        violations.append(
            _Violation(
                path=path,
                line=1,
                message=f"module must define exactly one Handler; found {len(handlers)}",
            )
        )
    if len(requests) != 1:
        violations.append(
            _Violation(
                path=path,
                line=1,
                message=(
                    "module must define exactly one Command or Query; "
                    f"found {len(requests)}"
                ),
            )
        )
    if len(handlers) == 1 and len(requests) == 1:
        handler_prefix = handlers[0].name.removesuffix("Handler")
        request_prefix = requests[0].name.removesuffix("Command").removesuffix("Query")
        if handler_prefix != request_prefix:
            violations.append(
                _Violation(
                    path=path,
                    line=handlers[0].lineno,
                    message=(
                        f"Handler prefix {handler_prefix!r} must match request "
                        f"prefix {request_prefix!r}"
                    ),
                )
            )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.append(
                _Violation(
                    path=path,
                    line=node.lineno,
                    message=f"top-level helper function {node.name!r} is not allowed",
                )
            )
            continue

        if not isinstance(node, ast.ClassDef):
            continue

        if not node.name.endswith(_ALLOWED_CLASS_SUFFIXES):
            violations.append(
                _Violation(
                    path=path,
                    line=node.lineno,
                    message=(
                        f"class {node.name!r} must be a Command, Query, Result, "
                        "or Handler"
                    ),
                )
            )
            continue

        if not node.name.endswith("Handler"):
            continue

        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name not in _ALLOWED_HANDLER_METHODS:
                violations.append(
                    _Violation(
                        path=path,
                        line=child.lineno,
                        message=(
                            f"handler method {child.name!r} is not allowed; "
                            "use cases expose only __init__ and handle"
                        ),
                    )
                )

    return violations


def test_usecase_entrypoints_contain_only_boundary_types_and_handle() -> None:
    """Use case entrypoints must not accumulate hidden helper responsibilities."""
    violations = [
        violation
        for path, tree in _usecase_modules()
        for violation in _find_violations(path, tree)
    ]

    assert not violations, _render_violations(violations)


def test_infrastructure_does_not_depend_on_usecases() -> None:
    """Infrastructure implementations must not invoke application entrypoints."""
    violations: list[_Violation] = []
    for path in sorted(INFRASTRUCTURE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "app.usecases."
            ):
                violations.append(
                    _Violation(
                        path=path,
                        line=node.lineno,
                        message=(
                            "infrastructure must not import an application "
                            f"entrypoint: {node.module}"
                        ),
                    )
                )

    assert not violations, _render_violations(violations)


def _render_violations(violations: list[_Violation]) -> str:
    lines = ["use case structure violations:"]
    for violation in violations:
        relative_path = violation.path.relative_to(PROJECT_ROOT)
        lines.append(f"- {relative_path}:{violation.line}: {violation.message}")
    return "\n".join(lines)
