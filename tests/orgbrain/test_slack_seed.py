from orgbrain.slack.seed import parse_thread, pick_threads


def test_parse_thread_handles_continuations_and_names():
    content = "sasha: p99 up 3x\nsince the driver rollout\nkevin: noisy neighbor?\nci-bot: build 412 failed"
    assert parse_thread(content) == [("Sasha", "p99 up 3x\nsince the driver rollout"), ("Kevin", "noisy neighbor?"),
                                     ("ci-bot", "build 412 failed")]


def test_pick_threads_is_deterministic_and_respects_size():
    rows = [(f"d{i}", "incidents", "\n".join(f"a{j}: m" for j in range(n))) for i, n in enumerate([1, 3, 5, 20, 4, 2])]
    picked = pick_threads(rows, per_channel=2)
    assert picked == pick_threads(rows, per_channel=2) and len(picked["incidents"]) == 2
    assert not {"d0", "d3"} & set(picked["incidents"])


def test_seed_posts_threads_under_speaker_names_and_resumes(tmp_path, monkeypatch):
    import asyncio
    import sqlite3

    import orgbrain.slack.seed as seed_mod

    db = tmp_path / "docstore.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE docs (doc_id TEXT PRIMARY KEY, source_type TEXT, title TEXT, content TEXT)")
    con.executemany("INSERT INTO docs VALUES (?, ?, ?, ?)", [
        ("s1", "slack", "incidents", "sasha: p99 < 50ms & rising\nkevin: rolling back"),
        ("s2", "slack", "product", "ana: roadmap\nbo: ok"),
        ("s3", "slack", "incidents", "solo: one message only")])
    con.commit()
    con.close()

    class Client:
        def __init__(self):
            self.posts, self.created = [], []

        async def conversations_list(self, **kw):
            return {"channels": [{"name": "incidents", "id": "C0"}]}

        async def conversations_create(self, name):
            self.created.append(name)
            return {"channel": {"id": f"C-{name}"}}

        async def conversations_join(self, channel):
            return {}

        async def chat_postMessage(self, **kw):
            self.posts.append(kw)
            return {"ts": f"{len(self.posts)}.0"}

    async def no_sleep(_):
        return None

    monkeypatch.setattr(seed_mod.asyncio, "sleep", no_sleep)
    state, client = tmp_path / "state.json", Client()
    dry = asyncio.run(seed_mod.seed(None, db, state, 5, dry_run=True))
    assert dry["channels"]["incidents"] == 1 and dry["messages"] == 2
    assert asyncio.run(seed_mod.seed(client, db, state, 5, dry_run=False)) == {"posted_threads": 1}
    assert [(p["channel"], p["username"], p["text"], p["thread_ts"]) for p in client.posts] == [
        ("C0", "Sasha", "p99 &lt; 50ms &amp; rising", None), ("C0", "Kevin", "rolling back", "1.0")]
    assert "incidents" not in client.created and len(client.created) == 5
    assert asyncio.run(seed_mod.seed(None, db, state, 5, dry_run=True))["messages"] == 0
