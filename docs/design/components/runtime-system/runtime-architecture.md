# Runtime Architecture

Status: proposal (supersedes the external `robot_runtime_architecture.md` draft)
Scope: one robot, one fixed-FPS loop, one active action source.

This document describes the production single-rate robot runtime for
`physicalai` **as it exists today** and the one architectural change needed to
generalize it: making the action source pluggable so the same loop can run a
policy, a teleoperator, a human-in-the-loop mix, or a scripted routine.

It is written against the current code in `src/physicalai/runtime/`, not an
aspirational rewrite. Where the earlier external draft
(`robot_runtime_architecture.md`) disagrees with the shipped implementation,
this document follows the code.

## The Design Question

> Today the control loop is `PolicyRuntime`. It hard-wires policy inference into
> the loop. How do we run _any_ action source — policy, teleop, HIL, scripted —
> without forking the loop?

Answer:

```text
RobotRuntime      owns the robot loop and lifecycle (the loop we already have)
Controller        chooses the next action        (the missing abstraction)
PolicyController  adapts inference into a Controller
PolicyRuntime     stays as a policy-only RobotRuntime subclass (backward-compatible entry point)
```

The loop, the resilient IO, the callback/event system, and the config/CLI
surface already exist and stay. The only new concept is `Controller`, which
lifts "how the next action is chosen" out of the loop body.

## What Exists Today

`PolicyRuntime` (`src/physicalai/runtime/runtime.py`) is the top-level loop. Its
constructor takes the robot, the model, the execution strategy, the action
queue, cameras, callbacks, and a task string directly:

```python
PolicyRuntime(
    robot, model, execution, fps,
    cameras=..., action_queue=..., callbacks=..., task=...,
)
```

The loop body is, in essence:

```python
robot_obs, camera_frames = self._resilient_observe()
self._execution.maybe_request(self._build_model_input_from(robot_obs, camera_frames))
action = self._action_queue.pop()
if action is None:
    action = last_action            # hold last
    self._handle_hold(step=step)
action = self._bus.invoke_before_send_action(action=action, step=step)
self._resilient_send(action)
self._bus.invoke_on_action_sent(action=action, step=step)
```

The policy is not a component the loop calls — it _is_ the loop. `maybe_request`,
`pop`, the hold/fallback, and `_build_model_input_from` (the `STATE` / `IMAGES` /
`TASK` model-input formatting) are all inlined into `PolicyRuntime`.

Everything else that the runtime owns is already generic and worth keeping:

| Concern                                         | Where it lives now                       | Keep? |
| ----------------------------------------------- | ---------------------------------------- | ----- |
| Fixed-FPS timing, sleep-to-tick                 | `PolicyRuntime.run()`                    | yes   |
| Resilient observe (retry + stale fallback)      | `_resilient_observe`, `_retry_robot_obs` | yes   |
| Resilient send (retry + consecutive-error stop) | `_resilient_send`                        | yes   |
| Warmup with retry                               | `_warmup_with_retry`                     | yes   |
| Safe shutdown + queue drain                     | `_shutdown`                              | yes   |
| Connect/disconnect, context manager             | `connect`/`disconnect`/`__enter__`       | yes   |
| Callback + event bus                            | `_CallbackBus`, `events.py`              | yes   |
| Config / CLI / `from_config`                    | `cli/run.py`, jsonargparse               | yes   |

### Inference stack (already generic, already shipped)

The policy side is already factored into replaceable strategies. These do **not**
need to change; they become owned by `PolicyController` instead of the runtime.

