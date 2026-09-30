"""Images in chat: save them, pass them to a vision-capable lead, or have a small
vision model DESCRIBE them so a text-only lead (qwen coder, llama3.2...) can work.

The UI sends `images: [dataURL|base64, ...]` on the newest user message only.
prepare() returns (messages, notes): messages are ready for ollama (native images for a
vision lead, or the description appended as text for a blind one); notes is the
`image_note` SSE payload the UI appends to that message so follow-ups keep the context.
"""
from __future__ import annotations

import base64
import os
import re
import time

import tools

VISION_HINTS = ("llava", "vision", "moondream", "minicpm-v", "gemma3", "qwen2.5vl",
                "qwen3-vl", "qwen2.5-vl", "bakllava", "llama4", "mistral-small3")
DEFAULT_VISION = "qwen2.5vl:3b"
MAX_IMAGES = 4
MAX_BYTES = 8 * 1024 * 1024
DESCRIBE_PROMPT = (
    "Describe this image for a game developer. List what is visible: objects, layout, "
    "colors, UI, and any error message. Transcribe visible text exactly. Be concrete and "
    "under 200 words. No guessing about what is not shown.")


def is_vision(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in VISION_HINTS)


def _b64(data: str) -> bytes | None:
    m = re.match(r"^data:image/[\w.+-]+;base64,(.*)$", data or "", re.S)
    raw = m.group(1) if m else (data or "")
    try:
        b = base64.b64decode(raw, validate=False)
    except Exception:
        return None
    return b if 0 < len(b) <= MAX_BYTES else None


def _ext(b: bytes) -> str:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    return "png"


def save_image(b: bytes, idx: int) -> str:
    """Write into the workspace so agents can open/reference it. Returns relative path."""
    rel = f"attachments/img-{time.strftime('%Y%m%d-%H%M%S')}-{idx}.{_ext(b)}"
    full = os.path.join(tools.SANDBOX, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(b)
    return rel


def pick_vision_model(client, want: str, installed: set) -> str:
    """Setting first, then any installed model that looks vision-capable, else ''."""
    have = installed or set()
    if want and (not have or want in have or f"{want}:latest" in have):
        return want
    for n in sorted(have):
        if is_vision(n):
            return n
    return ""


def describe(client, model: str, images: list[bytes], hint: str = "") -> str:
    out = []
    for i, b in enumerate(images, 1):
        prompt = DESCRIBE_PROMPT + (f"\nThe user asks: {hint[:300]}" if hint else "")
        r = client.chat(model=model, stream=False, keep_alive=0,     # free RAM right after
                        options={"num_ctx": 4096},
                        messages=[{"role": "user", "content": prompt, "images": [b]}])
        text = r["message"]["content"] or ""
        out.append(text.strip() or "(no description)")
    return "\n\n".join(f"[image {i}] {t}" for i, t in enumerate(out, 1))


def prepare(client, lead: str, history: list[dict], vision_model: str,
            installed: set) -> tuple[list[dict], dict | None]:
    """Resolve `images` on the newest user message; strip them everywhere else."""
    hist = [dict(m) for m in history]
    last = next((i for i in range(len(hist) - 1, -1, -1) if hist[i].get("role") == "user"), None)
    for i, m in enumerate(hist):
        if i != last:
            m.pop("images", None)
    if last is None:
        return hist, None
    m = hist[last]
    raw = [x for x in (m.pop("images", None) or [])][:MAX_IMAGES]
    blobs = [b for b in (_b64(x) for x in raw) if b]
    if not blobs:
        return hist, None
    paths = [save_image(b, i) for i, b in enumerate(blobs, 1)]
    listing = ", ".join(paths)
    if is_vision(lead):
        m["images"] = blobs                       # the lead can see them itself
        m["content"] = (m.get("content", "") + f"\n[attached: {listing}]").strip()
        return hist, {"paths": paths, "description": "", "mode": "native"}
    vm = pick_vision_model(client, vision_model, installed)
    if not vm:
        desc = (f"(no vision model installed — run `ollama pull {DEFAULT_VISION}` so the crew "
                "can read images)")
    else:
        try:
            desc = describe(client, vm, blobs, m.get("content", ""))
        except Exception as e:
            desc = f"(vision model {vm} failed: {e})"
    m["content"] = (m.get("content", "") + f"\n[attached: {listing}]\n{desc}").strip()
    return hist, {"paths": paths, "description": desc, "mode": "described", "model": vm}
