# Hiwonder SO-101 ACT Workflow

This is the focused, current workflow for the SO-101 cube pick-and-place task.
For initial hardware setup, calibration, camera discovery, and troubleshooting,
see [the complete Hiwonder setup guide](hiwonder-lerobot-setup.md).

## Pre-test checklist (do this before every session)

Physical wiring, port assignments, and camera device paths on this rig have
drifted before (see the camera-mapping correction in Section 1) and can
change again after reconnecting cables, rebooting, or hardware swaps. Verify
these every time before recording or deploying, not just the first time:

| Check | How |
| --- | --- |
| Arm ports | Confirm `--robot.port` (follower) and `--teleop.port` (leader, if teleoperating) still match `/dev/ttyACM*` reality — ports can renumber after reconnect/reboot. |
| Camera device mapping | Confirm which `/dev/video*` is physically the fixed (tripod/overhead) camera and which is the hand-eye (wrist-mounted) camera — do not assume the last known mapping still holds. |
| Camera framing | Quick look (`--display_data=true` or a short test clip) that both feeds actually show what they're supposed to, not an occluded/misaimed view. |
| System load | `uptime` and `ps aux --sort=-%cpu \| head` — check for stray/runaway processes (e.g. `ripgrep`) before any real-time policy deployment, since CPU contention directly slows inference (see Section 5). |
| Workspace reset | Cube back on the white pick square, box empty, before every clean trial. |

## Scope and status

This workflow uses an ACT (Action Chunking Transformer) policy. It learns to
map fixed-camera and hand-eye images plus the current six-joint arm state to
six joint-position targets. It is not a separate object-detection or image
classification system.

The current checkpoint has completed seven operator-observed pick-and-place
runs in the same workspace: evaluation trials 10 and 13, plus five deployment
batch-2 trials. Continue supervised operation; the active per-command safety
limit does not bound cumulative arm travel.

## Required inputs and output

| Item | ACT role |
| --- | --- |
| Fixed camera | Shows the cube, box, arm, and workspace |
| Hand-eye camera | Shows the gripper and grasp interaction |
| `observation.state` | Current six-joint arm position |
| Task text | `pick up the cube and place it in the box` |
| Demonstrated action | Next six joint-position targets during teleoperation |

The action order is `shoulder_pan`, `shoulder_lift`, `elbow_flex`,
`wrist_flex`, `wrist_roll`, and `gripper`.

## 1. Collect demonstrations

Use this only to collect new teleoperation demonstrations. Keep the cube, box,
cameras, lighting, and workspace within the conditions you intend ACT to
support. Do not use an `eval_` dataset name for teleoperation.

> **Camera mapping correction (2026-09-10):** `/dev/video0` is the physical
> hand-eye (wrist-mounted) camera and `/dev/video2` is the physical fixed
> (tripod/overhead) camera — confirmed by physically checking each device.
> Earlier commands in this doc had these swapped (`"fixed"` pointed at
> `/dev/video0`, `"handeye"` at `/dev/video2`), so all datasets recorded
> before this fix have the two camera folders labeled backwards internally
> (`observation.images.fixed` actually contains hand-eye footage, and vice
> versa). This did not affect training or the v1/v2 success-rate analysis —
> policy inputs are just two arbitrary channels, and rollout review always
> used whichever folder showed the workspace clearly, regardless of its
> name — but new recordings will now have correctly labeled camera folders.

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

lerobot-record \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 \
  --robot.id=follower_arm \
  --robot.cameras='{"fixed": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30}, "handeye": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}}' \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM0 \
  --teleop.id=leader_arm \
  --dataset.repo_id=wansnap/pick_cube_teleop_<run_name> \
  --dataset.single_task="pick up the cube and place it in the box" \
  --dataset.num_episodes=50 \
  --dataset.episode_time_s=60 \
  --dataset.push_to_hub=false \
  --display_data=false
