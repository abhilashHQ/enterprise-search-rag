from pathlib import Path

import pytest

from orgbrain import cli


def _probes(down: str | None = None):
    async def up(name):
        return f"{name} fine"

    async def broken():
        raise ConnectionError("connection refused")

    names = ["qdrant", "postgres", "redis", "models", "search", "api"]
    return {n: (broken if n == down else (lambda n=n: up(n))) for n in names}


def test_status_all_up(monkeypatch, capsys):
    monkeypatch.setattr(cli, "probes", lambda settings: _probes())
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert out.count("up") == 6
    assert "qdrant fine" in out


def test_status_one_down_names_it(monkeypatch, capsys):
    monkeypatch.setattr(cli, "probes", lambda settings: _probes(down="redis"))
    assert cli.main(["status"]) == 1
    line = next(l for l in capsys.readouterr().out.splitlines() if "redis" in l)
    assert "down" in line and "connection refused" in line


def test_demo_arguments():
    a = cli.parser().parse_args(["demo", "--repo", "me/idx", "--revision", "v1", "--dir", "x", "--force",
                                 "--keep-download"])
    assert (a.cmd, a.repo, a.revision, a.dir, a.force, a.keep_download) == ("demo", "me/idx", "v1", Path("x"), True, True)
    d = cli.parser().parse_args(["demo"])
    assert d.repo == cli.DEFAULT_REPO and d.revision is None and not d.force and not d.keep_download


def test_connect_folder_delegates(monkeypatch):
    calls = []

    async def fake_run(database_url, root, name, watch):
        calls.append((root, name, watch))

    monkeypatch.setattr(cli, "folder_run", fake_run)
    assert cli.main(["connect", "folder", "notes", "--name", "notes", "--watch", "5"]) == 0
    assert calls == [(Path("notes"), "notes", 5.0)]


def test_connect_requires_name():
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["connect", "folder", "notes"])
