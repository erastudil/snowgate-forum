"""Deterministic checks for prune, parsing, password variations, state loads, and live web search."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
import board
import agents


def test_prune_drops_old_threads():
    moment = datetime.now(timezone.utc).replace(microsecond=0)
    old = (moment - timedelta(hours=49)).isoformat().replace("+00:00", "Z")
    fresh = moment.isoformat().replace("+00:00", "Z")
    threads = [
        {"id": 1, "category": "tech", "last_bump": old, "posts": [{"id": 1, "seat": "Operator", "note": "stay"}]},
        {"id": 2, "category": "tech", "last_bump": fresh, "posts": [{"id": 2, "seat": "Operator", "note": "live"}]},
    ]
    kept, removed = board.prune(threads)
    assert removed == 1
    assert [thread["id"] for thread in kept] == [2]


def test_prune_keeps_the_last_thread_on_a_quiet_board():
    moment = datetime.now(timezone.utc).replace(microsecond=0)
    older = (moment - timedelta(hours=80)).isoformat().replace("+00:00", "Z")
    old = (moment - timedelta(hours=49)).isoformat().replace("+00:00", "Z")
    threads = [
        {"id": 1, "category": "cooking", "last_bump": older, "posts": [{"id": 1}]},
        {"id": 2, "category": "cooking", "last_bump": old, "posts": [{"id": 2}]},
        {"id": 3, "category": "music", "last_bump": older, "posts": [{"id": 3}]},
    ]
    kept, removed = board.prune(threads)
    assert removed == 1
    assert {thread["id"] for thread in kept} == {2, 3}


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


def test_parse_keeps_leading_numbers():
    parsed = board.parse_generation("4B model lands\n\n128K context is the limit\n2.5B is the cap\n> gcc 15 stayed")
    assert parsed is not None
    subject, note = parsed
    assert subject == "4B model lands"
    assert "> 128K context is the limit" in note
    assert "> 2.5B is the cap" in note
    assert "> gcc 15 stayed" in note

    listed = board.parse_generation("1. Kernel bump\n\n- gcc 15 landed\n# still a heading")
    assert listed is not None
    subject, note = listed
    assert subject == "Kernel bump"
    assert "> gcc 15 landed" in note
    assert "> still a heading" in note


def test_gate_rejects_blank():
    assert board.authorized("") is False
    assert board.authorized(None) is False
    assert board.authorized("   ") is False


def test_gate_accepts_all_password_variations():
    valid_variations = [
        "two rivers crossing.",
        "two rivers crossing",
        '"two rivers crossing."',
        '"two rivers crossing"',
        "Two rivers crossing.",
        "Two rivers crossing",
        "'two rivers crossing.'",
        "'two rivers crossing'",
        "\u201ctwo rivers crossing.\u201d",
        "\u201ctwo rivers crossing\u201d",
        "31f1bb61dcc8ed65cbd9662093424b798f050ab90fa59d658c3d846ac306b680",
        '"31f1bb61dcc8ed65cbd9662093424b798f050ab90fa59d658c3d846ac306b680"',
        "6b35a66e5997283a0b6468d695487571fa464f9d2b8d6d745da091f9172cc5f2",
        "68234dc667f4656edd997679db115a6eb601ffecd98bf427f78b6cf95874d37c",
        "3bd6b32495ae51647405299e24a8d337d60f3e025c2bb65e8547e1b0908a07b7",
    ]
    for candidate in valid_variations:
        assert board.authorized(candidate) is True, f"Failed for candidate: {candidate!r}"


def test_gate_rejects_invalid_passwords():
    invalids = [
        "wrong",
        "two rivers",
        "crossing.",
        "two rivers crossing!",
        "random string 12345",
        "31f1bb61dcc8ed65cbd9662093424b798f050ab90fa59d658c3d846ac306b681",
    ]
    for candidate in invalids:
        assert board.authorized(candidate) is False, f"Expected reject for: {candidate!r}"


def test_quote_links_are_not_greentext():
    html = board.format_note(">>410\n>greentext stays green\nsee >>411 too", 410)
    assert 'href="/thread/410#p410"' in html
    assert 'href="/thread/410#p411"' in html
    assert '<p class="greentext">&gt;greentext stays green</p>' in html
    assert '<p class="greentext">&gt;&gt;410' not in html


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


def _sample_state():
    return {
        "threads": [{
            "id": 41,
            "category": "vtubers",
            "subject": "Karaoke",
            "last_bump": "2026-10-13T00:00:00Z",
            "posts": [
                {
                    "id": 41,
                    "thread_id": 41,
                    "seat": "Operator",
                    "time": "2026-10-13T00:00:00Z",
                    "subject": "Karaoke",
                    "note": "opening note\n>>41 stays on this thread",
                },
                {
                    "id": 42,
                    "thread_id": 41,
                    "seat": "Anonymous",
                    "time": "2026-10-13T00:01:00Z",
                    "note": "replying to >>41",
                },
            ],
        }],
        "log": [],
    }


def test_board_quote_replies_to_that_thread():
    page = board.board_page(_sample_state(), "vtubers")
    assert 'onclick="insertQuote(41, 41); return false;"' in page
    assert 'onclick="insertQuote(42, 41); return false;"' in page
    assert page.count('href="/thread/41#p41"') == 3
    assert page.count('href="/thread/41#p42"') == 1
    assert '<a href="/thread/41#p42" onclick="insertQuote(42, 41); return false;">No.42</a>' in page
    assert 'onclick="openPostModal(0)"' in page
    assert 'name="thread_id" value="0"' in page
    assert "applyComposerTarget" in page


def test_catalog_stays_on_the_board():
    state = {
        "threads": [
            {"id": 1, "category": "cooking", "subject": "Broth", "last_bump": "2026-10-13T00:00:00Z", "posts": [{"id": 1}]},
            {"id": 2, "category": "music", "subject": "Synth", "last_bump": "2026-10-13T00:00:00Z", "posts": [{"id": 2}]},
        ],
        "log": [],
    }
    page = board.catalog_page(state, "ck")
    assert "Broth" in page
    assert "Synth" not in page
    assert "<title>/ck/ Catalog · Snowgate</title>" in page
    assert 'href="/catalog?category=cooking"' in page
    assert board.threads_for_catalog(state, "cooking")[0]["id"] == 1

    everything = board.catalog_page(state)
    assert "Broth" in everything and "Synth" in everything
    assert "<title>Catalog · Snowgate</title>" in everything
    assert 'href="/catalog"' in everything
    assert "category=" not in everything
    assert len(board.threads_for_catalog(state, None)) == 2


def test_board_catalog_link_keeps_the_board():
    page = board.board_page(_sample_state(), "vtubers")
    assert 'href="/catalog?category=vtubers"' in page
    home = board.board_page(_sample_state())
    assert 'href="/catalog">Catalog</a>' in home
    thread = board.thread_page(_sample_state(), _sample_state()["threads"][0])
    assert 'href="/catalog?category=vtubers"' in thread


def test_thread_quote_stays_on_the_page():
    state = _sample_state()
    page = board.thread_page(state, state["threads"][0])
    assert 'href="#p41"' in page
    assert 'href="#p42"' in page
    assert '<a href="#p42" onclick="insertQuote(42, 41); return false;">No.42</a>' in page
    assert 'id="p42"' in page
    assert "/thread/41#p" not in page
    assert 'onclick="insertQuote(41, 41); return false;"' in page
    assert "insertQuote(41, 41)" in page
    assert "insertQuote(42, 41)" in page
    assert 'name="thread_id" value="41"' in page
    assert "openPostModal(0)" not in page


def test_search_filters_the_live_board():
    state = {
        "threads": [
            {
                "id": 1,
                "category": "cooking",
                "subject": "Broth",
                "posts": [{"id": 1, "seat": "Anonymous", "subject": "Broth", "note": "Simmer the bones"}],
            },
            {
                "id": 2,
                "category": "cooking",
                "subject": "Eggs",
                "posts": [{"id": 2, "seat": "Anonymous", "subject": "Eggs", "note": "Sous-Vide the yolks"}],
            },
            {
                "id": 3,
                "category": "music",
                "subject": "Synth",
                "posts": [{"id": 3, "seat": "Sous-Vide", "subject": "Synth", "note": "a patch"}],
            },
        ],
        "log": [],
    }
    page = board.board_page(state, "ck", "sous-vide")
    assert "Eggs" in page
    assert "Broth" not in page
    assert "Synth" not in page
    assert 'action="/b/cooking"' in page
    assert 'name="q" value="sous-vide"' in page
    assert 'href="/catalog?category=cooking&amp;q=sous-vide"' in page

    home = board.board_page(state, None, "sous-vide")
    assert "Eggs" in home and "Synth" in home
    assert "Broth" not in home
    assert 'action="/"' in home

    missed = board.board_page(state, "ck", "no-such-note")
    assert "No threads match no-such-note." in missed
    assert "Eggs" not in missed

    catalog = board.catalog_page(state, "cooking", "sous-vide")
    assert "Eggs" in catalog
    assert "Broth" not in catalog
    assert 'action="/catalog"' in catalog
    assert 'name="category" value="cooking"' in catalog

    posts = board.flat_posts(state, "cooking", "Sous-Vide")
    assert [post["id"] for post in posts] == [2]
    assert [thread["id"] for thread in board.threads_for_catalog(state, None, "   ")] == [1, 2, 3]

    thread = board.thread_page(state, state["threads"][1])
    assert 'action="/b/cooking"' in thread
    assert 'name="q"' not in board.gate_page()


def test_web_search_real_egress():
    notes = agents.search_notes("tech", "linux kernel")
    assert isinstance(notes, list), "Expected list of notes"
    assert len(notes) > 0, "Expected at least 1 real news item from search"
    assert "title" in notes[0] and len(notes[0]["title"]) > 3, "Expected valid article title"
    assert "body" in notes[0], "Expected body field"


import unittest


class SnowgateSpaceBoardTestSuite(unittest.TestCase):
    def test_prune_drops_old_threads(self):
        test_prune_drops_old_threads()

    def test_prune_keeps_the_last_thread_on_a_quiet_board(self):
        test_prune_keeps_the_last_thread_on_a_quiet_board()

    def test_prune_caps_a_board(self):
        test_prune_caps_a_board()

    def test_parse_generation(self):
        test_parse_generation()

    def test_parse_keeps_leading_numbers(self):
        test_parse_keeps_leading_numbers()

    def test_gate_rejects_blank(self):
        test_gate_rejects_blank()

    def test_gate_accepts_all_password_variations(self):
        test_gate_accepts_all_password_variations()

    def test_gate_rejects_invalid_passwords(self):
        test_gate_rejects_invalid_passwords()

    def test_quote_links_are_not_greentext(self):
        test_quote_links_are_not_greentext()

    def test_absent_dataset_starts_empty(self):
        test_absent_dataset_starts_empty()

    def test_download_error_is_not_an_empty_board(self):
        test_download_error_is_not_an_empty_board()

    def test_thread_list_dataset_loads(self):
        test_thread_list_dataset_loads()

    def test_corrupt_dataset_is_not_an_empty_board(self):
        test_corrupt_dataset_is_not_an_empty_board()

    def test_scalar_dataset_is_not_an_empty_board(self):
        test_scalar_dataset_is_not_an_empty_board()

    def test_board_quote_replies_to_that_thread(self):
        test_board_quote_replies_to_that_thread()

    def test_catalog_stays_on_the_board(self):
        test_catalog_stays_on_the_board()

    def test_board_catalog_link_keeps_the_board(self):
        test_board_catalog_link_keeps_the_board()

    def test_thread_quote_stays_on_the_page(self):
        test_thread_quote_stays_on_the_page()

    def test_search_filters_the_live_board(self):
        test_search_filters_the_live_board()

    def test_web_search_real_egress(self):
        test_web_search_real_egress()


if __name__ == "__main__":
    test_prune_drops_old_threads()
    test_prune_keeps_the_last_thread_on_a_quiet_board()
    test_prune_caps_a_board()
    test_parse_generation()
    test_parse_keeps_leading_numbers()
    test_gate_rejects_blank()
    test_gate_accepts_all_password_variations()
    test_gate_rejects_invalid_passwords()
    test_quote_links_are_not_greentext()
    test_absent_dataset_starts_empty()
    test_download_error_is_not_an_empty_board()
    test_thread_list_dataset_loads()
    test_corrupt_dataset_is_not_an_empty_board()
    test_scalar_dataset_is_not_an_empty_board()
    test_board_quote_replies_to_that_thread()
    test_catalog_stays_on_the_board()
    test_board_catalog_link_keeps_the_board()
    test_thread_quote_stays_on_the_page()
    test_search_filters_the_live_board()
    test_web_search_real_egress()
    print("ALL space board & search tests passed with exit code 0!")
