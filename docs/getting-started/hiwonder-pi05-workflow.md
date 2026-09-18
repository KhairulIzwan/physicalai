# Hiwonder SO-101 Pi0.5 Workflow

This is an integration and evaluation plan for Pi0.5 on the SO-101. It is not
yet a live deployment guide. For the working ACT workflow, see [the Hiwonder
ACT workflow](hiwonder-act-workflow.md). For earlier OpenVINO/Panther Lake
inference benchmark history, see [the physicalai exploration
record](../../EXPLORATION.md).

No Pi0.5-to-SO-101 action adapter was validated before 2026-09-15. As of
that date, an offline adapter validation and three supervised hardware runs
have been completed — see [the 2026-09-15
update](#update-2026-09-15-openvino-export-offline-replay-and-first-hardware-runs)
below before running further trials. Do not send a Pi0.5 action to the arm
outside a short, supervised trial with an operator present and the workspace
clear.

## Current status: fine-tuning via physical-ai-studio (2026-09)

Pi0.5 fine-tuning is being run through `physical-ai-studio` (a separate
application from this `physicalai` repo) on an Intel integrated GPU
(`xpu:0`). The training dataset is the same 50-episode run used for the
SO-101 ACT baseline: it was copied/re-imported from the existing ACT dataset
cache at
`/home/user/.cache/huggingface/lerobot/wansnap/pick_cube_teleop_50ep_run5`
into physical-ai-studio as dataset `pick_cube_teleop_50ep_run5_inherit_hiwonder`,
so no new demonstrations were collected for this fine-tuning attempt.

**First attempt** (`pick_cube_run5_pi05_v2_xpu`, `batch_size=2`) failed at
step 1370/10000 (14%) with `RuntimeError: level_zero backend failed with
error: 39 (UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY)`. The iGPU shares system
RAM for device memory, and full fine-tuning of the PaliGemma-2B backbone plus
the 300M action expert exhausted it even at the minimum practical batch size.

**Retry** (`pick_cube_run5_pi05_v3_xpu_frozen_vit`) uses the same dataset and
`batch_size=2`, but adds `freeze_vision_encoder=true` to reduce activation
memory. As of this writing it is running past step 6300/10000 (63%) without
error, well beyond the point where the previous attempt crashed, with loss
trending down (~0.03-0.15).

This is a training-only milestone: it confirms Pi0.5 can be fine-tuned on
this hardware and dataset, but it does not by itself validate any SO-101
action adapter, camera/state/action mapping, or hardware rollout. All gates
in this document still apply before any action from a fine-tuned Pi0.5
checkpoint is sent to the arm.

## Model interface versus SO-101

At the policy level, Pi0.5 accepts camera images, task text, and a padded
robot state, then predicts a padded future action chunk. The current SO-101
ACT workflow uses:

```text
fixed image + hand-eye image + state[1, 6] -> action[1, 6]
```

| Contract | Pi0.5 | Current SO-101 ACT setup | Required work |
| --- | --- | --- | --- |
| Cameras | Configurable camera slots (fixed/hand-eye images), internally resized to 224 x 224 | Fixed and hand-eye 640 x 480 inputs | Define camera names, ordering, resizing, and color convention |
| State | Padded to `state[1, 32]` (`max_state_dim`) | 6 joint positions | Determine the meaning of the padded/unused state values; never pad with zeros without model documentation |
| Action | `chunk_size`/`n_action_steps` future actions, padded to `[1, 50, 32]` (`max_action_dim`) | 6 joint-position targets | Map action meaning, joint order, units, and absolute/delta convention |
| Task | Tokenized natural-language string | One fixed task string | Verify exact prompt/tokenizer behavior |
| Timing | One action chunk per inference | Online joint commands | Choose a safe action-chunk execution and refresh strategy |

The Pi0.5 model is a vision-language-action policy. It predicts robot actions;
it is not a conventional object detector or classifier. Its language input may
provide broader task conditioning, but it does not remove the need for a
correct SO-101 action interface.

## Build and test the SO-101 adapter offline

Before connecting the robot, implement an adapter with explicit checks for:

1. The exact Pi0.5 checkpoint’s state and action semantics.
2. Fixed/hand-eye camera ordering, resize/crop, RGB/BGR conversion, and frame history.
3. All six SO-101 joint names and their order.
4. Joint units and whether actions are absolute positions or deltas.
5. Pi0.5 normalization/de-normalization statistics.
6. Mapping or documented placeholders for the padded state/action format.
7. How the action chunk is refreshed and which action steps are executed.

Replay observations from `wansnap/pick_cube_teleop_50ep_run5` through the
adapter without a robot connection. Save predicted actions and reject any
non-finite values, incorrect shapes, or values outside documented SO-101 joint
limits. Compare them with recorded actions only after both action conventions
are known to match.

## Hardware gate

Do not run a pick-and-place task until all of these conditions hold:

- The exact Pi0.5 checkpoint's documentation supports the selected runtime and
  action representation.
- Offline SO-101 adapter tests pass on recorded run5 episodes.
- The camera, state, joint order, units, normalization, and action-chunk
  semantics are documented and tested.
- Independent joint safety limits are active, the operator is present, the
  workspace is clear, and arm power is immediately accessible.
- A short supervised motion test succeeds with the cube removed.

Only then run one supervised, recorded Pi0.5 evaluation in the unchanged run5
workspace. Use the ACT workflow as the performance baseline: seven confirmed
successful operator-observed pick-and-place runs with the existing ACT
checkpoint.

## Update (2026-09-15): OpenVINO export, offline replay, and first hardware runs

Checkpoint `pick_cube_run5_pi05_v7_xpu_frozen_vit_step7106_recovered` (model
id `a3d214c7-e60f-47d2-988e-5ae0d936cbbf`, `train_job_id
b21a00ac-2d87-4bd7-8caf-51941e4189e6`) has the lowest validation loss
(0.1204) of the four recovered checkpoints from this fine-tuning run. It was
exported to OpenVINO via `physicalai export --policy
physicalai.policies.Pi05 --ckpt_path model.ckpt --backend openvino
--output_dir /tmp/pi05_v7_openvino_export` and evaluated as follows.

### Offline replay validation (adapter gate: passed)

Do not hand-roll the pre/postprocessing pipeline against the raw ONNX/OpenVINO
graph. The `Pi05Preprocessor` builds a prompt string that embeds the
*discretized, normalized state* as text (`"Task: …, State: 0 1 2…;\nAction:
"`) before tokenization — the tokenizer input is not the plain task string.
Use `physicalai.inference.InferenceModel.load(export_dir)` and its
`predict_action_chunk(observation)` method, which applies the manifest's
declared preprocessors (state normalization, image resize-with-pad + [-1,1]
scaling, prompt construction, tokenization) and postprocessors (action
denormalization) exactly as the training code does.

Replayed 10 frames spread across episode 0 of
`pick_cube_teleop_50ep_run5_inherit_hiwonder` (idle, grasp, and place phases),
comparing the model's predicted first action step against the recorded
demonstration action:

- Overall mean absolute error: **3.0°** across all 6 joints.
- Per-joint MAE: `[0.64, 6.46, 4.1, 3.04, 1.45, 2.34]` degrees.

This passes the offline adapter gate for this checkpoint on episode 0.

### Hardware runs

The `physical-ai-studio` backend server holds `/dev/ttyACM0` and
`/dev/ttyACM1` open exclusively for its own teleop/robot-control features. It
must be stopped before `physicalai run` (CLI) can open the follower's serial
port directly. The two camera devices are shared via
`physicalai.capture.SharedCamera`, subscribing to the existing
`_publisher_worker` processes (these can keep running independently of the
backend).

Runtime config used: `/tmp/runtime.yaml` — `SO101` follower on
`/dev/ttyACM1`, `InferenceModel` pointed at the OpenVINO export,
`SyncExecution`, task string `"pick up the cube and place it in the box"`,
cameras mapped as `fixed` → `camera-01` (`/dev/video0`) and `handeye` →
`camera-follower-01` (`/dev/video2`).

Three supervised runs (operator present, workspace clear, cube in position):

1. 15 s, `device: CPU` — clean exit, arm behavior judged reasonable.
2. 120 s, `device: CPU` — clean exit, completed pick-and-place cycles well.
3. 120 s, `device: CPU` — arm moved to the pick area and then stalled.

Benchmarked `predict_action_chunk` latency on the same export directly
(random dummy inputs, 3-call average after 1 warmup call):

- **CPU: ~25 s per inference call.**
- **GPU (Intel iGPU, OpenVINO `GPU` device): ~0.69 s per inference call**
  (after first-call kernel compilation, which itself takes several minutes
  and should be treated as a one-time warmup cost, not a per-run cost).

GPU is ~36x faster than CPU and comfortably covers the ~1.7 s of motion in
each 50-step/30 fps action chunk, so `device: GPU` alone (without needing
`AsyncExecution`) should resolve the stall seen in run 3.

The stall in run 3 is explained by CPU latency, not a policy or hardware
fault: `SyncExecution` blocks the control loop while waiting for the next
action chunk. A chunk covers `chunk_size=50` steps at 30 fps (~1.7 s of
motion), so a ~25 s CPU inference call leaves the arm holding position for
over 20 s between chunks — this reads as a "stall" even though the run exits
cleanly. Runs 1 and 2 likely did not hit this gap as visibly by chance of
timing/task phase, not because CPU inference was actually fast enough.

**Before further hardware trials**, set `device: GPU` in the runtime config
(Intel iGPU via OpenVINO) instead of `CPU`. Expect the first inference call
after process start to take several minutes (GPU kernel compilation); warm up
before starting a timed/recorded trial, or run once and discard the first
chunk. `execution: physicalai.runtime.AsyncExecution` remains an option for
further jitter reduction but is not required to resolve the run-3 stall.

Do not run further hardware trials with `SyncExecution` on `CPU` — the stall
is a control-loop throughput problem, independent of the checkpoint's offline
accuracy, and is resolved by using `GPU`.

### Follow-up: GPU retest still stalled — two additional suspects found

A repeat 120s hardware trial with `device: GPU` in `runtime.yaml` still stalled, ruling out CPU
latency as the sole cause. Investigation (read-only, no actuation) turned up two concrete issues:

1. **Reset pose sits at the edge of (or outside) the training distribution.** Reading the
   follower's actual joint state at the pre-trial reset pose gave
   `[5.3, -98.6, 98.4, 43.8, 3.7, 0.0]` degrees. Comparing against the training dataset's
   per-joint `min`/`max` (baked into the OpenVINO export's normalizer stats): `shoulder_lift`
   (-98.6, range -99.4..70.8) and `elbow_flex` (98.4, range -71.4..99.9) sit at the extreme edge,
   and `gripper` (0.0, range 1.7..51.0) is **outside** the training range entirely. Near/beyond
   quantile-normalization bounds the model extrapolates, which can produce invalid/near-limit
   commands the servo firmware refuses or clamps — visible as a stall.
2. **Possible calibration/provenance mismatch.** The pi05 v7 checkpoint was trained on dataset
   `89ed29e0-...` (`so101_follower` type, 50 episodes — matches the "pick_cube_teleop_50ep..."
   name). Four robot calibration profiles exist on disk, but only two distinct homing-offset
   sets are represented, and it could not be confirmed (app backend was offline) that the
   robot/calibration that recorded `89ed29e0` matches `follower-01`'s current calibration
   (`6a9601c3-.../633558be-...`). If they differ, "degrees" in the dataset do not correspond to
   the same physical joint angle on the currently connected arm.

**Decision:** rather than patch around this, the plan is to (a) shut down and install a discrete
GPU (removing the CPU/iGPU latency question entirely), (b) **recollect the training dataset on
the actual current `follower-01` hardware/calibration**, using reset poses with margin away from
joint extremes and some pose-to-pose randomization so the distribution has slack, and (c)
retrain pi05 from this new dataset before further hardware trials. This resolves both suspects
at once rather than debugging them independently.

## Data strategy

Pi0.5 pretraining may reduce the amount of task-specific data needed for useful
visual and language behavior. It does not make the 50 run5 episodes directly
compatible automatically. Fine-tuning or adapter calibration still requires
SO-101 demonstrations in the same camera, state, action, and timing convention
used at deployment.

Keep the current 50 reviewed ACT demonstrations as the baseline. Collect more
only to support a stated goal, such as higher reliability or controlled
variation in cube position, box position, start pose, lighting, or task text.
