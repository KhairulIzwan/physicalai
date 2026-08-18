# Hiwonder LeRobot Setup

This guide records the clean-install process for the Hiwonder Open-Source
6-Axis Robotic Arm on Ubuntu. Use Hiwonder's LeRobot package for initial
hardware bring-up. Use `physicalai` only after calibration, teleoperation, and
camera operation have been verified.

The tested host layout for this setup is:

- Workspace: `/home/user/physicalai`
- Hiwonder LeRobot environment: `lerobot`
- Python: 3.11
- Arm connections: `/dev/ttyACM0` and `/dev/ttyACM1`
- Cameras: `/dev/video*`

The serial and camera paths are examples. Confirm them again after reconnecting
USB devices.

## Current setup status

Completed on this host:

- Host checks: two serial devices and four video device nodes detected.
- Conda installation: Miniforge installed at `/home/user/miniconda3` because
  the configured proxy returned `403 Forbidden` for `repo.anaconda.com`.
  Conda `26.3.2` is installed and `auto_activate_base` is set to `false`.
- Environment: `lerobot` created with Python 3.11 and FFmpeg 7.1.1.
- Hiwonder package: LeRobot `0.3.4` installed editable at
  `/home/user/hiwonder/lerobot`.
- Servo dependency: `feetech-servo-sdk` `1.0.0` installed.
- Serial permissions: `dialout` group membership granted and confirmed active
  after reboot.
- Port identification: leader = `/dev/ttyACM0`, follower = `/dev/ttyACM1`
  (confirmed 2026-08-18).
- Calibration: leader and follower both calibrated 2026-08-18. See sections
  6.1 and 6.2 for recorded ranges. The follower required one recalibration
  pass to fix a near-zero gripper range.
- Teleoperation without vision: confirmed working 2026-08-18. See section
  6.3.
- Camera discovery: two cameras identified 2026-08-18 — `/dev/video0` =
  `handeye` (gripper), `/dev/video2` = `fixed` (environment). See section 6.4.
- Teleoperation with vision: confirmed working 2026-08-18 (arms + cameras
  connected, joint data streaming). The Rerun display window doesn't open
  in this headless session; that's a GUI limitation, not a hardware issue.

Current step:

- This host is shared with other users. Coordinate hardware access (check
  `loto-status` / contact the tagged user) before running calibration,
  teleoperation, or data collection. Confirmed with the tagged user
  (Izwan) on 2026-08-18.
- Next: collect a small test dataset. See section 7.

## 1. Hardware and safety

