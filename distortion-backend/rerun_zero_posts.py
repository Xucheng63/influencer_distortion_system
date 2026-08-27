#!/usr/bin/env python3
"""
rerun_zero_posts.py — 只重跑上次 0 posts 的账号

运行方式（必须用 ischool 环境）：
  /usr/local/Caskroom/miniconda/base/envs/ischool/bin/python3 rerun_zero_posts.py
"""
import asyncio, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_50")
OUTPUT_DIR.mkdir(exist_ok=True)

# 上次成功有数据的账号（直接用，不重跑）
DONE_WITH_DATA = [
    {"handle": "simonwillison",  "platform": "newsletter", "category": "tech",        "distortion_index": 14, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 3.3, "temporal_distortion": 3.3,  "consistency_score": 86.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "dhh",            "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 9},
    {"handle": "ruanyifeng",     "platform": "newsletter", "category": "tech_cn",     "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 6},
    {"handle": "lesswrong",      "platform": "newsletter", "category": "rationalism", "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "astralcodexten", "platform": "newsletter", "category": "rationalism", "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "karpathy",       "platform": "newsletter", "category": "ai_ml",       "distortion_index": 0,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 0.0,   "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10},
    {"handle": "fireship",       "platform": "youtube",    "category": "tech_edu",    "distortion_index": 11, "significance_inflation": 5.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 5.0, "temporal_distortion": 10.0, "consistency_score": 50.0,  "deletion_rate": 4.8, "deleted_count": 1, "total_posts": 20},
    {"handle": "ycombinator",    "platform": "youtube",    "category": "startup",     "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "lexfridman",     "platform": "youtube",    "category": "ai_ml",       "distortion_index": 9,  "significance_inflation": 5.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
    {"handle": "swyx",           "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30},
    {"handle": "coolshell",      "platform": "newsletter", "category": "tech_cn",     "distortion_index": 0,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,  "consistency_score": 0.0,   "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 15},
    {"handle": "aiexplained",    "platform": "youtube",    "category": "ai_ml",       "distortion_index": 8,  "significance_inflation": 0.0,  "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 5.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20},
]

# 上次 0 posts 的账号 — 本次重跑
RERUN_ACCOUNTS = [
    {"handle": "martinfowler",     "platform": "newsletter", "category": "tech"},
    {"handle": "joelonsoftware",   "platform": "newsletter", "category": "tech"},
    {"handle": "overreacted",      "platform": "newsletter", "category": "tech"},
    {"handle": "stratechery",      "platform": "newsletter", "category": "tech"},
    {"handle": "latentspace",      "platform": "newsletter", "category": "ai_ml"},
    {"handle": "pragmaticengineer","platform": "newsletter", "category": "tech"},
    {"handle": "timferriss",       "platform": "newsletter", "category": "lifestyle"},
    {"handle": "sspai",            "platform": "newsletter", "category": "tech_cn"},
    {"handle": "techcrunch",       "platform": "newsletter", "category": "tech_media"},
    {"handle": "theverge",         "platform": "newsletter", "category": "tech_media"},
    {"handle": "wired-ai",         "platform": "newsletter", "category": "tech_media"},
    {"handle": "arstechnica",      "platform": "newsletter", "category": "tech_media"},
    {"handle": "thenextweb",       "platform": "newsletter", "category": "tech_media"},
    {"handle": "venturebeat",      "platform": "newsletter", "category": "tech_media"},
    {"handle": "zdnet",            "platform": "newsletter", "category": "tech_media"},
    {"handle": "hackernews",       "platform": "newsletter", "category": "tech_media"},
    {"handle": "mit-tech-review",  "platform": "newsletter", "category": "tech_media"},
    {"handle": "huggingface",      "platform": "newsletter", "category": "ai_ml"},
    {"handle": "openai-news",      "platform": "newsletter", "category": "ai_ml"},
    {"handle": "deepmind",         "platform": "newsletter", "category": "ai_ml"},
    {"handle": "marktechpost",     "platform": "newsletter", "category": "ai_ml"},
    {"handle": "the-decoder",      "platform": "newsletter", "category": "ai_ml"},
    {"handle": "marketwatch",      "platform": "newsletter", "category": "finance"},
    {"handle": "businessinsider",  "platform": "newsletter", "category": "finance"},
    {"handle": "financialsamurai", "platform": "newsletter", "category": "finance"},
    {"handle": "coindesk",         "platform": "newsletter", "category": "crypto"},
    {"handle": "notboring",        "platform": "newsletter", "category": "finance"},
    {"handle": "peterattiamd",     "platform": "newsletter", "category": "health"},
    {"handle": "markmanson",       "platform": "newsletter", "category": "lifestyle"},
    {"handle": "jamesclear",       "platform": "newsletter", "category": "lifestyle"},
    {"handle": "becomingminimalist","platform": "newsletter", "category": "lifestyle"},
    {"handle": "sidehustlenation", "platform": "newsletter", "category": "finance"},
    {"handle": "clevergirlfinance","platform": "newsletter", "category": "finance"},
    {"handle": "twocentspbs",      "platform": "youtube",    "category": "finance"},
]

async def api_post(client, path):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=120)
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
    print("Rerun — 0-posts accounts only")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Accounts to rerun: {len(RERUN_ACCOUNTS)}")
    print("="*60)

    async with httpx.AsyncClient() as client:
        # Check backend
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ Backend online")
        except Exception:
            print("\n✗ Backend offline — run: uvicorn app.main:app --reload --port 8001")
            return

        # Rerun analysis
        print(f"\n{'='*60}\nStep 1: Re-analyze {len(RERUN_ACCOUNTS)} accounts\n{'='*60}")
        new_profiles = []
        for i, acc in enumerate(RERUN_ACCOUNTS, 1):
            handle = acc["handle"]
            print(f"\n  [{i}/{len(RERUN_ACCOUNTS)}] @{handle}...")
            t0 = time.time()
            data = await api_post(client, f"/analyze/{handle}")
            elapsed = round(time.time() - t0, 1)
            if not data or not data.get("profile"):
                print(f"  ✗ failed ({elapsed}s)")
                new_profiles.append({**acc, "distortion_index": 0, "significance_inflation": 0.0,
                    "anxiety_manufacturing": 0.0, "novelty_claims": 0.0, "temporal_distortion": 0.0,
                    "consistency_score": 0.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 0})
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

        # Merge all profiles
        all_profiles = DONE_WITH_DATA + new_profiles
        print(f"\n  Total accounts: {len(all_profiles)}")

        # Collect corpus
        print(f"\n{'='*60}\nStep 2: Collect corpus\n{'='*60}")
        corpus = []
        for acc in all_profiles:
            handle = acc["handle"]
            data = await api_get(client, f"/posts/{handle}?limit=50")
            posts = data.get("posts", [])
            for p in posts:
                corpus.append({
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
        print(f"\n  Corpus total: {len(corpus)} posts")

        # Cross analysis
        print(f"\n{'='*60}\nStep 3: Cross analysis\n{'='*60}")
        by_platform: dict = {}
        by_category: dict = {}
        for p in all_profiles:
            by_platform.setdefault(p["platform"], []).append(p)
            by_category.setdefault(p["category"], []).append(p)

        print("\nBy platform:")
        for plat, accs in by_platform.items():
            indices = [a["distortion_index"] for a in accs]
            avg = round(statistics.mean(indices), 1)
            print(f"  {plat} ({len(accs)}): avg={avg} max={max(indices)} min={min(indices)}")

        print("\nBy category:")
        for cat, accs in sorted(by_category.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            indices = [a["distortion_index"] for a in accs]
            avg = round(statistics.mean(indices), 1)
            posts = sum(a["total_posts"] for a in accs)
            print(f"  {cat} ({len(accs)}): avg={avg} posts={posts}")

        # Export
        print(f"\n{'='*60}\nStep 4: Export\n{'='*60}")

        # corpus.jsonl
        with open(OUTPUT_DIR / "corpus_final.jsonl", "w", encoding="utf-8") as f:
            for item in corpus:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  corpus_final.jsonl — {len(corpus)} posts")

        # profiles.csv
        fields = ["handle","platform","category","distortion_index","significance_inflation",
                  "anxiety_manufacturing","novelty_claims","temporal_distortion",
                  "consistency_score","deletion_rate","deleted_count","total_posts"]
        with open(OUTPUT_DIR / "profiles_final.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_profiles)
        print(f"  profiles_final.csv — {len(all_profiles)} rows")

        # report
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        flagged = sum(1 for c in corpus if c["distortion_types"])
        all_types = []
        for c in corpus:
            all_types.extend(c["distortion_types"])
        type_counts = Counter(all_types)

        lines = [
            "# Influencer Distortion Detection — Final Research Report",
            f"\nGenerated: {now}",
            f"\n---\n",
            "## 1. Corpus Overview",
            f"- Accounts analyzed: **{len(all_profiles)}**",
            f"- Total posts: **{sum(a['total_posts'] for a in all_profiles)}**",
            f"- Posts with distortion flags: **{flagged}** ({round(flagged/len(corpus)*100,1) if corpus else 0}%)",
            f"- Deleted posts detected: **{sum(a['deleted_count'] for a in all_profiles)}**",
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
                  "| Category | Accounts | Avg Index | Avg Inflation | Avg Anxiety | Avg Novelty | Avg Temporal | Total Posts |",
                  "|----------|----------|-----------|---------------|-------------|-------------|--------------|-------------|"]
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

        lines += ["", "## 5. Key Findings", ""]
        avg = round(statistics.mean(a["distortion_index"] for a in all_profiles), 1)
        hi = max(all_profiles, key=lambda x: x["distortion_index"])
        lo = min(all_profiles, key=lambda x: x["distortion_index"])
        above15 = [a for a in all_profiles if a["distortion_index"] >= 15]
        lines += [
            f"- Overall average distortion index: **{avg}/100**",
            f"- Highest: @{hi['handle']} ({hi['distortion_index']}) — {hi['category']}",
            f"- Lowest: @{lo['handle']} ({lo['distortion_index']}) — {lo['category']}",
            f"- Accounts with index ≥ 15: **{len(above15)}** ({', '.join('@'+a['handle'] for a in above15)})",
            f"- YouTube avg ({round(statistics.mean(a['distortion_index'] for a in by_platform.get('youtube',[])),1)}) vs Newsletter avg ({round(statistics.mean(a['distortion_index'] for a in by_platform.get('newsletter',[])),1)})",
            "",
        ]

        lines += ["## 6. Distortion Type Distribution", ""]
        total_posts = len(corpus)
        for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {dtype}: {count} posts ({round(count/total_posts*100,1) if total_posts else 0}%)")

        lines += ["", "---", f"*Generated: {now}*"]

        with open(OUTPUT_DIR / "report_final.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  report_final.md")

    print(f"\n{'='*60}")
    print(f"✓ Done! Files in {OUTPUT_DIR}/")
    print(f"  {len(all_profiles)} accounts | {len(corpus)} posts")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