```

Use `s` then Enter to save a completed episode early, `r` then Enter to discard
and redo it, and `q` then Enter to discard the unfinished episode and stop.
Review every saved episode: keep only clear, successful demonstrations with
consistent camera views.

### Parameter reference

| Flag | Meaning |
| --- | --- |
| `--robot.type` | Which physical follower arm driver to use. `so101_follower` matches the SO-101 hardware in this workflow. |
| `--robot.port` | Serial/USB port the follower arm is connected on (e.g. `/dev/ttyACM1`). Differs per machine/cable. |
| `--robot.id` | Free-form label to distinguish this robot from others of the same type; used in logs/calibration lookup. |
| `--robot.cameras` | JSON dict of camera streams to record. Each entry names a stream (`fixed`, `handeye`), its driver (`opencv`), device path, resolution, and fps. Stream names must match what the trained policy expects (`observation.images.fixed`, `observation.images.handeye`). |
| `--teleop.type` | Which leader/teleoperation device drives the follower arm. `so101_leader` matches the SO-101 leader arm. |
| `--teleop.port` | Serial/USB port the leader arm is connected on (e.g. `/dev/ttyACM0`). |
| `--teleop.id` | Free-form label for the leader device, analogous to `--robot.id`. |
| `--dataset.repo_id` | Local dataset identifier, `{namespace}/{name}` (e.g. `wansnap/pick_cube_teleop_run5`). Determines the folder under `~/.cache/huggingface/lerobot/`. |
| `--dataset.single_task` | Short natural-language description of the task, stored as the task text ACT conditions on. |
| `--dataset.num_episodes` | How many demonstration episodes to record in this session. |
| `--dataset.episode_time_s` | Max seconds per episode before it auto-stops (can end early with `s`). |
| `--dataset.push_to_hub` | Whether to upload the dataset to the Hugging Face Hub. `false` keeps data local only. |
| `--display_data` | Whether to show a live camera preview window while recording. `false` is typical for headless/robot-side sessions. |

## 2. Validate the dataset

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

python3 -c "
from lerobot.datasets.lerobot_dataset import LeRobotDataset
ds = LeRobotDataset('wansnap/pick_cube_teleop_50ep_run5')
print('Episodes:', ds.num_episodes)
print('Frames:', ds.num_frames)
print('Action features:', ds.features['action']['names'])
print('Observation features:', [name for name in ds.features if name.startswith('observation.')])
"
```

The validated run5 dataset has 50 episodes, 15,938 frames, two image streams,
and a six-value action.

### Parameter reference

