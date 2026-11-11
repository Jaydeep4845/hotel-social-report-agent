from app.metrics import build_metrics


def post(pid, day, platform="instagram", fmt="reel", reach=1000, likes=0, comments=0, shares=0, saves=0, clicks=0):
    return {
        "post_id": pid, "date": day, "platform": platform, "format": fmt, "topic": "rooms",
        "impressions": reach, "reach": reach, "likes": likes, "comments": comments,
        "shares": shares, "saves": saves, "link_clicks": clicks,
    }


def test_engagement_rate_is_reach_weighted_and_compared_to_previous_month():
    posts = [
        post("P1", "2026-09-10", reach=1000, likes=50),                     # Sep: 50 / 1000 = 5%
        post("P2", "2026-10-05", reach=1000, likes=60, comments=10),        # Oct: 70
        post("P3", "2026-10-20", reach=3000, likes=20, shares=5, saves=5),  # Oct: 30
    ]
    m = build_metrics(posts)

    assert m["period"] == "2026-10"
    assert m["previous_period"] == "2026-09"
    assert m["totals"]["engagements"] == 100
    assert m["totals"]["reach"] == 4000
    assert m["totals"]["engagement_rate"] == 2.5          # 100 / 4000, not avg(7%, 1%)
    assert m["change_pct"]["engagement_rate"] == -50.0    # 5% -> 2.5%


def test_breakdown_keeps_post_ids_for_evidence():
    posts = [
        post("R1", "2026-10-01", fmt="reel", likes=100),
        post("F1", "2026-10-02", fmt="photo", likes=20),
    ]
    m = build_metrics(posts)
    by_format = {r["format"]: r for r in m["by_format"]}
    assert by_format["reel"]["post_ids"] == ["R1"]
    assert by_format["reel"]["engagement_rate"] == 10.0
    assert m["top_posts"][0]["post_id"] == "R1"
