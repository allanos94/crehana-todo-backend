"""Architecture test: `domain` and `application` must stay framework-free.

Walks every module under `app.domain` and `app.application` with `ast` and
fails if any of them imports FastAPI, SQLAlchemy, Pydantic, PyJWT, pwdlib,
Starlette, or `app.infrastructure`. This mechanically enforces ADR-01's
dependency rule (domain -> stdlib only; application -> domain + stdlib only).
"""

import ast
import importlib
from pathlib import Path

FORBIDDEN_MODULES = (
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "jwt",
    "pwdlib",
    "starlette",
    "app.infrastructure",
)

LAYER_ROOTS = ("src/app/domain", "src/app/application")


def _iter_python_files(layer_root: Path) -> list[Path]:
    return sorted(layer_root.rglob("*.py"))


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def _is_forbidden(module_name: str) -> str | None:
    for forbidden in FORBIDDEN_MODULES:
        if module_name == forbidden or module_name.startswith(forbidden + "."):
            return forbidden
    return None


def test_domain_and_application_are_real_packages() -> None:
    """`domain`/`application` must be regular packages (own `__init__.py`),
    not implicit namespace packages, so the layer boundary is explicit."""
    for module_name in ("app.domain", "app.application"):
        module = importlib.import_module(module_name)
        assert module.__file__ is not None, f"{module_name} has no __init__.py"


def test_domain_and_application_do_not_import_frameworks() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    for layer_root_str in LAYER_ROOTS:
        layer_root = repo_root / layer_root_str
        for path in _iter_python_files(layer_root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for module_name in _imported_module_names(tree):
                forbidden = _is_forbidden(module_name)
                if forbidden is not None:
                    violations.append(
                        f"{path.relative_to(repo_root)} imports {forbidden!r}"
                    )

    assert (
        not violations
    ), "Framework imports found in domain/application:\n" + "\n".join(violations)
