"""Local checks for prune, parsing, and the gate hash compare."""

from datetime import datetime, timedelta, timezone

import board


def test_prune_drops_old_threads():
    old = (datetime.now(timezone.utc) - timedelta(hours=49)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    threads = [{"id": 1, "category": "tech", "last_bump": old, "posts": [{"id": 1, "seat": "Operator", "note": "stay"}]}]
    kept, removed = board.prune(threads)
    assert removed == 1
    assert kept == []


def test_prune_caps_a_board():
    fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    threads = [{"id": index, "category": "cooking", "last_bump": fresh, "posts": [{"id": index}]} for index in range(16)]
    kept, removed = board.prune(threads)
    assert removed == 1
    assert len(kept) == 15


def test_parse_generation():
    parsed = board.parse_generation("Kernel bump\n\n> gcc 15 landed\n> the note names gcc")
    assert parsed is not None
    subject, note = parsed
    assert subject == "Kernel bump"
    assert note.startswith(">")


def test_gate_rejects_blank():
    assert board.authorized("") is False
    assert board.authorized(None) is False


if __name__ == "__main__":
    test_prune_drops_old_threads()
    test_prune_caps_a_board()
    test_parse_generation()
    test_gate_rejects_blank()
    print("board checks passed")
