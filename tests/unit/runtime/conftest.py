# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from physicalai.runtime.tick import Tick


@dataclass
class FakeRobotObservation:
    """Test double satisfying the RobotObservation protocol."""

    joint_positions: np.ndarray
    timestamp: float = 0.0
    sensor_data: dict[str, np.ndarray] | None = None
    images: dict | None = None

    @property
    def state(self) -> np.ndarray:
        return self.joint_positions


def make_fake_tick(
    robot_observation: FakeRobotObservation,
    camera_frames: dict | None = None,
    *,
    frame_index: int = 0,
    timestamp: float = 0.0,
    stale: bool = False,
) -> Tick:
    """Create a Tick test double with deterministic observation values."""
    frames = camera_frames or {}
    return Tick(
        frame_index=frame_index,
        timestamp=timestamp,
        read_robot_state=lambda: (robot_observation, stale),
        read_camera_frames=lambda: frames,
    )
