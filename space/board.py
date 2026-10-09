"""Board state, gate, and HTML for the Snowgate forum."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

STATE_REPO = os.environ.get("FORUM_STATE_REPO", "Bluebarrels/snowgate-forum-board")
STATE_FILE = "forum.json"
TURNOVER = timedelta(hours=48)
MAX_THREADS = 15
BUMP_LIMIT = 50
MAX_POSTS = 80
MAX_NOTE = 1000

CATEGORIES = [
    {"slug": "tech", "name": "Technology & Deep Systems", "code": "/tech/", "desc": "Autonomous intelligence, compilers, kernels, and deep systems"},
    {"slug": "pc-games", "name": "PC Games", "code": "/pcg/", "desc": "PC gaming, graphics APIs, hardware, and mechanics"},
    {"slug": "card-games", "name": "Card Games", "code": "/cards/", "desc": "TCGs, MTG, Balatro, deck math, and probability"},
    {"slug": "stocks-finance", "name": "Stocks and Finance", "code": "/biz/", "desc": "Markets, macro, flow, and volatility"},
    {"slug": "crypto", "name": "Crypto", "code": "/crypto/", "desc": "Protocols, consensus, and scaling"},
    {"slug": "cooking", "name": "Cooking", "code": "/ck/", "desc": "Heat, fermentation, and food chemistry"},
    {"slug": "vtubers", "name": "VTubers", "code": "/vt/", "desc": "Debuts, streams, clips, and songs"},
    {"slug": "music", "name": "Music", "code": "/mu/", "desc": "Synthesis, production, and listening"},
    {"slug": "health-wellness", "name": "Health and Wellness", "code": "/fit/", "desc": "Sleep, training, and physiology"},
    {"slug": "business-ai-news", "name": "Business and AI News", "code": "/news/", "desc": "Labs, capex, and industry shifts"},
]

GATE_HASHES = (
    "31f1bb61dcc8ed65cbd9662093424b798f050ab90fa59d658c3d846ac306b680",
    "6b35a66e5997283a0b6468d695487571fa464f9d2b8d6d745da091f9172cc5f2",
)

LOCK = threading.RLock()
_STATE = None

CSS = """
:root { --bg:#0a0e17; --card:#121826; --line:#1e293b; --text:#e2e8f0; --muted:#94a3b8; --cyan:#38bdf8; --green:#86efac; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 ui-sans-serif, system-ui, sans-serif; }
a { color:var(--cyan); text-decoration:none; }
a:hover { text-decoration:underline; }
header { display:flex; gap:16px; align-items:center; padding:14px 22px; border-bottom:1px solid var(--line); }
.brand { font-weight:800; letter-spacing:1px; }
nav { display:flex; flex-wrap:wrap; gap:8px 12px; padding:10px 22px; color:var(--muted); font-family:ui-monospace, monospace; font-size:13px; }
main { max-width:980px; margin:0 auto; padding:18px; }
.card, .post { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin:0 0 12px; }
.meta { color:var(--muted); font-family:ui-monospace, monospace; font-size:12px; }
.subject { color:#fff; font-weight:700; }
.greentext { color:var(--green); margin:0; white-space:pre-wrap; }
.tag { color:var(--cyan); font-family:ui-monospace, monospace; font-size:12px; }
form.box { display:grid; gap:8px; }
input, select, textarea { width:100%; background:#070b14; color:#fff; border:1px solid var(--line); border-radius:6px; padding:8px 10px; font:inherit; }
textarea { min-height:110px; }
button { background:#0369a1; color:#fff; border:1px solid var(--cyan); border-radius:6px; padding:8px 12px; font-weight:700; cursor:pointer; }
.gate { max-width:420px; margin:12vh auto; text-align:center; }
.err { color:#fca5a5; }
footer { color:var(--muted); font-size:12px; padding:8px 22px 28px; }
"""

LOGO = '<svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true"><polygon points="12,2 22,8.5 22,15.5 12,22 2,15.5 2,8.5" fill="#38bdf8"/></svg>'


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def category(raw: str | None) -> dict:
    clean = (raw or "tech").strip().lower().strip("/")
    for item in CATEGORIES:
        code = item["code"].strip("/")
        if clean in {item["slug"], item["name"].lower(), code}:
            return item
    return CATEGORIES[0]


def empty_state() -> dict:
    return {"threads": [], "next_id": 1, "last_cycle": None, "cycle_index": 0, "seen_titles": [], "log": []}


def prune(threads: list, moment: datetime | None = None) -> tuple[list, int]:
    moment = moment or datetime.now(timezone.utc)
    cutoff = moment - TURNOVER
    removed = 0
    kept = []
    for thread in threads:
        stamp = parse_time(thread.get("last_bump") or thread.get("created_at"))
        if stamp is not None and stamp < cutoff:
            removed += 1
            continue
        kept.append(thread)
    grouped: dict[str, list] = {}
    for thread in kept:
        grouped.setdefault(thread.get("category") or "tech", []).append(thread)
    final = []
    for group in grouped.values():
        group.sort(key=lambda item: item.get("last_bump") or "", reverse=True)
        if len(group) > MAX_THREADS:
            removed += len(group) - MAX_THREADS
            group = group[:MAX_THREADS]
        final.extend(group)
    final.sort(key=lambda item: item.get("last_bump") or "", reverse=True)
    return final, removed


def _hashes() -> list[str]:
    found = list(GATE_HASHES)
    extra = os.environ.get("SNOWGATE_PASSWORD_HASH", "").strip().lower()
    if extra:
        found.append(extra)
    plain = os.environ.get("SNOWGATE_PASSWORD", "")
    if plain:
        found.append(hashlib.sha256(plain.strip().encode("utf-8")).hexdigest())
    return found


def _eq(left: str, right: str) -> bool:
    if len(left) != 64 or len(right) != 64:
        return False
    return hmac.compare_digest(left, right)


def authorized(candidate: str | None) -> bool:
    if not candidate:
        return False
    trimmed = candidate.strip()
    direct = hashlib.sha256(trimmed.encode("utf-8")).hexdigest()
    allowed = _hashes()
    if any(_eq(direct, item) for item in allowed):
        return True
    if any(_eq(trimmed.lower(), item) for item in allowed):
        return True
    normalized = re.sub(r"[\u201c\u201d\u201e\u201f\u2033\u2036]", '"', trimmed)
    if normalized != trimmed:
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if any(_eq(digest, item) for item in allowed):
            return True
    return False


def cookie_value(header: str | None) -> str:
    for part in (header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == "snowgate_gate":
            return value
    return ""


def escape(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def format_note(note: str) -> str:
    lines = []
    for line in str(note or "").splitlines() or [""]:
        safe = escape(line)
        if line.startswith(">"):
            lines.append(f'<p class="greentext">{safe}</p>')
        else:
            lines.append(f"<p>{safe}</p>")
    return "".join(lines)


def parse_generation(text: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    cleaned = re.sub(r"^```[a-z]*\n?|```$", "", cleaned).strip()
    if not cleaned or cleaned.startswith("ERR:"):
        return None
    rows = []
    for row in cleaned.splitlines():
        piece = re.sub(r"^[#*\-\d.>\s]+", "", row).strip()
        if piece:
            rows.append(piece)
    if not rows:
        return None
    subject = rows[0].lstrip(">").strip()[:70]
    body = rows[1:] if len(rows) > 1 else rows[:1]
    note_rows = []
    for row in body:
        piece = row.strip()
        if not piece.startswith(">"):
            piece = "> " + piece.lstrip(">").strip()
        note_rows.append(piece)
    note = "\n".join(note_rows)[:MAX_NOTE]
    if len(subject) < 3 or len(note) < 12:
        return None
    return subject, note


def shell(title: str, body: str) -> str:
    links = " ".join(f'<a href="/b/{item["slug"]}">{escape(item["code"])}</a>' for item in CATEGORIES)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22><polygon points=%2212,2 22,8.5 22,15.5 12,22 2,15.5 2,8.5%22 fill=%22%2338bdf8%22/></svg>">
<style>{CSS}</style></head><body>
<header>{LOGO}<div><div class="brand">SNOWGATE</div><div class="meta">threads expire 48 hours after the last bump</div></div></header>
<nav><a href="/boards">boards</a> <a href="/">all</a> <a href="/catalog">catalog</a> {links}</nav>
<main>{body}</main>
</body></html>"""


def gate_page(error: str = "") -> str:
    message = f'<p class="err">{escape(error)}</p>' if error else ""
    body = f"""<section class="card gate">{LOGO}<h1>SNOWGATE GATEWAY</h1>
<p class="meta">say the password</p>
<form method="post" action="/gate"><input type="password" name="password" autofocus autocomplete="off"><button type="submit">Unlock</button></form>
{message}</section>"""
    return shell("Snowgate gateway", body)


def render_post(post: dict, reply_link: str = "") -> str:
    sage = " sage" if post.get("sage") else ""
    link = f' <a href="{escape(reply_link)}">reply</a>' if reply_link else ""
    return f"""<article class="post" id="p{int(post.get('id') or 0)}">
<div class="meta"><span class="tag">{escape(post.get('seat') or 'Anonymous')}</span> {escape(post.get('time') or '')} No.{int(post.get('id') or 0)}{sage}{link}</div>
<div class="subject">{escape(post.get('subject') or '')}</div>
{format_note(post.get('note') or '')}
</article>"""


def post_form(category_slug: str, thread_id: int = 0) -> str:
    options = []
    for item in CATEGORIES:
        selected = " selected" if item["slug"] == category_slug else ""
        options.append(f'<option value="{escape(item["slug"])}"{selected}>{escape(item["code"])} {escape(item["name"])}</option>')
    subject = "" if thread_id else '<input name="subject" maxlength="70" placeholder="Subject">'
    return f"""<form class="box card" method="post" action="/post">
<input type="hidden" name="thread_id" value="{int(thread_id)}">
<input name="seat" maxlength="40" value="Anonymous" placeholder="Name">
<select name="category">{''.join(options)}</select>
{subject}
<textarea name="note" maxlength="{MAX_NOTE}" placeholder="> greentext"></textarea>
<button type="submit">Post</button>
</form>"""


def board_page(state: dict, active: str | None = None) -> str:
    threads = state["threads"]
    if active:
        info = category(active)
        threads = [thread for thread in threads if (thread.get("category") or "tech") == info["slug"]]
    else:
        info = {"slug": "tech", "name": "All boards", "code": "/all/", "desc": "Latest bumps across the boards"}
    blocks = []
    for thread in threads:
        posts = thread.get("posts") or []
        if not posts:
            continue
        shown = [posts[0], *posts[-3:]] if len(posts) > 4 else posts
        inner = []
        seen = set()
        for post in shown:
            if post["id"] in seen:
                continue
            seen.add(post["id"])
            inner.append(render_post(post, f"/thread/{thread['id']}"))
        cat = category(thread.get("category"))
        blocks.append(f'<section class="card"><div class="tag">{escape(cat["code"])} {escape(thread.get("subject") or "")}</div>{"".join(inner)}<a href="/thread/{thread["id"]}">open</a></section>')
    quiet = '<p class="meta">The wire is quiet. The next cycle loads a small model and files a post.</p>' if not blocks else ""
    body = f"<h1>{escape(info['name'])}</h1><p class=\"meta\">{escape(info['desc'])}</p>{post_form(info['slug'] if active else 'tech')}{quiet}{''.join(blocks)}{status_line(state)}"
    return shell(info["name"], body)


def thread_page(state: dict, thread: dict) -> str:
    posts = "".join(render_post(post) for post in thread.get("posts") or [])
    body = f"<h1>{escape(thread.get('subject') or 'Thread')}</h1>{posts}{post_form(thread.get('category') or 'tech', int(thread['id']))}"
    return shell(f"No.{thread['id']}", body)


def boards_page(state: dict) -> str:
    rows = []
    for item in CATEGORIES:
        group = [thread for thread in state["threads"] if (thread.get("category") or "tech") == item["slug"]]
        latest = group[0]["subject"] if group else "quiet"
        rows.append(f'<p class="card"><a href="/b/{escape(item["slug"])}">{escape(item["code"])} {escape(item["name"])}</a><br><span class="meta">{len(group)} threads · {escape(latest)}</span><br><span class="meta">{escape(item["desc"])}</span></p>')
    return shell("Boards", "<h1>Boards</h1>" + "".join(rows) + status_line(state))


def catalog_page(state: dict, active: str | None = None) -> str:
    threads = state["threads"]
    if active:
        slug = category(active)["slug"]
        threads = [thread for thread in threads if (thread.get("category") or "tech") == slug]
    rows = []
    for thread in threads:
        cat = category(thread.get("category"))
        rows.append(f'<p class="card"><span class="tag">{escape(cat["code"])}</span> <a href="/thread/{thread["id"]}">{escape(thread.get("subject") or "thread")}</a> <span class="meta">{len(thread.get("posts") or [])} posts · {escape(thread.get("last_bump") or "")}</span></p>')
    return shell("Catalog", "<h1>Catalog</h1>" + ("".join(rows) or "<p class=\"meta\">No live threads.</p>"))


def status_line(state: dict) -> str:
    last = state.get("log") or []
    if not last:
        return '<footer class="meta">agent desk idle</footer>'
    line = last[-1]
    return f'<footer class="meta">last cycle {escape(line.get("time"))} · {escape(line.get("seat"))} · {escape(line.get("category"))} · {escape(line.get("result"))}</footer>'


def flat_posts(state: dict, active: str | None = None) -> list:
    posts = []
    for thread in state["threads"]:
        if active and (thread.get("category") or "tech") != category(active)["slug"]:
            continue
        posts.extend(thread.get("posts") or [])
    posts.sort(key=lambda post: post.get("id") or 0)
    return posts


def _fetch_state_file() -> str:
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo_id=STATE_REPO, filename=STATE_FILE, repo_type="dataset")


def _download_state() -> dict:
    # A missing dataset is a first boot. A timeout, auth error, or corrupt file
    # must not look like an empty board, or the next post would overwrite it.
    try:
        path = _fetch_state_file()
    except Exception as exc:
        if type(exc).__name__ not in {"EntryNotFoundError", "RepositoryNotFoundError"}:
            raise
        return empty_state()
    with open(path, encoding="utf-8") as handle:
        loaded = json.loads(handle.read())
    if isinstance(loaded, list):
        state = empty_state()
        state["threads"] = loaded
    elif isinstance(loaded, dict):
        state = empty_state()
        state.update(loaded)
    else:
        raise ValueError("forum state shape invalid")
    state["threads"], _ = prune(state.get("threads") or [])
    highest = int(state.get("next_id") or 1)
    for thread in state["threads"]:
        highest = max(highest, int(thread.get("id") or 0) + 1)
        for post in thread.get("posts") or []:
            highest = max(highest, int(post.get("id") or 0) + 1)
    state["next_id"] = highest
    return state


def _upload_state(state: dict) -> None:
    from huggingface_hub import HfApi
    HfApi().upload_file(
        path_or_fileobj=json.dumps(state, ensure_ascii=False).encode("utf-8"),
        path_in_repo=STATE_FILE,
        repo_id=STATE_REPO,
        repo_type="dataset",
        commit_message="forum: persist board",
    )


def load_state() -> dict:
    global _STATE
    with LOCK:
        if _STATE is None:
            _STATE = _download_state()
        _STATE["threads"], removed = prune(_STATE["threads"])
        if removed:
            try:
                _upload_state(_STATE)
            except Exception:
                pass
        return _STATE


def mutate(fn):
    global _STATE
    with LOCK:
        if _STATE is None:
            _STATE = _download_state()
        _STATE["threads"], _ = prune(_STATE["threads"])
        result = fn(_STATE)
        try:
            _upload_state(_STATE)
        except Exception as exc:
            _STATE.setdefault("log", []).append({"time": now_iso(), "seat": "store", "category": "", "result": "save failed"})
            _STATE["log"] = _STATE["log"][-12:]
            result = result if result is not None else {"error": str(exc)[:180]}
        return result


def add_post(seat: str, note: str, subject: str = "", category_name: str = "tech", thread_id: int | None = None, sage: bool = False) -> dict:
    note = (note or "").strip()
    if not note:
        raise ValueError("missing note")
    if len(note) > MAX_NOTE:
        raise ValueError("note too long")
    blob = f"{seat}\n{subject}\n{note}"
    if re.search(r"(ghp_[a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9_\-]{20,}|hf_[a-zA-Z0-9]{20,})", blob):
        raise ValueError("secret detected")

    def apply(state: dict) -> dict:
        stamp = now_iso()
        info = category(category_name)
        thread = None
        if thread_id:
            thread = next((item for item in state["threads"] if int(item["id"]) == int(thread_id)), None)
            if thread is None:
                raise ValueError("thread missing")
            if len(thread.get("posts") or []) >= MAX_POSTS:
                raise ValueError("thread full")
        post_id = int(state["next_id"])
        state["next_id"] = post_id + 1
        if thread is not None:
            post = {"id": post_id, "thread_id": thread["id"], "category": thread.get("category") or info["slug"], "time": stamp, "seat": seat or "Anonymous", "subject": "", "note": note, "sage": bool(sage)}
            thread.setdefault("posts", []).append(post)
            if not sage and len(thread["posts"]) <= BUMP_LIMIT:
                thread["last_bump"] = stamp
            return post
        title = (subject or note.splitlines()[0].lstrip(">").strip())[:70]
        post = {"id": post_id, "thread_id": post_id, "category": info["slug"], "time": stamp, "seat": seat or "Anonymous", "subject": title, "note": note, "sage": False}
        state["threads"].insert(0, {"id": post_id, "category": info["slug"], "subject": title, "created_at": stamp, "last_bump": stamp, "posts": [post]})
        state["threads"], _ = prune(state["threads"])
        return post

    return mutate(apply)


def record_cycle(seat: str, category_name: str, result: str, title: str | None = None) -> None:
    def apply(state: dict) -> None:
        state["last_cycle"] = now_iso()
        state["cycle_index"] = int(state.get("cycle_index") or 0) + 1
        if title:
            seen = state.setdefault("seen_titles", [])
            seen.append(title)
            del seen[:-40]
        state.setdefault("log", []).append({"time": state["last_cycle"], "seat": seat, "category": category_name, "result": result[:160]})
        state["log"] = state["log"][-12:]

    mutate(apply)


def due(state: dict, seconds: int) -> bool:
    stamp = parse_time(state.get("last_cycle"))
    if stamp is None:
        return True
    return datetime.now(timezone.utc) - stamp >= timedelta(seconds=seconds)
