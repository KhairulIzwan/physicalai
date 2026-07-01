# Robot Plugins — Discovery, Distribution & Catalog

## Overview

The [Robot API Reference](../../reference/robot-api.md) defines _what_ a robot
is — the `Robot` Protocol. This document covers _how robots are packaged,
discovered, and distributed_.

The key finding of this review: **most of what a "plugin system" would provide
already exists in the repo.** Robots are already constructed from config, and
third-party robots already work, via jsonargparse `class_path` + `init_args`.
A registry would add only short-name ergonomics, a `robots list` command, and a
catalog of _uninstalled_ robots. This document is therefore scoped around one
real decision (see [The Decision](#the-decision)), not a from-scratch
design.

> Status: **scope decided (A2), design-only.** Two robots already ship in-tree
> (SO101, Trossen WidowXAI). The contract and construction paths exist. The
> registry is approved as a thin alias + discovery layer (A2); not yet
> implemented. See [The Decision](#the-decision).

---

## What Already Exists in the Repo (verified 2026-06-30)

| Capability                    | Where                                                                             | Implication                                                                                 |
| ----------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `Robot` Protocol contract     | `robot/interface.py` (`runtime_checkable`; 6 members, returns `RobotObservation`) | Extension contract — done                                                                   |
| Structural conformance        | `isinstance(robot, Robot)` (`runtime_checkable`)                                  | Hardware-less CI gate — done                                                                |
| Behavioral conformance        | `verify_robot()` (`robot/verify.py`)                                              | Real-hardware, self-attested check — **not** a substitute for the structural gate           |
| Two in-tree robots            | `robot/so101/`, `robot/trossen/` (WidowXAI, BimanualWidowXAI)                     | The "2nd robot" trigger has already arrived                                                 |
| Lazy loading of robot classes | `robot/__init__.py` `__getattr__`                                                 | Heavy SDKs (`feetech-servo-sdk`, `trossen-arm`) load only on use                            |
| Optional extras per robot     | `pyproject.toml` (`so101`, `trossen`; `ur`/`abb`/`franka` empty)                  | Dependency isolation — done; placeholders confirm more robots coming                        |
| **Construction from config**  | `PolicyRuntime` + jsonargparse `add_class_arguments` / `instantiate`              | **Any robot, incl. third-party, instantiates from a YAML `class_path` + `init_args` today** |
| Config example                | `examples/runtime/runtime.yaml` (`robot.class_path: physicalai.robot.SO101`)      | The selection + construction UX already ships                                               |
| Manifest hardware descriptors | `manifest.py` `HardwareSpec`/`RobotSpec`                                          | `RobotSpec.type` is **informational only** ("e.g. Koch v1.1") — it does not resolve a class |

The consequence: **heterogeneous construction (port vs IP vs creds) is a solved
problem.** `init_args` is exactly the per-robot constructor payload. A
third-party robot needs no registry to be usable — pip-install it, point
`class_path` at it, done.

---

## In-House Registry Precedents

If we add a robot registry, it should mirror patterns the codebase already uses
three times — not invent a new one:

| Precedent                | Location                                                    | Shape                                                                                    |
| ------------------------ | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `ComponentRegistry`      | `inference/component_factory.py`                            | name → `class_path`, with `type`/`class_path` dual resolution (`ComponentSpec`)          |
| `RuntimeAdapterRegistry` | `inference/adapters/registry.py` + `adapters/_discovery.py` | in-process `@register` for built-ins **+** entry-point discovery for third-party         |
| CLI subcommands          | `cli/main.py` `_BUILTINS` + `cli/_discovery.py`             | in-process built-ins dict **+** `physicalai.cli.subcommands` entry points; built-ins win |

The shared idea across all three: **built-ins registered in-process; third-party
discovered via entry points.** But the two discovery modules differ in a way
that matters here:

- **CLI (`cli/_discovery.py`) is lazy** — it returns un-loaded `EntryPoint`s and
  warns on name collisions; nothing imports until a subcommand is selected.
- **Adapters (`adapters/_discovery.py`) are eager** — `_load_external_adapters()`
  calls `ep.load()` + `register(registry)` at import time.

A robot registry must **mirror the CLI (lazy) shape**, not the adapter shape:
heavy SDKs (`feetech-servo-sdk`, `trossen-arm`) must not import during
discovery. Discovery scans metadata only; the import happens later in
`load_robot()`.

> Correction to the earlier draft: built-in robots are **not** registered as
> entry points. Following the precedent, built-ins live in an in-process map;
> the entry-point group is the _third-party_ extension surface.

---

## The Decision

Given construction already works via `class_path`, what does a registry add, and
is it worth building now?

| Option                          | Build                                                                                                                                                     | What it adds                                                                                 | Verdict                                                                                        |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **A1 — No registry**            | Nothing in code; a docs-only catalog page lists known robots.                                                                                             | Discoverability via docs only.                                                               | Cheapest. `class_path` stays the one mechanism.                                                |
| **A2 — Thin alias + discovery** | `physicalai.robot.drivers` entry points, in-process built-ins, `available_robots()` / `load_robot()` resolving to `class_path`, `physicalai robots list`. | Short names, `robots list`, third-party auto-discovery. Construction still via `class_path`. | **Recommended** — reuses the `ComponentRegistry` + lazy-CLI patterns, ~1–2 days, non-breaking. |
| **A3 — Full registry**          | A2 + registry as the primary selection path + `registry.json` catalog + `robots search`.                                                                  | Browse uninstalled robots; `--robot` shorthand.                                              | Defer the catalog half to Phase 2; don't let it replace `class_path`.                          |

**Decision: A2** (chosen 2026-06-30). Keep `class_path` as the load-bearing
construction mechanism; add the registry purely as an ergonomic + discovery
layer that resolves a short name to a `class_path`. The catalog portion (A3) is
deferred to Phase 2.

**Locked naming decision (forever — changing it breaks every published plugin):**
the entry-point group is **`physicalai.robot.drivers`** — singular `robot` to
match the package path, mirroring `physicalai.cli.subcommands` /
`physicalai.inference.adapters` (dotted package path + contributed-noun);
"drivers" matches in-repo terminology. The short name (e.g. `so101`) is the
canonical robot id.

The sections below specify the chosen A2 design. It is **design-only** for now —
not yet implemented.

---

## Packaging

**First-party robots stay in-tree** under `physicalai.robot.*`, gated by optional
extras (the pattern already in `pyproject.toml`):

```toml
[project.optional-dependencies]
so101   = ["feetech-servo-sdk"]          # real, shipping
trossen = ["trossen-arm>=1.9.0"]         # real, shipping
ur      = []                             # placeholder — coming
abb     = []                             # placeholder — coming
franka  = []                             # placeholder — coming
robots  = [                              # umbrella extra
    "physicalai[ur]", "physicalai[abb]", "physicalai[franka]",
    "physicalai[trossen]; python_version < '3.14'", "physicalai[so101]",
]
```

**Third-party robots are separate pip packages** depending on `physicalai`.
They already work via `class_path` today; an entry point (A2) only adds
discoverability. They implement the Protocol and import no internals.

Rationale: the core install stays useful out of the box, while the boundary for
heavy/conflicting native deps (libfranka, ur-rtde) is a package boundary — the
same reasoning as the existing `physicalai` / `physicalai-train` split.

---

## Discovery & Resolution (A2)

Built-in robots live in an **in-process map**; the `physicalai.robot.drivers`
**entry-point group** is the third-party surface. Discovery is lazy and warns on
collisions, mirroring `cli/_discovery.py`.

```toml
# Third-party physicalai-ur5e/pyproject.toml — built-ins do NOT need this
[project.entry-points."physicalai.robot.drivers"]
ur5e = "physicalai_ur5e:UR5e"
```

```python
# src/physicalai/robot/_discovery.py — mirrors the LAZY cli/_discovery.py
import logging
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)
ENTRY_POINT_GROUP = "physicalai.robot.drivers"

# Built-ins registered in-process (name -> class_path), like cli/main.py _BUILTINS.
# Uses the public dotted path (matches runtime.yaml's `physicalai.robot.SO101`).
# NOTE: this duplicates the PascalCase symbols in robot/__init__.py __getattr__;
# adding a robot means updating both (or derive one from the other).
_BUILTIN_ROBOTS: dict[str, str] = {
    "so101": "physicalai.robot.SO101",
    "widowxai": "physicalai.robot.WidowXAI",
    "bimanual_widowxai": "physicalai.robot.BimanualWidowXAI",
}

def discover_robots() -> dict[str, str]:
    """{name: dotted class_path}. Built-ins win collisions. Imports nothing.

    Third-party entry points are normalized from the "module:Class" form to a
    dotted path so the value is a valid jsonargparse `class_path`. Reading
    `ep.module` / `ep.attr` parses metadata only — it does NOT import the class.
    """
    discovered = dict(_BUILTIN_ROBOTS)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        dotted = f"{ep.module}.{ep.attr}"   # "physicalai_ur5e:UR5e" -> "physicalai_ur5e.UR5e"
        if ep.name in discovered:
            logger.warning(
                "robot plugin %r from %s collides with an existing entry; keeping the first.",
                ep.name, ep.dist.name if ep.dist else "<unknown>",
            )
            continue
        discovered[ep.name] = dotted
    return discovered
```

**Lazy boundary (the invariant the design sells):**

- `available_robots()` → metadata scan only, **no class import** (safe at
  startup / in `robots list`).
- `load_robot(name)` → the **import point**; the robot's heavy SDK loads here.

Both are public — add them to `robot/__init__.py` `__all__`.

```python
from physicalai.robot import available_robots, load_robot

available_robots()             # {"so101": "physicalai.robot.SO101", ...}  (no imports)
SO101 = load_robot("so101")    # imports + returns the class (deps load here)

# The real construction path is unchanged — a short name simply expands to:
#   runtime.robot.class_path = available_robots()["so101"]
# jsonargparse then builds it from init_args, exactly as today.
```

`load_robot()` raises a clear error listing known names on a miss. This reuses
the `ComponentRegistry` idea (name → `class_path`) rather than adding a new
abstraction. Conformance is two-tier: `isinstance(robot, Robot)` (structural,
hardware-less) and `verify_robot()` (behavioral, needs hardware).

---

## Catalog — Uninstalled Discovery (Phase 2)

Deferred until external contributors or a third-party ecosystem appear. A single
curated `registry.json` in-repo lists robots you can install but haven't.
PR-based contribution = the curation gate (open-source-native).

```jsonc
// docs/plugins/registry.json
{
  "schema_version": 1,
  "robots": [
    {
      "name": "so101",
      "package": "physicalai",
      "description": "SO-101 6-DOF arm",
      "homepage": "https://github.com/openvinotoolkit/physicalai",
      "official": true,
    },
    {
      "name": "ur5e",
      "package": "physicalai-ur5e",
      "description": "Universal Robots UR5e (RTDE)",
      "homepage": "https://github.com/acme/physicalai-ur5e",
      "maintainer": "acme",
      "official": false,
    },
  ],
}
```

`httpx` is **not** a runtime dependency; use `urllib.request` (below) or add the
dep when Phase 2 lands.

```python
import json
import urllib.request

def catalog() -> list[dict]:
    with urllib.request.urlopen(CATALOG_URL) as resp:   # noqa: S310
        data = json.load(resp)["robots"]
    installed = set(available_robots())
    for entry in data:
        entry["installed"] = entry["name"] in installed
    return data
```

---

## CLI Surface

The runtime is **config-driven today** — robot selection lives in the YAML
`class_path`, and that path already works:

```bash
physicalai run --config runtime.yaml          # robot from runtime.robot.class_path
```

The registry (A2) adds a discovery command; it does not replace `--config`.
`robots` is a new built-in CLI subcommand — a `SubcommandSpec` added to
`_BUILTINS` in `cli/main.py`, exactly like `run` (`cli/run.py`):

```bash
physicalai robots list            # installed: built-ins + entry points
physicalai robots search          # + uninstalled (catalog, Phase 2)
```

A `--robot <name>` shorthand is **optional and secondary**: it would expand a
short name to `runtime.robot.class_path`, but only cleanly covers
single-argument constructors. Multi-arg robots (creds, IK objects) still use the
YAML `class_path` + `init_args`. Decide whether the shorthand is worth the
asymmetry before building it.

---

## Trust & Security

- **`official`** = maintained by the physicalai org. **listed** = a maintainer
  merged the catalog PR. Neither means "hardware-tested" — we don't own most of
  the hardware. Documented honestly; no `verified` flag that implies otherwise.
- **Installing a plugin = trusting its code.** Entry-point loading executes
  plugin code (same trust model as pytest plugins).
- Name uniqueness (extra / entry-point name / catalog) is enforced by **PR
  review**, not code. The manifest's `RobotSpec.type` is informational and not
  part of this namespace.

---

## Contribution Workflow (Open Source)

A plugin author:

1. implements the `Robot` Protocol per the
   [Robot API Reference](../../reference/robot-api.md) (6 members; returns a
   `RobotObservation`),
2. publishes `physicalai-<robot>` to PyPI,
3. declares a `physicalai.robot.drivers` entry point,
4. checks `isinstance(robot, Robot)` (structural) and, with hardware,
   `verify_robot()` (behavioral, self-attested),
5. opens a PR adding one `registry.json` entry.

Reviewer checks: package exists, entry point declared, no name collision,
accurate description.

---

## Phasing

The "2nd robot" trigger has already passed (SO101 + Trossen ship today) and A2
is the chosen scope, so Phase 1 is ready to implement once we move past
design-only.

| Phase      | Scope                                                                                                                                    | Status / Trigger                |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **1 (A2)** | `physicalai.robot.drivers` group + `_discovery.py` (lazy) + in-process built-ins + `available_robots`/`load_robot` + `robots` subcommand | Ready now (2 robots in-tree)    |
| **2**      | `registry.json` catalog + `robots search` + contribution docs                                                                            | 3rd-party contributors arrive   |
| Optional   | `--robot` shorthand for simple constructors                                                                                              | Only if CLI ergonomics demanded |

---

## Resolved by This Review

- **Heterogeneous construction (was "largest gap"): solved.** jsonargparse
  `class_path` + `init_args` already builds any robot from config
  (`runtime.yaml`). No `from_config` convention or `SupportsConfig` Protocol is
  needed.
- **Manifest `type` → class mapping: not needed.** `RobotSpec.type` is
  informational; instantiation is driven by `class_path`, not manifest type.
- **Built-in registration: settled.** Built-ins are in-process (mirroring
  `cli/main.py` `_BUILTINS` and the adapter registry), not entry points.
- **Canonical id: convention.** The entry-point / built-in name is the canonical
  id (e.g. `so101`); the matching extra is a convenience and need not be
  enforced in code.

## Remaining Open Questions

1. **`--robot` shorthand: deferred (decide later).** YAML `class_path` is the
   selection UX for now. Revisit a `--robot <name>` shorthand if CLI ergonomics
   demand it; note it only cleanly covers single-argument constructors.
2. **Catalog hosting (Phase 2 only).** Which URL/branch serves `registry.json`,
   and do we add a CI job to flag yanked PyPI packages? Defer until Phase 2.

---

## Summary

| Decision              | Choice                                                             |
| --------------------- | ------------------------------------------------------------------ |
| Construction          | jsonargparse `class_path` + `init_args` (**already exists**)       |
| Registry scope        | A2 (chosen): thin alias + discovery layer                          |
| Discovery group       | `physicalai.robot.drivers` entry points (third-party)              |
| Built-ins             | In-process map, mirroring `cli/main.py` / adapter registry         |
| Resolution            | name → `class_path` (reuses `ComponentRegistry` shape)             |
| Uninstalled discovery | Curated `registry.json`, PR-based (**Phase 2**)                    |
| Trust                 | `official`/listed; reviewed ≠ hardware-tested                      |
| Conformance           | `isinstance(.., Robot)` (structural) + `verify_robot()` (hardware) |

---

## References

- [Robot API Reference](../../reference/robot-api.md) — the `Robot` Protocol contract (source of truth)
- `examples/runtime/runtime.yaml` — robot selected/constructed via `class_path`
- `src/physicalai/inference/component_factory.py` — `ComponentRegistry` (name → class_path)
- `src/physicalai/inference/adapters/_discovery.py` — in-process + entry-point registry precedent
- `src/physicalai/cli/main.py`, `src/physicalai/cli/_discovery.py` — CLI plugin precedent
- `src/physicalai/inference/manifest.py` — `HardwareSpec`/`RobotSpec` (`type` is informational)
- `src/physicalai/robot/interface.py` — `Robot` Protocol; `verify.py` — conformance gate
