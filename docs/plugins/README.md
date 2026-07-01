# Robot Plugin Catalog

`registry.json` is the curated catalog of robots that can be installed into a
`physicalai` environment. It powers `physicalai robots search`, which lists every
catalog entry and marks each one **installed** (already importable here) or
**available** (installable from PyPI).

The CLI fetches this file from the repository's `main` branch:

```text
https://raw.githubusercontent.com/openvinotoolkit/physicalai/main/docs/plugins/registry.json
```

Robots that are merely _installed_ (built-ins and third-party packages declaring
the `physicalai.robot.drivers` entry point) already appear in `physicalai robots
list` without any catalog entry. The catalog exists purely so people can
**discover robots before installing them**.

## Schema

```jsonc
{
  "schema_version": 1,
  "robots": [
    {
      "name": "ur5e", // required: short id == entry-point name
      "package": "physicalai-ur5e", // required: PyPI package to install
      "description": "Universal Robots UR5e (RTDE).",
      "homepage": "https://github.com/acme/physicalai-ur5e",
      "maintainer": "acme", // omit for official entries
      "official": false, // true only for physicalai-org packages
    },
  ],
}
```

| Field         | Required | Meaning                                                                         |
| ------------- | -------- | ------------------------------------------------------------------------------- |
| `name`        | yes      | Short robot id; must match the `physicalai.robot.drivers` entry-point name.     |
| `package`     | yes      | PyPI package a user installs to get the robot.                                  |
| `description` | no       | One-line summary shown in `robots search`.                                      |
| `homepage`    | no       | Project or documentation URL.                                                   |
| `maintainer`  | no       | Handle shown for community entries. Omit when `official` is true.               |
| `official`    | no       | `true` only for packages maintained by the physicalai org. Defaults to `false`. |

## Add your robot

1. Implement the `Robot` protocol — see the [Robot API Reference](../reference/robot-api.md).
2. Publish `physicalai-<robot>` to PyPI, depending on `physicalai`.
3. Declare the entry point in your package's `pyproject.toml`:

   ```toml
   [project.entry-points."physicalai.robot.drivers"]
   <name> = "your_package:YourRobot"
   ```

4. Confirm conformance: `isinstance(robot, Robot)` (structural, no hardware) and,
   on real hardware, `physicalai.robot.verify_robot(robot)` (behavioral).
5. Open a PR adding **one** entry to `registry.json`.

## Reviewer checklist

- Package exists on PyPI and depends on `physicalai`.
- Entry point `physicalai.robot.drivers` is declared and `name` matches.
- No `name` collision with an existing entry or a built-in robot.
- `official` is `true` only for physicalai-org packages.
- `description` is accurate and one line.
