from orgbrain.slack.render import Decision, conversation_id, footnotes, parse_decision, step_line, to_mrkdwn

CITES = [{"ref": "a1b2c3", "doc_id": "d1", "source": "confluence", "title": "perf-canary runbook"},
         {"ref": "d4e5f6", "doc_id": "d2", "source": "slack", "title": "eng-releases"}]


def test_conversation_id_is_stable_and_32_hex():
    a = conversation_id("C1", "1700000000.0001")
    assert a == conversation_id("C1", "1700000000.0001") != conversation_id("C1", "1700000000.0002") and len(a) == 32


def test_refs_become_numbered_footnotes_in_order_of_first_use():
    out = footnotes("Pin the tag [d4e5f6]. Then roll back [a1b2c3][d4e5f6]. Unknown [zzzzzz].", CITES)
    assert out == ("Pin the tag [1]. Then roll back [2][1]. Unknown.\n\n"
                   "[1] eng-releases (slack)\n[2] perf-canary runbook (confluence)")
    assert footnotes("No sources here.", []) == "No sources here."


def test_grouped_refs_each_get_a_number():
    assert footnotes("Roll back [a1b2c3, d4e5f6; zzzzzz].", CITES) == (
        "Roll back [1][2].\n\n[1] perf-canary runbook (confluence)\n[2] eng-releases (slack)")


def test_to_mrkdwn():
    md = "# Rollback\n**Pin** the tag, see [runbook](https://x.io/r) & keep p99 < 50ms.\n## Steps\n__one__"
    assert to_mrkdwn(md) == ("*Rollback*\n*Pin* the tag, see <https://x.io/r|runbook> &amp; keep p99 &lt; 50ms.\n"
                             "*Steps*\n*one*")
    assert to_mrkdwn("Jan 12 [1].\n\n[1] Freeze (confluence)") == "Jan 12 [1].\n\n[1] Freeze (confluence)"


def test_step_lines():
    assert step_line({"kind": "tool_call", "tool": "search", "arguments": {"query": "deploy freeze"}}) == "Searching: deploy freeze"
    assert step_line({"kind": "tool_call", "tool": "read_doc", "arguments": {"doc_id": "d1"}}) == "Reading a document"
    assert step_line({"kind": "tool_call", "tool": "find_people", "arguments": {"query": "renewals"}}) == "Looking up people: renewals"
    assert step_line({"kind": "tool_result", "tool": "search", "count": 10, "error": None}) is None


def test_parse_decision():
    assert parse_decision("SILENT") == Decision("silent")
    assert parse_decision("REACT :eyes:\n") == Decision("react", emoji="eyes")
    assert parse_decision("REPLY\nThe freeze starts Jan 12 [a1b2c3].") == Decision("reply", "The freeze starts Jan 12 [a1b2c3].")
    assert parse_decision("The freeze starts Jan 12.") == Decision("reply", "The freeze starts Jan 12.")


def test_parse_decision_reply_on_the_same_line():
    assert parse_decision("REPLY The freeze starts Jan 12.\nMore [1].") == Decision("reply", "The freeze starts Jan 12.\nMore [1].")
    assert parse_decision("REPLY: The freeze starts Jan 12.") == Decision("reply", "The freeze starts Jan 12.")
    assert parse_decision("Replying soon.") == Decision("reply", "Replying soon.")
