# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""``physicalai robots`` — list and search robots available to the runtime."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from jsonargparse import ArgumentParser

from physicalai.cli._spec import SubcommandSpec  # noqa: PLC2701

if TYPE_CHECKING:
    from jsonargparse import Namespace

HELP = "List or search robots (built-in, installed plugins, and online catalog)."
_HELP_TEMPLATE = """usage: {prog} {{list,search}}

{description}

commands:
  list                          List installed robots (built-ins + plugins).
  search                        List the online catalog, marking each installed.
"""


def build_parser() -> ArgumentParser:
    """Build the ``robots`` subcommand parser.

    Returns:
        Parser exposing the ``robots`` commands (``list`` and ``search``).
    """
    parser = ArgumentParser(prog="physicalai robots", description=HELP)
    parser.add_argument("command", choices=["list", "search"], help="Robots command to run.")
    return parser


def print_help(prog: str) -> None:
    """Print lightweight help without building the full parser."""
    print(_HELP_TEMPLATE.format(prog=prog, description=HELP))  # noqa: T201


def _list_robots() -> int:
    """Print discovered robots, one per line, as ``name  class_path  (source)``.

    Returns:
        Process exit code (``0``).
    """
    from physicalai.robot import available_robots  # noqa: PLC0415
    from physicalai.robot._discovery import _BUILTIN_ROBOTS  # noqa: PLC0415, PLC2701

    robots = available_robots()
    if not robots:
        print("No robots available.")  # noqa: T201
        return 0
    width = max(len(name) for name in robots)
    for name in sorted(robots):
        source = "built-in" if name in _BUILTIN_ROBOTS else "plugin"
        print(f"{name:<{width}}  {robots[name]}  ({source})")  # noqa: T201
    return 0


def _search_robots() -> int:
    """Print the online catalog with each entry marked installed or available.

    Returns:
        Process exit code (``0`` on success, ``1`` if the catalog cannot be fetched).
    """
    from physicalai.robot import available_robots  # noqa: PLC0415
    from physicalai.robot._catalog import CatalogError, fetch_catalog  # noqa: PLC0415, PLC2701

    try:
        catalog = fetch_catalog()
    except CatalogError as exc:
        print(exc, file=sys.stderr)  # noqa: T201
        return 1

    if not catalog.robots:
        print("Catalog is empty.")  # noqa: T201
        return 0

    installed = set(available_robots())
    entries = sorted(catalog.robots, key=lambda entry: entry.name)
    name_width = max(len(entry.name) for entry in entries)
    pkg_width = max(len(entry.package) for entry in entries)
    for entry in entries:
        status = "installed" if entry.name in installed else "available"
        tag = "official" if entry.official else (entry.maintainer or "community")
        print(  # noqa: T201
            f"{entry.name:<{name_width}}  {entry.package:<{pkg_width}}  [{status}]  ({tag})  {entry.description}",
        )
    return 0


def run(parser: ArgumentParser, cfg: Namespace) -> int:  # noqa: ARG001
    """Dispatch a ``robots`` command.

    Args:
        parser: The ``robots`` parser (unused; kept for the Dispatch contract).
        cfg: Parsed configuration namespace; ``cfg.command`` selects the action.

    Returns:
        Process exit code (``0`` on success).
    """
    dispatch = {"list": _list_robots, "search": _search_robots}
    return dispatch[cfg.command]()


def register() -> SubcommandSpec:
    """Return the :class:`SubcommandSpec` for ``physicalai robots``.

    Returns:
        Spec wiring :func:`build_parser` and :func:`run` for the host parser.
    """
    return SubcommandSpec(name="robots", parser=build_parser(), dispatch=run, help=HELP)
