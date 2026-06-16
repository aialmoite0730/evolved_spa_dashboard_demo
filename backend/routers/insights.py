"""
AI Insights
===========
POST /api/insights

The frontend (AiInsights.jsx) builds the full prompt client-side (it has all
the dashboard numbers already loaded) and sends it here. This router:

  1. Hashes the prompt into a cache_key.
  2. Checks the `ai_insights_log` table in BigQuery for a recent row with that
     cache_key (within AI_INSIGHTS_CACHE_TTL_MINUTES). If found, returns it
     immediately — no AI call, no cost.
  3. On a cache miss, calls OpenAI (gpt-4o-mini) first, falling back to
     Gemini (gemini-flash-latest) if OpenAI is not configured or fails.
  4. Fire-and-forget inserts the new result into `ai_insights_log` so the
     next identical request (same tab + same numbers) is served from cache.

Requires these env vars (server-side only — never shipped to the browser):
  OPENAI_API_KEY            (optional)
  GEMINI_API_KEY            (optional — used if OPENAI_API_KEY absent or fails)
  AI_INSIGHTS_CACHE_TTL_MINUTES   (optional, default 60)

ai_insights_log schema (auto-created if missing):
  cache_key   STRING    — sha256(tab + "|" + prompt)
  tab         STRING
  view_mode   STRING
  start_date  STRING
  end_date    STRING
  locations   STRING    — JSON-encoded array
  prompt      STRING
  insight     STRING
  provider    STRING    — "openai" | "gemini"
  created_at  TIMESTAMP
  environment STRING
"""

import os
import json
import hashlib
import threading
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from google.cloud import bigquery

from config import BQ_CLIENT, PROJECT_ID, DATASET, INSIGHTS_TABLE, FULL_INSIGHTS, PLAIN_INSIGHTS
from utils.errors import log_and_raise_from_request

router = APIRouter()

_ENV = os.getenv("APP_ENV", "production")


# ─── AI provider config ────────────────────────────────────────────────────────
OPENAI_URL   = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

CACHE_TTL_MINUTES = int(os.getenv("AI_INSIGHTS_CACHE_TTL_MINUTES", "60"))

AI_TIMEOUT_SECONDS = 30.0

# ─── Debug logging ──────────────────────────────────────────────────────────────
# Prints diagnostics for every /api/insights call. Set AI_INSIGHTS_DEBUG=0 to
# silence (it's on by default since this endpoint is easy to misconfigure —
# missing/invalid API keys, BQ permission issues, etc.).
DEBUG = os.getenv("AI_INSIGHTS_DEBUG", "1") != "0"


def _debug(msg: str) -> None:
    if DEBUG:
        print(f"🔍 [insights] {msg}")


_debug(
    f"startup — OPENAI_API_KEY={'set (' + OPENAI_API_KEY[:4] + '...)' if OPENAI_API_KEY else 'NOT SET'}, "
    f"GEMINI_API_KEY={'set (' + GEMINI_API_KEY[:4] + '...)' if GEMINI_API_KEY else 'NOT SET'}, "
    f"cache_table={FULL_INSIGHTS}, ttl={CACHE_TTL_MINUTES}min"
)


