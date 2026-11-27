import sqlite3

from orgbrain.docs import DocReader


def make_docs(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS docs (doc_id TEXT PRIMARY KEY, source_type TEXT, title TEXT, content TEXT)")
    con.executemany("INSERT INTO docs VALUES (?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    return path


def reader(tmp_path):
    redwood = make_docs(tmp_path / "docstore.sqlite", [("d1", "confluence", "Runbook", "old text")])
    live = make_docs(tmp_path / "live.sqlite", [("d1", "confluence", "Runbook", "new text"),
                                                ("file:notes:a.md", "files", "a", "notes")])
    return DocReader(redwood, live)


def test_live_store_wins_and_missing_is_none(tmp_path):
    r = reader(tmp_path)
    assert r.get("d1") == {"doc_id": "d1", "source": "confluence", "title": "Runbook", "content": "new text"}
    assert r.get("file:notes:a.md")["source"] == "files"
    assert r.get("missing") is None


def test_has_and_counts_count_a_doc_in_both_stores_once(tmp_path):
    r = reader(tmp_path)
    assert r.has(["d1", "x"]) == {"d1"} and r.has([]) == set()
    assert r.counts() == {"confluence": 1, "files": 1}


def test_no_redwood_docstore(tmp_path):
    live = make_docs(tmp_path / "live.sqlite", [("m1", "memory", "Memory", "x")])
    r = DocReader(tmp_path / "missing.sqlite", live)
    assert r.get("m1")["source"] == "memory" and r.counts() == {"memory": 1}


def test_redwood_docstore_restored_after_start_is_picked_up(tmp_path):
    live = make_docs(tmp_path / "live.sqlite", [("m1", "memory", "Memory", "x")])
    r = DocReader(tmp_path / "docstore.sqlite", live)
    assert r.get("d1") is None and r.counts() == {"memory": 1}
    make_docs(tmp_path / "docstore.sqlite", [("d1", "confluence", "Runbook", "text")])
    assert r.get("d1")["title"] == "Runbook"
    assert r.counts() == {"confluence": 1, "memory": 1}
