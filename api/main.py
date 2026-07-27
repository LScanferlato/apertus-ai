"""
Translation Gateway for Apertus 1.5 8B

A small FastAPI application that exposes a DeepL-style REST endpoint
(`/translate`) on top of the Apertus 1.5 8B model served by vLLM.
It also transparently proxies the upstream OpenAI-compatible API
(/v1/chat/completions, /v1/models) provided by vLLM.

Rationale:
    Apertus 1.5 is multimodal (text + image + audio). Ollama lacks native
    support for this architecture, so we use the official Swiss-AI vLLM
    container image (ghcr.io/swiss-ai/vllm_apertus_1.5_release) as the
    inference backend and add a thin translation-oriented API layer.

The translation prompt is enriched with a multilingual system message
inspired by the Canton Ticino / Artificialy use case: the model is
instructed to act as a professional translator for the languages used
in the Swiss administrative context (Italian, German, French, Romansh,
plus extra ones such as English, Spanish, Romanian, Ukrainian).
"""

from __future__ import annotations

import os
import json
import time
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

log = logging.getLogger("apertus-translator")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VLLM_BASE_URL = os.environ.get(
    "VLLM_BASE_URL", "http://vllm:8000"
).rstrip("/")
MODEL_NAME = os.environ.get(
    "MODEL_NAME", "artificialy/Apertus-v1.5-8B-FP8-DYNAMIC"
)
# Optional: second served name registered in vLLM (e.g. the thinking variant).
THINKING_MODEL_NAME = os.environ.get("THINKING_MODEL_NAME", "")
DEFAULT_TARGET_LANG = os.environ.get("DEFAULT_TARGET_LANG", "Italian")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8080"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "300"))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "50000"))

# Professional system prompt that turns Apertus into a translator.
TRANSLATION_SYSTEM_PROMPT = (
    "You are a professional, highly accurate translator used by a Swiss "
    "public administration. Translate the user's text from the source "
    "language into the requested target language. Preserve the original "
    "meaning, tone, register, formatting (paragraphs, lists, headings) "
    "and any proper nouns, numbers, dates and currencies. Do not add "
    "explanations, notes, or commentary unless explicitly asked. Output "
    "only the translated text."
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TranslateRequest(BaseModel):
    text: str = Field(..., description="Text to translate")
    source_lang: Optional[str] = Field(
        None,
        description="Source language (ISO 639-1 or full name). "
        "Omit to let the model auto-detect.",
    )
    target_lang: str = Field(
        ...,
        description="Target language (ISO 639-1 or full name).",
    )
    glossary: Optional[Dict[str, str]] = Field(
        None,
        description="Optional term mapping {source_term: target_term}.",
    )
    context: Optional[str] = Field(
        None,
        description="Optional domain / context hint "
        "(e.g. 'legal', 'medical', 'public administration').",
    )
    thinking: bool = Field(
        False,
        description="Enable Apertus thinking mode (slower, higher quality).",
    )
    temperature: float = 0.2
    max_tokens: Optional[int] = 4096


class TranslateResponse(BaseModel):
    translations: List[Dict[str, str]] = Field(
        ..., description="List of translation results."
    )
    detected_source_lang: Optional[str] = None
    model: str
    usage: Dict[str, int] = Field(default_factory=dict)
    timings: Dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Apertus Translation Gateway",
    description="DeepL-style REST API on top of Apertus 1.5 8B (vLLM).",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_prompt(req: TranslateRequest) -> str:
    """Compose the user prompt that asks Apertus to translate."""
    parts: List[str] = []

    src_clause = (
        f"Source language: {req.source_lang}."
        if req.source_lang
        else "Source language: auto-detect."
    )
    parts.append(f"{src_clause} Target language: {req.target_lang}.")

    if req.context:
        parts.append(f"Context / domain: {req.context}.")

    if req.glossary:
        terms = ", ".join(
            f'"{k}" -> "{v}"' for k, v in req.glossary.items()
        )
        parts.append(
            "Use the following terminology consistently: " + terms + "."
        )

    parts.append(
        "Translate the text delimited by <src></src> tags. "
        "Output only the translation, nothing else."
    )

    parts.append(f"<src>\n{req.text}\n</src>")
    return "\n".join(parts)


def _pick_model(req: TranslateRequest) -> str:
    if req.thinking and THINKING_MODEL_NAME:
        return THINKING_MODEL_NAME
    return MODEL_NAME


async def _forward_to_vllm(
    path: str, method: str = "POST", **kwargs: Any
) -> httpx.Response:
    url = f"{VLLM_BASE_URL}{path}"
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            log.error("Error contacting vLLM at %s: %s", url, exc)
            raise HTTPException(
                status_code=503,
                detail=f"Upstream vLLM unreachable: {exc}",
            ) from exc
    return resp


# ---------------------------------------------------------------------------
# DeepL-style translation endpoint
# ---------------------------------------------------------------------------


@app.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest) -> TranslateResponse:
    if len(req.text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Text too large: {len(req.text)} chars "
            f"(max {MAX_TEXT_CHARS}).",
        )
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text.")

    model_name = _pick_model(req)
    user_prompt = _build_user_prompt(req)
    t0 = time.perf_counter()

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "stream": False,
    }

    resp = await _forward_to_vllm(
        "/v1/chat/completions",
        method="POST",
        headers={"Content-Type": "application/json"},
        content=json.dumps(payload),
    )
    t1 = time.perf_counter()
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"vLLM error: {resp.text}",
        )

    data = resp.json()
    choices = data.get("choices", [])
    translated = choices[0]["message"]["content"] if choices else ""
    usage = data.get("usage", {})
    detected = req.source_lang

    return TranslateResponse(
        translations=[{"text": translated, "target_lang": req.target_lang}],
        detected_source_lang=detected,
        model=model_name,
        usage=usage,
        timings={"total": round(t1 - t0, 3)},
    )


@app.post("/translate/batch")
async def translate_batch(payload: Dict[str, Any]) -> JSONResponse:
    """Translate multiple texts in one request (DeepL-compatible-ish)."""
    if "texts" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'texts' list.")
    target_lang = payload.get("target_lang", DEFAULT_TARGET_LANG)
    source_lang = payload.get("source_lang")
    thinking = payload.get("thinking", False)

    results = []
    for text in payload["texts"]:
        req = TranslateRequest(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            thinking=thinking,
        )
        try:
            r = await translate(req)
            results.append(r.translations[0])
        except HTTPException as exc:
            results.append({"error": exc.detail})
    return JSONResponse({"translations": results})


# ---------------------------------------------------------------------------
# OpenAI-compatible passthrough
# ---------------------------------------------------------------------------


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_vllm(path: str, request: Request) -> Response:
    """Transparently forward OpenAI-compatible calls to vLLM."""
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    resp = await _forward_to_vllm(
        f"/v1/{path}",
        method=request.method,
        headers=headers,
        content=body,
    )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding")
        },
        media_type=resp.headers.get("content-type", "application/json"),
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    try:
        resp = await _forward_to_vllm("/health", method="GET")
        vllm_ok = resp.status_code == 200
    except HTTPException:
        vllm_ok = False
    return {
        "status": "ok" if vllm_ok else "degraded",
        "vllm": "up" if vllm_ok else "down",
        "model": MODEL_NAME,
    }


@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "service": "apertus-translator",
        "model": MODEL_NAME,
        "endpoints": "/translate, /translate/batch, /v1/*, /health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=GATEWAY_PORT)
