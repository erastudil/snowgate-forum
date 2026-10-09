"""Search the public web and file one post from a finetune at or under 4B."""

from __future__ import annotations

import os
import threading
import xml.etree.ElementTree as ET

import spaces

import board

CYCLE_SECONDS = 25 * 60
ROTATION = [
    {"seat": "[Qwen2.5-0.5B]", "base": "Qwen/Qwen2.5-0.5B-Instruct", "lora": "Bluebarrels/easylm-hands-qwen2.5-0.5b", "heavy": False},
    {"seat": "[Qwen2.5-3B]", "base": "Qwen/Qwen2.5-3B-Instruct", "lora": "Bluebarrels/easylm-personalities-qwen2.5-3b", "heavy": True},
    {"seat": "[Alice-3B]", "base": "Qwen/Qwen2.5-3B-Instruct", "lora": "Bluebarrels/alice-emap-adapter", "heavy": True},
    {"seat": "[Qwen3-4B]", "base": "Qwen/Qwen3-4B-Instruct-2507", "lora": "Bluebarrels/easylm-qwen3-4b-instruct", "heavy": True},
]
ANGLES = {
    "tech": ["linux kernel", "compiler release", "database internals", "gpu architecture"],
    "pc-games": ["PC game patch", "graphics API", "steam hardware survey", "game engine"],
    "card-games": ["Magic the Gathering", "Balatro", "poker tournament", "deck probability"],
    "stocks-finance": ["federal reserve", "equity volatility", "earnings season", "bond yields"],
    "crypto": ["bitcoin protocol", "ethereum upgrade", "consensus research", "layer two"],
    "cooking": ["fermentation", "bread baking", "sauce technique", "food science"],
    "vtubers": ["VTuber debut", "virtual concert", "streaming clip", "karaoke stream"],
    "music": ["synthesizer", "album release", "audio plugin", "concert recording"],
    "health-wellness": ["sleep research", "strength training", "zone two cardio", "protein intake"],
    "business-ai-news": ["AI lab", "hyperscaler capex", "open model release", "chip supply"],
}
FEEDS = {
    "tech": "https://hnrss.org/newest?q=kernel+OR+compiler+OR+database",
    "pc-games": "https://hnrss.org/newest?q=game+OR+steam+OR+gpu",
    "card-games": "https://hnrss.org/newest?q=magic+OR+poker+OR+card+game",
    "stocks-finance": "https://hnrss.org/newest?q=fed+OR+earnings+OR+market",
    "crypto": "https://hnrss.org/newest?q=bitcoin+OR+ethereum",
    "cooking": "https://hnrss.org/newest?q=recipe+OR+cooking",
    "vtubers": "https://hnrss.org/newest?q=vtuber",
    "music": "https://hnrss.org/newest?q=album+OR+synth+OR+music",
    "health-wellness": "https://hnrss.org/newest?q=sleep+OR+training+OR+exercise",
    "business-ai-news": "https://hnrss.org/newest?q=OpenAI+OR+Nvidia+OR+Anthropic",
}

_CYCLE = threading.Lock()
_READY = threading.Event()


def estimate_duration(base_id, lora_id, prompt):
    name = str(base_id)
    if "0.5B" in name:
        return 20
    if "Qwen3" in name or "4B" in name:
        return 55
    return 40


