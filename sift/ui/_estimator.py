"""Time-based progress driver used by ``ScrapeProgress`` / ``PipelineProgress``.

Why this exists: Sift's scrapers and pipeline stages don't expose mid-flight
progress callbacks. If we relied only on ``advance()`` we'd get a bar that
freezes for tens of seconds and then jumps. Instead we estimate how long a
unit of work *typically* takes (see :mod:`sift.ui.timings`) and animate the
bar on a curve that:

  - fills linearly from 0 → 0.90 over the expected duration
  - then asymptotically creeps from 0.90 → 1.0 if the task overruns

When the real task completes, we either snap forward to 1.0 immediately, or
(if the bar hasn't reached 0.95 yet) wait briefly so the bar can catch up
before snapping. The brief "catch-up" delay is deliberate: users find a bar
that completes naturally less jarring than one that disappears at 30%.

The driver runs in a background thread per active slot. Rich's
``Progress.update`` is internally thread-safe, so we only need our own
``Event`` to stop the tick loop. We never touch Rich's render loop directly.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

from rich.progress import Progress, TaskID

# Curve constants. These are the only knobs you need to tune the feel of the
# bar. See the module docstring for the shape they produce.
LINEAR_CAP = 0.90       # how high the linear segment climbs
CATCHUP_THRESHOLD = 0.95  # if curve < this when work returns, briefly wait
MAX_CATCHUP_SECONDS = 2.0  # …but never wait longer than this
TICK_INTERVAL = 0.1     # seconds between bar updates


def _curve(elapsed: float, expected: float) -> float:
    """Return a value in [0, 1) for how filled the bar should be.

    Linear up to LINEAR_CAP, then asymptotic (1 - (1-cap)·e^(-Δt/expected)).
    Never reaches 1.0 — only the explicit snap on exit does that.
    """
    if expected <= 0:
        return LINEAR_CAP
    if elapsed <= expected:
        return LINEAR_CAP * (elapsed / expected)
    overshoot = elapsed - expected
    return 1.0 - (1.0 - LINEAR_CAP) * math.exp(-overshoot / expected)


class EstimatedTask:
    """Drive a Rich ``Progress`` task between two ``completed`` values.

    Treat the bar as having a "slot" from ``start_completed`` up to
    ``start_completed + 1.0``. While inside the ``with`` block, the slot is
    animated on the curve above; on exit, ``completed`` snaps to
    ``start_completed + 1.0`` (possibly after a short catch-up delay).
    """

    def __init__(
        self,
        progress: Progress,
        task_id: TaskID,
        expected_seconds: float,
        start_completed: float,
    ):
        self._progress = progress
        self._task_id = task_id
        self._expected = max(0.1, float(expected_seconds))
        self._start = float(start_completed)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started_at = 0.0
        self.elapsed: float = 0.0  # populated on exit, used by caller for EMA
        # Whether the wrapped work returned normally. Callers gate EMA
        # recording on this so a 0.5s exception-path doesn't poison the
        # learned duration for a slot whose real cost is 60s.
        self.succeeded: bool = False

    def __enter__(self) -> "EstimatedTask":
        self._started_at = time.monotonic()
        self._progress.update(self._task_id, completed=self._start)
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()
        return self

    def _tick(self) -> None:
        while not self._stop.wait(TICK_INTERVAL):
            elapsed = time.monotonic() - self._started_at
            p = _curve(elapsed, self._expected)
            try:
                self._progress.update(self._task_id, completed=self._start + p)
            except Exception:
                # Rich is occasionally torn down before the thread sees the stop
                # event (e.g., interpreter shutdown). Swallow rather than spam.
                return

    def __exit__(self, exc_type, exc, tb) -> None:
        self.elapsed = time.monotonic() - self._started_at
        self.succeeded = exc_type is None
        # Stop the ticker first so it can't race the snap.
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=TICK_INTERVAL * 3)

        # Catch-up: if the bar hasn't reached CATCHUP_THRESHOLD yet, briefly
        # let it climb so the user sees the slot actually finish rather than
        # jumping from 40% to 100% in one frame.
        current = _curve(self.elapsed, self._expected)
        if exc_type is None and current < CATCHUP_THRESHOLD:
            # How much extra elapsed-time do we need on the curve to reach the
            # threshold? Solve _curve(t, expected) = threshold:
            #   if threshold ≤ LINEAR_CAP: t = (threshold/LINEAR_CAP) * expected
            #   else (asymptotic):         t = expected + expected * ln((1-LINEAR_CAP)/(1-threshold))
            if CATCHUP_THRESHOLD <= LINEAR_CAP:
                t_target = (CATCHUP_THRESHOLD / LINEAR_CAP) * self._expected
            else:
                t_target = self._expected + self._expected * math.log(
                    (1.0 - LINEAR_CAP) / (1.0 - CATCHUP_THRESHOLD)
                )
            wait = min(MAX_CATCHUP_SECONDS, max(0.0, t_target - self.elapsed))
            # Animate during the catch-up so the user sees motion, not a freeze.
            catchup_start = time.monotonic()
            while wait > 0:
                slept = min(TICK_INTERVAL, wait)
                time.sleep(slept)
                wait -= slept
                fake_elapsed = self.elapsed + (time.monotonic() - catchup_start)
                p = _curve(fake_elapsed, self._expected)
                try:
                    self._progress.update(self._task_id, completed=self._start + p)
                except Exception:
                    break

        # Snap to the end of the slot. The caller's ``advance()`` will move
        # the slot index forward; here we just guarantee the bar shows the
        # slot as visually complete.
        try:
            self._progress.update(self._task_id, completed=self._start + 1.0)
        except Exception:
            pass
