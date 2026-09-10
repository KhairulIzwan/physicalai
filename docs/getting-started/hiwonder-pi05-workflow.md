# Hiwonder SO-101 Pi0.5 Workflow

This is an integration and evaluation plan for Pi0.5 on the SO-101. It is not
yet a live deployment guide. For the working ACT workflow, see [the Hiwonder
ACT workflow](hiwonder-act-workflow.md). For the underlying Panther Lake
benchmark results, see [the physicalai exploration record](../../EXPLORATION.md)
and Intel's [Pi0.5 OpenVINO optimization documentation](https://docs.openedgeplatform.intel.com/2026.1/edge-ai-suites/robotics-ai-suite/embodied/openvino_optimization.html).

## Current status

`physicalai` already contains an OpenVINO Pi0.5 benchmark path. It supports
model discovery/download, task-text preprocessing, and inference benchmarks.
The earlier Panther Lake measurements were:

| Model | Device | Median inference latency | Throughput |
| --- | --- | ---: | ---: |
| Pi0.5 Libero FP16 | GPU | 524.6 ms | 1.9 FPS |
| Pi0.5 Libero INT8 | GPU | 361.4 ms | 2.8 FPS |
| Pi0.5 Libero FP16 | CPU | 12,429 ms | 0.1 FPS |

The NPU did not complete Pi0.5 inference because the model exceeds its memory
budget. Use the GPU for Pi0.5 experiments. The model artifacts are not in the
repository; use the benchmark download workflow when they are needed.

No Pi0.5-to-SO-101 action adapter or hardware rollout is validated yet. Do not
send a Pi0.5 action directly to the arm.

## Model interface versus SO-101

At the policy level, the benchmarked Pi0.5 Libero export accepts two camera
images, task text, and an eight-value robot state, then predicts a 50-step
seven-value action chunk:

```text
2 camera images + task string + state[1, 8] -> action chunk[1, 50, 7]
```

The OpenVINO graph uses padded internal representations. Intel's reference
benchmark supplies `state[1, 32]` and `actions[1, 50, 32]`, along with image,
mask, and language-token tensors. The Pi0.5 preprocessor/adapter converts
between the policy-level robot values and these internal tensors. The SO-101
adapter must use that preprocessing layer rather than send raw six-value joint
vectors directly to the graph.

The current SO-101 ACT workflow uses:

```text
fixed image + hand-eye image + state[1, 6] -> action[1, 6]
```

| Contract | Pi0.5 benchmark export | Current SO-101 ACT setup | Required work |
| --- | --- | --- | --- |
| Cameras | Two 224 x 224 images plus one empty camera slot | Fixed and hand-eye 640 x 480 inputs | Define camera names, ordering, resizing, and color convention |
| State | 8 robot values, then padded to graph `state[1, 32]` | 6 joint positions | Determine the meaning of the two missing robot values; never pad with zeros without model documentation |
| Action | 50 future 7-value actions, internally padded to `[1, 50, 32]` | 6 joint-position targets | Map action meaning, joint order, units, and absolute/delta convention |
| Task | Tokenized natural-language string | One fixed task string | Verify exact prompt/tokenizer behavior |
| Timing | One action chunk per inference | Online joint commands | Choose a safe action-chunk execution and refresh strategy |

The Pi0.5 model is a vision-language-action policy. It predicts robot actions;
it is not a conventional object detector or classifier. Its language input may
provide broader task conditioning, but it does not remove the need for a
correct SO-101 action interface.

## 1. Benchmark the model offline

Follow Intel's documented Pi0.5 environment in a separate environment: Python
3.10, a Hugging Face LeRobot source checkout with `pip install -e ".[pi]"`,
then its documented OpenVINO and NNCF versions. Do not modify the working
Hiwonder `lerobot` environment. Once that environment is available, use the
existing benchmark script. A Hugging Face access token may be required for
gated models; set it directly in the shell and never store it in this document.

```bash
cd /home/user/physicalai
.venv/bin/python benchmark.py \
  --model OpenVINO/pi05-libero-fp16-ov \
  --device GPU \
  --task "pick up the cube and place it in the box" \
  --iters 20 \
  --warmup 3
```

For the existing locally quantized INT8 export, use its actual local directory:

```bash
cd /home/user/physicalai
.venv/bin/python benchmark.py \
  --model models/pi05-libero-int8 \
  --device GPU \
  --task "pick up the cube and place it in the box"
```

This benchmark uses dummy zero-valued observations. It validates model loading
and latency only; it is not evidence of correct SO-101 behavior.

## 2. Build and test the SO-101 adapter offline

Before connecting the robot, implement an adapter with explicit checks for:

1. The exact Pi0.5 checkpoint’s state and action semantics.
2. Fixed/hand-eye camera ordering, resize/crop, RGB/BGR conversion, and frame history.
3. All six SO-101 joint names and their order.
4. Joint units and whether actions are absolute positions or deltas.
5. Pi0.5 normalization/de-normalization statistics.
6. Mapping or documented placeholders for the 8-state/7-action format.
7. How the 50-step action chunk is refreshed and which action steps are executed.

Replay observations from `wansnap/pick_cube_teleop_50ep_run5` through the
adapter without a robot connection. Save predicted actions and reject any
non-finite values, incorrect shapes, or values outside documented SO-101 joint
limits. Compare them with recorded actions only after both action conventions
are known to match.

## 3. Hardware gate

Do not run a pick-and-place task until all of these conditions hold:

- The exact Pi0.5 model documentation supports the selected runtime and action
  representation.
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

## Data strategy

Pi0.5 pretraining may reduce the amount of task-specific data needed for useful
visual and language behavior. It does not make the 50 run5 episodes directly
compatible automatically. Fine-tuning or adapter calibration still requires
SO-101 demonstrations in the same camera, state, action, and timing convention
used at deployment.

Keep the current 50 reviewed ACT demonstrations as the baseline. Collect more
only to support a stated goal, such as higher reliability or controlled
variation in cube position, box position, start pose, lighting, or task text.
