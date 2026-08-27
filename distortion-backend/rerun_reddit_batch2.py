#!/usr/bin/env python3
"""
rerun_reddit_batch2.py — 清掉9个新账号的数据库记录，用 HTTP JSON 重新抓取

原因：Playwright 方式只抓了标题，HTTP JSON 方式抓 title + selftext[:300]
这9个账号是 batch2 新增的，旧44个不受影响

运行：python rerun_reddit_batch2.py
（后端需要在线：uvicorn app.main:app --reload --port 8001）
"""
import asyncio, sqlite3, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_reddit")
CACHE_FILE = OUTPUT_DIR / "successful_profiles.json"

# 9个需要重新抓取的账号（batch2 新增，之前只有标题）
RERUN_ACCOUNTS = [
    # 原9个（Playwright只抓标题，改用HTTP JSON重新抓）
    {"handle": "r/chatgpt",             "category": "ai_ml",    "expected": "high"},
    {"handle": "r/openai",              "category": "ai_ml",    "expected": "high"},
    {"handle": "r/cryptocurrency",      "category": "crypto",   "expected": "high"},
    {"handle": "r/economy",             "category": "finance",  "expected": "moderate"},
    {"handle": "r/cscareerquestions",   "category": "tech",     "expected": "low"},
    {"handle": "r/askhistorians",       "category": "learning", "expected": "low"},
    {"handle": "r/space",               "category": "science",  "expected": "low"},
    {"handle": "r/physics",             "category": "science",  "expected": "low"},
    {"handle": "u/gallowboob",          "category": "culture",  "expected": "low"},
    # 新增6个（之前超时失败，现在用HTTP JSON）
    {"handle": "r/bitcoin",             "category": "crypto",   "expected": "high"},
    {"handle": "r/worldpolitics",       "category": "politics", "expected": "high"},
    {"handle": "r/geopolitics",         "category": "politics", "expected": "moderate"},
    {"handle": "r/stockmarket",         "category": "finance",  "expected": "moderate"},
    {"handle": "r/investing_discussion","category": "finance",  "expected": "moderate"},
    {"handle": "r/nutrition",           "category": "health",   "expected": "low"},
]

DB_PATH = Path("data/distortion.db")

def clear_db_records(handles: list[str]):
    """清掉指定账号的所有数据库记录"""
    if not DB_PATH.exists():
        print(f"✗ 数据库不存在: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    try:
        ph = ",".join("?" * len(handles))
        # 删除帖子
        c1 = conn.execute(
            f"DELETE FROM post WHERE account_id IN "
            f"(SELECT id FROM account WHERE handle IN ({ph}))", handles
        )
        # 删除档案
        c2 = conn.execute(
            f"DELETE FROM distortionprofile WHERE account_id IN "
            f"(SELECT id FROM account WHERE handle IN ({ph}))", handles
        )
        # 删除账号
        c3 = conn.execute(
            f"DELETE FROM account WHERE handle IN ({ph})", handles
        )
        conn.commit()
        print(f"✓ 清除完成：{c3.rowcount} 个账号，"
              f"{c1.rowcount} 条帖子，{c2.rowcount} 个档案")
        return True
    except Exception as e:
        print(f"✗ 数据库错误: {e}")
        return False
    finally:
        conn.close()

def update_cache(handles_to_remove: list[str]):
    """从缓存文件里删掉这9个账号"""
    if not CACHE_FILE.exists():
        return
    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)
    removed = 0
    for h in handles_to_remove:
        if h in cache:
            del cache[h]
            removed += 1
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"✓ 缓存更新：移除 {removed} 个账号，剩余 {len(cache)} 个")

async def api_post(client, path, timeout=180):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=timeout)
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
    print("Reddit Batch2 重新抓取（HTTP JSON 方式）")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"目标账号: {len(RERUN_ACCOUNTS)} 个（原9个重抓 + 新6个首次）")
    print("="*60)

    handles = [a["handle"] for a in RERUN_ACCOUNTS]

    # Step 1: 清库
    print("\nStep 1: 清除数据库记录...")
    if not clear_db_records(handles):
        return
    update_cache(handles)

    async with httpx.AsyncClient() as client:
        # 检查后端
        try:
            r = await client.get(
                f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线 — 请先运行: uvicorn app.main:app --reload --port 8001")
            return

        # Step 2: 重新分析
        print(f"\nStep 2: 重新分析 {len(RERUN_ACCOUNTS)} 个账号（HTTP JSON）")
        print("（每个约 15-30 秒，不使用 Playwright）\n")

        results = []
        for i, acc in enumerate(RERUN_ACCOUNTS, 1):
            handle = acc["handle"]
            print(f"  [{i}/{len(RERUN_ACCOUNTS)}] {handle}...", end="", flush=True)
            t0 = time.time()
            data = await api_post(client, f"/analyze/{handle}")
            elapsed = round(time.time() - t0, 1)

            if not data or not data.get("profile"):
                print(f" ✗ 失败 ({elapsed}s)")
                continue

            p = data["profile"]
            new_posts = data.get("new_posts_crawled", 0)
            print(f" ✓ ({elapsed}s) index={p['distortion_index']} "
                  f"posts={new_posts} "
                  f"infl={round(p['significance_inflation_rate']*100,1)}% "
                  f"anx={round(p['anxiety_manufacturing_rate']*100,1)}%")

            results.append({
                "handle":   handle,
                "type":     "subreddit" if handle.startswith("r/") else "user",
                "platform": "reddit",
                "category": acc["category"],
                "expected": acc["expected"],
                "distortion_index":       p["distortion_index"],
                "significance_inflation": round(p["significance_inflation_rate"]*100,1),
                "anxiety_manufacturing":  round(p["anxiety_manufacturing_rate"]*100,1),
                "novelty_claims":         round(p["novelty_claim_rate"]*100,1),
                "temporal_distortion":    round(p["temporal_distortion_rate"]*100,1),
                "consistency_score":      round(p["consistency_score"]*100,1),
                "total_posts":            p["total_posts_analyzed"],
                "new_posts":              new_posts,
                "analyzed_at":            datetime.utcnow().isoformat(),
            })

        # Step 3: 更新缓存
        print(f"\nStep 3: 更新缓存...")
        if CACHE_FILE.exists():
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        else:
            cache = {}

        for r in results:
            cache[r["handle"]] = r
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 缓存已更新，共 {len(cache)} 个账号")

        # Step 4: 对比报告
        if results:
            print(f"\nStep 4: 重新抓取结果对比")
            print(f"{'账号':<30} {'指数':>5} {'膨胀':>7} {'焦虑':>7} {'新颖':>7} {'帖子':>5}")
            print("-"*60)
            for r in sorted(results, key=lambda x: -x["distortion_index"]):
                print(f"  {r['handle']:<28} {r['distortion_index']:>5} "
                      f"{r['significance_inflation']:>6}% "
                      f"{r['anxiety_manufacturing']:>6}% "
                      f"{r['novelty_claims']:>6}% "
                      f"{r['total_posts']:>5}")

            indices = [r["distortion_index"] for r in results]
            print(f"\n  平均失真指数: {round(statistics.mean(indices),1)}")
            print(f"  最高: {max(indices)} ({max(results,key=lambda x:x['distortion_index'])['handle']})")

    print(f"\n{'='*60}")
    print(f"✓ 完成！{len(results)}/{len(RERUN_ACCOUNTS)} 个账号重新抓取成功")
    print(f"  结果已更新到 {CACHE_FILE}")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
