import pytest

from orgbrain.waiting import wait_for


def test_retries_until_the_check_passes():
    calls, slept = [], []

    def check():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("refused")
        return "ok"

    assert wait_for(check, "models", sleep=slept.append, clock=lambda: 0.0) == "ok"
    assert len(calls) == 3 and slept == [2.0, 2.0]


def test_gives_up_after_the_timeout():
    t = iter([0.0, 1.0, 400.0])

    def check():
        raise ConnectionError("refused")

    with pytest.raises(RuntimeError, match="models not reachable after 300s: refused"):
        wait_for(check, "models", sleep=lambda s: None, clock=lambda: next(t))