| Line | Meaning |
| --- | --- |
| `LeRobotDataset('wansnap/pick_cube_teleop_50ep_run5')` | Loads the dataset by `repo_id` from local cache (`~/.cache/huggingface/lerobot/`); errors if it hasn't been recorded/downloaded. |
| `ds.num_episodes` | Total number of recorded demonstration episodes in the dataset. |
| `ds.num_frames` | Total number of individual timesteps (frames) across all episodes — this is what training step counts are measured against (see Section 3's undertraining note). |
| `ds.features['action']['names']` | The six named action dimensions the policy is trained to predict, in order. |
| `ds.features` (filtered to `observation.*`) | Lists every observation stream available (camera image keys plus `observation.state`), confirming the dataset has the inputs ACT expects. |

## 3. Train ACT

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

lerobot-train \
  --policy.type=act \
  --dataset.repo_id=wansnap/pick_cube_teleop_50ep_run5 \
  --output_dir=/home/user/hiwonder/lerobot_checkpoints/pick_cube_run5_act \
  --steps=2000 \
  --batch_size=8 \
  --save_checkpoint=true \
  --save_freq=500 \
  --policy.device=cpu \
  --policy.push_to_hub=false
```

The existing checkpoint is at
`/home/user/hiwonder/lerobot_checkpoints/pick_cube_run5_act/checkpoints/002000/pretrained_model`.

### Parameter reference

| Flag | Meaning |
| --- | --- |
| `--policy.type` | Which policy architecture to train. `act` selects Action Chunking Transformer. |
| `--dataset.repo_id` | Local dataset to train on, must already exist (see Section 1/2). |
| `--output_dir` | Where checkpoints, logs, and the final trained model are written. |
| `--steps` | Total optimizer steps to run. Combined with `--batch_size` and dataset frame count, this determines how many epochs are actually trained (see the undertraining note below). |
| `--batch_size` | Number of frames per gradient update. Larger batches are more stable but need more memory/compute per step. |
| `--save_checkpoint` | Whether to periodically save checkpoints during training (vs. only at the end). |
| `--save_freq` | How many steps between checkpoint saves. |
| `--policy.device` | Compute device for training (`cpu` or `cuda`). This machine has no GPU, so `cpu` is required here. |
| `--policy.push_to_hub` | Whether to upload the trained policy to the Hugging Face Hub. `false` keeps it local only. |

### Known issue: jerky arm motion at deployment, and why

This checkpoint's `train_config.json` shows `temporal_ensemble_coeff: None`,
`chunk_size: 100`, and `n_action_steps: 100`. With `n_action_steps` equal to
`chunk_size`, the policy commits to a full 100-step block of predicted
actions and executes it open-loop before it re-queries the cameras. Any noise
in that single forward pass plays out for the whole block, and each time the
policy re-plans at the chunk boundary the new prediction can start from a
slightly different pose than the arm is actually in — both effects show up as
visible jerk/jumps during a rollout, and are a known ACT deployment behavior
when temporal ensembling is disabled.

Separately, `--dataset.repo_id=wansnap/pick_cube_teleop_50ep_run5` has 15,938
frames. At `--batch_size=8`, one epoch is `15938 / 8 ≈ 1992` steps, so
`--steps=2000` trains for roughly **one epoch only** — likely undertrained,
which compounds the jerkiness with imprecise/noisy action predictions.

Recommended retrain settings to address both:

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

lerobot-train \
  --policy.type=act \
  --dataset.repo_id=wansnap/pick_cube_teleop_50ep_run5 \
  --output_dir=/home/user/hiwonder/lerobot_checkpoints/pick_cube_run5_act_v2 \
  --steps=10000 \
  --batch_size=8 \
  --save_checkpoint=true \
  --save_freq=1000 \
  --policy.device=cpu \
  --policy.temporal_ensemble_coeff=0.01 \
  --policy.n_action_steps=1 \
  --policy.push_to_hub=false
```

Notes:
- `temporal_ensemble_coeff` requires `n_action_steps=1` (the policy must run
  inference at every environment step to form the ensemble); LeRobot enforces
  this at config validation time.
- `chunk_size` (100) is left unchanged; only how many of the predicted steps
  are actually executed per inference call (`n_action_steps`) changes.
- `--steps=10000` is roughly 5 epochs over the 50-episode dataset, versus the
  original ~1 epoch. This is CPU-only training (no GPU detected on this
  machine), so expect a materially longer run than the original 2000-step
  checkpoint (which itself took multiple hours) — plan for a multi-hour
  background run and monitor via the checkpoint directory's `save_freq`
  outputs rather than waiting synchronously.

New/changed flags versus Section 3's base command:

| Flag | Meaning |
| --- | --- |
| `--policy.temporal_ensemble_coeff` | Exponential-weighting coefficient that blends overlapping action-chunk predictions across consecutive inference calls, smoothing the jerk that otherwise appears at chunk boundaries. `null`/unset disables it. |
| `--policy.n_action_steps` | How many of the policy's predicted `chunk_size` actions are actually executed before the next inference call. `1` means re-inferring every environment step (required for temporal ensembling); `100` (equal to `chunk_size`) means fully open-loop execution of the whole chunk. |

### v1 vs v2 comparison

Both checkpoints use the identical ACT model architecture: `vision_backbone:
resnet18` (ImageNet-pretrained CNN encoder for the fixed and hand-eye camera
streams) and `chunk_size: 100`. Only these `train_config.json` fields differ:

| Field | v1 (`pick_cube_run5_act`) | v2 (`pick_cube_run5_act_v2`) |
| --- | --- | --- |
| `n_action_steps` | 100 | 1 |
| `temporal_ensemble_coeff` | `null` (disabled) | 0.01 |
| `steps` | 2000 | 10000 |
| `save_freq` | 500 | 1000 |

Note: v1's console training log was not preserved (it was trained before this
documentation was written), so the comparison here is based on the saved
`train_config.json` files in each checkpoint directory, not a log diff. v2's
own training log shows loss at step 2000 (the point where v1 stopped) was
already 0.956 and continued declining past that point, which is the basis for
treating v1 as likely undertrained relative to v2.