Follow the [Hiwonder Open-Source 6-Axis Robotic Arm User
Manual](https://wiki.hiwonder.com/projects/LeRobot/en/latest/docs/LeRobot_Open_Source_6_Axis_Robotic_Arm_User_Manual.html)
for mechanical assembly, wiring, power, and the calibration pose.

Before changing servo cables, disassembling brackets, or changing wiring,
disconnect the arm power supply. Keep the arm's motion area clear during
calibration and teleoperation.

For a pre-assembled kit, skip servo-ID programming. For a DIY kit, set IDs one
servo at a time as described in the manual; do not leave multiple unconfigured
servos connected during ID programming.

## 2. Check the Linux host

```bash
python3 --version
find /dev -maxdepth 1 \( -name 'ttyACM*' -o -name 'ttyUSB*' -o -name 'video*' \) \\
  -printf '%f\n' | sort
```

The arm should expose two serial devices after both USB control boards are
connected. On Ubuntu, grant access if required:

```bash
sudo usermod -aG dialout "$USER"
```

Log out and back in after changing group membership. Avoid using `chmod 666`
as a permanent permission fix.

## 3. Install Conda

The Hiwonder manual uses Miniconda. A user-local Miniconda installation is
preferred so it does not modify the system Python. If the corporate proxy
blocks `repo.anaconda.com`, Miniforge is a compatible Conda distribution and
can be installed instead:

```bash
cd /home/user
wget -O Miniforge3-Linux-x86_64.sh \\
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p "$HOME/miniconda3"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda config --set auto_activate_base false
```

Open a new terminal, or source the Conda profile script again before using
`conda`.

Status: done (2026-08-18). Miniforge is installed at `/home/user/miniconda3`
and verified with Conda `26.3.2`. The base environment is not activated
automatically.

## 4. Create the isolated environment

```bash
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda create -n lerobot python=3.11 ffmpeg=7.1.1 -y
conda activate lerobot
python --version
ffmpeg -version | sed -n '1p'
```

Status: done (2026-08-18). The `lerobot` environment contains Python
`3.11.15` and FFmpeg `7.1.1`.

Keep all Hiwonder commands in this environment. Do not install the Hiwonder
package into the `physicalai` development environment.

## 5. Install Hiwonder's LeRobot package

Download `lerobot.zip` from the Hiwonder manual's **Software Tools & Source
Code** section:

[Hiwonder software and source-code downloads](https://drive.google.com/drive/folders/1znOVSfGEBI5AMCkcNf1wbgCxmS5_Zfm5?usp=sharing)

The Google Drive folder downloads a wrapper archive. On this host it was saved
as `Source Code-20260818T043226Z-1-001.zip`, containing the actual nested
`Source Code/lerobot.zip` archive.

Extract it outside the `physicalai` repository, for example:

```bash
mkdir -p /home/user/hiwonder-download /home/user/hiwonder
unzip '/home/user/Downloads/Source Code-20260818T043226Z-1-001.zip' \
  'Source Code/lerobot.zip' -d /home/user/hiwonder-download
unzip /home/user/hiwonder-download/'Source Code/lerobot.zip' \
  -d /home/user/hiwonder
find /home/user/hiwonder -maxdepth 2 -type f \\
  \( -name 'pyproject.toml' -o -name 'setup.py' -o -name 'README*' \) -print
```

Enter the extracted project directory and follow the package's own install
instructions. Hiwonder's package may differ from the public Hugging Face
LeRobot release, so do not replace it with `pip install lerobot`:

```bash
cd /home/user/hiwonder/lerobot
conda activate lerobot
python -m pip install -e ".[feetech]"
```

If the archive has a different directory name or extra install command, use
the command documented in its included README instead.

Verify that the package imports before connecting to the robot:

```bash
python -c 'import lerobot; print(lerobot.__file__)'
python -m pip show lerobot feetech-servo-sdk
```

Expected results include LeRobot `0.3.4`, Feetech SDK `1.0.0`, and the editable
project location `/home/user/hiwonder/lerobot`.

Status: done (2026-08-18). LeRobot `0.3.4` and Feetech SDK `1.0.0` are
installed in the `lerobot` environment from `/home/user/hiwonder/lerobot`.

## 6. Bring up the arms

Identify the leader and follower ports by connecting the follower first and
then the leader, as described in the Hiwonder manual. Do not assume that
`/dev/ttyACM0` is always the leader. The installed package provides
`lerobot-find-port`. The command requires physically unplugging one USB
controller at a time; it does not identify leader versus follower by itself.

First check access:

```bash
id -nG | tr ' ' '\n' | grep -Fx dialout
```

If that command prints nothing, run this once and then log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

Then identify the ports in two passes:

1. Connect only the follower controller, run the command, disconnect the USB
  cable when prompted, note the reported path, and reconnect it.
2. Connect only the leader controller, repeat the command, note its reported
  path, and reconnect it.

Do not unplug servo power or servo cables during this procedure. Keep the arm
power and mechanical connections unchanged; only remove the controller's USB
data cable.

Run the command from the Hiwonder environment:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-find-port
```

Record the result here before continuing:

```text
Leader:   /dev/ttyACM0
Follower: /dev/ttyACM1
Date:     2026-08-18
```

Status: port identification done (2026-08-18). The active user is in the
`dialout` group, both controller nodes are present with group read/write
permissions, and the two-pass unplug test confirmed the mapping above.

Note: this host is shared. `lerobot-find-port` printed a "SYSTEM CURRENTLY IN
USE" notice for another tagged user during this session. Coordinate before
running hardware commands (calibration, teleoperation, data collection) on a
shared machine, and check `loto-status` if unsure.

Run the Hiwonder commands in this order:

1. Optional servo-ID setup for DIY kits.
2. Leader calibration.
3. Follower calibration.
4. Teleoperation without vision.
5. Camera discovery.
6. Teleoperation with vision.

Use the actual paths detected on this host in every command. Stop with
`Ctrl+C` if motion is unexpected. Recalibrate rather than continuing when
joint direction, amplitude, or initial position is wrong.

### 6.1 Leader arm calibration

Rotate all leader joints to the calibration initial position shown in the
Hiwonder manual first. Then run:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 \
  --teleop.id=leader_arm
```

Press Enter to start (or `c` then Enter to recalibrate), then manually rotate
each joint through its full range as prompted.

Status: done (2026-08-18). Calibration saved to
`/home/user/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/leader_arm.json`.

Recorded ranges (ticks):

| joint | min | max |
|---|---|---|
| shoulder_pan | 747 | 3294 |
| shoulder_lift | 2045 | 3764 |
| elbow_flex | 694 | 2070 |
| wrist_flex | 1581 | 2277 |
| wrist_roll | 951 | 2988 |
| gripper | 869 | 3269 |

### 6.2 Follower arm calibration

Rotate all follower joints to the calibration initial position, then run:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
  --robot.id=follower_arm
```

Status: done (2026-08-18). Calibration saved to
`/home/user/.cache/huggingface/lerobot/calibration/robots/so101_follower/follower_arm.json`.

Recorded ranges (ticks), recalibrated 2026-08-18:

| joint | min | max |
|---|---|---|
| shoulder_pan | 776 | 3258 |
| shoulder_lift | 2041 | 3844 |
| elbow_flex | 489 | 2053 |
| wrist_flex | 1442 | 2290 |
| wrist_roll | 1129 | 3378 |
| gripper | 1803 | 3479 |

**Resolved:** the first calibration attempt produced a near-zero gripper
range (2047-2050) because the gripper was not exercised through its full
travel. Recalibrating with `c` at the reuse prompt and fully opening/closing
the gripper fixed it (range now 1803-3479, comparable to the leader's
869-3269).

### 6.3 Teleoperation without vision

With both arms calibrated, confirm the leader drives the follower correctly
before connecting cameras:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 \
  --teleop.id=leader_arm --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 --robot.id=follower_arm
```

Press `Ctrl+C` to stop. If direction, amplitude, or initial position looks
wrong, recalibrate rather than continuing.

Status: done (2026-08-18). Follower correctly mirrors the leader arm.

### 6.4 Camera discovery and teleoperation with vision

Camera discovery command:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-find-cameras opencv
```

Result (2026-08-18): only two distinct physical cameras are detected, at
`/dev/video0` and `/dev/video2`. `/dev/video1` and `/dev/video3` are
secondary/metadata nodes for the same two devices (each icspring camera
exposes two `/dev/video*` nodes), not separate cameras. Test images were
saved to `outputs/captured_images`.

Identified by image content:

| index_or_path | role | notes |
|---|---|---|
| `/dev/video0` | `handeye` (gripper camera) | extreme close-range, mounted on/near the follower gripper |
| `/dev/video2` | `fixed` (environment camera) | wide view of the follower arm and desk area |

Camera IDs are not permanently fixed. Re-run `lerobot-find-cameras opencv` and
re-check the saved images after reconnecting USB cameras, changing ports, or
switching machines.

Vision teleoperation command:

```bash
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 \
  --teleop.id=leader_arm --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 --robot.id=follower_arm \
  --robot.cameras='{
    "fixed": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30},
    "handeye": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}
  }' \
  --display_data=true
