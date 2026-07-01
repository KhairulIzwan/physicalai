# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Robot driver discovery for the ``physicalai.robot.drivers`` entry-point group.

Built-in robots live in an in-process map (:data:`_BUILTIN_ROBOTS`); third-party
robots are contributed through the ``physicalai.robot.drivers`` entry-point
group. Discovery is **lazy**: it resolves names to dotted ``class_path`` strings
by reading entry-point metadata only and never imports a robot class, so heavy
hardware SDKs (``feetech-servo-sdk``, ``trossen-arm``) stay unimported until
:func:`physicalai.robot.load_robot` is called.

This mirrors :mod:`physicalai.cli._discovery` (the lazy CLI subcommand variant),
not the eager adapter-discovery variant.
"""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

#: Entry-point group used by other distributions to contribute robot drivers.
#:
#: Each entry point maps a short robot name to a ``"module:Class"`` target, e.g.
#: ``ur5e = "physicalai_ur5e:UR5e"``. The target class must implement the
#: :class:`~physicalai.robot.interface.Robot` protocol.
ENTRY_POINT_GROUP = "physicalai.robot.drivers"

# Short name -> public dotted ``class_path``. ``physicalai.robot.<Name>`` resolves
# through this package's ``__getattr__``, so each built-in here requires a matching
# branch there; ``load_robot`` imports via this path and ``runtime.yaml`` displays it.
_BUILTIN_ROBOTS: dict[str, str] = {
    "so101": "physicalai.robot.SO101",
    "widowxai": "physicalai.robot.WidowXAI",
    "bimanual_widowxai": "physicalai.robot.BimanualWidowXAI",
}


def discover_robots() -> dict[str, str]:
    """Return a ``{name: dotted class_path}`` map of all available robots.

    Built-in robots always win name collisions; among third-party entry points,
    the first one returned by :func:`importlib.metadata.entry_points` wins and a
    ``WARNING`` is logged for the loser. Entry-point targets in ``"module:Class"``
    form are normalized to a dotted ``module.Class`` path so the value is a valid
    jsonargparse ``class_path``.

    Reading ``ep.module`` / ``ep.attr`` parses metadata only — it does **not**
    import the robot class.

    Returns:
        Mapping of robot short name to its fully-qualified dotted class path.
        No robot class is imported by this function.
    """
    discovered = dict(_BUILTIN_ROBOTS)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in discovered:
            logger.warning(
                "physicalai.robot: driver '%s' from %s collides with an existing robot; keeping the first.",
                ep.name,
                ep.dist.name if ep.dist else "<unknown>",
            )
            continue
        discovered[ep.name] = f"{ep.module}.{ep.attr}"
    return discovered


def available_robots() -> dict[str, str]:
    """Return a ``{name: class_path}`` map of all discoverable robots.

    Includes built-in robots and any installed third-party drivers contributed
    via the ``physicalai.robot.drivers`` entry-point group. No robot class is
    imported; values are dotted ``class_path`` strings suitable for a YAML
    ``class_path`` field.

    Returns:
        Mapping of robot short name to its fully-qualified dotted class path.
    """
    return discover_robots()


def load_robot(name: str) -> type:
    """Resolve a robot short name to its class, importing it on demand.

    Args:
        name: A registered robot short name (e.g. ``"so101"``).
            Use :func:`available_robots` to list the known names.

    Returns:
        The robot class. Importing it loads the robot's hardware SDK, so call
        this only when you intend to construct and use the robot.

    Raises:
        ValueError: If *name* is not a known robot. The message lists the
            available names.
    """
    robots = discover_robots()
    class_path = robots.get(name)
    if class_path is None:
        known = ", ".join(sorted(robots)) or "<none>"
        msg = f"Unknown robot {name!r}. Available robots: {known}"
        raise ValueError(msg)
    module_path, class_name = class_path.rsplit(".", maxsplit=1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
