#!/usr/bin/env python3
"""
test_reddit_single.py — 快速测试单个 Reddit Subreddit 和用户

运行：
  python test_reddit_single.py
"""
import asyncio, json, time
from datetime import datetime
import httpx

API_BASE = "http://localhost:8001/api"

TEST_ACCOUNTS = [
    {"handle": "r/technology",    "type": "subreddit", "category": "tech"},
    {"handle": "u/spez",          "type": "user",      "category": "tech"},
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
    print("Reddit 单账号测试")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    async with httpx.AsyncClient() as client:
        # 检查后端
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线")
            return

        for acc in TEST_ACCOUNTS:
            handle = acc["handle"]
            print(f"\n{'='*50}")
            print(f"测试: {handle} ({acc['type']})")
            print(f"{'='*50}")

            t0 = time.time()
            data = await api_post(client, f"/analyze/{handle}")
            elapsed = round(time.time() - t0, 1)

            if not data or not data.get("profile"):
                print(f"✗ 失败 ({elapsed}s) — 没有返回 profile 数据")
                continue

            p = data["profile"]
            new_posts = data.get("new_posts_crawled", 0)

            print(f"✓ 完成 ({elapsed}s)")
            print(f"  帖子数:     {new_posts} new / {p['total_posts_analyzed']} total")
            print(f"  失真指数:   {p['distortion_index']}/100")
            print(f"  Inflation:  {round(p['significance_inflation_rate']*100,1)}%")
            print(f"  Anxiety:    {round(p['anxiety_manufacturing_rate']*100,1)}%")
            print(f"  Novelty:    {round(p['novelty_claim_rate']*100,1)}%")
            print(f"  Temporal:   {round(p['temporal_distortion_rate']*100,1)}%")
            print(f"  Consistency:{round(p['consistency_score']*100,1)}")

            # 查看几条帖子内容
            posts_data = await api_get(client, f"/posts/{handle}?limit=5")
            posts = posts_data.get("posts", [])
            if posts:
                print(f"\n  最近 {len(posts)} 条帖子预览:")
                for i, post in enumerate(posts[:3], 1):
                    content = post["content"][:80].replace("\n", " ")
                    flags = post["distortion_types"]
                    conf = round(post["confidence"]*100) if post["confidence"] else 0
                    flag_str = f" [{', '.join(flags)}]" if flags else ""
                    print(f"  {i}. {content}...")
                    print(f"     Confidence: {conf}%{flag_str}")
            else:
                print(f"\n  ⚠ 没有帖子数据")

    print(f"\n{'='*60}")
    print("测试完成！")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
