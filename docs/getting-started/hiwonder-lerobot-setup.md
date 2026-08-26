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
- Calibration: follower and leader both recalibrated successfully 2026-08-26.
  See sections 6.1 and 6.2 for recorded ranges. The follower required one
  recalibration pass to fix a near-zero gripper range; the leader required a
  fresh pass after invalid encoder-wrap values were observed.
- Teleoperation without vision: confirmed working 2026-08-18. See section
  6.3.
- Camera discovery: two cameras identified 2026-08-18 — `/dev/video0` =
  `handeye` (gripper), `/dev/video2` = `fixed` (environment). See section 6.4.
- Teleoperation with vision: confirmed working 2026-08-18 (arms + cameras
  connected, joint data streaming). The Rerun display window doesn't open
  in this headless session; that's a GUI limitation, not a hardware issue.
- USB stability: a faulty Type-C cable and a marginal hub port caused
  intermittent device loss and corrupted camera frames on 2026-08-19. Both
  resolved by reseating cables and swapping hub ports. See section 10.

Verified working configuration (2026-08-19):

| Device | Serial | Hub port | Role |
|---|---|---|---|
| `/dev/ttyACM0` | `5C4C124628` | `5.1` | leader |
| `/dev/ttyACM1` | `5C82108705` | `5.2` | follower |
| `/dev/video0` | *(none)* | `5.4` | `handeye` (gripper) |
| `/dev/video2` | `202404160005` | `5.3` | `fixed` (environment) |

Current step:

- This host is shared with other users. Coordinate hardware access (check
  `loto-status` / contact the tagged user) before running calibration,
  teleoperation, or data collection. Confirmed with the tagged user
  (Izwan) on 2026-08-18.
- Next: collect a small test dataset (section 7) then train/evaluate (section 8).

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

Status: done (2026-08-26). Calibration saved to
`/home/user/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/leader_arm.json`.

Recorded ranges (ticks), recalibrated 2026-08-26:

| joint | min | max |
|---|---|---|
| shoulder_pan | 832 | 3365 |
| shoulder_lift | 797 | 2931 |
| elbow_flex | 1247 | 3147 |
| wrist_flex | 2043 | 3117 |
| wrist_roll | 916 | 3185 |
| gripper | 1117 | 3040 |

Validation: all saved ranges are within the STS3215 encoder limits `0-4095`;
the previous invalid wrap values (`329xx`) and over-limit values (`4430`) are
no longer present.

### 6.2 Follower arm calibration

Rotate all follower joints to the calibration initial position, then run:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM1 \
  --robot.id=follower_arm
```

Status: done (2026-08-26). Calibration saved to
`/home/user/.cache/huggingface/lerobot/calibration/robots/so101_follower/follower_arm.json`.

Recorded ranges (ticks), recalibrated 2026-08-26:

| joint | min | max |
|---|---|---|
| shoulder_pan | 786 | 3317 |
| shoulder_lift | 815 | 2558 |
| elbow_flex | 1563 | 3121 |
| wrist_flex | 2034 | 3138 |
| wrist_roll | 988 | 3128 |
| gripper | 2046 | 3483 |

Validation: all saved ranges are within the STS3215 encoder limits `0-4095`.
The earlier near-zero gripper range was corrected by recalibrating with `c`
and fully opening/closing the gripper.

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
| `/dev/video0` | `fixed` (environment camera) | wide/top view of the follower arm and desk area |
| `/dev/video2` | `handeye` (gripper camera) | close-range view from the follower gripper |

Camera IDs are not permanently fixed. Re-run `lerobot-find-cameras opencv` and
re-check the saved images after reconnecting USB cameras, changing ports, or
switching machines.

Vision teleoperation command:

```bash
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 \
  --teleop.id=leader_arm --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 --robot.id=follower_arm \
  --robot.cameras='{
    "fixed": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30},
    "handeye": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30}
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

