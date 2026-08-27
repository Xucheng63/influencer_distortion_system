#!/usr/bin/env python3
"""补充预检测3个候选"""
import asyncio, httpx

BSKY_API = "https://public.api.bsky.app/xrpc"

CANDIDATES = [
    ("npr.org",                  "media",   "low"),
    ("theatlantic.com",          "media",   "moderate"),
    ("wired.com",                "tech",    "moderate"),
    ("thenation.com",            "politics","high"),
    ("harpers.org",              "culture", "low"),
]

async def check(handle, client):
    try:
        r = await client.get(f"{BSKY_API}/app.bsky.actor.getProfile",
                             params={"actor": handle}, timeout=10)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        d = r.json()
        posts = d.get("postsCount", 0)
        if posts == 0:
            return False, "0 帖子"
        return True, f"{d.get('displayName', handle)} ({d.get('followersCount',0):,} followers, {posts:,} posts)"
    except Exception as e:
        return False, str(e)[:40]

async def main():
    print("\n补充预检测")
    good = []
    async with httpx.AsyncClient() as client:
        for handle, cat, exp in CANDIDATES:
            print(f"  {handle:<40}", end="", flush=True)
            ok, info = await check(handle, client)
            print(f"{'✓' if ok else '✗'} {info}")
            if ok:
                good.append((handle, cat, exp))
    print(f"\n✓ 通过: {len(good)} 个")
    for h, c, e in good:
        print(f"   {h} [{c}] {e}")

if __name__ == "__main__":
    asyncio.run(main())
