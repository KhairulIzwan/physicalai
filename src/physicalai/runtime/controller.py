# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Controller abstraction and policy-backed controller implementation."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np

from physicalai.inference.constants import IMAGES, STATE, TASK
from physicalai.runtime._action_queue import ChunkedActionQueue  # noqa: PLC2701
from physicalai.runtime.smoothers import LerpSmoother

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

    from physicalai.capture.frame import Frame
    from physicalai.inference.model import InferenceModel
    from physicalai.robot.interface import Robot, RobotObservation
    from physicalai.runtime._callback_bus import _CallbackBus
    from physicalai.runtime.execution import Execution
    from physicalai.runtime.runtime import ActionQueue
    from physicalai.runtime.tick import Tick

_DEFAULT_LERP_FRAMES = 5


@runtime_checkable
class Controller(Protocol):
    """Protocol for action-selection components consumed by RobotRuntime.

    Only the members every controller must implement. Bus injection, stats
    reporting, queue draining, and hold-status introspection are optional
    capabilities the runtime detects via :class:`SupportsBus`,
    :class:`SupportsStats`, :class:`SupportsDrain`, and
    :class:`SupportsHoldInfo` rather than requiring every controller (e.g.
    :class:`TeleopController`) to implement them.
    """

    def start(self) -> None:
        """Initialize resources before loop start."""
        ...

    def warmup(self, tick: Tick) -> None:
        """Optional pre-loop warmup using a fresh tick."""
        ...

    def update(self, tick: Tick) -> np.ndarray | None:
        """Return action for this tick, or None to request hold."""
        ...

    def stop(self) -> None:
        """Stop background activity/resources."""
        ...

    def reset(self) -> None:
        """Reset session-scoped state before a run."""
        ...


@runtime_checkable
class SupportsBus(Protocol):
    """Optional capability: controller wants the runtime's callback bus/session."""

    def set_bus(self, bus: _CallbackBus, session_id: str) -> None:
        """Inject callback bus/session (e.g. forwarded to an Execution)."""
        ...


@runtime_checkable
class SupportsStats(Protocol):
    """Optional capability: controller contributes stats merged into RunStats."""

    def stats(self) -> Mapping[str, int]:
        """Return controller-owned counters (e.g. total_pops, total_holds)."""
        ...


@runtime_checkable
class SupportsDrain(Protocol):
    """Optional capability: controller owns a queue drained on shutdown."""

    @property
    def remaining(self) -> int:
        """Number of unconsumed queued actions."""
        ...

    def drain(self, limit: int) -> Iterable[np.ndarray]:
        """Yield up to ``limit`` remaining queued actions for shutdown flush."""
        ...


@runtime_checkable
class SupportsHoldInfo(Protocol):
    """Optional capability: controller reports hold/fallback status for logging."""

    @property
    def last_was_hold(self) -> bool:
        """Whether the latest update() returned a held action fallback."""
        ...

    @property
    def holds(self) -> int:
        """Consecutive hold count."""
        ...


