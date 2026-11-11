"""Export approved reports as Markdown, CSV or JSON."""

import csv
import io
import json


def _pct(v):
    return "n/a" if v is None else f"{v:+}%"


def to_markdown(report, audit):
    p = report["payload"]
    t, chg = p["metrics"]["totals"], p["metrics"]["change_pct"]
    lines = [
        f"# {p['client']['name']} - Social Media Report, {p['period_label']}",
        "",
        f"*Status: **{report['status'].upper()}** by {report['reviewer']} on {report['reviewed_at']}*",
        "",
        "## Summary",
        "",
        p["summary"],
        "",
        "## Key numbers",
        "",
        "| Metric | Value | vs previous month |",
        "|---|---:|---:|",
        f"| Posts | {t['posts']} | {_pct(chg.get('posts'))} |",
        f"| Reach | {t['reach']:,} | {_pct(chg.get('reach'))} |",
        f"| Impressions | {t['impressions']:,} | {_pct(chg.get('impressions'))} |",
        f"| Engagements | {t['engagements']:,} | {_pct(chg.get('engagements'))} |",
        f"| Engagement rate | {t['engagement_rate']}% | {_pct(chg.get('engagement_rate'))} |",
        f"| Link clicks | {t['link_clicks']:,} | {_pct(chg.get('link_clicks'))} |",
        "",
        "## Insights",
        "",
    ]
    for i, ins in enumerate(p["insights"], start=1):
        ev = ins["evidence"]
        values = ", ".join(f"{k}: {v}" for k, v in ev["values"].items())
        sample = ", ".join(f"{k}: {v} posts" for k, v in ev["sample"].items())
        lines += [
            f"### {i}. {ins['title']}",
            "",
            ins["text"],
            "",
            f"**Recommendation:** {ins['recommendation']}",
            "",
            f"<sub>Evidence - {ev['metric']}: {values}"
            + (f" | sample: {sample}" if sample else "")
            + (f" | posts: {', '.join(ev['post_ids'][:10])}" if ev["post_ids"] else "")
            + "</sub>",
            "",
        ]
    lines += ["## Review history", ""]
    for a in audit:
        lines.append(f"- {a['at']} - {a['action']} by {a['actor']}" + (f": {a['note']}" if a["note"] else ""))
    lines += ["", "---", "*Generated from synthetic data. Engagement rate = (likes+comments+shares+saves) / reach.*"]
    return "\n".join(lines)


def to_csv(report):
    p = report["payload"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["client", "period", "section", "item", "value", "change_vs_previous_pct", "evidence"])
    t, chg = p["metrics"]["totals"], p["metrics"]["change_pct"]
    for k, v in t.items():
        w.writerow([p["client"]["name"], p["period"], "kpi", k, v, chg.get(k, ""), ""])
    for ins in p["insights"]:
        w.writerow([
            p["client"]["name"], p["period"], "insight", ins["title"], ins["text"], "",
            json.dumps(ins["evidence"]),
        ])
    return buf.getvalue()


def to_json(report, audit):
    return json.dumps({**report, "audit": audit}, indent=2)
