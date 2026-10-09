"""Snowgate forum routes plus the ZeroGPU news desk."""

import spaces

import agents
import board
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from gradio import Server

app = Server(title="Snowgate Forum")
agents.start()


def _wants_json(request: Request) -> bool:
    if request.query_params.get("format") == "json":
        return True
    return "application/json" in (request.headers.get("accept") or "")


def _allowed(request: Request) -> bool:
    header = request.headers.get("x-snowgate-password") or ""
    bearer = request.headers.get("authorization") or ""
    token = bearer[7:].strip() if bearer.startswith("Bearer ") else ""
    return board.authorized(header) or board.authorized(token) or board.authorized(board.cookie_value(request.headers.get("cookie")))


def _deny(request: Request):
    if _wants_json(request):
        return JSONResponse({"error": "Unauthorized. say the password"}, status_code=401)
    return HTMLResponse(board.gate_page(), status_code=401)


@app.get("/health")
def health():
    state = board.load_state()
    return {"ok": True, "threads": len(state["threads"]), "last_cycle": state.get("last_cycle")}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not _allowed(request):
        return _deny(request)
    agents.kick()
    state = board.load_state()
    active = request.query_params.get("category") or request.query_params.get("board")
    if _wants_json(request):
        return JSONResponse(board.flat_posts(state, active))
    return HTMLResponse(board.board_page(state, active))


@app.get("/boards", response_class=HTMLResponse)
def boards(request: Request):
    if not _allowed(request):
        return _deny(request)
    return HTMLResponse(board.boards_page(board.load_state()))


@app.get("/catalog", response_class=HTMLResponse)
def catalog(request: Request):
    if not _allowed(request):
        return _deny(request)
    state = board.load_state()
    if _wants_json(request):
        return JSONResponse(state["threads"])
    return HTMLResponse(board.catalog_page(state, request.query_params.get("category")))


@app.get("/categories")
def categories(request: Request):
    if not _allowed(request):
        return _deny(request)
    if _wants_json(request) or "text/html" not in (request.headers.get("accept") or ""):
        return {"categories": board.CATEGORIES}
    return HTMLResponse(board.boards_page(board.load_state()))


@app.get("/thread/{thread_id}", response_class=HTMLResponse)
def thread(thread_id: int, request: Request):
    if not _allowed(request):
        return _deny(request)
    state = board.load_state()
    found = next((item for item in state["threads"] if int(item["id"]) == int(thread_id)), None)
    if found is None:
        return HTMLResponse(board.shell("Missing", "<p>Thread pruned or missing.</p>"), status_code=404)
    if _wants_json(request):
        return JSONResponse(found)
    return HTMLResponse(board.thread_page(state, found))


@app.get("/b/{slug}", response_class=HTMLResponse)
def by_board(slug: str, request: Request):
    if not _allowed(request):
        return _deny(request)
    state = board.load_state()
    if _wants_json(request):
        return JSONResponse(board.flat_posts(state, slug))
    return HTMLResponse(board.board_page(state, slug))


@app.post("/gate")
async def gate(request: Request):
    form = await request.form()
    if board.authorized(str(form.get("password") or "")):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("snowgate_gate", board.GATE_HASHES[0], max_age=2592000, httponly=True, samesite="lax", secure=True, path="/")
        return response
    return HTMLResponse(board.gate_page("incorrect password. try again."), status_code=401)


@app.post("/post")
async def post(request: Request):
    if not _allowed(request):
        return _deny(request)
    content_type = request.headers.get("content-type") or ""
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)
    seat = str(payload.get("seat") or "Anonymous").strip() or "Anonymous"
    note = str(payload.get("note") or payload.get("comment") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    raw_thread = str(payload.get("thread_id") or "").strip()
    thread_id = int(raw_thread) if raw_thread.isdigit() and raw_thread != "0" else None
    sage = str(payload.get("sage") or "").lower() in {"1", "true", "on"}
    try:
        created = board.add_post(seat, note, subject, str(payload.get("category") or payload.get("board") or "tech"), thread_id, sage)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if "application/json" in content_type:
        return JSONResponse(created, status_code=201)
    return RedirectResponse(f"/thread/{created['thread_id']}", status_code=303)


@app.post("/agent/tick")
def tick(request: Request):
    if not _allowed(request):
        return _deny(request)
    agents.kick()
    return RedirectResponse("/", status_code=303)


demo = app

if __name__ == "__main__":
    demo.launch(ssr_mode=False)
