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

### Optional: install the preserved fork

The original Hiwonder archive step above remains the reference installation
path. If you want the Hiwonder source plus the compatibility fixes and tested
SO101 workflow preserved in Git, use the fork instead of extracting the
archive:

```bash
cd /home/user
git clone --branch hiwonder-validated-so101 \
  https://github.com/KhairulIzwan/lerobot.git hiwonder/lerobot
cd /home/user/hiwonder/lerobot
conda activate lerobot
python -m pip install -e ".[feetech]"
```

This fork branch contains the Hiwonder source and the validated
`max_relative_target` compatibility fix. Do not install both trees into the
same location. If `/home/user/hiwonder/lerobot` already contains the extracted
archive, keep using that working tree or move it aside before cloning the fork.

Verify the selected source and package installation:

```bash
git remote -v
git branch --show-current
python -c 'import lerobot; print(lerobot.__file__)'
```

Expected branch: `hiwonder-validated-so101`. The fork is optional; the
original Hiwonder download and install instructions above remain valid when a
vendor archive is required.

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

Validated dataset naming and motion behavior for the SO101 follower workflow
(2026-08-28): the clamp-free teleop path was tested successfully with one
recorded episode. Do not add `--robot.max_relative_target=5` to the normal
teleop collection command: it can hold a joint away from the leader target and
produce repeated safety-clamp warnings, especially during larger elbow motion.
Use the clamp only for a short, supervised safety test when the follower has
been verified to track correctly without it.

### Two data-collection modes: teleop vs. autonomous

There are two distinct recording modes, and they use different dataset naming
rules:

1. Teleoperation dataset collection (leader controls follower): no policy is
   used, and the dataset name should not start with `eval_`.
2. Autonomous policy recording (policy controls follower): a policy is used,
   and the dataset name must start with `eval_`.

This distinction matters. A run with `--policy.path` and a repo id like
`wansnap/pick_cube_autonomous_trial` fails immediately, and a teleop run with an
`eval_` repo id also fails because the policy is missing.

Use these patterns:

- Teleop demo collection:
  `wansnap/pick_cube_teleop_50ep_run1`
- Autonomous policy rollout:
  `wansnap/eval_pick_cube_autonomous_trial_run3`

If a previous failed run created an empty local dataset directory, move it out
of the way before recording again. `lerobot-record` creates a new dataset when
`--resume=false`, so an existing path causes `FileExistsError`:

```bash
mv /home/user/.cache/huggingface/lerobot/wansnap/pick_cube_teleop_50ep_run1 \
  /home/user/.cache/huggingface/lerobot/wansnap/pick_cube_teleop_50ep_run1_failed_$(date +%Y%m%d_%H%M%S)
```

### Correct teleop collection command (for 50+ demos)

Use this when collecting demonstrations with the leader arm. It does not use a
policy and should not include `eval_` in the dataset name.

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 \
  --robot.id=follower_arm \
  --robot.cameras='{ \
    "fixed": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}, \
    "handeye": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30} \
  }' \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM0 \
  --teleop.id=leader_arm \
  --dataset.repo_id=wansnap/pick_cube_teleop_50ep_run2 \
  --dataset.single_task="pick up the cube and place it in the box" \
  --dataset.num_episodes=50 \
  --dataset.episode_time_s=60 \
  --dataset.push_to_hub=false \
  --display_data=false
```

This is the validated pattern for collecting a larger demonstration set. The
repo name remains plain, and the run is driven by the leader teleop device.
Before starting 50 episodes, perform one short supervised motion check and
confirm that the follower tracks every joint, including the elbow. Keep the
follower arm clear because no relative-target clamp is enabled in this command.

In a headless terminal, episode recording is automatic by default, but manual
controls are also available by typing a command followed by Enter:

- `s`: finish and save the current episode immediately
- `r`: discard the current episode and rerecord it
- `q`: discard the unfinished episode and stop recording

**Automatic episode flow**

When no manual command is entered:

1. **Recording:** the episode runs for `dataset.episode_time_s` seconds.
2. **Saving:** LeRobot saves the completed episode automatically.
3. **Reset:** the `dataset.reset_time_s` interval begins so you can replace the
  cube and prepare the arms.
4. **Next episode:** the following episode starts automatically when the reset
  interval ends.

In short: **record up to 60 s -> save -> reset 60 s -> record the next episode**.
Type `s` followed by Enter as soon as the task is complete to save early; the
full 60 seconds is only the maximum recording time.

### Correct autonomous rollout command (with policy)

Use this only when a trained policy is running the follower arm. The repo name
must start with `eval_`, and the checkpoint path must be a real local model.

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 \
  --robot.id=follower_arm \
  --robot.max_relative_target=5 \
  --robot.cameras='{ \
    "fixed": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}, \
    "handeye": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30} \
  }' \
  --policy.path=/home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act_smoke/checkpoints/000010/pretrained_model \
  --policy.device=cpu \
  --dataset.repo_id=wansnap/eval_pick_cube_autonomous_trial_run3 \
  --dataset.single_task="pick up the cube and place it in the box" \
  --dataset.num_episodes=1 \
  --dataset.episode_time_s=10 \
  --dataset.push_to_hub=false \
  --display_data=false
```

