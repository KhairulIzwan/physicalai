# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""``physicalai run`` — execute a runtime (PolicyRuntime or any RobotRuntime)."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from jsonargparse import ActionConfigFile, ArgumentParser

from physicalai.cli._spec import SubcommandSpec  # noqa: PLC2701

if TYPE_CHECKING:
    from jsonargparse import Namespace

    from physicalai.runtime import RobotRuntime

logger = logging.getLogger(__name__)

HELP = "Run a trained policy (or any controller) on robot hardware."
_HELP_TEMPLATE = """usage: {prog} --config CONFIG [--run.duration_s SECONDS]

{description}

options:
  -h, --help                    Show this help message and exit.
  --config CONFIG               YAML/JSON runtime config file.
  --run.duration_s SECONDS      Stop after the given duration in seconds.

Runtime constructor arguments are available under --runtime.* when executing
the command. Use --print_config with a complete command to inspect the full
jsonargparse schema.

Supports two config schemas:
  Flat (PolicyRuntime, backward-compatible):
    runtime:
      robot: {{...}}
      model: {{...}}
      execution: {{...}}
      fps: 30.0

  General (any RobotRuntime subclass):
    runtime:
      class_path: physicalai.runtime.RobotRuntime
      init_args:
        robot: {{...}}
        controller: {{class_path: ..., init_args: {{...}}}}
        fps: 30.0
"""


def _peek_config_uses_general_schema() -> bool:
    config_path = _find_config_in_argv(sys.argv)
    if config_path is None:
        return False
    return _yaml_has_runtime_class_path(config_path)


def _find_config_in_argv(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
        if arg == "--config" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def _yaml_has_runtime_class_path(path: str) -> bool:
    import yaml  # noqa: PLC0415

    try:
        with open(path, encoding="utf-8") as f:  # noqa: PTH123
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        logger.debug("Failed to peek config %s for schema detection", path, exc_info=True)
        return False
    if isinstance(data, dict):
        runtime = data.get("runtime", {})
        if isinstance(runtime, dict):
            return "controller" in runtime
    return False


def _build_legacy_parser() -> ArgumentParser:
    from physicalai.runtime import PolicyRuntime  # noqa: PLC0415

    parser = ArgumentParser(prog="physicalai run", description=HELP)
    parser.add_argument("--config", action=ActionConfigFile, help="YAML/JSON config file.")
    parser.add_class_arguments(PolicyRuntime, "runtime")
    parser.add_method_arguments(PolicyRuntime, "run", "run")
    return parser


def _build_general_parser() -> ArgumentParser:
    from physicalai.runtime import RobotRuntime  # noqa: PLC0415

    parser = ArgumentParser(prog="physicalai run", description=HELP)
    parser.add_argument("--config", action=ActionConfigFile, help="YAML/JSON config file.")
    parser.add_class_arguments(RobotRuntime, "runtime")
    parser.add_method_arguments(RobotRuntime, "run", "run")
    return parser


def build_parser() -> ArgumentParser:
    """Build the ``run`` subcommand parser.

    Peeks at sys.argv to determine the config schema: if the config file
    declares ``runtime.class_path``, uses the general (subclass) parser;
    otherwise uses the flat PolicyRuntime parser for backward compatibility.

    Returns:
        Parser appropriate for the detected config schema.
    """
    if _peek_config_uses_general_schema():
        return _build_general_parser()
    return _build_legacy_parser()


def print_help(prog: str) -> None:
    """Print lightweight help without building the full runtime parser."""
    print(_HELP_TEMPLATE.format(prog=prog, description=HELP))  # noqa: T201


def run(parser: ArgumentParser, cfg: Namespace) -> int:
    """Instantiate the runtime from ``cfg`` and invoke ``run()``.

    Args:
        parser: The ``run`` subcommand parser used to instantiate classes from ``cfg``.
        cfg: Parsed configuration namespace produced by ``parser.parse_args``.

    Returns:
        Process exit code (``0`` on success).
    """
    init = parser.instantiate(cfg)
    runtime: RobotRuntime = init.runtime
    run_kwargs: dict = {}
    if hasattr(cfg, "run"):
        raw = cfg.run
        run_kwargs = raw.as_dict() if hasattr(raw, "as_dict") else {"duration_s": raw.duration_s}

    with runtime:
        stats = runtime.run(**run_kwargs)

    logger.info(
        "Run complete: %d steps, %d pops, %d holds, %d inferences",
        stats.steps,
        stats.total_pops,
        stats.total_holds,
        stats.inference_count,
    )
    return 0


def register() -> SubcommandSpec:
    """Return the :class:`SubcommandSpec` for ``physicalai run``.

    Returns:
        Spec wiring :func:`build_parser` and :func:`run` for the host parser.
    """
    return SubcommandSpec(name="run", parser=build_parser(), dispatch=run, help=HELP)
