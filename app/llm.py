"""Optional LLM layer: turns rule-based findings into client-friendly wording.

Guard rails:
  * the model only ever receives ONE client's findings (never raw data of others)
  * it never calculates anything - every number it may use is in the evidence
  * every sentence it returns is checked: a number or post id that isn't in the
    evidence -> that piece is thrown away and the template text is kept
  * no API key / LLM_MODE=off / hourly cap reached -> templates only

The app is fully usable without this module doing anything.
"""

import json
import logging
import os
import re
import time
from collections import deque

log = logging.getLogger(__name__)

_recent_calls = deque()

SYSTEM_PROMPT = """You write the monthly social-media report for a hotel client of a marketing agency.
You receive pre-computed findings. Each finding has an id, a draft text, a recommendation and its evidence.

Rules:
- Rewrite each finding so a hotel manager understands it in one or two short sentences.
- Use ONLY numbers that appear in that finding's evidence or draft text. Never compute new numbers,
  never round differently, never add percentages, ratios or totals of your own.
- Keep post ids exactly as given. Do not mention any other hotel.
- Recommendations must be concrete and follow from the finding.
- The summary is 2-3 sentences and may only use numbers from the totals or the findings."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": ["id", "text", "recommendation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "insights"],
    "additionalProperties": False,
}


def is_enabled():
    return os.environ.get("LLM_MODE", "auto") != "off" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _under_hourly_cap():
    cap = int(os.environ.get("LLM_MAX_REPORTS_PER_HOUR", "20"))
    cutoff = time.time() - 3600
    while _recent_calls and _recent_calls[0] < cutoff:
        _recent_calls.popleft()
    return len(_recent_calls) < cap


# ---- validation ----------------------------------------------------------

POST_ID_RE = re.compile(r"\b[A-Z]{2}-\d{4}\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _collect_numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_numbers(v, out)
            _collect_numbers_from_text(str(k), out)  # e.g. "October 2026"
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)
    elif isinstance(obj, str):
        _collect_numbers_from_text(obj, out)


def _collect_numbers_from_text(text, out):
    text = DATE_RE.sub(" ", POST_ID_RE.sub(" ", text))
    for n in NUMBER_RE.findall(text):
        out.add(float(n.replace(",", "")))


def unsupported_numbers(text, allowed):
    """Numbers in `text` that can't be traced back to `allowed`.

    A number counts as supported if some allowed value rounds to it at the
    precision it was written with (so 2.1 matches 2.13, but 2.5 doesn't).
    Small integers (<= 10) are allowed for phrasing like "2-3 posts a week".
    """
    bad = []
    clean = DATE_RE.sub(" ", POST_ID_RE.sub(" ", text))
    for raw in NUMBER_RE.findall(clean):
        value = float(raw.replace(",", ""))
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        if decimals == 0 and value <= 10:
            continue
        if not any(round(a, decimals) == value for a in allowed):
            bad.append(raw)
    return bad


def unknown_post_ids(text, allowed_ids):
    return [p for p in POST_ID_RE.findall(text) if p not in allowed_ids]


# ---- the call ------------------------------------------------------------

def _call_claude(payload):
    import anthropic

    model = os.environ.get("LLM_MODEL", "claude-opus-5-5")
    client = anthropic.Anthropic(max_retries=1, timeout=60)
    kwargs = dict(
        model=model,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
    )
    # server-side refusal fallback isn't available for Haiku models
    if not model.startswith("claude-haiku"):
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"

    response = client.beta.messages.create(**kwargs)
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"model stopped with {response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text), model


def phrase_findings(client_name, metrics, findings):
    """Returns (summary or None, {finding_id: {"text", "recommendation"}}, info dict)."""
    info = {"used": False, "model": None, "rejected": []}
    if not findings or not is_enabled():
        info["reason"] = "disabled"
        return None, {}, info
    if not _under_hourly_cap():
        info["reason"] = "hourly cap reached"
        return None, {}, info

    payload = {
        "client": client_name,
        "period": metrics["period"],
        "previous_period": metrics["previous_period"],
        "totals": metrics["totals"],
        "findings": findings,
    }
    try:
        _recent_calls.append(time.time())
        result, model = _call_claude(payload)
    except Exception as exc:  # any API/parse problem -> templates
        log.warning("LLM phrasing failed, using templates: %s", exc)
        info["reason"] = f"error: {type(exc).__name__}"
        return None, {}, info

    info.update(used=True, model=model)
    by_id = {f["id"]: f for f in findings}
    accepted = {}

    for item in result.get("insights", []):
        f = by_id.get(item.get("id"))
        if not f:
            continue
        allowed = set()
        _collect_numbers(f["evidence"], allowed)
        _collect_numbers_from_text(f["text"], allowed)
        _collect_numbers(metrics["totals"], allowed)
        combined = f"{item['text']} {item['recommendation']}"
        bad = unsupported_numbers(combined, allowed) + unknown_post_ids(combined, set(f["evidence"]["post_ids"]))
        if bad:
            info["rejected"].append({"id": f["id"], "unsupported": bad})
            continue
        accepted[f["id"]] = {"text": item["text"], "recommendation": item["recommendation"]}

    summary = result.get("summary")
    if summary:
        allowed = set()
        _collect_numbers(metrics["totals"], allowed)
        _collect_numbers(metrics["period"], allowed)
        for f in findings:
            _collect_numbers(f["evidence"], allowed)
            _collect_numbers_from_text(f["text"], allowed)
        all_ids = {p for f in findings for p in f["evidence"]["post_ids"]}
        bad = unsupported_numbers(summary, allowed) + unknown_post_ids(summary, all_ids)
        if bad:
            info["rejected"].append({"id": "summary", "unsupported": bad})
            summary = None

    return summary, accepted, info