This command exited successfully with code 0 in the validated SO101 workflow.
For policy-driven recording, the dataset name must begin with `eval_` and the
local cache must not already contain that dataset path.

When running from a graphical local session, right arrow ends/saves the current
episode early, left arrow discards and re-records the current episode, and Esc
stops recording. In a headless SSH or VS Code Remote session, LeRobot disables
the on-screen camera display and keyboard listener, so arrow/Esc controls are
not available. Each episode runs for `dataset.episode_time_s` seconds
(default `60`), each reset period runs for `dataset.reset_time_s` seconds
(default `60`), and `Ctrl+C` is the reliable way to stop the command.

Dataset saves by default under the repo path you specify, for example:
`~/.cache/huggingface/lerobot/wansnap/pick_cube_teleop_50ep_run1`.

#### Continuing a partial recording

If you interrupt the recording before `num_episodes=5` is reached, **do not**
delete or rename the dataset folder. Instead, resume recording by adding
`--resume=true` and reduce `--dataset.num_episodes` to the remaining count.

For example, if you have already recorded 2 episodes and want 3 more to reach 5
total:

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
  --dataset.num_episodes=3 \
  --dataset.push_to_hub=false \
  --display_data=false \
  --resume=true
```

The dataset folder remains at `~/.cache/huggingface/lerobot/wansnap/pick_cube_test`
and the existing 2 episodes are preserved. After this continuation, the dataset
will have 5 total episodes.

**Historical troubleshooting note (resolved 2026-08-19):** a previous
`lerobot-record` failure at robot connect showed a missing gripper motor on the
follower bus. This was not a servo fault. The root cause was a failing USB
Type-C cable/connection feeding the follower controller, which dropped the whole
motor bus. After fixing the cable/connection and re-checking the hub/port,
teleoperation and recording again worked correctly. See section 10 for the full
diagnosis and the cable/port checklist.

## 8. Validation, training, and evaluation

Once Step 7 completes with 5 episodes, validate the dataset structure before
attempting training. The 5-episode smoke test is enough to verify the
recording pipeline but **not sufficient for a useful policy**. A real policy
typically requires 50+ diverse episodes. Use this section to validate, train
on the test data as a proof-of-concept, and evaluate performance on the same
small dataset. A pretrained policy can sometimes be run without local
demonstrations, but it must support this robot's action space, camera inputs,
and task interface.

### 8.1 Validate the dataset

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

python3 -c "
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('wansnap/pick_cube_test')
print('Episodes:', ds.num_episodes)
print('Frames:', ds.num_frames)
print('Tasks:', ds.meta.info['total_tasks'])
print('Action features:', ds.features['action']['names'])
print('Observation features:', [name.removeprefix('observation.') for name in ds.features if name.startswith('observation.')])
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
  --policy.type=act \
  --dataset.repo_id=wansnap/pick_cube_test \
  --output_dir=/home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act_smoke \
  --steps=10 \
  --batch_size=2 \
  --save_checkpoint=true \
  --save_freq=5 \
  --policy.device=cpu \
  --policy.push_to_hub=false
```

This is a local-only, 10-step smoke test. It does not connect to the robot or
upload to Hugging Face. It saves checkpoints at steps 5 and 10 to
`/home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act_smoke`. On this
host, the test completed successfully on CPU in about 7 minutes.

**Note:** 5 episodes is far too small for a real policy. This is a validation
step only. For a functional policy, collect at least 50 diverse episodes and
use GPU training (`device=cuda:0` if available).

