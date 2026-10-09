"""Local checks for prune, parsing, the gate hash compare, and state loads."""

import json
import os
import tempfile
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


def _with_fetch(fetch):
    original = board._fetch_state_file
    board._fetch_state_file = fetch
    try:
        return board._download_state()
    finally:
        board._fetch_state_file = original


def _raise(exc):
    def fetch():
        raise exc
    return fetch


def test_absent_dataset_starts_empty():
    class EntryNotFoundError(Exception):
        pass

    state = _with_fetch(_raise(EntryNotFoundError("forum.json")))
    assert state["threads"] == []
    assert state["next_id"] == 1


def test_download_error_is_not_an_empty_board():
    class Timeout(Exception):
        pass

    failed = False
    try:
        _with_fetch(_raise(Timeout("hub down")))
    except Timeout:
        failed = True
    assert failed, "a download failure was treated as an empty board"


def _expect_download_failure(payload, error):
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    handle.write(payload)
    path = handle.name
    handle.close()
    failed = False
    try:
        _with_fetch(lambda: path)
    except error:
        failed = True
    finally:
        os.unlink(path)
    assert failed, "bad board json was treated as an empty board"


def test_thread_list_dataset_loads():
    fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = json.dumps([{"id": 4, "category": "tech", "last_bump": fresh, "posts": [{"id": 4}]}])
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    handle.write(payload)
    path = handle.name
    handle.close()
    try:
        state = _with_fetch(lambda: path)
    finally:
        os.unlink(path)
    assert len(state["threads"]) == 1
    assert state["threads"][0]["id"] == 4
    assert state["next_id"] == 5


def test_corrupt_dataset_is_not_an_empty_board():
    _expect_download_failure("{", json.JSONDecodeError)


def test_scalar_dataset_is_not_an_empty_board():
    _expect_download_failure("null", ValueError)


if __name__ == "__main__":
    test_prune_drops_old_threads()
    test_prune_caps_a_board()
    test_parse_generation()
    test_gate_rejects_blank()
    test_absent_dataset_starts_empty()
    test_download_error_is_not_an_empty_board()
    test_thread_list_dataset_loads()
    test_corrupt_dataset_is_not_an_empty_board()
    test_scalar_dataset_is_not_an_empty_board()
    print("board checks passed")
