# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for robot driver discovery (``physicalai.robot._discovery``)."""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

import pytest

from physicalai.robot import available_robots, load_robot
from physicalai.robot._discovery import discover_robots  # noqa: PLC2701


class _FakeDriver: ...


def _fake_ep(name: str, module: str, attr: str, *, dist_name: str = "third-party") -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.module = module
    ep.attr = attr
    ep.dist.name = dist_name
    return ep


def _patch_entry_points(eps: list[MagicMock]) -> AbstractContextManager[MagicMock]:
    return patch("physicalai.robot._discovery.entry_points", return_value=eps)


class TestDiscoverRobots:
    """``discover_robots`` resolution, collisions, and laziness."""

    def test_builtins_present_without_plugins(self) -> None:
        with _patch_entry_points([]):
            robots = discover_robots()
        assert robots["so101"] == "physicalai.robot.SO101"
        assert robots["widowxai"] == "physicalai.robot.WidowXAI"
        assert robots["bimanual_widowxai"] == "physicalai.robot.BimanualWidowXAI"

    def test_third_party_value_normalized_to_dotted(self) -> None:
        ep = _fake_ep("ur5e", "physicalai_ur5e", "UR5e")
        with _patch_entry_points([ep]):
            robots = discover_robots()
        assert robots["ur5e"] == "physicalai_ur5e.UR5e"

    def test_discovery_does_not_import_plugin(self) -> None:
        ep = _fake_ep("ur5e", "physicalai_ur5e", "UR5e")
        with _patch_entry_points([ep]):
            discover_robots()
        ep.load.assert_not_called()

    def test_builtin_wins_collision_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        ep = _fake_ep("so101", "rogue_pkg", "Rogue", dist_name="rogue-pkg")
        with (
            _patch_entry_points([ep]),
            caplog.at_level(logging.WARNING, logger="physicalai.robot._discovery"),
        ):
            robots = discover_robots()
        assert robots["so101"] == "physicalai.robot.SO101"
        assert "rogue-pkg" in caplog.text

    def test_first_third_party_wins_collision(self, caplog: pytest.LogCaptureFixture) -> None:
        a = _fake_ep("ur5e", "pkg_a", "URa", dist_name="pkg-a")
        b = _fake_ep("ur5e", "pkg_b", "URb", dist_name="pkg-b")
        with (
            _patch_entry_points([a, b]),
            caplog.at_level(logging.WARNING, logger="physicalai.robot._discovery"),
        ):
            robots = discover_robots()
        assert robots["ur5e"] == "pkg_a.URa"
        assert "pkg-b" in caplog.text


class TestLoadRobot:
    """``load_robot`` import-on-demand and error handling."""

    def test_loads_plugin_class(self) -> None:
        ep = _fake_ep("fakebot", __name__, "_FakeDriver")
        with _patch_entry_points([ep]):
            cls = load_robot("fakebot")
        assert cls is _FakeDriver

    def test_unknown_name_raises_valueerror(self) -> None:
        with _patch_entry_points([]), pytest.raises(ValueError, match="Unknown robot 'nope'"):
            load_robot("nope")

    def test_unknown_name_message_lists_known(self) -> None:
        with _patch_entry_points([]), pytest.raises(ValueError, match="so101"):
            load_robot("nope")


class TestAvailableRobots:
    """``available_robots`` is the public wrapper over ``discover_robots``."""

    def test_matches_discover_robots(self) -> None:
        with _patch_entry_points([]):
            assert available_robots() == discover_robots()
