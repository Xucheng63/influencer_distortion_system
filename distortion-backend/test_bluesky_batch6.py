#!/usr/bin/env python3
"""
test_bluesky_batch6.py — 预检测30个新 Bluesky 候选账号
验证账号是否存在且有帖子

运行：python test_bluesky_batch6.py
"""
import asyncio
import httpx

BLUESKY_API = "https://public.api.bsky.app/xrpc"

CANDIDATES = [
    # 科技/AI
    ("simonw.bsky.social",          "tech",      "low"),
    ("mmitchell.bsky.social",       "ai_ml",     "low"),
    ("derspiegel.bsky.social",      "media",     "low"),
    ("quanta.bsky.social",          "science",   "low"),
    ("ashishkjha.bsky.social",      "health",    "low"),
    ("calculatedrisk.bsky.social",  "finance",   "low"),
    ("patrickrhone.bsky.social",    "lifestyle", "low"),
    ("amandapalmer.bsky.social",    "culture",   "moderate"),
    ("climatepower.bsky.social",    "science",   "moderate"),
    ("brianstelter.bsky.social",    "media",     "moderate"),
    # 媒体机构
    ("msnbc.com",                   "media",     "moderate"),
    ("politico.com",                "politics",  "moderate"),
    ("reuters.com",                 "media",     "low"),
    ("apnews.com",                  "media",     "low"),
    ("bbc.com",                     "media",     "low"),
    ("vice.com",                    "media",     "moderate"),
    ("motherjones.com",             "politics",  "moderate"),
    ("theintercept.com",            "politics",  "high"),
    ("newrepublic.com",             "politics",  "moderate"),
    ("slate.com",                   "media",     "moderate"),
    # 政治/文化大V
    ("mollyjongfast.bsky.social",   "media",     "high"),
    ("chrislhayes.bsky.social",     "media",     "moderate"),
    ("juddlegum.bsky.social",       "media",     "moderate"),
    ("oliverdarcy.bsky.social",     "media",     "moderate"),
    ("taylorlorenz.bsky.social",    "tech_media","high"),
    ("katienotopoulos.bsky.social", "tech_media","moderate"),
    ("johncusack.bsky.social",      "culture",   "high"),
    ("parismarx.bsky.social",       "tech_media","high"),
    ("michaelmann.bsky.social",     "science",   "moderate"),
    ("noahpinion.bsky.social",      "finance",   "moderate"),
]

async def check_account(handle: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    """验证 Bluesky 账号是否存在且有帖子"""
    try:
        # 获取账号信息
        r = await client.get(
            f"{BLUESKY_API}/app.bsky.actor.getProfile",
            params={"actor": handle},
            timeout=10,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        data = r.json()
        display = data.get("displayName", handle)
        followers = data.get("followersCount", 0)
        posts_count = data.get("postsCount", 0)

        if posts_count == 0:
            return False, f"0 帖子"

        return True, f"{display} ({followers:,} followers, {posts_count:,} posts)"

    except Exception as e:
        return False, str(e)[:40]

async def main():
    print("\n" + "="*65)
    print("Bluesky 第六批账号预检测")
    print(f"候选账号: {len(CANDIDATES)} 个")
    print("="*65)

    good = []
    bad = []

    async with httpx.AsyncClient() as client:
        for i, (handle, category, expected) in enumerate(CANDIDATES, 1):
            print(f"  [{i:2d}/30] {handle:<40}", end="", flush=True)
            ok, info = await check_account(handle, client)
            if ok:
                print(f"✓ {info}")
                good.append((handle, category, expected, info))
            else:
                print(f"✗ {info}")
                bad.append((handle, info))

    print(f"\n{'='*65}")
    print(f"✓ 验证通过: {len(good)} 个")
    for handle, cat, exp, info in good:
        print(f"   {handle:<40} [{cat}] {exp}")
    print(f"\n✗ 失败: {len(bad)} 个")
    for handle, reason in bad:
        print(f"   {handle:<40} {reason}")
    print("="*65 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
