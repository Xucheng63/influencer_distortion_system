#!/usr/bin/env python3
"""
recompute_di.py
用等权重公式重新计算各平台 profiles_v2.json 里的 distortion_index。
不调用 GPT，直接读取已有的五维度比率重算，几秒完成。

运行：
  cd ~/Desktop/ischool/distortion-full-project/distortion-backend
  conda activate ischool
  python recompute_di.py
"""
import json, statistics
from pathlib import Path

PLATFORMS = [
    {"name": "Weibo",   "profile": Path("research_results_weibo/profiles_v2.json")},
    {"name": "Bluesky", "profile": Path("research_results_bluesky/profiles_v2.json")},
    {"name": "Reddit",  "profile": Path("research_results_reddit/profiles_v2.json")},
    {"name": "Twitter", "profile": Path("research_results_twitter_v2/profiles_v2.json")},
    {"name": "YouTube", "profile": Path("research_results_youtube/profiles_v2.json")},
    {"name": "RSS",     "profile": Path("research_results_rss/profiles_v2.json")},
]


def compute_di(prof: dict) -> int:
    """
    等权重算术平均（方案C）。
    五维度各自独立报告为主要结果；
    DI 作为辅助汇总指标，采用等权重以避免主观权重假设。
    参考：Wang & Strong (1996) 多维度信息质量等权重框架。
    """
    dims = [
        prof.get("significance_inflation_rate", 0) / 100,
        prof.get("anxiety_manufacturing_rate",  0) / 100,
        prof.get("novelty_claims_rate",          0) / 100,
        prof.get("loaded_language_rate",         0) / 100,
        prof.get("temporal_distortion_rate",     0) / 100,
    ]
    return min(100, round(sum(dims) / len(dims) * 100))


def main():
    print("\n" + "=" * 60)
    print("DI 重新计算 — 等权重公式")
    print("公式: DI = (SI + AM + NC + LL + TD) / 5")
    print("=" * 60)

    for plat in PLATFORMS:
        name    = plat["name"]
        profile = plat["profile"]

        if not profile.exists():
            print(f"\n[{name}] ✗ 文件不存在: {profile}")
            continue

        with open(profile, encoding="utf-8") as f:
            profiles = json.load(f)

        old_dis, new_dis = [], []

        for handle, prof in profiles.items():
            old_di = prof.get("distortion_index", 0)
            new_di = compute_di(prof)
            prof["distortion_index"] = new_di
            old_dis.append(old_di)
            new_dis.append(new_di)

        with open(profile, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)

        print(f"\n[{name}] {len(profiles)} 个账号")
        print(f"  旧 DI 平均: {round(statistics.mean(old_dis), 1)}")
        print(f"  新 DI 平均: {round(statistics.mean(new_dis), 1)}")
        print(f"  最高: {max(new_dis)} ({max(profiles, key=lambda h: profiles[h]['distortion_index'])})")
        print(f"  ✓ 已写入 {profile}")

    print("\n" + "=" * 60)
    print("全部完成，六个平台 profiles_v2.json 已更新")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