## 4. Offline checkpoint check

This confirms the model loads without connecting to the robot:

```bash
python3 -c "
from lerobot.policies.act.modeling_act import ACTPolicy
checkpoint = '/home/user/hiwonder/lerobot_checkpoints/pick_cube_run5_act/checkpoints/002000/pretrained_model'
policy = ACTPolicy.from_pretrained(checkpoint)
print(type(policy).__name__)
"
```

### Parameter reference

| Line | Meaning |
| --- | --- |
| `checkpoint = '.../pretrained_model'` | Path to a specific checkpoint's `pretrained_model` folder (contains `config.json`, `model.safetensors`, `train_config.json`) — not the parent `checkpoints/` directory. |
| `ACTPolicy.from_pretrained(checkpoint)` | Loads the model architecture and trained weights from that folder, without any robot/camera hardware connection. This is the fastest way to catch a corrupted or incompatible checkpoint before attempting a physical rollout. |
| `print(type(policy).__name__)` | Prints `ACTPolicy` on success, confirming the checkpoint loaded as the expected policy class. |

To inspect a checkpoint's key inference-time settings instead of just
confirming it loads, print `policy.config` fields, e.g. `policy.config.n_action_steps`
and `policy.config.temporal_ensemble_coeff` (used in the v1/v2 comparison
above).

## 5. Supervised deployment

Use an `eval_`-prefixed, unique dataset name for every policy rollout. Keep an
operator present, the workspace clear, and arm power immediately accessible.
`max_relative_target=15` was used in all seven confirmed successful runs. It is
a per-command clamp only, not a fixed envelope around the initial arm pose.

```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lerobot
cd /home/user/hiwonder/lerobot

lerobot-record \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM1 \
  --robot.id=follower_arm \
  --robot.max_relative_target=15 \
  --robot.cameras='{"fixed": {"type": "opencv", "index_or_path": "/dev/video2", "width": 640, "height": 480, "fps": 30}, "handeye": {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}}' \
  --policy.path=/home/user/hiwonder/lerobot_checkpoints/pick_cube_run5_act/checkpoints/002000/pretrained_model \
  --policy.device=cpu \
  --dataset.repo_id=wansnap/eval_pick_cube_run5_<unique_name> \
  --dataset.single_task="pick up the cube and place it in the box" \
  --dataset.num_episodes=1 \
  --dataset.episode_time_s=120 \
  --dataset.push_to_hub=false \
  --display_data=false
```

Inspect the two saved videos and assign a manual success/failure label after
each rollout. The current evidence supports supervised use in the same trained
workspace; it does not establish robustness to substantially changed object
positions, lighting, camera placement, or tasks.

### Parameter reference

Same meanings as Section 1's table for `--robot.type`, `--robot.port`,
`--robot.id`, `--robot.cameras`, `--dataset.repo_id`, `--dataset.single_task`,
`--dataset.num_episodes`, `--dataset.episode_time_s`, `--dataset.push_to_hub`,
`--display_data`. Additional/changed flags for deployment:

| Flag | Meaning |
| --- | --- |
| `--robot.max_relative_target` | Per-command safety clamp: caps how far the arm can move in a single control step, regardless of what the policy predicts. Does not bound total cumulative travel over a rollout. `15` is the value used in all confirmed successful runs. |
| `--policy.path` | Local path to the trained checkpoint's `pretrained_model` directory to load and run for autonomous control (replaces `--teleop.*` from Section 1, since the policy now drives the arm instead of a human). |
| `--policy.device` | Compute device to run policy inference on during deployment (`cpu` here, matching training). |
| `--dataset.num_episodes` | Set to `1` for deployment so each invocation records exactly one rollout under a unique `eval_` name. |

### Known issue: shared machine CPU contention can stall real-time inference

With `n_action_steps=1` (the v2 fix for jerky motion), the policy must run a
full forward pass (ResNet18 + transformer) on every control step (~33 ms
budget at 30 fps), instead of once per 100 steps like v1. This is much more
sensitive to CPU contention than v1's open-loop execution.

