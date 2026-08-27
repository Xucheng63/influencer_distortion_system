#!/usr/bin/env python3
"""
experiment_weibo.py — 微博平台实验脚本

使用 Playwright 浏览器抓取微博用户帖子，无需 API key 和登录。
成功结果自动保存到缓存，中断后可继续。

运行：python experiment_weibo.py
"""
import asyncio, json, csv, re, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_weibo")
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_FILE = OUTPUT_DIR / "successful_profiles.json"

# ── 50个真实微博用户（UID + 分类）────────────────────────────────────────────
# handle 格式：weibo/{uid}，系统自动路由
CANDIDATE_ACCOUNTS = [
    # 已验证有帖子的11个账号（find_weibo_uids.py 验证通过）
    {"handle": "weibo/2853016445", "name": "钛媒体APP",   "category": "tech_cn",    "expected": "moderate"},
    {"handle": "weibo/1645823934", "name": "李大霄",      "category": "finance_cn", "expected": "high"},
    {"handle": "weibo/1191965271", "name": "三联生活周刊", "category": "culture_cn", "expected": "low"},
    {"handle": "weibo/2868676035", "name": "财联社APP",   "category": "finance_cn", "expected": "moderate"},
    {"handle": "weibo/1191050205", "name": "水皮",        "category": "finance_cn", "expected": "high"},
    {"handle": "weibo/2803301701", "name": "人民日报",    "category": "media_cn",   "expected": "low"},
    {"handle": "weibo/2656274875", "name": "央视新闻",    "category": "media_cn",   "expected": "low"},
    {"handle": "weibo/1639498782", "name": "南方周末",    "category": "media_cn",   "expected": "moderate"},
    {"handle": "weibo/5883677894", "name": "券商中国",    "category": "finance_cn", "expected": "high"},
    {"handle": "weibo/5104880035", "name": "科普中国",    "category": "science_cn", "expected": "low"},
    {"handle": "weibo/1195230310", "name": "何炅",        "category": "culture_cn", "expected": "moderate"},
]
# ── Weibo 抓取（直接调用，不经过后端）───────────────────────────────────────
def clean_text(raw: str) -> str:
    raw = raw.replace('&lt;','<').replace('&gt;','>').replace('&amp;','&')
    raw = raw.replace('&quot;','"').replace('&#39;',"'").replace('&nbsp;',' ')
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw

def scrape_weibo_user_sync(uid: str, max_posts: int = 50) -> list[dict]:
    """用 Playwright 抓取微博用户帖子"""
    from playwright.sync_api import sync_playwright
    import hashlib

    posts = []
    seen = set()
    containerid = f"107603{uid}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
            viewport={"width": 390, "height": 844},
        )
        page = context.new_page()
        try:
            # 初始化 Session
            page.goto("https://m.weibo.cn", timeout=20000)
            time.sleep(4)

            for page_num in range(1, 6):
                url = (
                    f"https://m.weibo.cn/api/container/getIndex"
                    f"?uid={uid}&type=uid&value={uid}"
                    f"&containerid={containerid}&page={page_num}"
                )
                page.goto(url, timeout=15000)
                time.sleep(2.5)
                try:
                    page_content = page.content()
                except Exception:
                    time.sleep(2)
                    page_content = page.content()
                content = page_content
                b = content.find("{")
                e = content.rfind("}") + 1
                if b < 0:
                    break
                try:
                    data = json.loads(content[b:e])
                except Exception:
                    break

                if data.get("ok") != 1:
                    break

                cards = data.get("data", {}).get("cards", [])
                new_count = 0
                for card in cards:
                    mblog = card.get("mblog", {})
                    if not mblog:
                        for sub in card.get("card_group", []):
                            if sub.get("mblog"):
                                mblog = sub["mblog"]
                                break
                    if not mblog:
                        continue
                    mid = mblog.get("id", "") or mblog.get("mid", "")
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    text = clean_text(mblog.get("text", ""))
                    if not text or len(text) < 3:
                        continue
                    created = mblog.get("created_at", "")
                    try:
                        from email.utils import parsedate_to_datetime
                        posted_dt = parsedate_to_datetime(created).replace(tzinfo=None)
                    except Exception:
                        posted_dt = datetime.utcnow()

                    posts.append({
                        "platform_id": mid,
                        "content": text[:500],
                        "posted_at": posted_dt.isoformat(),
                        "likes": mblog.get("attitudes_count", 0),
                        "comments": mblog.get("comments_count", 0),
                        "reposts": mblog.get("reposts_count", 0),
                    })
                    new_count += 1
                    if len(posts) >= max_posts:
                        break

                if new_count == 0 or len(posts) >= max_posts:
                    break

        except Exception as e:
            print(f"  [scraper error] {e}")
        finally:
            browser.close()

    return posts

