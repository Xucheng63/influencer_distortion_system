#!/usr/bin/env python3
"""
rerun_youtube6.py — 只重跑 Batch 2 失败的6个 YouTube 账号
成功结果自动追加到 research_results_batch2/successful_profiles.json

运行：
  python rerun_youtube6.py
"""
import asyncio, json, csv, time
from datetime import datetime
from pathlib import Path
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_batch2")
CACHE_FILE = OUTPUT_DIR / "successful_profiles.json"

YOUTUBE_ACCOUNTS = [
    {"handle": "3blue1brown", "feed": "UCYO_jab_esuFRV4b17AJtAg", "platform": "youtube", "category": "education"},
    {"handle": "kurzgesagt",  "feed": "UCsXVk37bltHxD1rDPwtNM8Q", "platform": "youtube", "category": "education"},
    {"handle": "veritasium",  "feed": "UCHnyfMqiRRG1u-2MsSQLbXA", "platform": "youtube", "category": "education"},
    {"handle": "andrewhuang", "feed": "UCddiUEpeqJcYeBxX1IVBKvQ", "platform": "youtube", "category": "tech_edu"},
    {"handle": "coldusion",   "feed": "UC4QZ_LsYcvcq7qOsOhpAX4A", "platform": "youtube", "category": "finance"},
    {"handle": "nandoogaming","feed": "UCo8bcnLyZH8tBIH9V1mLgqQ", "platform": "youtube", "category": "lifestyle"},
]

def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

async def api_post(client, path):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=300)
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
    print("Rerun — 6 YouTube accounts (Batch 2)")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线")
            return

        cache = load_cache()
        print(f"  已有缓存: {len(cache)} 个账号（不会重跑）")

        print(f"\n{'='*60}\n分析 6 个 YouTube 账号\n{'='*60}")
        success = 0
        for i, acc in enumerate(YOUTUBE_ACCOUNTS, 1):
            handle = acc["handle"]
            if handle in cache:
                print(f"\n  [{i}/6] @{handle} — 已在缓存，跳过")
                continue

            print(f"\n  [{i}/6] @{handle}...")
            t0 = time.time()
            data = await api_post(client, f"/analyze/{handle}")
            elapsed = round(time.time() - t0, 1)

            if not data or not data.get("profile"):
                print(f"  ✗ 失败 ({elapsed}s)")
                continue

            p = data["profile"]
            new_posts = data.get("new_posts_crawled", 0)
            result = {
                "handle": handle,
                "platform": acc["platform"],
                "category": acc["category"],
                "feed": acc["feed"],
                "distortion_index": p["distortion_index"],
                "significance_inflation": round(p["significance_inflation_rate"]*100, 1),
                "anxiety_manufacturing": round(p["anxiety_manufacturing_rate"]*100, 1),
                "novelty_claims": round(p["novelty_claim_rate"]*100, 1),
                "temporal_distortion": round(p["temporal_distortion_rate"]*100, 1),
                "consistency_score": round(p["consistency_score"]*100, 1),
                "deletion_rate": round(p["deletion_rate"]*100, 1),
                "deleted_count": p["deleted_count"],
                "total_posts": p["total_posts_analyzed"],
                "new_posts": new_posts,
                "analyzed_at": datetime.utcnow().isoformat(),
            }

            if result["total_posts"] > 0:
                cache[handle] = result
                save_cache(cache)
                success += 1
                print(f"  ✓ ({elapsed}s) index={result['distortion_index']} posts={new_posts} [已缓存]")
            else:
                print(f"  ~ ({elapsed}s) index={result['distortion_index']} posts=0 [数据为空]")

        # 更新 profiles.csv
        print(f"\n{'='*60}\n更新导出文件\n{'='*60}")
        fields = ["handle","platform","category","distortion_index","significance_inflation",
                  "anxiety_manufacturing","novelty_claims","temporal_distortion",
                  "consistency_score","deletion_rate","deleted_count","total_posts","analyzed_at"]
        with open(OUTPUT_DIR / "profiles.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(cache.values(), key=lambda x: x["distortion_index"], reverse=True))
        print(f"  profiles.csv — {len(cache)} 行")
        print(f"  successful_profiles.json — {len(cache)} 个账号")

    print(f"\n{'='*60}")
    print(f"✓ 完成！本次新增 {success} 个账号，缓存总计 {len(cache)} 个")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
