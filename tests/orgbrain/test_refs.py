import hashlib

from orgbrain.refs import cited_refs, ref
from orgbrain.sources import SOURCE_HELP, Source


def test_ref_is_first_six_hex_of_sha1():
    assert ref("dsid_abc") == hashlib.sha1(b"dsid_abc").hexdigest()[:6]
    assert len(ref("x")) == 6


def test_cited_refs_handles_adjacent_and_comma_lists_in_order():
    text = "Pin the tag [a1b2c3]. Then run revert [d4e5f6][a1b2c3]. Also [0f0f0f, 1a1a1a]."
    assert cited_refs(text) == ["a1b2c3", "d4e5f6", "0f0f0f", "1a1a1a"]


def test_cited_refs_ignores_numbers_and_wrong_lengths():
    assert cited_refs("see [2] and [abcdefa] and [ABCDEF]") == []


def test_every_source_has_help_text():
    assert set(SOURCE_HELP) == set(Source)
    assert Source("google_drive") is Source.GOOGLE_DRIVE