If a previous failed run created an empty local dataset directory, move it out
of the way before recording again. `lerobot-record` creates a new dataset when
`--resume=false`, so an existing path causes `FileExistsError`:

```bash
mv /home/user/.cache/huggingface/lerobot/wansnap/pick_cube_test \
  /home/user/.cache/huggingface/lerobot/wansnap/pick_cube_test_failed_$(date +%Y%m%d_%H%M%S)
```

Command:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower_arm \
  --robot.cameras='{
    "fixed": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30},
    "handeye": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30}
  }' \
  --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 --teleop.id=leader_arm \
  --dataset.repo_id=wansnap/pick_cube_test \
  --dataset.single_task="pick up the cube and place it in the box" \
  --dataset.num_episodes=5 \
  --dataset.push_to_hub=false \
  --display_data=false
```

When running from a graphical local session, right arrow ends/saves the current
episode early, left arrow discards and re-records the current episode, and Esc
stops recording. In a headless SSH or VS Code Remote session, LeRobot disables
the on-screen camera display and keyboard listener, so arrow/Esc controls are
not available. Each episode runs for `dataset.episode_time_s` seconds
(default `60`), each reset period runs for `dataset.reset_time_s` seconds
(default `60`), and `Ctrl+C` is the reliable way to stop the command.

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
during calibration and vision teleoperation minutes earlier.

**Root cause (identified 2026-08-19):** not a servo or servo-cable fault. The
follower's USB Type-C cable/connection was failing, so the whole motor bus
was unreliable. See section 9 for the full diagnosis. After fixing the USB
connection, both arms enumerate cleanly and the motor bus is stable.

## 8. Validation, training, and evaluation

Once Step 7 completes with 5 episodes, validate the dataset structure before
attempting training. The 5-episode smoke test is enough to verify the
recording pipeline but **not sufficient for a useful policy**. A real policy
typically requires 50+ diverse episodes. Use this section to validate, train
on the test data as a proof-of-concept, and evaluate performance on the same
small dataset.

### 8.1 Validate the dataset

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

python3 -c "
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('wansnap/pick_cube_test')
print(f'Episodes: {ds.num_episodes}')
print(f'Frames: {ds.num_frames}')
print(f'Tasks: {ds.meta[\"total_tasks\"]}')
print(f'Action features: {list(ds.action_keys)}')
print(f'Observation features: {list(ds.observation_keys)}')
"
```

Expected output for a successful 5-episode run:

```text
Episodes: 5
Frames: ~3500
Tasks: 1
Action features: ['shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos', 'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos']
Observation features: ['state', 'images.fixed', 'images.handeye']
```

### 8.2 Train a policy on the smoke-test dataset

LeRobot supports multiple policy architectures. For a quick proof-of-concept
with small data, use the `ACT` (Action Chunking Transformer) policy:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

lerobot-train \
  policy.type=act \
  policy.chunk_size=16 \
  policy.n_obs_steps=2 \
  policy.n_action_steps=16 \
  dataset_repo_id=wansnap/pick_cube_test \
  training.num_epochs=100 \
  training.batch_size=32 \
  training.lr=1e-4 \
  training.validate_every_n_epochs=10 \
  training.save_checkpoint_every_n_epochs=10 \
  training.output_dir=/home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act \
  device=cpu
```

This trains on CPU and saves checkpoints to
`/home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act`.

**Note:** 5 episodes is far too small for a real policy. This is a validation
step only. For a functional policy, collect at least 50 diverse episodes and
use GPU training (`device=cuda:0` if available).

### 8.3 Evaluate the trained policy

After training completes, evaluate the policy on the test dataset:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

lerobot-eval \
  -p /home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act/final_model \
  -d wansnap/pick_cube_test \
  --output-dir /home/user/hiwonder/lerobot_results/pick_cube_test_eval
```

This runs the policy on each episode in the test set and saves metrics
(success rate, mean action error, etc.) to the output directory.

