"""Deterministic checks for prune, parsing, password variations, and live web search."""

from datetime import datetime, timedelta, timezone
import board
import agents


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
    assert 'onclick="insertQuote(41, 41)"' in page
    assert 'onclick="insertQuote(42, 41)"' in page
    assert page.count('href="/thread/41#p41"') == 2
    assert 'href="/thread/41#p42"' not in page
    assert 'onclick="openPostModal(0)"' in page
    assert 'name="thread_id" value="0"' in page
    assert "applyComposerTarget" in page


def test_thread_quote_stays_on_the_page():
    state = _sample_state()
    page = board.thread_page(state, state["threads"][0])
    assert 'href="#p41"' in page
    assert 'id="p42"' in page
    assert "/thread/41#p" not in page
    assert 'onclick="insertQuote(41, 41)"' in page
    assert "insertQuote(41, 41)" in page
    assert "insertQuote(42, 41)" in page
    assert 'name="thread_id" value="41"' in page
    assert "openPostModal(0)" not in page


def test_web_search_real_egress():
    notes = agents.search_notes("tech", "linux kernel")
    assert isinstance(notes, list), "Expected list of notes"
    assert len(notes) > 0, "Expected at least 1 real news item from search"
    assert "title" in notes[0] and len(notes[0]["title"]) > 3, "Expected valid article title"
    assert "body" in notes[0], "Expected body field"


if __name__ == "__main__":
    test_prune_drops_old_threads()
    test_prune_caps_a_board()
    test_parse_generation()
    test_gate_rejects_blank()
    test_gate_accepts_all_password_variations()
    test_gate_rejects_invalid_passwords()
    test_board_quote_replies_to_that_thread()
    test_thread_quote_stays_on_the_page()
    test_web_search_real_egress()
    print("ALL space board & search tests passed with exit code 0!")
