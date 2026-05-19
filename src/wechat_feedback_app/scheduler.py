from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SchedulerState:
    enabled: bool = False
    interval_minutes: int = 60


def build_scheduler_state(interval_minutes: int) -> SchedulerState:
    return SchedulerState(enabled=False, interval_minutes=interval_minutes)
