import pytest

from orgbrain.uploads import save_uploads


def test_save_uploads_keeps_basenames_and_rejects_hidden_and_unknown(tmp_path):
    saved = save_uploads(tmp_path, [("a.md", b"a"), ("../../evil.md", b"e"), (".env", b"k"), ("x.exe", b"x"),
                                    (r"sub\b.TXT", b"b")])
    assert saved == ["a.md", "evil.md", "b.TXT"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md", "b.TXT", "evil.md"]
    assert (tmp_path / "evil.md").read_bytes() == b"e"


def test_save_uploads_raises_when_every_file_is_rejected(tmp_path):
    with pytest.raises(ValueError, match=".env, x.exe"):
        save_uploads(tmp_path, [(".env", b"k"), ("x.exe", b"x")])
