# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-loop tick handle with granular lazy observation pulls."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from physicalai.capture.frame import Frame
    from physicalai.robot.interface import RobotObservation


class Tick:
    """Concrete per-iteration tick object.

    ``Tick`` is created by :class:`~physicalai.runtime.runtime.RobotRuntime` and
    passed through the controller update path and the tick event path.

    Device reads are granular and memoized independently:
    - :meth:`robot_state` reads robot state at most once.
    - :meth:`camera_frames` reads camera frames at most once.

    Read metadata (``robot_state_read`` / ``robot_state_stale``) records whether
    a robot read happened this tick and whether it fell back to a stale
    observation, so telemetry can report per-tick staleness without depending on
    cross-tick error counters.
    """

    def __init__(
        self,
        *,
        frame_index: int,
        timestamp: float,
        read_robot_state: Callable[[], tuple[RobotObservation, bool]],
        read_camera_frames: Callable[[], dict[str, Frame]],
    ) -> None:
        """Initialize tick handle with memoized read callables.

        Args:
            frame_index: Loop tick identity (bookkeeping, no IO).
            timestamp: Loop tick scheduling time (no IO).
            read_robot_state: Callable returning ``(observation, was_stale)`` where
                ``was_stale`` is True when a stale fallback observation was used.
            read_camera_frames: Callable returning camera frames keyed by name.
        """
        self.frame_index = frame_index
        self.timestamp = timestamp
        self._read_robot_state = read_robot_state
        self._read_camera_frames = read_camera_frames
        self._robot_state_cache: RobotObservation | None = None
        self._camera_frames_cache: dict[str, Frame] | None = None
        self.robot_state_read: bool = False
        self.robot_state_stale: bool = False

    def robot_state(self) -> RobotObservation:
        """Read robot state lazily and memoize for this tick.

        Returns:
            Robot observation captured for this tick.
        """
        if self._robot_state_cache is None:
            observation, was_stale = self._read_robot_state()
            self._robot_state_cache = observation
            self.robot_state_read = True
            self.robot_state_stale = was_stale
        return self._robot_state_cache

    def camera_frames(self) -> Mapping[str, Frame]:
        """Read camera frames lazily and memoize for this tick.

        Returns:
            Mapping of camera name to frame for this tick.
        """
        if self._camera_frames_cache is None:
            self._camera_frames_cache = self._read_camera_frames()
        return self._camera_frames_cache

    def camera_frames_cached(self) -> bool:
        """Whether camera frames were already read/memoized this tick.

        Returns:
            True if :meth:`camera_frames` has already materialized frames, so a
            consumer can reuse them without forcing a new device read.
        """
        return self._camera_frames_cache is not None

    def observation(self) -> tuple[RobotObservation, dict[str, Frame]]:
        """Return convenience (robot_state, camera_frames) tuple."""
        return self.robot_state(), dict(self.camera_frames())

    def _set_camera_frames(self, frames: dict[str, Frame]) -> None:
        """Override cached camera frames.

        Internal helper used by AsyncCallback to replace borrowed shared-memory
        frame buffers with owned copies before enqueuing the event.
        """
        self._camera_frames_cache = frames
