# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Robot catalog — discovery of *uninstalled* robots.

The catalog is a curated ``registry.json`` served from the project repository.
Unlike :mod:`physicalai.robot._discovery` (which lists robots already installed
in the current environment), the catalog lists robots that exist in the wider
ecosystem and can be ``pip install``-ed. It powers ``physicalai robots search``.
"""

from __future__ import annotations

import http.client
import urllib.request

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CATALOG_URL = "https://raw.githubusercontent.com/openvinotoolkit/physicalai/main/docs/plugins/registry.json"


class CatalogError(RuntimeError):
    """Raised when the robot catalog cannot be fetched or parsed."""


class CatalogEntry(BaseModel):
    """One robot listed in the catalog.

    Attributes:
        name: Short robot id (matches the ``physicalai.robot.drivers`` entry-point name).
        package: PyPI package that provides the robot.
        description: Human-readable summary.
        homepage: Project or documentation URL.
        maintainer: Maintainer handle for community (non-official) entries.
        official: ``True`` when maintained by the physicalai org.
    """

    model_config = ConfigDict(frozen=True)
    name: str
    package: str
    description: str = ""
    homepage: str = ""
    maintainer: str = ""
    official: bool = False


class RobotCatalog(BaseModel):
    """Parsed ``registry.json`` document.

    Attributes:
        schema_version: Catalog schema version.
        robots: Catalog entries.
    """

    model_config = ConfigDict(frozen=True)
    schema_version: int = 1
    robots: list[CatalogEntry] = Field(default_factory=list)


def load_catalog(data: str | bytes) -> RobotCatalog:
    """Parse catalog JSON into a :class:`RobotCatalog`.

    Args:
        data: Raw ``registry.json`` text or bytes.

    Returns:
        The parsed catalog.

    Raises:
        CatalogError: If the JSON is malformed or violates the schema.
    """
    try:
        return RobotCatalog.model_validate_json(data)
    except ValidationError as exc:
        msg = f"Invalid robot catalog: {exc}"
        raise CatalogError(msg) from exc


def fetch_catalog(url: str = CATALOG_URL, *, timeout: float = 10.0) -> RobotCatalog:
    """Fetch and parse the remote robot catalog.

    Args:
        url: Catalog URL. Defaults to :data:`CATALOG_URL`.
        timeout: Socket timeout in seconds.

    Returns:
        The parsed catalog.

    Raises:
        CatalogError: If the catalog cannot be retrieved or parsed.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            data = response.read()
    except (OSError, http.client.HTTPException) as exc:
        msg = f"Could not fetch robot catalog from {url}: {exc}"
        raise CatalogError(msg) from exc
    return load_catalog(data)
