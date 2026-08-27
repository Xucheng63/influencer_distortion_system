#!/usr/bin/env python3
"""
experiment_youtube_batch2.py — YouTube 第二批实验脚本

handle 必须在 scraper.py 的 FEED_MAP 里（type=youtube）
后端自动走 RSS → 字幕抓取流水线，不需要 Playwright

运行：python experiment_youtube_batch2.py
"""
import asyncio, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_youtube")
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_FILE = OUTPUT_DIR / "successful_profiles.json"

# 旧10个 + 新22个，全部在 FEED_MAP 里
CANDIDATE_ACCOUNTS = [
    # ── 旧10个（已缓存自动跳过）───────────────────────────────────────────
    {"handle": "ycombinator",    "category": "startup",  "expected": "low"},
    {"handle": "lexfridman",     "category": "ai_ml",    "expected": "low"},
    {"handle": "fireship",       "category": "tech",     "expected": "low"},
    {"handle": "mkbhd",          "category": "tech",     "expected": "low"},
    {"handle": "aiexplained",    "category": "ai_ml",    "expected": "low"},
    {"handle": "twocentspbs",    "category": "finance",  "expected": "low"},
    {"handle": "3blue1brown",    "category": "science",  "expected": "low"},
    {"handle": "kurzgesagt",     "category": "science",  "expected": "low"},
    {"handle": "veritasium",     "category": "science",  "expected": "low"},
    {"handle": "coldusion",      "category": "finance",  "expected": "moderate"},
    # ── 新增22个（验证通过）───────────────────────────────────────────────
    {"handle": "cgpgrey",        "category": "learning", "expected": "low"},
    {"handle": "grahamstephan",  "category": "finance",  "expected": "high"},
    {"handle": "linustechtips",  "category": "tech",     "expected": "low"},
    {"handle": "markrober",      "category": "science",  "expected": "low"},
    {"handle": "teded",          "category": "learning", "expected": "low"},
    {"handle": "youngtturks",    "category": "politics", "expected": "high"},
    {"handle": "vicenews",       "category": "media",    "expected": "high"},
    {"handle": "polymatter",     "category": "learning", "expected": "low"},
    {"handle": "karpathy",       "category": "ai_ml",    "expected": "low"},
    {"handle": "twominutepapers","category": "ai_ml",    "expected": "low"},
    {"handle": "andreijikh",     "category": "finance",  "expected": "high"},
    {"handle": "cnn",            "category": "media",    "expected": "high"},
    {"handle": "sentdex",        "category": "tech",     "expected": "low"},
    {"handle": "freecodecamp",   "category": "tech",     "expected": "low"},
    {"handle": "computerphile",  "category": "tech",     "expected": "low"},
    {"handle": "numberphile",    "category": "science",  "expected": "low"},
    {"handle": "crashcourse",    "category": "learning", "expected": "low"},
    {"handle": "marktilbury",    "category": "finance",  "expected": "high"},
    {"handle": "minoritymindset","category": "finance",  "expected": "high"},
    {"handle": "meetkevin",      "category": "finance",  "expected": "high"},
    {"handle": "abcnews",        "category": "media",    "expected": "moderate"},
    {"handle": "nandoogaming",   "category": "culture",  "expected": "moderate"},
]

def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  已加载缓存: {len(data)} 个账号")
        return data
    return {}

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

