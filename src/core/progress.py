# src/core/progress.py
import json
from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar

_current_progress = ContextVar("generation_progress", default=None)


@contextmanager
def progress_context(progress):
    token = _current_progress.set(progress)
    try:
        yield
    finally:
        _current_progress.reset(token)


def report_activity(label, **details):
    progress = _current_progress.get()
    if progress is not None:
        progress.activity(label, **details)


@dataclass
class ProgressMeta:
    job_id: str
    queue: "Queue"

    def start(self, total: int):
        self._emit({"phase": "start", "total": total, "current": 0})

    def step(self, label: str, group: str, year: int, current: int, total: int):
        self._emit(
            {
                "phase": "tick",
                "label": label,
                "group": group,
                "year": year,
                "current": current,
                "total": total,
            }
        )

    def done(self):
        self._emit({"phase": "done"})
        self.queue.put("__CLOSE__")

    def activity(self, label, **details):
        self._emit({"phase": "activity", "label": label, **details})

    def _emit(self, payload: dict):
        self.queue.put(json.dumps(payload, ensure_ascii=False))
