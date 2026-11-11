"""KPI calculations. Pure pandas, no AI involved.

Definitions (kept simple and written down so a reviewer can check them):
  engagements      = likes + comments + shares + saves
  engagement rate  = sum(engagements) / sum(reach) * 100   (reach-weighted, in %)
  change %         = (current - previous) / previous * 100

The report period is the latest calendar month in the data; it's compared
with the month before it.
"""

import pandas as pd

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def to_frame(posts):
    df = pd.DataFrame(posts)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["weekday"] = df["date"].dt.day_of_week.map(lambda i: WEEKDAYS[i])
    df["engagements"] = df[["likes", "comments", "shares", "saves"]].sum(axis=1)
    return df


def engagement_rate(df):
    reach = df["reach"].sum()
    return round(df["engagements"].sum() / reach * 100, 2) if reach else 0.0


def pct_change(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def totals(df):
    return {
        "posts": int(len(df)),
        "impressions": int(df["impressions"].sum()),
        "reach": int(df["reach"].sum()),
        "engagements": int(df["engagements"].sum()),
        "engagement_rate": engagement_rate(df),
        "link_clicks": int(df["link_clicks"].sum()),
    }


def breakdown(df, column):
    out = []
    for key, group in df.groupby(column):
        out.append({
            column: key,
            "posts": int(len(group)),
            "reach": int(group["reach"].sum()),
            "engagements": int(group["engagements"].sum()),
            "engagement_rate": engagement_rate(group),
            "post_ids": sorted(group["post_id"].tolist()),
        })
    return sorted(out, key=lambda r: r["engagement_rate"], reverse=True)


def post_summary(row):
    return {
        "post_id": row["post_id"],
        "date": row["date"].strftime("%Y-%m-%d"),
        "platform": row["platform"],
        "format": row["format"],
        "topic": row["topic"],
        "reach": int(row["reach"]),
        "engagements": int(row["engagements"]),
        "engagement_rate": round(row["engagements"] / row["reach"] * 100, 2) if row["reach"] else 0.0,
    }


def build_metrics(posts):
    df = to_frame(posts)
    if df.empty:
        raise ValueError("no posts imported for this client yet")

    months = sorted(df["month"].unique())
    period = months[-1]
    previous = months[-2] if len(months) > 1 else None

    cur = df[df["month"] == period]
    prev = df[df["month"] == previous] if previous else df.iloc[0:0]

    cur_totals = totals(cur)
    prev_totals = totals(prev) if previous else None
    changes = {}
    if prev_totals:
        changes = {k: pct_change(cur_totals[k], prev_totals[k]) for k in cur_totals}

    ranked = cur.assign(er=cur["engagements"] / cur["reach"]).sort_values("er", ascending=False)

    return {
        "period": period,
        "previous_period": previous,
        "totals": cur_totals,
        "previous_totals": prev_totals,
        "change_pct": changes,
        "by_platform": breakdown(cur, "platform"),
        "by_format": breakdown(cur, "format"),
        "by_topic": breakdown(cur, "topic"),
        "by_weekday": breakdown(cur, "weekday"),
        "top_posts": [post_summary(r) for _, r in ranked.head(3).iterrows()],
        "weakest_post": post_summary(ranked.iloc[-1]),
    }