### 8.2.1 Check Pi0/Pi0.5 support

The installed Hiwonder LeRobot package exposes `pi0` and `pi0fast` policy types,
but it does not expose a separate `pi05` policy type. Check the installed CLI
before attempting to train or run a Pi0.5 checkpoint:

```bash
lerobot-train --help | grep -i 'pi0\|pi05'
lerobot-eval --help | grep -i 'pi0\|pi05'
```

The expected result contains `pi0` and possibly `pi0fast`, but no standalone
`pi05` entry. A Pi0.5 checkpoint can only be used directly if this package's
`pi0` implementation accepts that checkpoint and its expected robot and camera
interfaces. The ACT command above does not train Pi0.5.

Using a pretrained Pi0.5 policy directly does not require local demonstration
episodes or fine-tuning, but it is a zero-shot experiment rather than a policy
adapted to this arm and task. Fine-tuning requires demonstrations and creates a
new task-specific checkpoint. Confirm the model's required checkpoint,
authentication, image inputs, and inference command from the model release
before sending actions to the live arm. Start with low-risk motion limits and
keep an emergency stop available.

If the checkpoint is incompatible with the installed package, collect the
demonstrations first and use a LeRobot version and Pi0.5 training workflow that
explicitly supports that checkpoint. Do not change `policy.type=act` to
`policy.type=pi0` without also supplying the Pi0-specific configuration required
by the package.

### 8.3 Evaluate the trained policy

The installed `lerobot-eval` command evaluates a policy through rollouts in a
supported environment; it does not calculate success metrics from recorded
SO-101 episodes. First verify that the saved smoke-test checkpoint can be
loaded without connecting to the robot:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

python3 -c "
from lerobot.policies.act.modeling_act import ACTPolicy
checkpoint = '/home/user/hiwonder/lerobot_checkpoints/pick_cube_test_act_smoke/checkpoints/000010/pretrained_model'
policy = ACTPolicy.from_pretrained(checkpoint)
print('Loaded policy:', type(policy).__name__)
print('Device:', next(policy.parameters()).device)
"
```

This confirms that the final checkpoint files are complete and readable. It
does not measure task success and does not control the physical arm.

For performance evaluation, configure a supported simulated or hardware-in-the-
loop environment and run `lerobot-eval --policy.path=<checkpoint> ...` with a
defined task, reset procedure, safety limits, and an emergency stop. Do not use
the 5-episode smoke-test checkpoint for autonomous SO-101 control. Once you
collect 50+ consistent demonstrations, train a new policy and evaluate it in a
controlled environment before live deployment.

#### Future supervised autonomous rollout

After training a meaningful policy and validating its checkpoint, use
`lerobot-record` with `--policy.path` to run one tightly supervised rollout on
the physical arm. Do not include `--teleop.*` arguments: the policy provides
the actions. Use a fresh dataset name so autonomous-test data cannot overwrite
the demonstration dataset.

Before starting, place the follower arm in a clear workspace, make the power
disconnect immediately accessible, and have an operator physically present.
Start with a single short episode and keep `max_relative_target` conservative:

The original command below failed before recording because the dataset name and
mode were mismatched. For teleop collection, the dataset should not begin with
`eval_`; for policy-based autonomous rollout, it must begin with `eval_`. If the
repo name is corrected but the cache directory already exists, a second failure
appears as `FileExistsError`.

### Fix 1: remove the stale dataset and retry

Use this when the old directory contains only a failed or disposable run and
you intend to keep the same task/recording mode:

```bash
rm -rf /home/user/.cache/huggingface/lerobot/wansnap/pick_cube_teleop_50ep_run1
```

Then rerun the teleop command below with the plain dataset name. This is the
recommended recovery for a failed demo collection run.

### Fix 2: keep the old dataset

Do not delete the old directory. Use a different, fresh repo name instead:

```bash
--dataset.repo_id=wansnap/pick_cube_teleop_50ep_run2
```

This preserves the old dataset while writing the new rollout to a separate local
cache directory. The same rule applies to autonomous runs: keep the repo name
fresh and `eval_`-prefixed when `--policy.path` is being used.

Replace the policy path only with a checkpoint trained beyond the 10-step smoke
test. Stop immediately with `Ctrl+C` or disconnect arm power if the movement is
unexpected. Inspect the autonomous-trial videos and recorded actions before
increasing episode duration, motion limits, or the number of rollouts.

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
