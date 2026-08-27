#!/usr/bin/env python3
"""
clear_reddit_rerun.py — 清掉58个 Reddit 账号的数据库记录和缓存
清完后直接运行 experiment_reddit_batch3.py 重新抓取（带正文）

运行：python clear_reddit_rerun.py
"""
import sqlite3, json
from pathlib import Path

DB_PATH    = Path("data/distortion.db")
CACHE_FILE = Path("research_results_reddit/successful_profiles.json")

def main():
    # 读取所有缓存里的 Reddit 账号
    if not CACHE_FILE.exists():
        print("✗ 缓存文件不存在")
        return

    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)

    handles = list(cache.keys())
    print(f"缓存账号: {len(handles)} 个")

    # 清数据库
    if not DB_PATH.exists():
        print(f"✗ 数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    ph = ",".join("?" * len(handles))
    c1 = conn.execute(
        f"DELETE FROM post WHERE account_id IN "
        f"(SELECT id FROM account WHERE handle IN ({ph}))", handles
    )
    c2 = conn.execute(
        f"DELETE FROM distortionprofile WHERE account_id IN "
        f"(SELECT id FROM account WHERE handle IN ({ph}))", handles
    )
    c3 = conn.execute(
        f"DELETE FROM account WHERE handle IN ({ph})", handles
    )
    conn.commit()
    conn.close()
    print(f"✓ 数据库清除：{c3.rowcount} 账号 / {c1.rowcount} 帖子 / {c2.rowcount} 档案")

    # 清缓存
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
    print(f"✓ 缓存已清空")
    print(f"\n现在运行：python experiment_reddit.py")
    print(f"（会重新抓取所有58个账号，这次包含帖子正文）")

if __name__ == "__main__":
    main()
