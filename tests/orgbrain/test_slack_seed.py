from orgbrain.slack.seed import parse_thread, pick_threads


def test_parse_thread_handles_continuations_and_names():
    content = "sasha: p99 up 3x\nsince the driver rollout\nkevin: noisy neighbor?\nci-bot: build 412 failed"
    assert parse_thread(content) == [("Sasha", "p99 up 3x\nsince the driver rollout"), ("Kevin", "noisy neighbor?"),
                                     ("ci-bot", "build 412 failed")]


def test_parse_thread_corpus_speaker_shapes():
    content = ("deploy-bot: HOLD - preflight found drift\n\n"
               "maya (eng-release): who added payment.timeout_ms?\n"
               "Alex Chen: PR #4899\n"
               "Priya S.: ack\n"
               "Maria.T: probes spiking\n"
               "Linh Tran (CSE): customer impact?\n"
               "requests.exceptions.SSLError: tlsv1 alert\n"
               "[server] selected_kernel: fp8")
    assert parse_thread(content) == [
        ("deploy-bot", "HOLD - preflight found drift"),
        ("Maya (eng-release)", "who added payment.timeout_ms?"),
        ("Alex Chen", "PR #4899"),
        ("Priya S.", "ack"),
        ("Maria.T", "probes spiking"),
        ("Linh Tran (CSE)", "customer impact?\nrequests.exceptions.SSLError: tlsv1 alert\n[server] selected_kernel: fp8")]


def test_parse_thread_with_known_speakers_keeps_labels_and_code_as_text():
    content = ("sam: curl output below\n"
               "Response: 400 bad request\n"
               "```\nAuthorization: Bearer x\nkevin: not a speaker inside code\n```\n"
               "kevin: retrying\n"
               "Note: see runbook\n"
               "quota-bot: limit raised\n"
               "Note: twice means a speaker")
    assert parse_thread(content, known={"sam", "kevin"}) == [
        ("Sam", "curl output below\nResponse: 400 bad request\n```\nAuthorization: Bearer x\n"
                "kevin: not a speaker inside code\n```"),
        ("Kevin", "retrying"),
        ("Note", "see runbook"),
        ("quota-bot", "limit raised"),
        ("Note", "twice means a speaker")]


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
        ("s3", "slack", "incidents", "solo: one message only"),
        ("s4", "slack", "social", "kevin: hi\nana: yo")])
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


def test_unseed_deletes_only_seeded_posts(monkeypatch):
    import asyncio

    import orgbrain.slack.seed as seed_mod

    class Client:
        def __init__(self):
            self.deleted = []

        async def auth_test(self):
            return {"bot_id": "B1"}

        async def conversations_list(self, **kw):
            return {"channels": [{"name": "incidents", "id": "C0"}, {"name": "social", "id": "C9"}]}

        async def conversations_history(self, channel, **kw):
            assert channel == "C0"
            return {"messages": [
                {"ts": "1.0", "bot_id": "B1", "username": "Sasha", "reply_count": 1},
                {"ts": "2.0", "user": "U1", "text": "@orgbrain q", "reply_count": 1},
                {"ts": "3.0", "bot_id": "B1", "username": "ci-bot"},
                {"ts": "4.0", "bot_id": "B2", "username": "Other app"}], "response_metadata": {}}

        async def conversations_replies(self, channel, ts, **kw):
            return {"messages": {
                "1.0": [{"ts": "1.0", "bot_id": "B1", "username": "Sasha"}, {"ts": "1.1", "bot_id": "B1", "username": "Kevin"}],
                "2.0": [{"ts": "2.0", "user": "U1"}, {"ts": "2.1", "bot_id": "B1", "text": "answer"}]}[ts],
                "response_metadata": {}}

        async def chat_delete(self, channel, ts):
            self.deleted.append((channel, ts))
            return {}

    async def no_sleep(_):
        return None

    monkeypatch.setattr(seed_mod.asyncio, "sleep", no_sleep)
    client = Client()
    assert asyncio.run(seed_mod.unseed(client, dry_run=True)) == {"incidents": 3}
    assert client.deleted == []
    assert asyncio.run(seed_mod.unseed(client, dry_run=False)) == {"incidents": 3}
    assert client.deleted == [("C0", "1.1"), ("C0", "1.0"), ("C0", "3.0")]
