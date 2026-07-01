# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``physicalai robots`` CLI subcommand."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from jsonargparse import ArgumentParser

from physicalai.cli import robots as robots_module
from physicalai.cli._spec import SubcommandSpec  # noqa: PLC2701
from physicalai.cli.main import main
from physicalai.robot._catalog import CatalogEntry, CatalogError, RobotCatalog  # noqa: PLC2701

_FAKE_ROBOTS = {
    "so101": "physicalai.robot.SO101",
    "ur5e": "physicalai_ur5e.UR5e",
}


class TestRobotsRegister:
    """``register`` returns a valid ``SubcommandSpec``."""

    def test_returns_robots_spec(self) -> None:
        spec = robots_module.register()
        assert isinstance(spec, SubcommandSpec)
        assert spec.name == "robots"
        assert isinstance(spec.parser, ArgumentParser)
        assert callable(spec.dispatch)
        assert spec.help


class TestRobotsParser:
    """``build_parser`` accepts ``list`` and rejects unknown commands."""

    def test_accepts_list(self) -> None:
        cfg = robots_module.build_parser().parse_args(["list"])
        assert cfg.command == "list"

    def test_rejects_unknown_command(self) -> None:
        with pytest.raises(SystemExit) as exc:
            robots_module.build_parser().parse_args(["bogus"])
        assert exc.value.code != 0

    def test_print_help_outputs_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        robots_module.print_help("physicalai robots")
        out = capsys.readouterr().out
        assert "usage: physicalai robots" in out
        assert "search" in out


class TestRobotsList:
    """``robots list`` output."""

    def test_lists_builtin_and_plugin_robots(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = robots_module.build_parser()
        cfg = parser.parse_args(["list"])
        with patch("physicalai.robot.available_robots", return_value=_FAKE_ROBOTS):
            exit_code = robots_module.run(parser, cfg)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "so101" in out
        assert "physicalai_ur5e.UR5e" in out
        assert "(built-in)" in out
        assert "(plugin)" in out

    def test_empty_registry_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = robots_module.build_parser()
        cfg = parser.parse_args(["list"])
        with patch("physicalai.robot.available_robots", return_value={}):
            exit_code = robots_module.run(parser, cfg)
        assert exit_code == 0
        assert "No robots available." in capsys.readouterr().out

    def test_main_dispatches_robots_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("physicalai.robot.available_robots", return_value=_FAKE_ROBOTS):
            exit_code = main(["robots", "list"])
        assert exit_code == 0
        assert "so101" in capsys.readouterr().out


class TestRobotsSearch:
    """``robots search`` output and error handling."""

    def test_accepts_search(self) -> None:
        cfg = robots_module.build_parser().parse_args(["search"])
        assert cfg.command == "search"

    def test_lists_catalog_with_install_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        catalog = RobotCatalog(
            robots=[
                CatalogEntry(name="so101", package="physicalai", official=True, description="SO-101"),
                CatalogEntry(name="ur5e", package="physicalai-ur5e", maintainer="acme", description="UR5e"),
            ],
        )
        parser = robots_module.build_parser()
        cfg = parser.parse_args(["search"])
        with (
            patch("physicalai.robot.available_robots", return_value={"so101": "physicalai.robot.SO101"}),
            patch("physicalai.robot._catalog.fetch_catalog", return_value=catalog),
        ):
            exit_code = robots_module.run(parser, cfg)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "so101" in out
        assert "[installed]" in out
        assert "ur5e" in out
        assert "[available]" in out

    def test_fetch_failure_returns_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = robots_module.build_parser()
        cfg = parser.parse_args(["search"])
        with patch("physicalai.robot._catalog.fetch_catalog", side_effect=CatalogError("offline")):
            exit_code = robots_module.run(parser, cfg)
        assert exit_code == 1
        assert "offline" in capsys.readouterr().err

    def test_main_dispatches_robots_search(self, capsys: pytest.CaptureFixture[str]) -> None:
        catalog = RobotCatalog(robots=[CatalogEntry(name="ur5e", package="physicalai-ur5e")])
        with (
            patch("physicalai.robot.available_robots", return_value={}),
            patch("physicalai.robot._catalog.fetch_catalog", return_value=catalog),
        ):
            exit_code = main(["robots", "search"])
        assert exit_code == 0
        assert "ur5e" in capsys.readouterr().out
