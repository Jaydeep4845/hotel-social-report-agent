"""CSV import + validation. A file is imported completely or not at all."""

import csv
import io
from datetime import date

from app.db import POST_COLUMNS

PLATFORMS = {"instagram", "facebook", "tiktok"}
INT_COLUMNS = ["impressions", "reach", "likes", "comments", "shares", "saves", "link_clicks"]
MAX_ROWS = 5000


def parse_csv(raw_bytes):
    """Returns (rows, errors). If errors is non-empty nothing should be saved."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["File is not UTF-8 text"]

    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in POST_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}"]

    rows, errors, seen = [], [], set()
    for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
        if line_no > MAX_ROWS + 1:
            errors.append(f"Too many rows (max {MAX_ROWS})")
            break
        row, problems = {}, []

        post_id = (raw.get("post_id") or "").strip()
        if not post_id:
            problems.append("post_id is empty")
        elif post_id in seen:
            problems.append(f"duplicate post_id {post_id}")
        seen.add(post_id)
        row["post_id"] = post_id

        try:
            row["date"] = date.fromisoformat((raw.get("date") or "").strip()).isoformat()
        except ValueError:
            problems.append("date must be YYYY-MM-DD")

        platform = (raw.get("platform") or "").strip().lower()
        if platform not in PLATFORMS:
            problems.append(f"unknown platform '{platform}'")
        row["platform"] = platform
        row["format"] = (raw.get("format") or "").strip().lower() or "unknown"
        row["topic"] = (raw.get("topic") or "").strip().lower() or "other"

        for col in INT_COLUMNS:
            try:
                value = int(float(raw.get(col) or ""))
                if value < 0:
                    raise ValueError
                row[col] = value
            except ValueError:
                problems.append(f"{col} must be a non-negative number")

        if not problems and row["reach"] == 0:
            problems.append("reach is 0")

        if problems:
            errors.append(f"line {line_no}: " + "; ".join(problems))
        else:
            rows.append(row)

    if not rows and not errors:
        errors.append("File has no data rows")
    return rows, errors[:20]