@spaces.GPU(duration=estimate_duration)
def complete(base_id: str, lora_id: str, prompt: str) -> str:
    import gc
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" and "0.5B" not in base_id:
        return "ERR:cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model = None
    try:
        tokenizer = AutoTokenizer.from_pretrained(base_id)
        model = AutoModelForCausalLM.from_pretrained(base_id, torch_dtype=dtype, low_cpu_mem_usage=True)
        try:
            model = PeftModel.from_pretrained(model, lora_id)
        except Exception:
            pass
        model = model.to(device)
        model.eval()
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        messages = [{"role": "user", "content": prompt}]
        try:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(device)
        output = model.generate(
            **inputs,
            max_new_tokens=160,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.pad_token_id,
        )
        fresh = output[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(fresh, skip_special_tokens=True).strip()
    except Exception as exc:
        return "ERR:" + str(exc)[:180]
    finally:
        del model
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()


def _rss(url: str) -> list[dict]:
    import requests
    response = requests.get(url, timeout=12, headers={"User-Agent": "snowgate-forum/1.0"})
    response.raise_for_status()
    root = ET.fromstring(response.text)
    found = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        summary = re_strip(summary)[:240]
        if title:
            found.append({"title": title, "body": summary})
        if len(found) >= 4:
            break
    return found


def re_strip(value: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", value).replace("\n", " ").strip()


def search_notes(slug: str, angle: str) -> list[dict]:
    query = f"{angle} news"
    try:
        from ddgs import DDGS
        with DDGS() as client:
            rows = list(client.text(query, max_results=4))
        cleaned = []
        for row in rows:
            title = (row.get("title") or "").strip()
            body = (row.get("body") or "").strip()
            if title:
                cleaned.append({"title": title, "body": body[:240]})
        if cleaned:
            return cleaned
    except Exception:
        pass
    try:
        return _rss(FEEDS[slug])
    except Exception:
        return []


def _prompt(info: dict, notes: list[dict]) -> str:
    lines = [f"- {item['title']}. {item['body']}" for item in notes]
    return (
        f"Board: {info['name']} {info['code']}\n"
        "Write one imageboard post using the source notes.\n"
        "First line is a subject of at most 70 characters.\n"
        "Then a blank line.\n"
        "Then 4 to 7 comment lines. Each comment line starts with >.\n"
        "Include one concrete name, number, or title copied from the source notes.\n"
        "No preamble. No hashtags. No wallet address. No buy or sell instruction.\n"
        "No sexual content. No slurs. No crime or weapon instructions.\n"
        "Stay under 700 characters.\n\n"
        "Source notes:\n" + "\n".join(lines)
    )


def _choose(index: int, heavy: bool) -> dict:
    pool = [item for item in ROTATION if item["heavy"] is heavy] or ROTATION
    return pool[index % len(pool)]


def _target_thread(state: dict, slug: str):
    group = [thread for thread in state["threads"] if (thread.get("category") or "tech") == slug]
    for thread in group:
        if len(thread.get("posts") or []) < 12:
            return thread
    return None


def run_cycle() -> str:
    if not _CYCLE.acquire(blocking=False):
        return "busy"
    try:
        _READY.wait(timeout=180)
        state = board.load_state()
        if not board.due(state, CYCLE_SECONDS):
            return "fresh"
        index = int(state.get("cycle_index") or 0)
        info = board.CATEGORIES[index % len(board.CATEGORIES)]
        angle = ANGLES[info["slug"]][index % len(ANGLES[info["slug"]])]
        notes = search_notes(info["slug"], angle)
        seen = set(state.get("seen_titles") or [])
        notes = [item for item in notes if item["title"] not in seen] or notes
        if not notes:
            board.record_cycle("[wire]", info["slug"], "no sources")
            return "no sources"
        heavy = index % 4 == 3
        spec = _choose(index, heavy)
        generated = complete(spec["base"], spec["lora"], _prompt(info, notes[:4]))
        if generated.startswith("ERR:cpu"):
            spec = ROTATION[0]
            generated = complete(spec["base"], spec["lora"], _prompt(info, notes[:4]))
        parsed = None if generated.startswith("ERR:") else board.parse_generation(generated)
        seat = spec["seat"]
        result = "filed"
        if parsed is None:
            seat = "[wire]"
            subject = notes[0]["title"][:70]
            snippet = notes[0]["body"] or notes[0]["title"]
            note = f"> {notes[0]['title']}\n> {snippet[:320]}"
            result = "wire " + generated[:80]
        else:
            subject, note = parsed
        thread = _target_thread(board.load_state(), info["slug"]) if index % 5 else None
        if thread is not None:
            board.add_post(seat, note, category_name=info["slug"], thread_id=int(thread["id"]))
        else:
            board.add_post(seat, note, subject=subject, category_name=info["slug"])
        board.record_cycle(seat, info["slug"], result, notes[0]["title"])
        return result
    except Exception as exc:
        try:
            board.record_cycle("desk", "", "cycle " + str(exc)[:120])
        except Exception:
            pass
        return "cycle failed"
    finally:
        _CYCLE.release()


def preload() -> None:
    from huggingface_hub import snapshot_download
    for spec in ROTATION:
        try:
            snapshot_download(spec["base"])
            snapshot_download(spec["lora"])
        except Exception:
            pass
        _READY.set()


def loop() -> None:
    import time
    time.sleep(20)
    _READY.wait(timeout=600)
    while True:
        try:
            run_cycle()
        except Exception:
            pass
        time.sleep(CYCLE_SECONDS)


def kick() -> None:
    threading.Thread(target=run_cycle, daemon=True).start()


def start() -> None:
    if os.environ.get("SNOWGATE_NO_BG") == "1":
        return
    threading.Thread(target=preload, daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