```

Status: done (2026-08-18). Both arms and both cameras connected
successfully; joint positions streamed at ~7 Hz while teleoperating.

**Known limitation:** with `--display_data=true`, the Rerun visualization
window failed to open (`neither WAYLAND_DISPLAY nor WAYLAND_SOCKET nor
DISPLAY is set`). This is a headless/remote-session GUI limitation, not a
robot or camera fault — the underlying camera and robot data pipeline worked
correctly. Omit `--display_data` (or set it to `false`) when running from a
session without a graphical display; use the Rerun viewer only from a
machine/session that has one.

## 7. Collect a small test dataset

Only collect data after non-vision and vision teleoperation are stable. Start
with a small number of episodes to validate camera ordering, storage, and task
reset behavior. Keep camera count, names, resolution, scene, lighting, and
initial arm pose consistent between collection, training, and inference.

Test parameters chosen on 2026-08-18:

| parameter | value |
|---|---|
| `HF_USER` | `wansnap` |
| `dataset.single_task` | "pick up the cube and place it in the box" |
| `dataset.num_episodes` | 5 |
| `dataset.push_to_hub` | `false` (local only) |

Command:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower_arm \
  --robot.cameras='{
    "fixed": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30},
    "handeye": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}
  }' \
  --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 --teleop.id=leader_arm \
  --dataset.repo_id=wansnap/pick_cube_test \
  --dataset.single_task="pick up the cube and place it in the box" \
  --dataset.num_episodes=5 \
  --dataset.push_to_hub=false
```

