"""Generate synthetic social-media data for two fictional hotels.

Everything here is made up. Each hotel gets a slightly different "story"
baked in, so the generated reports should come out clearly different:

  * Atlas Riad Marrakech - Reels do roughly 2x better than photos, local-culture
    posts lead, reach grows month over month.
  * Blue Coast Resort Agadir - engagement drops in October, TikTok is barely
    used but performs best per post, beach/pool content is the strongest topic.

Run:  python scripts/generate_data.py
"""

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MONTHS = [(2026, 9), (2026, 10)]

COLUMNS = [
    "post_id", "date", "platform", "format", "topic",
    "impressions", "reach", "likes", "comments", "shares", "saves", "link_clicks",
]

FORMATS_BY_PLATFORM = {
    "instagram": ["reel", "photo", "carousel"],
    "facebook": ["photo", "video", "carousel"],
    "tiktok": ["video"],
}

BASE_REACH = {"instagram": 4200, "facebook": 2600, "tiktok": 5200}

PROFILES = {
    "atlas-marrakech": {
        "name": "Atlas Riad Marrakech",
        "city": "Marrakech",
        "prefix": "AM",
        "posts_per_month": 30,
        "platform_weights": {"instagram": 0.55, "facebook": 0.30, "tiktok": 0.15},
        "format_er": {"reel": 0.078, "photo": 0.034, "carousel": 0.052, "video": 0.058},
        "platform_er": {"instagram": 1.0, "facebook": 0.8, "tiktok": 1.05},
        "topics": {"local_culture": 1.35, "food": 1.15, "rooms": 0.9, "pool": 1.0, "spa": 0.95},
        "best_weekday": 4,  # Friday
        "month_reach": {9: 1.0, 10: 1.18},
        "month_er": {9: 1.0, 10: 1.06},
        "click_rate": 0.008,
        "month_clicks": {9: 1.0, 10: 1.1},
    },
    "blue-coast-agadir": {
        "name": "Blue Coast Resort Agadir",
        "city": "Agadir",
        "prefix": "BC",
        "posts_per_month": 28,
        "platform_weights": {"instagram": 0.50, "facebook": 0.42, "tiktok": 0.08},
        "format_er": {"reel": 0.055, "photo": 0.040, "carousel": 0.058, "video": 0.050},
        "platform_er": {"instagram": 1.0, "facebook": 0.85, "tiktok": 1.7},
        "topics": {"beach_pool": 1.35, "dining": 1.0, "rooms": 0.85, "events": 0.9, "family": 1.05},
        "best_weekday": 6,  # Sunday
        "month_reach": {9: 1.0, 10: 0.93},
        "month_er": {9: 1.0, 10: 0.74},
        "click_rate": 0.009,
        "month_clicks": {9: 1.0, 10: 0.7},
    },
}


def month_days(year, month):
    d = date(year, month, 1)
    while d.month == month:
        yield d
        d += timedelta(days=1)


def make_posts(client_id, profile, rng):
    rows = []
    counter = 1
    platforms = list(profile["platform_weights"])
    weights = list(profile["platform_weights"].values())
    topics = list(profile["topics"])

    for year, month in MONTHS:
        days = list(month_days(year, month))
        for _ in range(profile["posts_per_month"]):
            day = rng.choice(days)
            platform = rng.choices(platforms, weights)[0]
            fmt = rng.choice(FORMATS_BY_PLATFORM[platform])
            topic = rng.choice(topics)

            reach = BASE_REACH[platform] * profile["month_reach"][month] * rng.lognormvariate(0, 0.25)
            er = (
                profile["format_er"][fmt]
                * profile["platform_er"][platform]
                * profile["topics"][topic]
                * profile["month_er"][month]
                * (1.25 if day.weekday() == profile["best_weekday"] else 1.0)
                * rng.uniform(0.85, 1.15)
            )
            engagements = reach * er

            rows.append({
                "post_id": f"{profile['prefix']}-{counter:04d}",
                "date": day.isoformat(),
                "platform": platform,
                "format": fmt,
                "topic": topic,
                "impressions": round(reach * rng.uniform(1.2, 1.6)),
                "reach": round(reach),
                "likes": round(engagements * 0.70),
                "comments": round(engagements * 0.06),
                "shares": round(engagements * 0.09),
                "saves": round(engagements * 0.15),
                "link_clicks": round(
                    reach * profile["click_rate"] * profile["month_clicks"][month] * rng.uniform(0.7, 1.3)
                ),
            })
            counter += 1

    rows.sort(key=lambda r: (r["date"], r["post_id"]))
    return rows


def main():
    DATA_DIR.mkdir(exist_ok=True)
    rng = random.Random(42)  # fixed seed -> same data every run
    clients = []

    for client_id, profile in PROFILES.items():
        rows = make_posts(client_id, profile, rng)
        out = DATA_DIR / f"{client_id}.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        clients.append({"id": client_id, "name": profile["name"], "city": profile["city"]})
        print(f"wrote {len(rows)} posts -> {out.relative_to(DATA_DIR.parent)}")

    (DATA_DIR / "clients.json").write_text(json.dumps(clients, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
