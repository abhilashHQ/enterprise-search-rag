import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
log = logging.getLogger("orgbrain.waiting")


def wait_for(check: Callable[[], T], what: str, timeout: float = 300.0, every: float = 2.0,
             sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> T:
    deadline = clock() + timeout
    while True:
        try:
            return check()
        except Exception as e:
            if clock() >= deadline:
                raise RuntimeError(f"{what} not reachable after {timeout:.0f}s: {e}") from e
            log.info("waiting for %s: %s", what, e)
            sleep(every)
