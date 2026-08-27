#!/usr/bin/env python3
"""
rerun_6.py — 只重跑6个失败账号，成功的40个直接用缓存

运行：
  python rerun_6.py
"""
import asyncio, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_50")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 40个已成功的账号（直接用，不重跑） ────────────────────────────────────────
DONE = [
    {"handle": "huggingface",      "platform": "newsletter", "category": "ai_ml",       "distortion_index": 18, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 30.0, "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "dhh",              "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 9},
    {"handle": "ruanyifeng",       "platform": "newsletter", "category": "tech_cn",     "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 6},
    {"handle": "astralcodexten",   "platform": "newsletter", "category": "rationalism", "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "swyx",             "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "martinfowler",     "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 23},
    {"handle": "stratechery",      "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "timferriss",       "platform": "newsletter", "category": "lifestyle",   "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "openai-news",      "platform": "newsletter", "category": "ai_ml",       "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "deepmind",         "platform": "newsletter", "category": "ai_ml",       "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "financialsamurai", "platform": "newsletter", "category": "finance",     "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 7},
    {"handle": "notboring",        "platform": "newsletter", "category": "finance",     "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "peterattiamd",     "platform": "newsletter", "category": "health",      "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 24},
    {"handle": "clevergirlfinance","platform": "newsletter", "category": "finance",     "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 6},
    {"handle": "simonwillison",    "platform": "newsletter", "category": "tech",        "distortion_index": 14, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 3.3, "temporal_distortion": 3.3,  "consistency_score": 86.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "latentspace",      "platform": "newsletter", "category": "ai_ml",       "distortion_index": 14, "significance_inflation": 5.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 5.0,  "consistency_score": 79.8,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "fireship",         "platform": "youtube",    "category": "tech_edu",    "distortion_index": 11, "significance_inflation": 5.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 5.0, "temporal_distortion": 10.0, "consistency_score": 50.0,  "deletion_rate": 4.8, "deleted_count": 1, "total_posts": 20},
    {"handle": "pragmaticengineer","platform": "newsletter", "category": "tech",        "distortion_index": 10, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 5.0,  "consistency_score": 64.6,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "zdnet",            "platform": "newsletter", "category": "tech_media",  "distortion_index": 10, "significance_inflation": 0.0,  "anxiety_manufacturing": 5.0, "novelty_claims": 0.0, "temporal_distortion": 10.0, "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "mit-tech-review",  "platform": "newsletter", "category": "tech_media",  "distortion_index": 10, "significance_inflation": 10.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "lexfridman",       "platform": "youtube",    "category": "ai_ml",       "distortion_index": 9,  "significance_inflation": 5.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "lesswrong",        "platform": "newsletter", "category": "rationalism", "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "ycombinator",      "platform": "youtube",    "category": "startup",     "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "aiexplained",      "platform": "youtube",    "category": "ai_ml",       "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 5.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "overreacted",      "platform": "newsletter", "category": "tech",        "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 1},
    {"handle": "sspai",            "platform": "newsletter", "category": "tech_cn",     "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "techcrunch",       "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "theverge",         "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "wired-ai",         "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "arstechnica",      "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "thenextweb",       "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "venturebeat",      "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 7},
    {"handle": "hackernews",       "platform": "newsletter", "category": "tech_media",  "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 6.7,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "marktechpost",     "platform": "newsletter", "category": "ai_ml",       "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "the-decoder",      "platform": "newsletter", "category": "ai_ml",       "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "marketwatch",      "platform": "newsletter", "category": "finance",     "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "businessinsider",  "platform": "newsletter", "category": "finance",     "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "coindesk",         "platform": "newsletter", "category": "crypto",      "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 25},
    {"handle": "karpathy",         "platform": "newsletter", "category": "ai_ml",       "distortion_index": 0,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 0.0,   "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "coolshell",        "platform": "newsletter", "category": "tech_cn",     "distortion_index": 0,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 0.0,   "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 15},
]

# ── 6个需要重跑的账号 ─────────────────────────────────────────────────────────
RERUN = [
    {"handle": "joelonsoftware",    "feed": "https://www.joelonsoftware.com/feed/",            "platform": "newsletter", "category": "tech"},
    {"handle": "markmanson",        "feed": "https://markmanson.net/rss",                      "platform": "newsletter", "category": "lifestyle"},
    {"handle": "jamesclear",        "feed": "https://jamesclear.com/feed",                     "platform": "newsletter", "category": "lifestyle"},
    {"handle": "becomingminimalist","feed": "https://www.becomingminimalist.com/feed/",        "platform": "newsletter", "category": "lifestyle"},
    {"handle": "sidehustlenation",  "feed": "https://sidehustlenation.com/feed",               "platform": "newsletter", "category": "finance"},
    {"handle": "twocentspbs",       "feed": "UCzWQYUVCpZqtN93H8RR44Qw",                       "platform": "youtube",    "category": "finance"},
]

async def api_post(client, path):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=180)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"  [error] {e}")
        return {}

async def api_get(client, path):
    try:
        r = await client.get(f"{API_BASE}{path}", timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

async def main():
    print("\n" + "="*60)
    print("Rerun — 6 failed accounts")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    async with httpx.AsyncClient() as client:
        # Check backend
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ Backend online")
        except Exception:
            print("\n✗ Backend offline")
            return

        # Step 1: Rerun 6 accounts
        print(f"\n{'='*60}\nStep 1: Rerun 6 accounts\n{'='*60}")
        new_profiles = []
        for i, acc in enumerate(RERUN, 1):
            handle = acc["handle"]
            print(f"\n  [{i}/6] @{handle}...")
            t0 = time.time()
            data = await api_post(client, f"/analyze/{handle}")
            elapsed = round(time.time() - t0, 1)
            if not data or not data.get("profile"):
                print(f"  ✗ failed ({elapsed}s)")
                new_profiles.append({**acc, "distortion_index": 0,
                    "significance_inflation": 0.0, "anxiety_manufacturing": 0.0,
                    "novelty_claims": 0.0, "temporal_distortion": 0.0,
                    "consistency_score": 0.0, "deletion_rate": 0.0,
                    "deleted_count": 0, "total_posts": 0})
                continue
            p = data["profile"]
            result = {
                **acc,
                "distortion_index": p["distortion_index"],
                "significance_inflation": round(p["significance_inflation_rate"]*100, 1),
                "anxiety_manufacturing": round(p["anxiety_manufacturing_rate"]*100, 1),
                "novelty_claims": round(p["novelty_claim_rate"]*100, 1),
                "temporal_distortion": round(p["temporal_distortion_rate"]*100, 1),
                "consistency_score": round(p["consistency_score"]*100, 1),
                "deletion_rate": round(p["deletion_rate"]*100, 1),
                "deleted_count": p["deleted_count"],
                "total_posts": p["total_posts_analyzed"],
            }
            new_profiles.append(result)
            print(f"  ✓ ({elapsed}s) index={result['distortion_index']} posts={data.get('new_posts_crawled',0)}")

        # Merge all
        all_profiles = DONE + new_profiles
        print(f"\n  Total: {len(all_profiles)} accounts ({len(DONE)} cached + {len(new_profiles)} new)")

        # Step 2: Corpus — only from new accounts (cached accounts already in corpus_final.jsonl)
        print(f"\n{'='*60}\nStep 2: Corpus\n{'='*60}")

        # Load existing corpus
        existing_corpus = []
        existing_path = OUTPUT_DIR / "corpus_final.jsonl"
        if existing_path.exists():
            with open(existing_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        existing_corpus.append(json.loads(line))
            print(f"  Loaded existing corpus: {len(existing_corpus)} posts")

        # Fetch new posts
        new_corpus = []
        for acc in new_profiles:
            handle = acc["handle"]
            data = await api_get(client, f"/posts/{handle}?limit=50")
            posts = data.get("posts", [])
            for p in posts:
                new_corpus.append({
                    "handle": handle,
                    "platform": acc["platform"],
                    "category": acc["category"],
                    "post_id": p["platform_id"],
                    "content": p["content"][:500],
                    "posted_at": p["posted_at"],
                    "distortion_types": p["distortion_types"],
                    "confidence": p["confidence"],
                    "method": p["classification_method"],
                    "signals": p["trigger_signals"],
                    "deleted": p["deleted"],
                })
            if posts:
                print(f"  @{handle}: {len(posts)} posts")

        all_corpus = existing_corpus + new_corpus
        print(f"  Total corpus: {len(all_corpus)} posts")

        # Step 3: Export
        print(f"\n{'='*60}\nStep 3: Export\n{'='*60}")

        # corpus_final.jsonl
        with open(OUTPUT_DIR / "corpus_final.jsonl", "w", encoding="utf-8") as f:
            for item in all_corpus:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  corpus_final.jsonl — {len(all_corpus)} posts")

        # profiles_final.csv
        fields = ["handle","platform","category","distortion_index","significance_inflation",
                  "anxiety_manufacturing","novelty_claims","temporal_distortion",
                  "consistency_score","deletion_rate","deleted_count","total_posts"]
        with open(OUTPUT_DIR / "profiles_final.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(all_profiles, key=lambda x: x["distortion_index"], reverse=True))
        print(f"  profiles_final.csv — {len(all_profiles)} rows")

        # report
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        flagged = sum(1 for c in all_corpus if c["distortion_types"])
        all_types = []
        for c in all_corpus:
            all_types.extend(c["distortion_types"])
        type_counts = Counter(all_types)

        by_platform: dict = {}
        by_category: dict = {}
        for p in all_profiles:
            by_platform.setdefault(p["platform"], []).append(p)
            by_category.setdefault(p["category"], []).append(p)

        avg_all = round(statistics.mean(p["distortion_index"] for p in all_profiles), 1)
        hi = max(all_profiles, key=lambda x: x["distortion_index"])
        lo_posts = [p for p in all_profiles if p["total_posts"] > 0]
        lo = min(lo_posts, key=lambda x: x["distortion_index"]) if lo_posts else all_profiles[0]
        above15 = [p for p in all_profiles if p["distortion_index"] >= 15]

        lines = [
            "# Influencer Distortion Detection — Final Research Report (Complete)",
            f"\nGenerated: {now}",
            f"\n---\n",
            "## 1. Corpus Overview",
            f"- Accounts analyzed: **{len(all_profiles)}**",
            f"- Total posts in corpus: **{sum(p['total_posts'] for p in all_profiles)}**",
            f"- Posts with distortion flags: **{flagged}** ({round(flagged/len(all_corpus)*100,1) if all_corpus else 0}%)",
            f"- Deleted posts detected: **{sum(p['deleted_count'] for p in all_profiles)}**",
            f"- Platforms: newsletter, youtube",
            f"- Languages: English, Chinese",
            "",
            "## 2. Account Profiles (sorted by distortion index)",
            "",
            "| Account | Platform | Category | Index | Inflation | Anxiety | Novelty | Temporal | Consistency | Posts |",
            "|---------|----------|----------|-------|-----------|---------|---------|----------|-------------|-------|",
        ]
        for p in sorted(all_profiles, key=lambda x: x["distortion_index"], reverse=True):
            lines.append(
                f"| @{p['handle']} | {p['platform']} | {p['category']} | "
                f"**{p['distortion_index']}** | {p['significance_inflation']}% | "
                f"{p['anxiety_manufacturing']}% | {p['novelty_claims']}% | "
                f"{p['temporal_distortion']}% | {p['consistency_score']} | {p['total_posts']} |"
            )

        lines += ["", "## 3. Cross-Platform Comparison", ""]
        for plat, accs in by_platform.items():
            indices = [a["distortion_index"] for a in accs]
            lines += [
                f"### {plat} ({len(accs)} accounts)",
                f"- Avg distortion index: **{round(statistics.mean(indices),1)}** (range {min(indices)}–{max(indices)})",
                f"- Total posts analyzed: {sum(a['total_posts'] for a in accs)}",
                "",
            ]

        lines += ["## 4. Cross-Category Comparison", "",
                  "| Category | Accounts | Avg Index | Avg Inflation | Avg Anxiety | Avg Novelty | Avg Temporal | Posts |",
                  "|----------|----------|-----------|---------------|-------------|-------------|--------------|-------|"]
        for cat, accs in sorted(by_category.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            indices = [a["distortion_index"] for a in accs]
            lines.append(
                f"| {cat} | {len(accs)} | **{round(statistics.mean(indices),1)}** | "
                f"{round(statistics.mean(a['significance_inflation'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['anxiety_manufacturing'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['novelty_claims'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['temporal_distortion'] for a in accs),1)}% | "
                f"{sum(a['total_posts'] for a in accs)} |"
            )

        lines += [
            "",
            "## 5. Key Findings",
            "",
            f"- Overall average distortion index: **{avg_all}/100**",
            f"- Highest: @{hi['handle']} ({hi['distortion_index']}/100) — {hi['category']}",
            f"- Accounts with index ≥ 15: **{len(above15)}** ({', '.join('@'+a['handle'] for a in above15)})",
            f"- YouTube avg ({round(statistics.mean(a['distortion_index'] for a in by_platform.get('youtube',[])),1)}) vs Newsletter avg ({round(statistics.mean(a['distortion_index'] for a in by_platform.get('newsletter',[])),1)})",
            f"- Accounts with deleted posts: {sum(1 for p in all_profiles if p['deleted_count'] > 0)}",
            "",
            "## 6. Distortion Type Distribution",
            "",
        ]
        total_c = len(all_corpus)
        for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {dtype}: {count} posts ({round(count/total_c*100,1) if total_c else 0}%)")

        lines += ["", "---", f"*Generated: {now}*"]

        with open(OUTPUT_DIR / "report_final.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  report_final.md")

    print(f"\n{'='*60}")
    print(f"✓ Done! {len(all_profiles)} accounts | {len(all_corpus)} posts")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