# ── 缓存工具 ──────────────────────────────────────────────────────────────────
def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  已加载缓存: {len(data)} 个账号")
        return data
    return {}

def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ── 主流程 ────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "="*60)
    print("微博平台实验")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"候选账号: {len(CANDIDATE_ACCOUNTS)}")
    print("="*60)

    cache = load_cache()

    # 去重（同一 UID 可能有多个条目）
    seen_uids = set()
    unique_accounts = []
    for acc in CANDIDATE_ACCOUNTS:
        uid = acc["handle"].split("/")[1]
        if uid not in seen_uids:
            seen_uids.add(uid)
            unique_accounts.append(acc)
    print(f"去重后: {len(unique_accounts)} 个唯一账号")

    # Step 1: 分析
    print(f"\n{'='*60}\n分析账号\n{'='*60}")

    corpus = []
    loop = asyncio.get_event_loop()

    for i, acc in enumerate(unique_accounts, 1):
        handle = acc["handle"]
        uid = handle.split("/")[1]
        name = acc["name"]

        if handle in cache:
            print(f"  [{i:2d}/{len(unique_accounts)}] {name:<12} [已缓存，跳过]")
            # 读取缓存帖子加入语料库
            cached = cache[handle]
            for p in cached.get("posts", []):
                corpus.append({**p, "handle": handle, "name": name,
                               "category": acc["category"], "platform": "weibo"})
            continue

        print(f"  [{i:2d}/{len(unique_accounts)}] {name:<12} (uid={uid})...", end="", flush=True)
        t0 = time.time()

        # 在线程池中运行 Playwright（同步）
        posts = await loop.run_in_executor(None, scrape_weibo_user_sync, uid, 50)
        elapsed = round(time.time() - t0, 1)

        if not posts:
            print(f" ~ ({elapsed}s) 0 帖子 [跳过]")
            continue

        # 简单失真分析（关键词规则）
        distortion_keywords = {
            "significance_inflation": ["震惊","重磅","突发","紧急","最新","大消息","惊天","史上最"],
            "anxiety_manufacturing":  ["危险","崩溃","末日","完了","倒塌","危机","恐慌","崩了"],
            "novelty_claims":         ["首次","独家","全球首","史无前例","第一次","破纪录","前所未有"],
            "temporal_distortion":    ["回顾","当年","历史上的今天","多年前","旧事"],
        }

        dim_counts = {k: 0 for k in distortion_keywords}
        for post in posts:
            text = post["content"]
            for dim, keywords in distortion_keywords.items():
                if any(kw in text for kw in keywords):
                    dim_counts[dim] += 1

        total = len(posts)
        rates = {k: round(v/total*100, 1) for k, v in dim_counts.items()}
        distortion_index = min(100, sum(dim_counts.values()) * 3)

        result = {
            "handle": handle,
            "name": name,
            "platform": "weibo",
            "category": acc["category"],
            "expected": acc["expected"],
            "uid": uid,
            "distortion_index": distortion_index,
            **rates,
            "total_posts": total,
            "analyzed_at": datetime.utcnow().isoformat(),
            "posts": posts[:50],
        }

        cache[handle] = result
        save_cache(cache)

        for p in posts:
            corpus.append({**p, "handle": handle, "name": name,
                          "category": acc["category"], "platform": "weibo"})

        print(f" ✓ ({elapsed}s) {total}帖 index={distortion_index} infl={rates['significance_inflation']}% anx={rates['anxiety_manufacturing']}% [已缓存]")

    # Step 2: 分析结果
    profiles = [v for v in cache.values() if "distortion_index" in v]
    print(f"\n{'='*60}\n分析结果\n{'='*60}")
    print(f"成功账号: {len(profiles)}")
    print(f"总帖子数: {sum(p['total_posts'] for p in profiles)}")

    if profiles:
        indices = [p["distortion_index"] for p in profiles]
        print(f"平均失真指数: {round(statistics.mean(indices), 1)}")
        print(f"最高: {max(indices)} ({max(profiles, key=lambda x:x['distortion_index'])['name']})")
        print(f"最低: {min(indices)} ({min(profiles, key=lambda x:x['distortion_index'])['name']})")

        by_cat = defaultdict(list)
        for p in profiles:
            by_cat[p["category"]].append(p)
        print("\n按类别:")
        for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            idx = [a["distortion_index"] for a in accs]
            print(f"  {cat:<15} n={len(accs):2d} avg={round(statistics.mean(idx),1):5.1f}")

        print("\n五维度触发:")
        for dim in ["significance_inflation","anxiety_manufacturing","novelty_claims","temporal_distortion"]:
            flagged = sorted([p for p in profiles if p.get(dim, 0) > 0], key=lambda x: -x.get(dim, 0))
            if flagged:
                print(f"  {dim}: {len(flagged)}个账号，最高 {flagged[0][dim]}% ({flagged[0]['name']})")

    # Step 3: 导出
    print(f"\n{'='*60}\n导出\n{'='*60}")

    # corpus.jsonl（不含 posts 字段）
    with open(OUTPUT_DIR/"corpus.jsonl", "w", encoding="utf-8") as f:
        for item in corpus:
            row = {k: v for k, v in item.items() if k != "posts"}
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    print(f"  corpus.jsonl — {len(corpus)} 条")

    # profiles.csv
    fields = ["handle","name","platform","category","expected","distortion_index",
              "significance_inflation","anxiety_manufacturing","novelty_claims",
              "temporal_distortion","total_posts","analyzed_at"]
    with open(OUTPUT_DIR/"profiles.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(profiles, key=lambda x: x["distortion_index"], reverse=True))
    print(f"  profiles.csv — {len(profiles)} 行")

    # report.md
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 微博平台实验报告",
        f"\nGenerated: {now}\n---\n",
        "## 1. 概览",
        f"- 平台: **微博**（中文短内容，140-2000字）",
        f"- 成功账号: **{len(profiles)}**",
        f"- 总帖子数: **{sum(p['total_posts'] for p in profiles)}**",
    ]
    if profiles:
        avg = round(statistics.mean(p['distortion_index'] for p in profiles), 1)
        lines += [f"- 平均失真指数: **{avg}/100**", ""]
        lines += ["## 2. 账号档案", "",
                  "| 账号 | 类别 | 预期 | 失真指数 | 膨胀 | 焦虑 | 新颖 | 时间 | 帖子数 |",
                  "|------|------|------|---------|------|------|------|------|--------|"]
        for p in sorted(profiles, key=lambda x: x["distortion_index"], reverse=True):
            lines.append(
                f"| {p['name']} | {p['category']} | {p['expected']} | "
                f"**{p['distortion_index']}** | {p.get('significance_inflation',0)}% | "
                f"{p.get('anxiety_manufacturing',0)}% | {p.get('novelty_claims',0)}% | "
                f"{p.get('temporal_distortion',0)}% | {p['total_posts']} |"
            )

    lines += ["", "## 3. 与其他平台对比", "",
              "| 平台 | 格式 | 语言 | 平均失真指数 |",
              "|------|------|------|------------|",
              "| RSS/Newsletter | 长文 | 英/中 | 10.2 |",
              "| YouTube | 视频字幕 | 英文 | 9.0 |",
              "| Bluesky | 短帖(300字) | 英文 | 13.8 |",
              "| Reddit | 社区帖子 | 英文 | 14.3 |",
              f"| **微博** | **短帖(140-2000字)** | **中文** | **{avg if profiles else 'TBD'}** |",
              "", "---", f"*{now}*"]

    with open(OUTPUT_DIR/"report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  report.md")
    print(f"  successful_profiles.json — {len(cache)} 个账号")

    print(f"\n{'='*60}")
    print(f"✓ 完成！{len(profiles)} 个账号 | {len(corpus)} 条帖子")
    print(f"  结果保存在 {OUTPUT_DIR}/")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
