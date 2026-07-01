# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the robot catalog (``physicalai.robot._catalog``)."""

from __future__ import annotations

import http.client
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from physicalai.robot._catalog import (  # noqa: PLC2701
    CATALOG_URL,
    CatalogError,
    RobotCatalog,
    fetch_catalog,
    load_catalog,
)

_REGISTRY_JSON = Path(__file__).resolve().parents[3] / "docs" / "plugins" / "registry.json"
_VALID = '{"schema_version": 1, "robots": [{"name": "ur5e", "package": "physicalai-ur5e"}]}'


class TestLoadCatalog:
    """``load_catalog`` parsing and validation."""

    def test_parses_valid_json(self) -> None:
        catalog = load_catalog(_VALID)
        assert isinstance(catalog, RobotCatalog)
        assert catalog.robots[0].name == "ur5e"
        assert catalog.robots[0].package == "physicalai-ur5e"
        assert catalog.robots[0].official is False

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(CatalogError):
            load_catalog('{"robots": [{"name": "x"}]}')

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(CatalogError):
            load_catalog("not json")


class TestFetchCatalog:
    """``fetch_catalog`` network handling."""

    def test_fetches_and_parses(self) -> None:
        response = MagicMock()
        response.read.return_value = _VALID.encode()
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=None)
        with patch("urllib.request.urlopen", return_value=response):
            catalog = fetch_catalog()
        assert catalog.robots[0].name == "ur5e"

    def test_network_error_raises_catalogerror(self) -> None:
        with (
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")),
            pytest.raises(CatalogError, match="Could not fetch"),
        ):
            fetch_catalog()

    def test_connection_error_raises_catalogerror(self) -> None:
        with (
            patch("urllib.request.urlopen", side_effect=ConnectionResetError("reset")),
            pytest.raises(CatalogError, match="Could not fetch"),
        ):
            fetch_catalog()

    def test_incomplete_read_raises_catalogerror(self) -> None:
        with (
            patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"")),
            pytest.raises(CatalogError, match="Could not fetch"),
        ):
            fetch_catalog()


class TestShippedRegistry:
    """The in-repo ``docs/plugins/registry.json`` is valid and complete."""

    def test_registry_json_is_valid(self) -> None:
        if not _REGISTRY_JSON.exists():
            pytest.skip("registry.json not present in this checkout")
        catalog = load_catalog(_REGISTRY_JSON.read_text(encoding="utf-8"))
        names = {entry.name for entry in catalog.robots}
        assert {"so101", "widowxai", "bimanual_widowxai"} <= names
        assert all(entry.package for entry in catalog.robots)

    def test_catalog_url_points_to_registry(self) -> None:
        assert CATALOG_URL.endswith("docs/plugins/registry.json")