During v2 clean-trial testing, the arm appeared to react sluggishly. Root
cause: two stray VS Code `ripgrep` file-search processes were pegged at
1016% and 704% CPU (stuck/runaway search), driving load average to ~23-26 on
a 16-core machine. Killing those PIDs (`kill <pid>`) dropped the 1-min load
average from ~23 to ~10 within a minute, no reboot required. Before any
deployment session, check `uptime` and `ps aux --sort=-%cpu | head` first; a
reboot only helps if it happens to clear the same kind of stray process, and
does not address the underlying CPU-per-step sensitivity introduced by
`n_action_steps=1`.

### Known issue: recorded/video duration is nominal, not real elapsed time

`lerobot-record`'s control loop (`record_loop` in `record.py`) tracks real
wall-clock time internally (via `time.perf_counter()`) to decide when to stop
and how long to sleep between steps, but it does **not** pass that real
timestamp when saving each frame. `LeRobotDataset.add_frame()` then falls
back to its default:

```python
if timestamp is None:
    timestamp = frame_index / self.fps
```

So every saved timestamp — and therefore the episode/video "duration" derived
from frame count ÷ configured fps — is a fabricated, perfectly even nominal
timeline. It does **not** reflect how long each control step actually took to
compute. If per-step ACT inference is slower than the 1/fps budget (e.g. under
CPU contention, or simply because `n_action_steps=1` requires inference every
step), the dataset/video will report a much shorter duration than the real
wall-clock time the operator observed. Example: a rollout that took ~90 s in
real time by stopwatch was saved and reported as a ~10 s episode (frame count
÷ 30 fps), because each step actually took ~9x longer than 33 ms to compute.

Takeaway: **do not use recorded episode/video duration as a proxy for
real-time inference speed or CPU load** — it can't detect slowdowns by
construction. Use a stopwatch, or wrap `lerobot-record` with a wall-clock
timer, if actual control-loop timing needs to be measured.

### Workspace layout and stop key

- **Pick location**: white square outline (cube starts here at the beginning
  of an episode).
- **Place location**: black holder ("black box" — the target).
- **Stop key**: tap the **right arrow key (`→`)** the instant you observe
  success — this is `events["exit_early"]` in `lerobot-record`'s keyboard
  listener (`control_utils.py`), ending the current episode immediately. Left
  arrow (`←`) does the same but also discards/re-records the episode. `Esc`
  stops recording entirely. There is no `s`/`Enter` shortcut for this.

Reset the cube to the white pick square before starting each trial — if the
cube is left in the black box from a previous rollout, the next episode
starts from a non-standard state and is not a clean pick trial.

`eval_pick_cube_run5_v2_clean_trial3` and `trial4` (recorded 2026-09-10),
reviewed frame-by-frame:

- **trial4** (12.9 s): cube starts in the white pick square, is grasped, and
  is carried into the black box by the end of the episode. **Success** —
  matches the operator's real-time observation.
- **trial3** (8.8 s): cube was already sitting in the black box at frame 0
  (not reset to the pick square beforehand), so this was not a clean
  pick-from-marker trial. The policy re-grasped the cube and set it back
  down in the box; final state was still "in box," but the trial should be
  excluded/re-run with a proper reset rather than counted as a clean
  success or failure.

## 6. Review rollout outcomes

There is no automated success/failure label in the dataset metadata — use this
script to pull the last frame of each `eval_` rollout's fixed-camera video so
you can visually confirm whether the cube ended up in the box:

```bash
DATASET_ROOT=/home/user/.cache/huggingface/lerobot/wansnap
OUT=/tmp/act_rollout_last_frames
mkdir -p "$OUT"

for d in "$DATASET_ROOT"/eval_*/; do
  name=$(basename "$d")
  vid=$(find "$d" -path "*observation.images.fixed*" -iname "*.mp4" 2>/dev/null | head -1)
  if [ -n "$vid" ]; then
    ffmpeg -y -sseof -0.5 -i "$vid" -frames:v 1 -q:v 2 "$OUT/${name}.jpg" -loglevel error
  else
    echo "NO VIDEO: $name"
  fi
done

echo "Last frames written to $OUT — open each image and label success/failure manually."
```

