"""Rule-based findings.

Each finding carries its own evidence (the exact numbers, sample sizes and
post ids it is based on). The template text is the safe default; the LLM may
rephrase it later, but it can only use numbers that appear in the evidence.

Rules only fire when there's enough data behind them (MIN_POSTS) and the gap
is big enough to matter - no insight is better than a weak one.
"""

import calendar

MIN_POSTS = 3


def month_name(period):
    if not period:
        return None
    year, month = period.split("-")
    return f"{calendar.month_name[int(month)]} {year}"


DISPLAY_NAMES = {
    "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook",
    "beach_pool": "beach & pool", "local_culture": "local culture",
}


def pretty(label):
    return DISPLAY_NAMES.get(label, label.replace("_", " "))


def article(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


def finding(fid, title, text, recommendation, metric, values, sample=None, post_ids=None):
    return {
        "id": fid,
        "title": title,
        "text": text,
        "recommendation": recommendation,
        "evidence": {
            "metric": metric,
            "values": values,
            "sample": sample or {},
            "post_ids": post_ids or [],
        },
    }


def trend_findings(m):
    out = []
    if not m["previous_totals"]:
        return out
    cur, prev, chg = m["totals"], m["previous_totals"], m["change_pct"]
    now_m, prev_m = month_name(m["period"]), month_name(m["previous_period"])

    c = chg["engagement_rate"]
    if c is not None and abs(c) >= 5:
        direction = "rose" if c > 0 else "fell"
        out.append(finding(
            "engagement_trend",
            f"Engagement rate {direction} {abs(c)}% month over month",
            f"Engagement rate {direction} from {prev['engagement_rate']}% in {prev_m} "
            f"to {cur['engagement_rate']}% in {now_m} ({c:+}%).",
            "Keep doing what drove the lift." if c > 0
            else "Review the formats and topics used this month against last month's best performers.",
            "engagement_rate (%)",
            {prev_m: prev["engagement_rate"], now_m: cur["engagement_rate"], "change_pct": c},
            {prev_m: prev["posts"], now_m: cur["posts"]},
        ))

    c = chg["reach"]
    if c is not None and abs(c) >= 5:
        direction = "grew" if c > 0 else "dropped"
        out.append(finding(
            "reach_trend",
            f"Reach {direction} {abs(c)}%",
            f"Total reach {direction} from {prev['reach']:,} in {prev_m} to {cur['reach']:,} in {now_m} ({c:+}%).",
            "Boost the top posts to keep growing reach." if c > 0
            else "Consider a small paid boost on the best-performing posts to recover reach.",
            "reach",
            {prev_m: prev["reach"], now_m: cur["reach"], "change_pct": c},
            {prev_m: prev["posts"], now_m: cur["posts"]},
        ))

    c = chg["link_clicks"]
    if c is not None and abs(c) >= 10:
        direction = "increased" if c > 0 else "decreased"
        out.append(finding(
            "clicks_trend",
            f"Link clicks {direction} {abs(c)}%",
            f"Link clicks {direction} from {prev['link_clicks']:,} in {prev_m} to {cur['link_clicks']:,} in {now_m} ({c:+}%).",
            "Keep the booking link in captions of the top formats." if c > 0
            else "Add a clear booking call-to-action and link to more posts.",
            "link_clicks",
            {prev_m: prev["link_clicks"], now_m: cur["link_clicks"], "change_pct": c},
            {prev_m: prev["posts"], now_m: cur["posts"]},
        ))
    return out


def format_finding(m):
    rows = [r for r in m["by_format"] if r["posts"] >= MIN_POSTS]
    if len(rows) < 2:
        return []
    best, worst = rows[0], rows[-1]
    if not worst["engagement_rate"]:
        return []
    ratio = round(best["engagement_rate"] / worst["engagement_rate"], 1)
    if ratio < 1.3:
        return []
    b, w = pretty(best["format"]), pretty(worst["format"])
    return [finding(
        "format_gap",
        f"{b.capitalize()}s outperform {w}s {ratio}x",
        f"{b.capitalize()}s averaged a {best['engagement_rate']}% engagement rate across {best['posts']} posts, "
        f"versus {worst['engagement_rate']}% for {w}s ({worst['posts']} posts) - {ratio}x higher.",
        f"Shift part of the {w} budget towards {b}s next month.",
        "engagement_rate (%) by format",
        {b: best["engagement_rate"], w: worst["engagement_rate"], "ratio": ratio},
        {b: best["posts"], w: worst["posts"]},
        best["post_ids"],
    )]


def platform_finding(m):
    rows = [r for r in m["by_platform"] if r["posts"] >= 2]
    if len(rows) < 2:
        return []
    total_posts = m["totals"]["posts"]
    best = rows[0]
    share = round(best["posts"] / total_posts * 100, 1)
    others = [r for r in rows[1:]]
    avg_others = round(sum(r["engagement_rate"] for r in others) / len(others), 2)
    name = pretty(best["platform"])

    if share < 20:
        return [finding(
            "platform_opportunity",
            f"{name} is under-used but performs best",
            f"{name} had the highest engagement rate ({best['engagement_rate']}%) but only "
            f"{best['posts']} of {total_posts} posts ({share}%) went there. "
            f"Other platforms averaged {avg_others}%.",
            f"Test 2-3 extra {name} posts per week next month.",
            "engagement_rate (%) by platform",
            {name: best["engagement_rate"], "other platforms avg": avg_others, "share_of_posts_pct": share},
            {name: best["posts"], "all platforms": total_posts},
            best["post_ids"],
        )]
    return [finding(
        "platform_leader",
        f"{name} is the strongest platform",
        f"{name} led with a {best['engagement_rate']}% engagement rate over {best['posts']} posts "
        f"(other platforms averaged {avg_others}%).",
        f"Keep {name} as the main channel.",
        "engagement_rate (%) by platform",
        {name: best["engagement_rate"], "other platforms avg": avg_others},
        {name: best["posts"]},
        best["post_ids"],
    )]


def topic_finding(m):
    rows = [r for r in m["by_topic"] if r["posts"] >= MIN_POSTS]
    if not rows:
        return []
    best = rows[0]
    overall = m["totals"]["engagement_rate"]
    if best["engagement_rate"] < overall * 1.15:
        return []
    t = pretty(best["topic"])
    return [finding(
        "best_topic",
        f"'{t.capitalize()}' content resonates most",
        f"Posts about {t} averaged {best['engagement_rate']}% engagement ({best['posts']} posts), "
        f"above the account average of {overall}%.",
        f"Plan more {t} stories in next month's calendar.",
        "engagement_rate (%) by topic",
        {t: best["engagement_rate"], "account average": overall},
        {t: best["posts"]},
        best["post_ids"],
    )]


def weekday_finding(m):
    rows = [r for r in m["by_weekday"] if r["posts"] >= MIN_POSTS]
    if not rows:
        return []
    best = rows[0]
    overall = m["totals"]["engagement_rate"]
    if best["engagement_rate"] < overall * 1.15:
        return []
    return [finding(
        "best_weekday",
        f"{best['weekday']} posts perform best",
        f"{best['weekday']} posts averaged {best['engagement_rate']}% engagement ({best['posts']} posts) "
        f"against {overall}% overall.",
        f"Schedule the most important posts on {best['weekday']}s.",
        "engagement_rate (%) by weekday",
        {best["weekday"]: best["engagement_rate"], "overall": overall},
        {best["weekday"]: best["posts"]},
        best["post_ids"],
    )]


def top_post_finding(m):
    p = m["top_posts"][0]
    return [finding(
        "top_post",
        f"Top post: {p['post_id']}",
        f"The best post of the month was {p['post_id']}, {article(pretty(p['platform']))} {pretty(p['platform'])} {pretty(p['format'])} about "
        f"{pretty(p['topic'])} on {p['date']}, with a {p['engagement_rate']}% engagement rate "
        f"({p['engagements']:,} engagements from {p['reach']:,} reach).",
        "Reuse this post's angle in a new piece of content.",
        "single post",
        {"engagement_rate": p["engagement_rate"], "engagements": p["engagements"], "reach": p["reach"]},
        {},
        [p["post_id"]],
    )]


def build_findings(m):
    return (
        trend_findings(m)
        + format_finding(m)
        + platform_finding(m)
        + topic_finding(m)
        + weekday_finding(m)
        + top_post_finding(m)
    )


def template_summary(client_name, m, findings):
    t = m["totals"]
    period = month_name(m["period"])
    lines = [
        f"In {period}, {client_name} published {t['posts']} posts reaching {t['reach']:,} people, "
        f"with an overall engagement rate of {t['engagement_rate']}%."
    ]
    if findings:
        lines.append("Key points: " + "; ".join(f["title"] for f in findings[:3]) + ".")
    return " ".join(lines)