class PolicyController:
    """Controller adapting model+execution+action-queue policy pipeline."""

    def __init__(
        self,
        model: InferenceModel,
        execution: Execution,
        action_queue: ActionQueue | None = None,
        *,
        task: str | None = None,
    ) -> None:
        """Initialize a policy-backed controller."""
        self._model = model
        self._execution = execution
        self._action_queue = action_queue or ChunkedActionQueue(
            smoother=LerpSmoother(duration_frames=_DEFAULT_LERP_FRAMES)
        )
        self._task = task
        self._last: np.ndarray | None = None
        self._last_was_hold = False

    @property
    def remaining(self) -> int:
        """Remaining queued actions."""
        return self._action_queue.remaining

    @property
    def action_queue(self) -> ActionQueue:
        """Underlying action queue.

        Returns:
            Action queue used by this controller.
        """
        return self._action_queue

    @property
    def holds(self) -> int:
        """Consecutive hold count from queue pop() behavior."""
        return self._action_queue.consecutive_holds

    @property
    def last_was_hold(self) -> bool:
        """Whether the latest update() returned a held action fallback."""
        return self._last_was_hold

    def set_bus(self, bus: _CallbackBus, session_id: str) -> None:
        """Forward bus/session injection to execution."""
        self._execution.set_bus(bus, session_id)

    def start(self) -> None:
        """Start execution strategy."""
        self._execution.start(self._model, self._action_queue)

    def warmup(self, tick: Tick) -> None:
        """Seed queue/discover chunk size using warmup sample."""
        self._execution.warmup(self._to_model_input(*tick.observation()))

    def update(self, tick: Tick) -> np.ndarray | None:
        """Maybe request inference and return next action (or fallback hold).

        Returns:
            Action to send this tick, or fallback hold action/None when queue is empty.
        """
        self._execution.maybe_request(lambda: self._to_model_input(*tick.observation()))

        action = self._action_queue.pop()
        if action is None:
            self._last_was_hold = True
            return self._last

        self._last_was_hold = False
        self._last = action
        return action

    def stop(self) -> None:
        """Stop execution strategy."""
        self._execution.stop()

    def drain(self, limit: int) -> Iterator[np.ndarray]:
        """Yield up to ``limit`` remaining queued actions for shutdown flush.

        Called after :meth:`stop` (execution already quiesced), so no concurrent
        producer is pushing into the queue.

        Args:
            limit: Maximum number of actions to yield.

        Yields:
            Remaining action vectors in order, at most ``limit`` of them.
        """
        for _ in range(max(limit, 0)):
            action = self._action_queue.pop()
            if action is None:
                return
            yield action

    def reset(self) -> None:
        """Reset queue and local fallback state for new run."""
        self._action_queue.reset()
        self._last = None
        self._last_was_hold = False

    def stats(self) -> dict[str, int]:
        """Policy/queue stats for RunStats merge.

        Returns:
            Mapping with ``total_pops``, ``total_holds``, ``inference_count``.
        """
        return {
            "total_pops": self._action_queue.total_pops,
            "total_holds": self._action_queue.total_holds,
            "inference_count": getattr(self._execution, "inference_count", 0),
        }

    def _to_model_input(self, robot_obs: RobotObservation, camera_frames: dict[str, Frame]) -> dict[str, Any]:
        """Assemble model input dict from observation and camera frames.

        Returns:
            Dictionary ready for model inference.
        """
        model_input: dict[str, Any] = {STATE: np.array([robot_obs.state], dtype=np.float32)}
        image_inputs: dict[str, np.ndarray] = {}
        # Merge robot-embedded images and external cameras
        if robot_obs.images:
            for name, frame in robot_obs.images.items():
                image_inputs[name] = frame.data[np.newaxis]
        for name, frame in camera_frames.items():
            image_inputs[name] = frame.data[np.newaxis]

        if len(image_inputs) > 1:
            for name, data in image_inputs.items():
                model_input[f"{IMAGES}.{name}"] = data
        elif len(image_inputs) == 1:
            model_input[IMAGES] = next(iter(image_inputs.values()))

        if self._task is not None:
            model_input[TASK] = [self._task]
        return model_input

    def to_model_input(self, robot_obs: RobotObservation, camera_frames: dict[str, Frame]) -> dict[str, Any]:
        """Public compatibility wrapper for model-input conversion.

        Returns:
            Dictionary ready for model inference.
        """
        return self._to_model_input(robot_obs, camera_frames)


class TeleopController:
    """Controller that reads a leader arm and writes to the follower.

    The action source is the leader device, not the follower's observation or
    any inference model. ``tick`` is never consumed — a teleop tick with no
    recording attached performs zero follower/camera reads.

    Args:
        leader: The leader robot (same ``Robot`` protocol; must support
            ``get_observation()``).
        to_action: Optional callable mapping a ``RobotObservation`` from the
            leader to an action array for the follower. Defaults to
            ``obs.joint_positions`` (identity for same-morphology leader/follower).
    """

    def __init__(  # noqa: D107
        self,
        leader: Robot,
        *,
        to_action: Callable[[RobotObservation], np.ndarray] | None = None,
    ) -> None:
        self._leader = leader
        self._to_action = to_action or (lambda obs: obs.joint_positions)
        self._leader_owned = False

    def start(self) -> None:
        """Connect leader if not already connected."""
        if not self._leader.is_connected():
            self._leader.connect()
            self._leader_owned = True

    def set_bus(self, bus: _CallbackBus, session_id: str) -> None:
        """No-op — teleop does not emit inference events."""

    def warmup(self, tick: Tick) -> None:
        """No-op — no inference to seed."""

    def update(self, tick: Tick) -> np.ndarray | None:  # noqa: ARG002
        """Read the leader arm and return the action for the follower.

        Returns:
            Action array for the follower robot.
        """
        return self._to_action(self._leader.get_observation())

    def stop(self) -> None:
        """Disconnect leader if we connected it."""
        if self._leader_owned:
            with contextlib.suppress(Exception):
                self._leader.disconnect()

    def reset(self) -> None:
        """No-op — no session state to clear."""