### Parameter reference

| Line | Meaning |
| --- | --- |
| `DATASET_ROOT=...` | Root folder containing all local LeRobot datasets for this Hugging Face namespace, including every `eval_*` rollout recording. |
| `OUT=/tmp/act_rollout_last_frames` | Scratch output folder for extracted still frames; safe to delete/recreate, not part of any dataset. |
| `for d in "$DATASET_ROOT"/eval_*/` | Iterates every rollout dataset folder whose name starts with `eval_` (the convention used for policy rollouts, as opposed to teleoperation datasets). |
| `find "$d" -path "*observation.images.fixed*" -iname "*.mp4"` | Locates that rollout's fixed-camera video specifically (as opposed to the hand-eye camera), since the fixed camera shows the cube/box/workspace needed to judge success. **Note:** for datasets recorded before the 2026-09-10 camera-mapping correction (see Section 1), the `images.fixed` folder actually contains hand-eye footage and vice versa — check which folder visually shows the full workspace before relying on the name alone. |
| `ffmpeg -sseof -0.5 -i "$vid" -frames:v 1 -q:v 2 "$OUT/${name}.jpg"` | Seeks to 0.5 seconds before end-of-file and extracts exactly one frame (`-frames:v 1`) at high JPEG quality (`-q:v 2`, lower is better) — i.e. the final state of the workspace after the rollout finished. |
| `echo "NO VIDEO: $name"` | Flags any rollout folder missing a fixed-camera video (e.g. corrupted or partial recording), so it isn't silently skipped. |

Manually reviewing this way is still required: the checkpoint's vision
encoder was trained only against the original blue-cube appearance, so
rollouts using a different-colored cube (or altered lighting/position/camera
placement) are out-of-distribution inputs and are not evidence of general
robustness, even if that rollout happens to succeed.

### Checkpoint timeline (which rollouts used which checkpoint)

LeRobot dataset metadata does not record which policy checkpoint produced a
rollout, so this has to be inferred from file timestamps:

| Checkpoint | Created | 
| --- | --- |
| v1 (`pick_cube_run5_act`, step 2000) | Aug 28 |
| v2 (`pick_cube_run5_act_v2`) | training started Sep 7 |

All `eval_pick_cube_teleop_50ep_run5_trial*` and all
`eval_pick_cube_run5_deployment_*` rollout folders were recorded **Sep 1** —
before v2 existed. This means every rollout reviewed so far, regardless of
folder name, was produced by the **v1 checkpoint**. The `deployment_*` naming
reflects different testing sessions/days, not a different model.

### v1 checkpoint (step 2000) rollout results (master table)

Merging the `teleop_50ep_run5_trial*` and `deployment_*` folders now that both
are confirmed to be v1. Several `deployment_*` rollouts introduced
differently colored cubes (red/green/multi-color, not the trained blue cube)
or show a hand actively repositioning objects in-frame — both are excluded
from the success-rate count as not comparable, consistent with the same rule
already applied to `trial15`.

