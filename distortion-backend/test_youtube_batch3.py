#!/usr/bin/env python3
"""
test_youtube_batch3.py — 预检测20个新 YouTube 候选频道（修正channel ID版）
运行：python test_youtube_batch3.py
"""
import asyncio
import httpx
from xml.etree import ElementTree as ET

CANDIDATES = [
    # 修正之前404的频道（正确channel ID）
    ("UC2C_jShtL725hvbm1arSV9w", "CGP Grey",         "learning", "low"),
    ("UCV6KDgJskWaEckne5aPA0aQ", "Graham Stephan",   "finance",  "high"),
    ("UCnMn9H2DpNwyGF4wXRFMHLA", "Primer",           "science",  "low"),
    ("UCHd_iCBDDGbMjkuqUMVqNYA", "Fox News",         "media",    "high"),
    ("UCeY0bbntWzzMn2MK6SFAmRg", "NBC News",         "media",    "moderate"),
    ("UC16niRr50-MSBwiO3He_OUQ", "MSNBC",            "media",    "moderate"),
    # 新增频道
    ("UCo8bcnLyZH8tBIH9V1mLgqQ", "Nando v Movies",  "culture",  "moderate"),
    ("UCXuqSBlHAE6Xw-yeJA0Tunw", "Linus Tech Tips",  "tech",     "low"),
    ("UC7cs8q-gJRlGwj4A8OmCmXg", "Mark Rober",       "science",  "low"),
    ("UCY1kMZp36IQSyNx_9h4mpCg", "Ted-Ed",           "learning", "low"),
    ("UCBcRF18a7Qf58cCRy5xuWwQ", "MKBHD",            "tech",     "low"),
    ("UCXvYKGdxgk-oDSMG3lFCEQQ", "Johnny Harris",    "media",    "moderate"),
    ("UC1yBKRuGpC1tSM73A0ZjYjQ", "The Young Turks",  "politics", "high"),
    ("UCi2LoI3GQV_k-3LZqRGw7Rw", "The Daily Show",   "politics", "high"),
    ("UCaXkIU1QidjPwiAYu6GcHjg", "VICE News",        "media",    "high"),
    ("UC5fdssPqmmGhkhsJi4VcckA", "Polymatter",       "learning", "low"),
    ("UCnUYZLuoy1rq1aVMwx4aTzw", "Andrej Karpathy",  "ai_ml",    "low"),
    ("UCZHmQk67mSJgfCCTn7xBfew", "Two Minute Papers","ai_ml",    "low"),
    ("UCGy7SkBjcIAgTiwkXEtPnYg", "Andrei Jikh",      "finance",  "high"),
    ("UCupvZG-5ko_eiXAupbDfxWw", "CNN",              "media",    "high"),
]

async def check_channel(channel_id: str, name: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        r = await client.get(rss_url, timeout=10, follow_redirects=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            return False, "0 个视频"
        title_el = entries[0].find("atom:title", ns)
        latest = title_el.text[:50] if title_el is not None else "unknown"
        return True, f"{len(entries)} 个视频，最新：{latest}"
    except Exception as e:
        return False, str(e)[:40]

async def main():
    print("\n" + "="*70)
    print("YouTube 第三批频道预检测（修正ID版）")
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
        print(f'   ("{channel_id}", "{name}", "{cat}", "{exp}"),')
    print(f"\n✗ 失败: {len(bad)} 个")
    for name, reason in bad:
        print(f"   {name}: {reason}")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