**Interpretation:** With only 5 episodes for both training and evaluation, the
results will not be statistically meaningful. The purpose here is to validate
that the LeRobot training and evaluation pipeline works end-to-end with your
arm and dataset format. Once you collect 50+ episodes with consistent scene,
lighting, and reset procedure, rerun training and evaluation to measure actual
policy performance.

## 9. Integrate with `physicalai` later

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

## 10. USB troubleshooting (2026-08-19)

A full morning was lost to what looked like a servo fault but was actually USB
hardware. Recording this so the same symptoms are recognised faster next time.

### Symptom 1: an arm disappears from `/dev`

`lerobot-find-port` failed with `Could not detect the port. No difference was
found ([])`, and only one `/dev/ttyACM*` node existed instead of two.

Diagnostic commands:

```bash
ls -l /dev/ttyACM*
lsusb | grep -i 1a86
sudo dmesg --time-format=iso | tail -n 30
```

The kernel log showed the failing controller never enumerating:

```text
usb 3-5.2: new low-speed USB device number 20 using xhci_hcd
usb 3-5.2: device descriptor read/64, error -32
usb 3-5.2: device not accepting address 22, error -71
usb 3-5-port2: unable to enumerate USB device
```

**Key diagnostic:** the CH340 (`1a86:55d3`) is a **full-speed** (12 Mbps)
device. A healthy connection logs `new full-speed USB device`. Logging
`new low-speed USB device` instead means the D+/D- data lines are not working
— a cable or connector fault, not a driver or software problem.

**Isolating cable vs. port vs. board:** swap the cable between the two arms.
If the fault follows the cable, the cable is at fault; if it stays with the
arm, the board is. Here the fault followed the cable across hub ports `5.1`,
`5.2`, and `5.4`, while the good cable worked first time on every port —
proving both BusLinker boards and the hub were healthy.

Note that a brand-new cable can still be faulty, and charge-only Type-C cables
have no data lines and produce exactly these symptoms. The connection was
eventually restored by reseating connectors; a poorly seated Type-C plug gives
the same signature as a dead cable.

### Symptom 2: corrupted camera frames

`lerobot-find-cameras opencv` succeeded, but one camera's test image was part
real image and part flat green fill, with torn horizontal bands.

**How to tell a corrupted frame from a genuinely green scene:** a real image
has texture, a lighting gradient, and sensor noise. A truncated USB frame
leaves a perfectly uniform fill (an unwritten YUV420 buffer renders as green).
Capturing twice also helps — the proportion of valid image changed between
captures (about 25%, then 55%), which a static scene cannot do.

**Cause:** bandwidth contention — two arms plus two uncompressed video streams
on a single 480 Mbps USB 2.0 hub. **Fix:** moving the affected camera to a
different hub port produced clean full frames. Moving a camera to a direct PC
port is the more robust fix if it recurs.

### Device names are not stable

`ttyACM*` and `video*` numbering depends on enumeration order, so it changes
whenever devices are replugged in a different sequence. Always re-verify the
mapping after any replug:

```bash
for d in /dev/ttyACM* /dev/video*; do
  printf '%s | serial=%s | path=%s\n' "$d" \
    "$(udevadm info --query=property --name="$d" | grep '^ID_SERIAL_SHORT=' | cut -d= -f2)" \
    "$(udevadm info --query=property --name="$d" | grep '^ID_PATH=' | cut -d= -f2)"
done
```

Match arms by serial (`5C4C124628` = leader, `5C82108705` = follower) and
confirm camera roles from the captured images, not from device numbers.
Persistent `udev` rules keyed on serial number would remove this ambiguity.

## Clean reinstall checklist

To repeat the software setup from scratch without touching the repository:

```bash
rm -rf "$HOME/miniconda3" "$HOME/hiwonder"
rm -f "$HOME/Miniforge3-Linux-x86_64.sh"
```

The command above removes only the user-local Conda and Hiwonder directories.
Do not run it if those locations contain unrelated environments or data.
