#!/usr/bin/env python3
"""
test_bluesky_batch7.py — 预检测15个候选账号，选出10个
运行：python test_bluesky_batch7.py
"""
import asyncio
import httpx

BSKY_API = "https://public.api.bsky.app/xrpc"

CANDIDATES = [
    # finance 大V（目前只有1个）
    ("felixsalmon.bsky.social",     "finance",   "moderate"),
    ("helaine.bsky.social",         "finance",   "moderate"),
    ("econunpacked.bsky.social",    "finance",   "low"),
    # crypto（目前0个）
    ("cobie.bsky.social",           "crypto",    "high"),
    ("coincenter.org",              "crypto",    "moderate"),
    # 国际媒体（目前只有 Der Spiegel 一个非英语）
    ("lemonde.fr",                  "media",     "low"),
    ("theguardian.com",             "media",     "low"),
    ("economist.com",               "media",     "low"),
    ("ft.com",                      "media",     "low"),
    ("time.com",                    "media",     "moderate"),
    # 科技大V（补充）
    ("benedictevans.bsky.social",   "tech",      "low"),
    ("gruber.bsky.social",          "tech",      "low"),
    ("stratechery.bsky.social",     "tech",      "low"),
    # 高失真补充
    ("davidfrum.bsky.social",       "politics",  "high"),
    ("ezraklein.bsky.social",       "politics",  "moderate"),
]

async def check(handle: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    try:
        r = await client.get(
            f"{BSKY_API}/app.bsky.actor.getProfile",
            params={"actor": handle},
            timeout=10,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        d = r.json()
        posts = d.get("postsCount", 0)
        followers = d.get("followersCount", 0)
        name = d.get("displayName", handle)
        if posts == 0:
            return False, "0 帖子"
        return True, f"{name} ({followers:,} followers, {posts:,} posts)"
    except Exception as e:
        return False, str(e)[:40]

async def main():
    print("\n" + "="*65)
    print("Bluesky 第七批预检测")
    print(f"候选: {len(CANDIDATES)} 个")
    print("="*65)

    good, bad = [], []
    async with httpx.AsyncClient() as client:
        for i, (handle, cat, exp) in enumerate(CANDIDATES, 1):
            print(f"  [{i:2d}/{len(CANDIDATES)}] {handle:<40}", end="", flush=True)
            ok, info = await check(handle, client)
            if ok:
                print(f"✓ {info}")
                good.append((handle, cat, exp))
            else:
                print(f"✗ {info}")
                bad.append((handle, info))

    print(f"\n{'='*65}")
    print(f"✓ 通过: {len(good)} 个")
    for h, c, e in good:
        print(f"   {h:<40} [{c}] {e}")
    print(f"\n✗ 失败: {len(bad)} 个")
    for h, r in bad:
        print(f"   {h:<40} {r}")
    print("="*65 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
