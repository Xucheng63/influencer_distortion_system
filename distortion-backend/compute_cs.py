#!/usr/bin/env python3
"""
compute_cs.py
从各平台已完成的 corpus_v2.jsonl 补算 Consistency Score（CS），
写入对应的 profiles_v2.json。

不需要重跑分类，直接读已有输出即可。

运行：
  cd ~/Desktop/ischool/distortion-full-project/distortion-backend
  conda activate ischool
  python compute_cs.py

CS 定义（与 aggregator.py 完全一致）：
  将账号帖子按周分桶，计算每周失真率，取标准差倒数归一化。
  std=0 → CS=1.0（高度一致）；std=0.5 → CS≈0.0（高度不稳定）
  数据不足1周 → CS=0.0；恰好1周 → CS=0.5（中立值）

CS 的使用（论文层面）：
  CS < 0.30 → 标注为低置信度，不参与跨平台比较
  CS 不参与 DI 公式，仅作为独立置信度指标报告
"""
import json, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ── 各平台的 corpus_v2.jsonl 和 profiles_v2.json 路径 ─────────────────────────
PLATFORMS = [
    {
        "name":    "RSS",
        "corpus":  Path("research_results_rss/corpus_v2.jsonl"),
        "profile": Path("research_results_rss/profiles_v2.json"),
    },
    {
        "name":    "Bluesky",
        "corpus":  Path("research_results_bluesky/corpus_v2.jsonl"),
        "profile": Path("research_results_bluesky/profiles_v2.json"),
    },
    {
        "name":    "Reddit",
        "corpus":  Path("research_results_reddit/corpus_v2.jsonl"),
        "profile": Path("research_results_reddit/profiles_v2.json"),
    },
    {
        "name":    "YouTube",
        "corpus":  Path("research_results_youtube/corpus_v2.jsonl"),
        "profile": Path("research_results_youtube/profiles_v2.json"),
    },
    {
        "name":    "Twitter",
        "corpus":  Path("research_results_twitter_v2/corpus_v2.jsonl"),
        "profile": Path("research_results_twitter_v2/profiles_v2.json"),
    },
    {
        "name":    "Weibo",
        "corpus":  Path("research_results_weibo/corpus_v2.jsonl"),
        "profile": Path("research_results_weibo/profiles_v2.json"),
    },
]


def parse_dt(s: str) -> datetime | None:
    """解析 ISO 格式时间字符串，兼容带/不带时区的格式"""
    if not s:
        return None
    try:
        # Python 3.11+ 支持 fromisoformat 直接解析 Z
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def compute_cs(posts: list[dict]) -> float:
    """
    按周分桶计算一致性分数（与 aggregator.py 逻辑完全一致）。

    posts: 每条含 posted_at（ISO字符串）和 distortion_types（list）
    """
    now = datetime.now(timezone.utc)

    weekly: dict[int, list[bool]] = defaultdict(list)
    for post in posts:
        dt = parse_dt(post.get("posted_at", ""))
        if dt is None:
            continue
        # 统一为 aware datetime
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days_ago = (now - dt).days
        if days_ago < 0:
            days_ago = 0
        week = days_ago // 7
        types = post.get("distortion_types", [])
        weekly[week].append(bool(types))

    week_rates = [sum(v) / len(v) for v in weekly.values() if v]

    if len(week_rates) >= 2:
        std = statistics.stdev(week_rates)
        cs  = max(0.0, 1.0 - std * 2)
    elif len(week_rates) == 1:
        cs = 0.5   # 数据不足，中立值
    else:
        cs = 0.0

    return round(cs, 4)


def main():
    print("\n" + "=" * 60)
    print("CS（一致性分数）补算")
    print("=" * 60)

    for plat in PLATFORMS:
        name    = plat["name"]
        corpus  = plat["corpus"]
        profile = plat["profile"]

        if not corpus.exists():
            print(f"\n[{name}] ✗ corpus 文件不存在: {corpus}")
            continue
        if not profile.exists():
            print(f"\n[{name}] ✗ profile 文件不存在: {profile}")
            continue

        # ── 读取 corpus，按 handle 分组 ───────────────────────────────────────
        handle_posts: dict[str, list] = defaultdict(list)
        with open(corpus, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                post = json.loads(line)
                handle_posts[post.get("handle", "")].append(post)

        # ── 读取 profiles ─────────────────────────────────────────────────────
        with open(profile, encoding="utf-8") as f:
            profiles = json.load(f)

        # ── 补算 CS 并写入 ────────────────────────────────────────────────────
        print(f"\n[{name}] {len(profiles)} 个账号")
        low_conf = []
        cs_values = []

        for handle, prof in profiles.items():
            posts = handle_posts.get(handle, [])

            # Twitter/Weibo 的帖子嵌在 profile 里，corpus 也有，优先用 corpus
            if not posts and "posts" in prof:
                posts = prof["posts"]

            cs = compute_cs(posts)
            prof["consistency_score"] = cs
            cs_values.append(cs)

            if cs < 0.30:
                low_conf.append(handle)

        # 写回
        with open(profile, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)

        avg_cs = round(statistics.mean(cs_values), 3) if cs_values else 0
        print(f"  平均 CS = {avg_cs}")
        print(f"  CS < 0.30（低置信度）: {len(low_conf)} 个账号")
        if low_conf:
            print(f"  → {', '.join(low_conf[:10])}" +
                  (f" ...（共{len(low_conf)}个）" if len(low_conf) > 10 else ""))
        print(f"  ✓ 已写入 {profile}")

    print("\n" + "=" * 60)
    print("所有平台 CS 补算完成")
    print("profiles_v2.json 已更新，新增 consistency_score 字段")
    print("CS < 0.30 的账号建议标注低置信度，不参与跨平台比较")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
