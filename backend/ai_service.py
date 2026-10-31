"""LLM diagnosis service — OpenAI or Anthropic via HTTP, JSON-only output."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

DIAGNOSIS_SCHEMA = {
    "root_cause": "string",
    "confidence": "string",
    "evidence": "string",
    "next_command": "string",
    "fix_steps": "string",
    "osi_layer": "string",
}

SYSTEM_PROMPT = """You are NetSage AI, a senior Cisco networking engineer.
Analyze the human-reported symptom and the Cisco IOS 'show' command output.
Return ONLY a single JSON object. No markdown, no code fences, no prose outside JSON.

The JSON MUST match this schema exactly:
{
  "root_cause": "string",
  "confidence": "string",
  "evidence": "string",
  "next_command": "string",
  "fix_steps": "string",
  "osi_layer": "string"
}

Rules:
- root_cause: concise diagnosis
- confidence: one of High, Medium, Low
- evidence: quote or paraphrase the specific lines that support the diagnosis
- next_command: the single most useful next Cisco show/debug command
- fix_steps: numbered operational steps a human can apply
- osi_layer: one of Layer 1, Layer 2, Layer 3, Layer 4, Layer 7, Multiple
If the output is insufficient, still fill every field; set confidence to Low and say what is missing in evidence.
"""


def _empty_diagnosis(reason: str) -> dict[str, str]:
    return {
        "root_cause": reason,
        "confidence": "Low",
        "evidence": "LLM response could not be parsed as JSON.",
        "next_command": "show ip interface brief",
        "fix_steps": "Re-run diagnosis after verifying API keys and show output.",
        "osi_layer": "Multiple",
    }


def _extract_json(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return _empty_diagnosis("Unparseable model output")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return _empty_diagnosis("Unparseable model output")
    out: dict[str, str] = {}
    for key in DIAGNOSIS_SCHEMA:
        val = data.get(key, "")
        out[key] = val if isinstance(val, str) else json.dumps(val)
    return out


async def _openai_complete(user_content: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key or api_key.startswith("sk-your-"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload["choices"][0]["message"]["content"]


async def _anthropic_complete(user_content: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        parts = payload.get("content") or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


async def diagnose(symptom: str, show_output: str) -> dict[str, Any]:
    user_content = (
        f"Symptom:\n{symptom.strip()}\n\n"
        f"Show command output:\n{show_output.strip()}"
    )
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    try:
        if provider == "anthropic":
            raw = await _anthropic_complete(user_content)
        else:
            raw = await _openai_complete(user_content)
        parsed = _extract_json(raw)
        return {"provider": provider, "ok": True, "diagnosis": parsed, "error": None}
    except Exception as exc:  # noqa: BLE001 — surface API errors to the UI
        fallback = _empty_diagnosis(f"AI service error: {exc}")
        return {
            "provider": provider,
            "ok": False,
            "diagnosis": fallback,
            "error": str(exc),
        }
