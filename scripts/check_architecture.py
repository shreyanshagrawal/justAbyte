#!/usr/bin/env python3
"""Check OpenCred architectural boundaries.

Enforces architecture constraints:
1. Any file under `src/opencred/core` must NOT import:
   - `opencred.cli`
   - `opencred.action`
   - `opencred.ai`
   - `opencred.simulation`
   - `typer`
   - `httpx`
   - `requests`
   - `urllib.request`
   - `socket`
2. Any file under `src/opencred/cli` must NOT import:
   - `opencred.action`

Prints each violation with file path and line number, and exits non-zero if any violation is found.
"""

import argparse
import ast
import sys
from pathlib import Path

CORE_FORBIDDEN_MODULES: tuple[str, ...] = (
    "opencred.cli",
    "opencred.action",
    "opencred.ai",
    "opencred.simulation",
    "typer",
    "httpx",
    "requests",
    "urllib.request",
    "socket",
)

CLI_FORBIDDEN_MODULES: tuple[str, ...] = ("opencred.action",)


class ArchitecturalViolation:
    """Represents a single import architectural boundary violation."""

    def __init__(
        self,
        file_path: Path,
        line_number: int,
        imported_module: str,
        forbidden_rule: str,
    ):
        self.file_path = file_path
        self.line_number = line_number
        self.imported_module = imported_module
        self.forbidden_rule = forbidden_rule

    def __str__(self) -> str:
        return (
            f"{self.file_path}:{self.line_number}: Architectural violation - "
            f"imported forbidden module '{self.imported_module}' ({self.forbidden_rule})"
        )


def _matches_forbidden(module_name: str, forbidden_patterns: tuple[str, ...]) -> str | None:
    """Check if an imported module matches or is a submodule of any forbidden prefix."""
    for pattern in forbidden_patterns:
        if module_name == pattern or module_name.startswith(f"{pattern}."):
            return pattern
    return None


def check_file_imports(
    file_path: Path,
    forbidden_modules: tuple[str, ...],
    rule_description: str,
) -> list[ArchitecturalViolation]:
    """Parse a Python source file using AST and find any forbidden imports."""
    violations: list[ArchitecturalViolation] = []
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception as err:
        violations.append(
            ArchitecturalViolation(file_path, 1, f"<parse-error: {err}>", "File parse error")
        )
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                match = _matches_forbidden(alias.name, forbidden_modules)
                if match:
                    violations.append(
                        ArchitecturalViolation(file_path, node.lineno, alias.name, rule_description)
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            # Check direct module import from `from x import y`
            match = _matches_forbidden(module_name, forbidden_modules)
            if match:
                violations.append(
                    ArchitecturalViolation(file_path, node.lineno, module_name, rule_description)
                )
            else:
                # Check if importing a forbidden submodule, e.g., `from urllib import request`
                for alias in node.names:
                    full_name = f"{module_name}.{alias.name}" if module_name else alias.name
                    sub_match = _matches_forbidden(full_name, forbidden_modules)
                    if sub_match:
                        violations.append(
                            ArchitecturalViolation(
                                file_path, node.lineno, full_name, rule_description
                            )
                        )

    return violations


def check_directory(
    dir_path: Path,
    forbidden_modules: tuple[str, ...],
    rule_description: str,
) -> list[ArchitecturalViolation]:
    """Scan all Python files in dir_path for architectural import violations."""
    if not dir_path.exists():
        return []

    violations: list[ArchitecturalViolation] = []
    for file_path in sorted(dir_path.rglob("*.py")):
        if file_path.is_file():
            violations.extend(check_file_imports(file_path, forbidden_modules, rule_description))
    return violations


def run_checks(root_dir: Path) -> list[ArchitecturalViolation]:
    """Run all architectural checks against a repository root directory."""
    violations: list[ArchitecturalViolation] = []

    # Rule 1: src/opencred/core restrictions
    core_dir = root_dir / "src" / "opencred" / "core"
    violations.extend(
        check_directory(
            core_dir,
            CORE_FORBIDDEN_MODULES,
            "core must not import cli, action, ai, simulation, or network/CLI libs",
        )
    )

    # Rule 2: src/opencred/cli restrictions
    cli_dir = root_dir / "src" / "opencred" / "cli"
    violations.extend(
        check_directory(
            cli_dir,
            CLI_FORBIDDEN_MODULES,
            "cli must not import action",
        )
    )

    return violations


def main() -> int:
    """CLI entry point for architecture verification."""
    parser = argparse.ArgumentParser(
        description="Verify OpenCred architectural boundaries and prohibited imports.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root directory (default: current directory).",
    )

    args = parser.parse_args()
    violations = run_checks(args.root)

    if violations:
        sys.stderr.write(f"Found {len(violations)} architectural boundary violation(s):\n")
        for v in violations:
            sys.stderr.write(f"  {v}\n")
        return 1

    sys.stdout.write("Architecture check PASSED: No boundary violations detected.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