# ─── BigQuery schema for the insights cache table ──────────────────────────────
_INSIGHTS_SCHEMA = [
    bigquery.SchemaField("cache_key",   "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("tab",         "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("view_mode",   "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("start_date",  "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("end_date",    "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("locations",   "STRING",    mode="NULLABLE"),
    # bigquery.SchemaField("prompt",      "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("insight",     "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("provider",    "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",  "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("environment", "STRING",    mode="NULLABLE"),
]


def _ensure_insights_table() -> None:
    """Create the AI insights cache table if it doesn't already exist."""
    dataset_ref = BQ_CLIENT.dataset(DATASET, project=PROJECT_ID)
    table_ref   = dataset_ref.table(INSIGHTS_TABLE)
    try:
        BQ_CLIENT.get_table(table_ref)
    except Exception:
        table = bigquery.Table(table_ref, schema=_INSIGHTS_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="created_at",
        )
        table.clustering_fields = ["cache_key"]
        try:
            BQ_CLIENT.create_table(table)
            print(f"✅ Created AI insights cache table: {FULL_INSIGHTS}")
        except Exception as create_exc:
            print(f"⚠️  Could not create AI insights cache table: {create_exc}")


# Run table check once at import time (fast — just a get_table call)
_ensure_insights_table()


# ─── Request / response models ─────────────────────────────────────────────────
class InsightRequest(BaseModel):
    tab:        str
    prompt:     str
    view_mode:  Optional[str] = None
    start_date: Optional[str] = None
    end_date:   Optional[str] = None
    locations:  List[str] = Field(default_factory=list)


# ─── Cache helpers ──────────────────────────────────────────────────────────────
def _cache_key(tab: str, prompt: str) -> str:
    """Identical tab + prompt → identical numbers → safe to reuse the response."""
    raw = f"{tab}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cached(cache_key: str) -> Optional[dict]:
    """Return the most recent cached insight for this key, if still within TTL."""
    query = f"""
        SELECT insight, provider, created_at
        FROM `{FULL_INSIGHTS}`
        WHERE cache_key = @cache_key
          AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @ttl_minutes MINUTE)
        ORDER BY created_at DESC
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("cache_key", "STRING", cache_key),
            bigquery.ScalarQueryParameter("ttl_minutes", "INT64", CACHE_TTL_MINUTES),
        ]
    )
    try:
        rows = list(BQ_CLIENT.query(query, job_config=job_config).result())
    except Exception as exc:
        # Cache lookup failures shouldn't break insight generation — log and
        # fall through to a cache miss.
        _debug(f"cache lookup FAILED ({exc!r}) — treating as cache miss")
        return None

    if not rows:
        _debug(f"cache MISS for {cache_key[:12]}...")
        return None

    row = rows[0]
    _debug(f"cache HIT for {cache_key[:12]}... (provider={row.provider}, created_at={row.created_at})")
    return {"insight": row.insight, "provider": row.provider}


def _insert_insight_row(row: dict) -> None:
    """Insert a single insight row into BigQuery. Runs in a daemon thread."""
    try:
        errors = BQ_CLIENT.insert_rows_json(PLAIN_INSIGHTS, [row])
        if errors:
            print(f"⚠️  AI insights cache insert failed: {errors}")
        else:
            _debug(f"cached insight saved (cache_key={row['cache_key'][:12]}..., provider={row['provider']})")
    except Exception as exc:
        print(f"⚠️  Could not write to AI insights cache: {exc}")


def _save_insight(payload: InsightRequest, cache_key: str, insight: str, provider: str) -> None:
    row = {
        "cache_key":   cache_key,
        "tab":         payload.tab,
        "view_mode":   payload.view_mode,
        "start_date":  payload.start_date,
        "end_date":    payload.end_date,
        "locations":   json.dumps(payload.locations or []),
        "prompt":      payload.prompt,
        "insight":     insight,
        "provider":    provider,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "environment": _ENV,
    }
    thread = threading.Thread(target=_insert_insight_row, args=(row,), daemon=True)
    thread.start()


# ─── AI provider calls ──────────────────────────────────────────────────────────
async def _call_openai(prompt: str) -> str:
    _debug(f"calling OpenAI ({OPENAI_MODEL}) — prompt length={len(prompt)} chars")
    async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
        res = await client.post(
            OPENAI_URL,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 600,
            },
        )

    _debug(f"OpenAI responded with HTTP {res.status_code}")

    if res.status_code != 200:
        try:
            err = res.json()
        except Exception:
            err = {}
        _debug(f"OpenAI error body: {err}")
        if res.status_code == 429:
            raise RuntimeError("OpenAI rate limit reached.")
        raise RuntimeError(err.get("error", {}).get("message") or f"OpenAI HTTP {res.status_code}")

    data = res.json()
    text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    _debug(f"OpenAI returned {len(text)} chars")
    return text


async def _call_gemini(prompt: str) -> str:
    _debug(f"calling Gemini (fallback) — prompt length={len(prompt)} chars")
    async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
        res = await client.post(
            GEMINI_URL,
            headers={
                "Content-Type":  "application/json",
                "X-goog-api-key": GEMINI_API_KEY,
            },
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600},
            },
        )

    _debug(f"Gemini responded with HTTP {res.status_code}")

    if res.status_code != 200:
        try:
            err = res.json()
        except Exception:
            err = {}
        _debug(f"Gemini error body: {err}")
        if res.status_code == 429:
            raise RuntimeError("Gemini rate limit reached.")
        raise RuntimeError(err.get("error", {}).get("message") or f"Gemini HTTP {res.status_code}")

    data = res.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
    text = (parts[0].get("text") or "").strip()
    _debug(f"Gemini returned {len(text)} chars")
    return text


# ─── Route ────────────────────────────────────────────────────────────────────
@router.post("/api/insights", tags=["AI Insights"])
async def get_insight(payload: InsightRequest, request: Request):
    """
    Returns: { "insight": str, "provider": "openai"|"gemini", "cached": bool }
    """
    try:
        _debug(
            f"request received — tab={payload.tab}, view_mode={payload.view_mode}, "
            f"dates={payload.start_date}..{payload.end_date}, "
            f"locations={payload.locations}, prompt_length={len(payload.prompt)}"
        )

        cache_key = _cache_key(payload.tab, payload.prompt)
        _debug(f"cache_key={cache_key[:12]}...")

        cached = _get_cached(cache_key)
        if cached:
            _debug(f"returning cached result (provider={cached.get('provider')})")
            return {**cached, "cached": True}

        if not OPENAI_API_KEY and not GEMINI_API_KEY:
            raise RuntimeError("No AI provider configured on the server "
                                "(set OPENAI_API_KEY and/or GEMINI_API_KEY).")

        text     = ""
        provider = None
        last_err = None

        # OpenAI is the primary provider — always tried first if configured.
        if OPENAI_API_KEY:
            try:
                text = await _call_openai(payload.prompt)
                provider = "openai"
            except Exception as exc:
                _debug(f"OpenAI FAILED: {exc!r}")
                last_err = exc
        else:
            _debug("OPENAI_API_KEY not set — skipping primary provider")

        # Gemini is only used as a fallback if OpenAI is unconfigured or failed.
        if not text and GEMINI_API_KEY:
            try:
                text = await _call_gemini(payload.prompt)
                provider = "gemini"
                last_err = None  # Gemini succeeded — clear the OpenAI error
            except Exception as exc:
                _debug(f"Gemini FAILED: {exc!r}")
                last_err = exc
        elif not text:
            _debug("GEMINI_API_KEY not set — no fallback available")

        if not text:
            _debug(f"both providers failed/unavailable — raising: {last_err!r}")
            raise last_err or RuntimeError("AI provider returned an empty response.")

        _debug(f"success via {provider} — insight length={len(text)} chars")
        _save_insight(payload, cache_key, text, provider)

        return {"insight": text, "provider": provider, "cached": False}

    except Exception as exc:
        _debug(f"request FAILED: {exc!r}")
        log_and_raise_from_request(exc, request)