| # | Trial | Category | Result | Details |
| --- | --- | --- | --- | --- |
| 1 | trial1 | Comparable | Fail | Cube sits untouched at center of workspace; gripper hovers empty above the box marker — arm never picked it up |
| 2 | trial2 | Comparable | Fail | Same as trial1 — cube untouched, gripper idle over box, no pick attempt visible in final frame |
| 3 | trial3 | Comparable | Fail | Cube untouched at center; gripper returned to hover position over box empty-handed |
| 4 | trial4 | Comparable | Fail | Gripper reached toward cube area but ended tilted/off to the side, away from box; cube not visible in gripper or box |
| 5 | trial5 | Comparable | Fail | Cube untouched, gripper hovering empty above box marker |
| 6 | trial6 | Comparable | Fail | Gripper positioned over box but appears empty; small light-blue object visible near gripper jaws, possibly dropped beside rather than inside |
| 7 | trial7 | Comparable | Fail | Gripper closed near box position, but nothing visibly deposited in box |
| 8 | trial8 | Comparable | Fail | Gripper hovers directly over box, closed, but box appears empty — cube likely dropped short or missed |
| 9 | trial9 | Comparable | Fail | Cube untouched, gripper idle over box, empty |
| 10 | trial10 | Comparable | Success | Cube clearly visible inside the box marker; gripper open and retracted after placement |
| 11 | trial11 | Comparable | Fail | Gripper hovering over box area with a small light-blue object beside it, not clearly deposited inside box boundary |
| 12 | trial12 | Comparable | Fail | Same pattern as trial11 — object sits adjacent to box, not inside |
| 13 | trial13 | Comparable | Success | Cube clearly visible inside the box marker; gripper open and retracted after placement |
| 14 | trial14 | Comparable | Fail | Gripper over box position, box appears empty, no cube visibly placed |
| 15 | trial15 | Excluded (OOD) | N/A | Novel green/red cubes introduced (not the trained blue cube) |
| 16 | deployment_trial1 | Comparable | Fail | Cube untouched near start position; gripper hovers over box, empty |
| 17 | deployment_trial1_retry1 | Excluded (OOD) | N/A | Red cube placed in box, green cube on table — novel colors, not the trained cube |
| 18 | deployment_trial2 | Comparable | Fail | Cube untouched, gripper tilted near box; operator hand visible at laptop keyboard (not touching the cube/box) |
| 19 | deployment_batch2_trial1 | Excluded (OOD) | N/A | Green cube outside box, red cube visible under gripper — novel colors |
| 20 | deployment_batch2_trial2 | Excluded (intervention + OOD) | N/A | Operator hand actively placing a red cube into the box; green cube also on table |
| 21 | deployment_batch2_trial3 | Excluded (OOD) | N/A | Rubik's-cube-style multi-color block and a blue cube under the gripper — novel objects |
| 22 | deployment_batch2_trial4 | Excluded (OOD) | N/A | Green marker box and a red cube in the box — novel colors |
| 23 | deployment_batch2_trial5 | Excluded (OOD) | N/A | Multiple novel-colored cubes (green on table, red under gripper) |
| 24 | deployment_test001 | Excluded (OOD) | N/A | Rubik's-cube-style block and a blue cube in the box — novel objects |
| 25 | deployment_test003 | Excluded (OOD) | N/A | Green cube and a red cube with marking in the box, novel colors |
| 26 | run5_20 | Excluded (OOD/blurry) | N/A | Multiple novel-colored cubes (green/blue/red), motion-blurred frame |

**Success rate: 2/16 comparable trials = 12.5%** (11 rollouts excluded as
out-of-distribution cube colors and/or operator intervention; `deployment_trial3`
and `deployment_test002` had no recoverable video and are omitted entirely).

**Common failure pattern**: most fails show the cube either completely
untouched at its start position, or dropped adjacent to the box rather than
inside it — consistent with the training diagnosis above (undertrained,
open-loop-jerky policy struggling with grasp precision and placement
accuracy). The high proportion of OOD rollouts (11 of 26 reviewed) also
suggests deliberate but unvalidated generalization testing with different
colored cubes, which the workflow doc explicitly does not claim support for.

### v2 checkpoint (step 10000) rollout results — "clean" batch

Recorded 2026-09-10 as `eval_pick_cube_run5_v2_clean_trial1` through
`trial10`, following the corrected protocol: cube reset to the white pick
square before every trial, right-arrow key pressed the instant success was
observed. Reviewed by comparing the first and last frame of each rollout.

| # | Trial | Duration | Result | Details |
| --- | --- | --- | --- | --- |
| 1 | trial1 | 9.8 s | Success | Cube starts in white pick square, ends in black box |
| 2 | trial2 | 9.9 s | Success | Cube starts in white pick square, ends in black box |
| 3 | trial3 | 11.0 s | Success | Cube starts in white pick square, ends in black box |
| 4 | trial4 | 10.1 s | Success | Cube starts in white pick square, ends in black box |
| 5 | trial5 | 9.9 s | Success | Cube starts in white pick square, ends in black box |
| 6 | trial6 | 11.8 s | Success | Cube starts in white pick square, ends in black box |
| 7 | trial7 | 10.5 s | Success | Cube starts in white pick square, ends in black box |
| 8 | trial8 | 10.5 s | Success | Cube starts in white pick square, ends in black box |
| 9 | trial9 | 10.3 s | Success | Cube starts in white pick square, ends in black box |
| 10 | trial10 | 10.3 s | Success | Cube starts in white pick square, ends in black box |