- `Execution` ABC (`execution.py`): `set_bus`, `start(model, queue)`,
  `maybe_request(observation)`, `warmup(sample)`, `stop`, `chunk_size`.
  Implementations: `SyncExecution`, `AsyncExecution`, `RTCExecution`. Phase 1
  changes `maybe_request` to take a **provider** (`maybe_request(observe_fn)`) so
  it pulls the observation only on ticks it actually requests inference — see
  [Observation is a pull](#observation-is-a-pull). Internal signature change
  across the three implementations; `chunk_size` stays internal to the policy
  (the loop never reads it).
- `ActionQueue` protocol: `pop`, `push_chunk`, `remaining`, `below_threshold`,
  `reset`, plus hold/pop counters. Implementations: `ChunkedActionQueue`,
  `RTCActionQueue`.
- Chunk smoothing: `LerpSmoother`, `ReplaceSmoother`.

Note: the external draft calls this `InferenceExecution` and treats RTC as a
future "merger". In this codebase it is `Execution`, and `RTCExecution` +
`RTCActionQueue` already ship. No rename is proposed — churn without benefit.

### Callbacks (already richer than the external draft)

The shipped callback system is an event bus, not the flat `on_observation` /
`on_user_event` interface in the external draft. Keep it. Two dispatch modes:

- Fire-and-forget events: `on_tick(TickEvent)`, `on_inference(InferenceEvent)`,
  `on_lifecycle(LifecycleEvent)` — telemetry, exceptions isolated.
- Request/response hooks: `before_send_action(action, step) -> action | None`,
  `on_action_sent(action, step)`, `on_hold(step, holds)` — action-path hooks,
  chained return values.

Shipped callbacks: `ConsoleCallback`, `JsonlCallback`, `AsyncCallback`,
`RerunCallback`. `LowPassFilterCallback` is an in-loop smoothing hook.

These are for side effects and instrumentation. They are **not** where action
arbitration belongs — that is the `Controller`'s job.

## Target Architecture

One change: introduce `Controller`, move the policy specifics behind it, and
turn the loop into `RobotRuntime`. `PolicyRuntime` is preserved as a
`RobotRuntime` subclass.

```python
RobotRuntime.run() tick:
  tick = Tick(robot, cameras, clock, frame_index)  # no device reads yet
  action = controller.update(tick)                 # pulls only what it needs
  action = callbacks.before_send_action(action)    # existing hook
  robot.send_action(action)                         # existing resilient send
  callbacks.on_action_sent(action)
  emit_tick(tick, action)                           # builds TickEvent(tick=...); recording pulls here
  sleep_until_next_tick()
```

Device reads are a **pull, not a push**, and they are **granular**:
`tick.robot_state()` and `tick.camera_frames()` each read at most once per tick,
independently, and only if a consumer asks. A teleop controller pulls neither; a
proprioceptive controller pulls only `robot_state()`; a vision policy pulls both.
See [Observation is a pull](#observation-is-a-pull) for why.

Ownership:

```text
RobotRuntime  decides when the loop runs, does robot IO, timing, resilience, events
Controller    decides what action to take
Robot         decides how hardware IO happens
```

### Controller

The new abstraction. Small on purpose.

```python
class Tick:                                              # concrete; RobotRuntime is the only producer
    frame_index: int                                     # bookkeeping, no IO
    timestamp: float                                     # loop tick time, no IO
    def robot_state(self) -> RobotObservation: ...       # lazy + cached: one follower read
    def camera_frames(self) -> Mapping[str, Frame]: ...  # lazy + cached: camera reads
    def observation(self) -> Observation: ...            # convenience: composes both


class Controller(Protocol):
    def set_bus(self, bus, session_id) -> None: ...      # optional; runtime injects if present
    def start(self) -> None: ...
    def warmup(self, tick: Tick) -> None: ...            # optional; no-op default
    def update(self, tick: Tick) -> np.ndarray | None: ...
    def stop(self) -> None: ...
    def reset(self) -> None: ...
```

`Tick` is a **concrete class**, not a Protocol: `RobotRuntime` is its only
producer, controllers and callbacks only consume it, and it carries real
memoized-read behavior that has to live in an implementation anyway. It mirrors
the existing runtime-produced per-tick objects `TickEvent` / `InferenceEvent` /
`LifecycleEvent`, which are concrete dataclasses too. It exposes cheap
bookkeeping (`frame_index`, `timestamp` — no IO) and **granular, independently
lazy** device reads. `frame_index`/`timestamp` are the loop's tick identity and
scheduling time; they are deliberately _not_ the capture timestamps —
`RobotObservation.timestamp` (when joints were read) and `Frame.timestamp`
(capture time) carry those, and come from the reads themselves. Each of
`robot_state()` / `camera_frames()` memoizes independently and carries its own
resilient-observe (retry + stale) logic. `observation()` is just the convenience
composition a vision policy uses to build model input.

- `set_bus(bus, session_id)` — optional, and only `PolicyController` implements
  it (it forwards to its `Execution`, which needs the bus + `session_id` to emit
  `InferenceEvent`s). The runtime calls it duck-typed before `start()`, exactly
  as it injects `Execution.set_bus` today. Teleop and scripted controllers omit
  it.
- `start()` — bind resources and spawn any workers. Argument-free.
- `warmup(tick)` — optional. The runtime reads a first tick with retry
  (`_warmup_with_retry`) and hands it to the controller so a policy can pull
  `tick.observation()`, seed its queue, and discover `chunk_size`. Teleop and
  scripted controllers no-op.
- `update(tick) -> np.ndarray | None` — the per-tick action choice. The
  controller **pulls** only the reads it needs: a vision policy pulls
  `observation()`; a teleop controller pulls nothing and reads its leader device
  instead. Returning `None` means "no action this tick"; the runtime holds the
  last sent action (the generic safety net that exists today). A policy normally
  returns a fallback (hold-last-policy-action) itself rather than `None`.
- `stop()` / `reset()` — lifecycle, mapping to `Execution.stop()` + `model.close()`
  and queue reset respectively.

Design decisions that diverge from the external draft, and why:

1. `update(tick)` receives a **tick handle with granular, lazy reads**, not an
   already-read observation. The action does not always depend on the follower
   observation — for teleop the action source is the leader arm, and the follower
   state + camera frames are needed only for recording. Even a policy may want
   state without images. Pushing an eager, bundled observation into every
   `update()` would add camera-read latency and jitter to the teleop action path
   and waste IO on ticks nobody consumes (including async-policy ticks that skip
   inference). See [Observation is a pull](#observation-is-a-pull).
2. Bus injection reuses the existing `set_bus(bus, session_id)` pattern rather
   than inventing a new `RuntimeContext` type. Only `PolicyController` needs it,
   the runtime already injects it into `Execution` this exact way today, and
   keeping it optional imposes nothing on non-policy controllers.
3. `warmup(tick)` is a first-class step, not folded into the first `update()`.
   This preserves the current retry-with-backoff warmup semantics (the runtime
   re-reads the robot and retries) rather than warming up lazily on a
   possibly-stale first observation.
4. `update()` may return `None` to mean "no action this tick" (e.g. the policy
   queue is starved); the runtime holds the last sent action, matching today's
   queue-empty behavior. This is distinct from `update()` **raising**: in
   Phase 1 an exception keeps today's **fail-stop** semantics (the run stops).
   Silently holding-and-continuing past a controller fault can be unsafe — a
   teleop leader-read fault would freeze the follower while the operator believes
   it is live — so hold-and-continue on error is an opt-in controller capability
   added with `TeleopController` in Phase 2, not a Phase-1 runtime default.

### PolicyController

Adapts the existing inference stack into a `Controller`. It owns what the loop
currently inlines:

```python
class PolicyController:
    def __init__(self, model, execution, action_queue=None, task=None, fallback=None): ...

    def set_bus(self, bus, session_id):
        self._execution.set_bus(bus, session_id)     # forward to Execution (unchanged wiring)

    def start(self):
        self._execution.start(self._model, self._action_queue)

    def warmup(self, tick):
        # Always needs the observation; the runtime hands a FRESH tick per retry.
        self._execution.warmup(self._to_model_input(tick.observation()))   # was _build_model_input_from

    def update(self, tick):
        # Pull-based: Execution invokes the provider only when it will request
        # inference this tick, so a full queue (async idle tick) reads nothing.
        self._execution.maybe_request(lambda: self._to_model_input(tick.observation()))
        action = self._action_queue.pop()
        if action is None:
            return self._fallback(tick)            # hold-last / configured fallback
        self._last = action
        return action

    def stop(self):
        self._execution.stop()
        self._model.close()

    def reset(self):
        self._action_queue.reset()
```

`_to_model_input` is today's `_build_model_input_from`: it assembles the
`STATE` / `IMAGES.<name>` / `TASK` mapping with batch dims. Both halves of
today's input path move here — `_build_model_input` (the wrapper that does the
device reads) becomes the `tick.observation()` pull, and `_build_model_input_from`
becomes `_to_model_input`. This is a **policy concern** and belongs here, not in
the loop. A `TeleopController` never sees `model_input` and never calls
`robot_state()` / `camera_frames()`; it reads its leader device.

### Observation is a pull

The earlier draft of this loop read the observation eagerly, before every
`controller.update`, and read robot state + cameras together. That is wrong once
the action source is not a vision policy.

Consider teleop: the action comes from a **leader** arm. The follower's state and
the camera frames are **not inputs to the action** — they are needed only for
recording the demonstration. Forcing an eager, bundled `observe()` before
`update()` therefore:

- adds follower-state + camera-read latency and jitter to the teleop action path
  (you want leader-read → follower-write to be tight);
- wastes IO whenever nothing consumes the reads;
- conflates the _action source_ (leader, owned by the controller) with the
  _logging observation_ (follower + cameras, owned by the runtime);
- couples two independent reads: a proprioceptive controller wanting only cheap
  joint state is forced to pay for the expensive camera reads too.

It is not teleop-specific. An async/chunked policy skips inference on most ticks
(the queue is full). To actually save those reads, `PolicyController.update`
hands `Execution.maybe_request` a **provider** rather than a materialized
observation, so `tick.observation()` fires only on ticks that request inference.
Without that — passing an already-read observation, as the shipped
`maybe_request(observation)` takes today — a vision policy would read _every_
tick regardless, and the async-idle row below would not hold. Making the read
savings real for the flagship policy path is precisely why `maybe_request`
becomes pull-based.

The provider only skips the pull if the `Execution` invokes it **conditionally**.
`SyncExecution` and `AsyncExecution` already gate on `below_threshold` (and, for
async, `not busy`) _before_ touching the observation, so wrapping the argument in
a provider is enough — they call it only on request ticks. `RTCExecution` is
structured differently: its main-thread `maybe_request` **unconditionally**
publishes the observation into `_obs_slot` every tick, and the _background_ thread
owns the `below_threshold` decision. A mechanical signature swap there would call
the provider — and read the device — on **every** tick, so the async-idle row
would not hold for RTC. RTC's `maybe_request` therefore needs an added main-thread
`below_threshold` pre-check (its `RTCActionQueue.below_threshold` is lock-safe to
call from the loop thread) so it invokes the provider only when a refill is
imminent. The one behavioral consequence: the background thread then inpaints from
the snapshot captured at the last sub-threshold tick rather than the absolute
latest tick — the same staleness `AsyncExecution` already accepts, and harmless in
practice.

So device reads are a **granular pull**: `tick.robot_state()` and
`tick.camera_frames()` each read **at most once per tick, independently, and only
if asked**. Each carries the existing resilient-observe logic (retry + stale
fallback) for its device. `tick.observation()` is a convenience that composes
both for a vision policy. Who pulls what:

| Scenario                                     | robot_state reads | camera reads  |
| -------------------------------------------- | ----------------- | ------------- |
| teleop, no recording                         | 0                 | 0             |
| teleop + recording                           | 1 (recording)     | 1 (recording) |
| proprioceptive controller                    | 1                 | 0             |
| async vision policy, idle tick, no recording | 0                 | 0             |
| vision policy request tick, or recording     | 1 (shared)        | 1 (shared)    |

Two invariants make the shared/zero rows real:

- **Exactly one `Tick` per loop iteration**, threaded through both
  `controller.update(tick)` and `emit_tick` (referenced by `TickEvent`). Memoized
  reads are shared only if it is the _same_ `Tick` instance; two instances mean a
  policy and a recording callback double-read.
- **Recording relocates the reads, it does not remove them.** `emit_tick` runs
  after the send/sleep boundary, so a recording callback pulling
  `tick.robot_state()` / `tick.camera_frames()` there does the device IO later in
  the tick and on the callback's turn, not at the top. Every recorded tick still
  reads robot + cameras once; only the timing moves. For **training data** this is
  why recording captures at a **pre-send** point (below), so the observation is
  time-aligned with the action; an `on_tick` (post-send) pull would record the
  follower _after_ it started moving.

Two levels, kept distinct:

- At the robot boundary: the typed `RobotObservation` (joint positions,
  timestamp, images, `.state`) plus camera `Frame`s. Unchanged. These carry the
  authoritative **capture** timestamps.
- Exposed via `tick`: cheap bookkeeping (`frame_index`, loop `timestamp` — no IO)
  plus the granular `robot_state()` / `camera_frames()` reads and the
  `observation()` composition. The policy converts to model-input internally;
  teleop ignores the reads; recording logs whatever the dataset needs.

The runtime no longer builds `model_input`, and no longer reads any device
unconditionally. Formatting moves into `PolicyController`; each read is deferred
to whoever needs it.

### RobotRuntime

The current `PolicyRuntime` loop with the policy specifics extracted:

```python
class RobotRuntime:
    def __init__(self, robot, controller, fps,
                 cameras=None, callbacks=()): ...

    def run(self, *, duration_s=None) -> RunStats: ...
    def connect(self) / disconnect(self) / __enter__ / __exit__
    @classmethod
    def from_config(cls, config) -> "RobotRuntime"
```

It keeps `_resilient_send`, `_shutdown`, the event bus, and the timing loop
verbatim. `_resilient_observe` splits **behind** `tick.robot_state()` and
`tick.camera_frames()` so each runs lazily and is cached per tick.
`_warmup_with_retry` now hands a `Tick` to `controller.warmup`. The main body
change is replacing the inlined eager `observe` + `maybe_request` + `pop` +
`_handle_hold` with a `Tick` plus `controller.update(tick)`.

Two consequences of moving the queue into the controller:

- **Shutdown drain moves into `controller.stop()`.** Today `_shutdown` drains
  `self._action_queue` directly; once the queue lives in `PolicyController`, the
  drain is the controller's responsibility (a teleop controller has nothing to
  drain). `RobotRuntime._shutdown` calls `controller.stop()` and no longer
  touches a queue.
- **`TickEvent` must carry the `Tick`, not eager reads.** Today `TickEvent`
  eagerly holds `robot_observation` and `camera_frames`; emitting it would force
  exactly the reads the lazy `Tick` defers. `emit_tick` therefore builds a
  `TickEvent` that references the `Tick` (and the sent action), so a recording
  callback pulls `tick.robot_state()` / `tick.camera_frames()` itself. This is a
  breaking change to `TickEvent`'s shape (blast radius: `JsonlCallback`,
  `RerunCallback`, `AsyncCallback` read those fields today) — see
  [Phasing](#phasing).
- **`RunStats` becomes controller-optional.** Today `run()` reads
  `inference_count` off `self._execution` and `total_pops` / `total_holds` off
  `self._action_queue`. Once those live in `PolicyController`, `RobotRuntime`
  owns only loop-level stats (`steps`, `transient_errors`, `stale_obs_ticks`);
  the controller contributes its own via an optional `stats()` the runtime
  merges. A non-policy controller contributes none.
- **Start-of-run reset splits.** `_reset_session` today resets the session id,
  error/stale counters, _and_ the queue. Keep session/error reset in the
  runtime; the queue reset moves to `controller.reset()`, which the runtime calls
  at the top of `run()`.
- **Fresh `Tick` per warmup retry.** `_warmup_with_retry` re-reads the robot on
  every attempt today. Because a `Tick` memoizes its reads, the runtime must
  build a **new** `Tick` per warmup attempt — re-handing one would reuse a stale
  read and lose the current re-read-on-failure resilience.
- **`consecutive_error_ticks` is read/attempt-driven, not tick-driven.** The
  counter is shared by observe and send (a send success resets the observe side).
  Once observe sits behind `tick.robot_state()`, a tick that never pulls it must
  neither advance nor reset the observe counter — drive it from actual read
  attempts, not from tick count.

### PolicyRuntime (backward compatibility)

`PolicyRuntime` is public API: the CLI does `add_class_arguments(PolicyRuntime)`,
`from_config` is documented, and `examples/runtime/runtime.yaml` targets it. It
is **not** renamed, and it stays a **class** (not a bare factory function) —
`cli/run.py` and `from_config` call `add_class_arguments` +
`add_method_arguments(..., "run", ...)`, which require a class exposing `run()`.
It subclasses `RobotRuntime` and builds the `PolicyController` in its
constructor, preserving today's signature:

```python
class PolicyRuntime(RobotRuntime):
    def __init__(self, *, robot, model, execution, fps,
                 cameras=None, action_queue=None, callbacks=(), task=None):
        super().__init__(
            robot=robot,
            controller=PolicyController(model, execution, action_queue, task=task),
            fps=fps, cameras=cameras, callbacks=callbacks,
        )
```

Existing configs, the `physicalai run` CLI, and `from_config` keep working
unchanged because `PolicyRuntime` is still a class with the same constructor and
`run()`. Selecting an arbitrary controller uses the general schema below, which
does require a CLI change (see [Config and CLI](#config-and-cli)).

## Workflow Patterns

All workflows reuse one loop. The variation is the controller (and callbacks).

| Workflow          | Controller                    | Callbacks                      |
| ----------------- | ----------------------------- | ------------------------------ |
| policy rollout    | `PolicyController`            | optional telemetry / recording |
| teleop collection | `TeleopController`            | recording                      |
| recorded rollout  | `PolicyController`            | recording                      |
| HIL               | `HILController` (deferred)    | optional recording             |
| DAgger            | `DAggerController` (deferred) | metrics / recording            |
| scripted routine  | `ScriptedController`          | recording                      |

`TeleopController` is the first non-policy controller and the one that proves the
abstraction. The robot interface already models leader arms as read-only for
teleoperation. The controller reads its **leader** and never touches
`tick.observation()` — so with no recording attached, a teleop tick performs
zero follower/camera reads and is just leader-read → follower-write:

```python
class TeleopController:
    def __init__(self, leader, to_action): ...
    def update(self, tick):
        return self._to_action(self._leader.read())   # never touches tick's reads
```

For teleop data collection, the recording callback pulls `tick.observation()`
(the one place the follower state + camera frames are read) and pairs it with the
action — so the observation is captured only because recording asked for it.

## Config and CLI

The existing schema (flat policy runtime) keeps working via `PolicyRuntime`:

```yaml
runtime:
  robot:
    { class_path: physicalai.robot.SO101, init_args: { port: /dev/ttyACM0 } }
  model:
    {
      class_path: physicalai.inference.InferenceModel,
      init_args: { export_dir: ./exports/act },
    }
  execution: { class_path: physicalai.runtime.SyncExecution }
  fps: 30.0
```

A general schema selects any controller:

```yaml
runtime:
  class_path: physicalai.runtime.RobotRuntime
  init_args:
    fps: 30.0
    robot:
      { class_path: physicalai.robot.SO101, init_args: { port: /dev/ttyACM0 } }
    controller:
      class_path: physicalai.runtime.PolicyController
      init_args:
        model:
          {
            class_path: physicalai.inference.InferenceModel,
            init_args: { export_dir: ./exports/act },
          }
        execution: { class_path: physicalai.runtime.SyncExecution }
```

`physicalai run --config ...` should dispatch both. The flat schema works today
because `cli/run.py` binds `runtime:` to `PolicyRuntime` via
`add_class_arguments`. The general schema (top-level `runtime.class_path`)
**requires a CLI change**: switch to `add_subclass_arguments(RobotRuntime,
"runtime")` (or equivalent) so `runtime.class_path` can select `RobotRuntime` or
`PolicyRuntime`. This is the one config/CLI change in the plan; the flat
`PolicyRuntime` path is unaffected.

## Errors and Shutdown

Mostly the current behavior; the `controller.update()` row is a **new** contract
that today's loop does not implement.

| Condition                                | Behavior                                                                                                                                               | Status                                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| `controller.update()` raises             | **Phase 1: fail-stop (unchanged)** — log, emit `on_lifecycle` error event, stop the run. Hold-and-continue is opt-in per controller, added in Phase 2. | today only `KeyboardInterrupt` / `WorkerDiedError` are caught; other exceptions stop the run |
| `robot.send_action()` fails past retries | count error; stop after N consecutive                                                                                                                  | current (`_resilient_send`)                                                                  |
| `robot.get_observation()` fails          | retry, then stale fallback, then stop                                                                                                                  | current (`_resilient_observe`, now behind `tick.robot_state()`)                              |

There is no `on_error` callback in the codebase; errors surface as `on_lifecycle`
events (`obs_error`, `send_error`, `connection_lost`, `warmup_failed`).
**Phase 1 preserves today's fail-stop semantics for `update()` errors** — a
controller exception stops the run. Swallowing it and holding is a
safety-relevant inversion (a teleop leader-read fault would freeze the follower
while the operator believes it is live), so hold-and-continue is an opt-in
controller capability (an `on_error_hold` flag or explicit error policy)
introduced with `TeleopController` in Phase 2, not a runtime default.

Shutdown order: `controller.stop()` (drains its own queue, if any) → lifecycle
`shutdown` event → `disconnect()` (via the context manager). `return_to_home`
is **not** in scope — no robot in the codebase exposes a `go_to_home()`, so it is
deferred until there is one.

## Phasing

**Phase 1 — invert the loop.** The whole value; ship first.

1. Add the `Controller` protocol and the concrete `Tick` class (granular lazy
   `robot_state()` / `camera_frames()`; bus injection via optional `set_bus`).
2. Add `PolicyController`; move `_build_model_input` / `_build_model_input_from`,
   `maybe_request`/`pop`, and hold/fallback into it. Its `stop()` owns the queue
   drain; its `reset()` owns the queue reset.
3. Change `Execution.maybe_request(observation)` to `maybe_request(observe_fn)`
   (provider) across `Sync`/`Async`/`RTCExecution`, so the policy reads only on
   ticks it requests inference. `Sync`/`Async` already gate on `below_threshold`
   before using the observation, so they just invoke the provider inside that
   guard. `RTCExecution` currently publishes the observation every tick (its
   background thread owns the threshold check), so it must **add a main-thread
   `below_threshold` pre-check** before invoking the provider — otherwise it reads
   the device every tick and the async-idle savings do not apply to RTC.
4. Add `RobotRuntime` (the current loop minus policy specifics). Change
   `TickEvent` to carry the `Tick` instead of eager `robot_observation` /
   `camera_frames` — the one **breaking** change (`JsonlCallback`,
   `RerunCallback`, `AsyncCallback` read those fields today and must switch to
   pulling from the `Tick`).
5. Keep `PolicyRuntime` as a `RobotRuntime` **subclass** (not a function) so
   `add_class_arguments` / `add_method_arguments` in `cli/run.py` and
   `from_config` keep working. Its signature and the flat config schema are
   unchanged.
6. Apply the ownership splits decided in [RobotRuntime](#robotruntime): `RunStats`
   controller-optional (runtime owns `steps`/error stats, controller contributes
   `stats()`); start-of-run reset (runtime owns session/error, `controller.reset()`
   owns the queue); **one `Tick` per iteration** threaded through `update()` and
   `emit_tick`; **fresh `Tick` per warmup retry**.
7. Keep **fail-stop** on `update()` errors — no behavior change. Existing tests
   stay green apart from the `TickEvent` shape update.

**Phase 2 — prove it with a second source.** Add `TeleopController`
(leader→follower). Finalize the generic observation contract. Add the general
`controller:` config path, switching `cli/run.py` to
`add_subclass_arguments(RobotRuntime, "runtime")`. Implement recording:
**capture obs + action at a pre-send hook** (time-aligned), copy borrowed frame
buffers synchronously, and offload the slow write to the recorder's own
background thread — `on_tick` (post-send) stays telemetry-only. Because a
pre-send capture is an action-path hook, the recorder cannot be wrapped in
`AsyncCallback` (which forwards fire-and-forget events only); it owns its writer
thread and uses a fail-loud (not silent-drop) queue policy.

**Phase 3 — deferred until a concrete consumer exists (YAGNI).**
`SafetyLayer`, `HILController` / `DAggerController` implementations,
`swap_controller` / mid-loop command bus, typed `RobotAction`, and any
multi-rate / composite runtime. These land only when something needs them.

## Decision Summary

```text
robot loop ownership      RobotRuntime (today's PolicyRuntime loop)
action selection          Controller (new)
policy inference          PolicyController owns model + Execution + ActionQueue
sync/async/RTC boundary   Execution (SyncExecution / AsyncExecution / RTCExecution) — shipped
side effects & telemetry  callback event bus (on_tick / on_inference / on_lifecycle) — shipped
action-path hooks         before_send_action / on_action_sent / on_hold — shipped
policy-only entry point   PolicyRuntime, kept as a RobotRuntime subclass (no rename, still a class)
model-input formatting    PolicyController, not the loop
device reads              granular lazy pull via tick.robot_state() / camera_frames() — once/tick, only if asked
tick object               concrete class (single producer), like TickEvent; carried inside TickEvent
teleop action source      leader arm, owned by the controller (not the runtime observation)
bus injection             existing set_bus(bus, session_id) (no new RuntimeContext type)
warmup                    runtime reads first tick with retry, calls controller.warmup
deferred                  SafetyLayer, HIL/DAgger, swap_controller, typed actions, composite
```
