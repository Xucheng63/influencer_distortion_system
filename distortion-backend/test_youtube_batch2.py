#!/usr/bin/env python3
"""
test_youtube_batch2.py — 预检测20个新 YouTube 候选频道
通过 RSS Feed 验证频道是否存在且有视频

运行：python test_youtube_batch2.py
"""
import asyncio
import httpx
from xml.etree import ElementTree as ET

# 20个候选频道（channel_id + 名称 + 类别）
# channel_id 从 YouTube 频道页面 URL 或 RSS 中获取
CANDIDATES = [
    # 科技/AI — 低失真预期
    ("UCnUYZLuoy1rq1aVMwx4aTzw", "Andrej Karpathy",    "ai_ml",    "low"),
    ("UCWX3yGbODM0gHbMHcpGRMcg", "Yannic Kilcher",     "ai_ml",    "low"),
    ("UCZHmQk67mSJgfCCTn7xBfew", "Two Minute Papers",  "ai_ml",    "low"),
    ("UCbmNph6atAoGfqLoCL_duAg", "Sentdex",            "tech",     "low"),
    ("UC8butISFwT-Wl7EV0hUK0BQ", "freeCodeCamp",       "tech",     "low"),
    ("UCVls1GmFKf6WlTraIb_IaJg", "Computerphile",      "tech",     "low"),
    ("UCoxcjq-8xIDTYp3uz647V5A", "Numberphile",        "science",  "low"),
    ("UC9-y-6csu5WGm29I7JiwpnA", "Crash Course",       "learning", "low"),
    ("UCWX3yGbODM0gHbMHcpGRMcg", "Primer",             "science",  "low"),
    ("UCJXGnMHGFBJy21VUs4EEHlQ", "CGP Grey",           "learning", "low"),
    # 财经/投资 — 中/高失真预期
    ("UCL-7uq3X-4hkDDBUMJCCEIA", "Graham Stephan",     "finance",  "high"),
    ("UCGy7SkBjcIAgTiwkXEtPnYg", "Andrei Jikh",        "finance",  "high"),
    ("UCsXVk37bltHxD1rDPwtNM8Q", "Mark Tilbury",       "finance",  "high"),
    ("UCzWQYUVCpZqtN93H8RR44Qw", "Minority Mindset",   "finance",  "high"),
    ("UC3Wn3dABlgESm8Bzn8Vamgg", "Meet Kevin",         "finance",  "high"),
    # 新闻/政治 — 中/高失真预期
    ("UCupvZG-5ko_eiXAupbDfxWw", "CNN",                "media",    "high"),
    ("UCHd_iCBDDGbMjkuqUMVqNYA", "Fox News",           "media",    "high"),
    ("UC16niRr50-MSBwiO3He_OUQ", "MSNBC",              "media",    "moderate"),
    ("UCIALMKvObZNtJ6AmdCLP7Lg", "ABC News",           "media",    "moderate"),
    ("UCYfdidRxbB8Qhf0Nx7ioOYw", "NBC News",           "media",    "moderate"),
]

async def check_channel(channel_id: str, name: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    """通过 RSS Feed 验证 YouTube 频道是否有视频"""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        r = await client.get(rss_url, timeout=10, follow_redirects=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        video_count = len(entries)

        if video_count == 0:
            return False, "0 个视频"

        # 获取最新视频标题
        latest = entries[0]
        title_el = latest.find("atom:title", ns)
        latest_title = title_el.text[:50] if title_el is not None else "unknown"

        return True, f"{video_count} 个视频，最新：{latest_title}"
    except Exception as e:
        return False, str(e)[:40]

async def main():
    print("\n" + "="*70)
    print("YouTube 第二批频道预检测")
    print(f"候选频道: {len(CANDIDATES)} 个")
    print("="*70)

    good = []
    bad = []

    async with httpx.AsyncClient() as client:
        for i, (channel_id, name, category, expected) in enumerate(CANDIDATES, 1):
            print(f"  [{i:2d}/20] {name:<25}", end="", flush=True)
            ok, info = await check_channel(channel_id, name, client)
            if ok:
                print(f"✓ {info}")
                good.append((channel_id, name, category, expected))
            else:
                print(f"✗ {info}")
                bad.append((name, info))

    print(f"\n{'='*70}")
    print(f"✓ 验证通过: {len(good)} 个")
    for channel_id, name, cat, exp in good:
        print(f"   {name:<25} id={channel_id} [{cat}] {exp}")
    print(f"\n✗ 失败: {len(bad)} 个")
    for name, reason in bad:
        print(f"   {name:<25} {reason}")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