**Success rate: 10/10 = 100%** (matched-setup, blue cube only, reset before
each trial, no operator intervention).

**v1 vs v2 side-by-side:**

| | v1 (step 2000) | v2 (step 10000) |
| --- | --- | --- |
| Comparable trials | 16 | 10 |
| Successes | 2 | 10 |
| Success rate | 12.5% | 100% |

This is a large, consistent improvement and matches the training diagnosis:
fixing `n_action_steps`/`temporal_ensemble_coeff` (closed-loop, smoothed
control) and training ~5x longer (10,000 vs 2,000 steps) directly addressed
the precision and jerkiness problems seen in v1. Caveats: sample size is
still small (10 trials), all in the same workspace/lighting/cube as training,
and duration alone doesn't guarantee correctness — always confirm by
comparing first/last frame, not just episode length, since a fast episode
could also mean an early miss.

## ACT vs. π0/π0.5: when to consider switching policy families

The v2 improvements above were achieved without changing model family — ACT
is still trained from scratch, purely on this task's own demonstrations, with
no external visual/semantic knowledge. That is enough for high accuracy
**inside the trained distribution** (same cube, same colors, same workspace),
but it has a structural ceiling: novel cube colors, novel objects, or new
workspaces are out-of-distribution inputs to a ResNet18 encoder that has
never seen anything but this task's 50 episodes.

| | ACT (current) | π0 / π0.5 (Physical Intelligence) |
| --- | --- | --- |
| Vision backbone | ResNet18, trained from scratch on this dataset only | Pretrained vision-language model (PaliGemma-based), trained on large multi-embodiment, multi-task data before ever seeing this task |
| Language conditioning | Dataset stores `single_task` text, but ACT does not use it | Uses the task-instruction text as a real conditioning input |
| Generalization to novel colors/objects | Not expected — color/appearance is entangled in what the vision encoder learned, with no abstracted "object" concept | Meaningfully better, because pretraining already encodes generic visual/semantic concepts (e.g. "cube," "box," color words) |
| Training approach | Train from scratch per task | Fine-tune a released pretrained checkpoint on your task's demonstrations (rarely trained from scratch) |
| Model size | ~11M params (ResNet18 + small transformer) | ~3B params (VLM backbone + action expert) |
| Compute | Trains/runs fine on CPU (this workflow: ~31 hours wall-clock for 10,000 steps on a 16-core CPU) | GPU strongly recommended for both fine-tuning and real-time inference; CPU-only is likely impractical at 30 fps control |
| LeRobot support here | Fully working (`pick_cube_run5_act`, `pick_cube_run5_act_v2`) | `pi0` and `pi0fast` policy code is present in this LeRobot install (`src/lerobot/policies/pi0`, `pi0fast`); **π0.5 specifically is not present** and would need to be added separately |

**Dataset reuse**: `wansnap/pick_cube_teleop_50ep_run5` can be reused directly
for π0 fine-tuning with no reformatting — LeRobot standardizes
`observation.images.*`, `observation.state`, `action`, and `single_task`
across all policy types, and π0's config (`PI0Config`) consumes exactly this
schema.

**Recommendation**: only move to π0/π0.5 if generalization beyond the trained
blue cube and this exact workspace is a real requirement, and only after
confirming GPU availability — otherwise, keep improving ACT (e.g. add a few
demonstrations with different cube colors to its own training set) as the
more practical near-term path on this CPU-only machine.

Once the v2 checkpoint (Section 3, "Recommended retrain settings") finishes
training, repeat Section 5 deployment with
`--policy.path=.../pick_cube_run5_act_v2/checkpoints/<step>/pretrained_model`,
record new `eval_` rollouts, then re-run the last-frame review script above
and rebuild this same table format for a direct before/after comparison.