Controls during recording: right arrow = save episode and continue, left
arrow = discard and re-record the current episode, `Ctrl+C`/Esc = stop.

Dataset saves by default under
`~/.cache/huggingface/lerobot/wansnap/pick_cube_test`.

Status: blocked (2026-08-18). `lerobot-record` failed at robot connect with:

```
RuntimeError: FeetechMotorsBus motor check failed on port '/dev/ttyACM1':
Missing motor IDs:
  - 6 (expected model: 777)
Full expected motor list (id: model_number): {1: 777, 2: 777, 3: 777, 4: 777, 5: 777, 6: 777}
Full found motor list (id: model_number): {1: 777, 2: 777, 3: 777, 4: 777, 5: 777}
```

Servo ID 6 (gripper) on the **follower** arm did not respond, despite working
during calibration and vision teleoperation minutes earlier. Suspected cause:
a loose daisy-chain servo cable to the gripper, possibly disturbed by the
heavy gripper motion during the follower recalibration pass. Action:
physically check the follower's gripper servo cable connection (both ends)
and power before retrying `lerobot-record`.

Also being tested: running `lerobot-record` directly on the physical machine
instead of over this remote/SSH session, to rule out a remote-session-specific
USB/serial glitch. Note that USB serial communication is a host-level
operation and is not normally affected by SSH vs. local execution unless the
session is itself a VM/container with passthrough USB, so a loose connector
remains the more likely cause. Result pending.

## 8. Integrate with `physicalai` later

This repository already contains an SO-101 runtime backend and can read
LeRobot-style calibration JSON files. It is not a replacement for Hiwonder's
bring-up and data-collection package.

After the Hiwonder workflow is verified:

```bash
cd /home/user/physicalai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[so101,capture]'
```

Then validate the runtime with the examples under
`examples/so101/` before attempting policy deployment. Keep the Hiwonder
Conda environment and the `physicalai` environment separate until the device
protocol, joint order, calibration format, and camera observations have been
confirmed compatible.

## Clean reinstall checklist

To repeat the software setup from scratch without touching the repository:

```bash
rm -rf "$HOME/miniconda3" "$HOME/hiwonder"
rm -f "$HOME/Miniforge3-Linux-x86_64.sh"
```

The command above removes only the user-local Conda and Hiwonder directories.
Do not run it if those locations contain unrelated environments or data.