async def api_post(client, path):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=1200)
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
    print("YouTube Platform Experiment — Batch 2")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"候选账号: {len(CANDIDATE_ACCOUNTS)}")
    print("="*60)

    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线")
            return

        cache = load_cache()
        need = [a for a in CANDIDATE_ACCOUNTS if a["handle"] not in cache]
        skip = len(CANDIDATE_ACCOUNTS) - len(need)
        print(f"  需分析: {len(need)} | 缓存跳过: {skip}")

        # Step 1: 分析
        print(f"\n{'='*60}\nStep 1: 分析 {len(need)} 个账号\n{'='*60}")
        for i, acc in enumerate(need, 1):
            handle = acc["handle"]
            print(f"\n  [{i}/{len(need)}] {handle} ({acc['category']})...")
            t0 = time.time()
            data = await api_post(client, f"/analyze/{handle}")
            elapsed = round(time.time() - t0, 1)

            if not data or not data.get("profile"):
                print(f"  ✗ 失败 ({elapsed}s)")
                continue

            p = data["profile"]
            new_posts = data.get("new_posts_crawled", 0)
            result = {
                "handle":   handle,
                "platform": "youtube",
                "category": acc["category"],
                "expected": acc["expected"],
                "distortion_index":       p["distortion_index"],
                "significance_inflation": round(p["significance_inflation_rate"]*100,1),
                "anxiety_manufacturing":  round(p["anxiety_manufacturing_rate"]*100,1),
                "novelty_claims":         round(p["novelty_claim_rate"]*100,1),
                "temporal_distortion":    round(p["temporal_distortion_rate"]*100,1),
                "consistency_score":      round(p["consistency_score"]*100,1),
                "total_posts":            p["total_posts_analyzed"],
                "analyzed_at":            datetime.utcnow().isoformat(),
            }

            if result["total_posts"] > 0:
                cache[handle] = result
                save_cache(cache)
                print(f"  ✓ ({elapsed}s) index={result['distortion_index']} "
                      f"posts={new_posts} [已缓存]")
            else:
                print(f"  ~ ({elapsed}s) posts=0 [数据为空，未缓存]")

        # Step 2: 语料库
        print(f"\n{'='*60}\nStep 2: 收集语料库\n{'='*60}")
        corpus = []
        for handle, prof in cache.items():
            data = await api_get(client, f"/posts/{handle}?limit=50")
            posts = data.get("posts", [])
            for p in posts:
                corpus.append({
                    "handle":   handle,
                    "platform": "youtube",
                    "category": prof["category"],
                    "post_id":  p["platform_id"],
                    "content":  p["content"][:500],
                    "posted_at":p["posted_at"],
                    "distortion_types": p["distortion_types"],
                    "confidence":       p["confidence"],
                    "method":           p["classification_method"],
                })
            if posts:
                print(f"  {handle}: {len(posts)} 条")
        print(f"\n  语料库总量: {len(corpus)} 条")

        # Step 3: 分析结果
        profiles = list(cache.values())
        if not profiles:
            print("\n没有成功数据")
            return

        print(f"\n{'='*60}\nStep 3: 分析结果\n{'='*60}")
        indices = [p["distortion_index"] for p in profiles]
        print(f"\n总账号: {len(profiles)}")
        print(f"总帖子: {sum(p['total_posts'] for p in profiles)}")
        print(f"平均失真指数: {round(statistics.mean(indices),1)}")
        print(f"最高: {max(indices)} ({max(profiles,key=lambda x:x['distortion_index'])['handle']})")
        print(f"最低: {min(indices)} ({min(profiles,key=lambda x:x['distortion_index'])['handle']})")

        by_cat = defaultdict(list)
        for p in profiles:
            by_cat[p["category"]].append(p)
        print("\n按类别:")
        for cat, accs in sorted(by_cat.items(),
                key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            idx = [a["distortion_index"] for a in accs]
            print(f"  {cat:<12} n={len(accs):2d} avg={round(statistics.mean(idx),1):5.1f} "
                  f"max={max(idx)} min={min(idx)}")

        # Step 4: 导出
        print(f"\n{'='*60}\nStep 4: 导出\n{'='*60}")
        with open(OUTPUT_DIR/"corpus.jsonl","w",encoding="utf-8") as f:
            for item in corpus:
                f.write(json.dumps(item,ensure_ascii=False)+"\n")
        print(f"  corpus.jsonl — {len(corpus)} 条")

        fields = ["handle","platform","category","expected","distortion_index",
                  "significance_inflation","anxiety_manufacturing","novelty_claims",
                  "temporal_distortion","consistency_score","total_posts","analyzed_at"]
        with open(OUTPUT_DIR/"profiles.csv","w",newline="",encoding="utf-8") as f:
            w = csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(profiles,key=lambda x:x["distortion_index"],reverse=True))
        print(f"  profiles.csv — {len(profiles)} 行")
        print(f"  successful_profiles.json — {len(cache)} 个账号")

    print(f"\n{'='*60}")
    print(f"✓ 完成！{len(profiles)} 个账号")
    print(f"  结果保存在 {OUTPUT_DIR}/")
    print("="*60+"\n")

if __name__ == "__main__":
    asyncio.run(main())
