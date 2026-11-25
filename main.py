from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from apkg_builder import build_apkg

BASE = Path(__file__).parent
app = FastAPI(title="Anki Card Maker")

COLS = ["word", "meaning", "pos", "example", "example_vi", "ipa", "synonym", "antonym"]

PROMPT = """Bạn là biên tập viên từ vựng IELTS/tiếng Anh cho người Việt, soạn thẻ Anki.
Với MỖI mục trong danh sách (từ, cụm từ hoặc cấu trúc ngữ pháp), trả về object có đúng các khóa:
word (giữ nguyên mục đầu vào), meaning (nghĩa tiếng Việt ngắn gọn, đúng ngữ cảnh học thuật),
pos (n., v., adj., adv., phrase hoặc structure), example (1 câu tiếng Anh tự nhiên có chứa mục đó),
example_vi (dịch câu ví dụ sang tiếng Việt), ipa (IPA, KHÔNG có dấu / /; để chuỗi rỗng nếu là cấu trúc/cụm dài hoặc không chắc),
synonym, antonym (tiếng Anh, cách nhau dấu phẩy; để rỗng nếu không có hoặc không chắc).
Với cấu trúc/cụm: pos = "structure" hoặc "phrase", và đặt công thức vào meaning cùng nghĩa (ví dụ "S + be likely to V: có khả năng ...").
Không bịa dữ liệu khi không chắc, hãy để rỗng. Chỉ trả JSON: {"rows":[...]} theo đúng thứ tự đầu vào.
Danh sách:
"""


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise HTTPException(502, f"AI trả lỗi {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Không gọi được AI: {e}")


def _scrub(msg: str, key: str) -> str:
    return msg.replace(key, "***") if len(key) >= 8 else msg


def _call_ai(provider: str, key: str, model: str, items: list[str]) -> list[dict[str, Any]]:
    prompt = PROMPT + json.dumps(items, ensure_ascii=False)
    if provider == "openai":
        data = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"},
                     {"model": model, "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]})
        text = data["choices"][0]["message"]["content"]
    else:
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                     {"x-goog-api-key": key},
                     {"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}})
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise HTTPException(502, "AI không trả nội dung (có thể bị chặn hoặc hết quota).")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(502, "AI trả JSON hỏng, hãy thử lại với ít mục hơn.")
    rows = obj.get("rows") if isinstance(obj, dict) else obj
    if not isinstance(rows, list):
        raise HTTPException(502, "AI trả sai cấu trúc.")
    return rows


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/fill")
def fill(payload: dict[str, Any]):
    key = str(payload.get("api_key") or "").strip()
    model = str(payload.get("model") or "").strip()
    provider = "openai" if payload.get("provider") == "openai" else "gemini"
    items = [str(x).strip() for x in (payload.get("items") or []) if str(x).strip()]
    if not key or not model:
        raise HTTPException(400, "Thiếu API key hoặc model.")
    if not items or len(items) > 40:
        raise HTTPException(400, "Mỗi lần gửi 1–40 mục.")
    try:
        rows = _call_ai(provider, key, model, items)
    except HTTPException as e:
        raise HTTPException(e.status_code, _scrub(str(e.detail), key))
    out = []
    for i, item in enumerate(items):
        r = rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}
        row = {c: str(r.get(c) or "").strip() for c in COLS}
        row["word"] = item
        out.append(row)
    return {"rows": out}


@app.post("/api/export")
def export(payload: dict[str, Any]):
    rows = [r for r in (payload.get("rows") or []) if isinstance(r, dict) and str(r.get("word") or "").strip()]
    if not rows:
        raise HTTPException(400, "Chưa có thẻ nào để xuất.")
    if len(rows) > 2000:
        raise HTTPException(400, "Tối đa 2000 thẻ mỗi lần.")
    path = build_apkg(str(payload.get("deck") or "Anki Card Maker"), rows)
    return FileResponse(path, media_type="application/octet-stream", filename="my_deck.apkg",
                        background=BackgroundTask(lambda: os.path.exists(path) and os.remove(path)))


@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")
