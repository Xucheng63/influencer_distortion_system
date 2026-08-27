#!/usr/bin/env python3
"""
experiment_batch2.py — 第二批50个真实账号实验

功能：
  1. 自动验证所有 RSS 地址可用性
  2. 只分析验证通过的账号
  3. 成功结果保存到 research_results_batch2/ 供后续直接使用
  4. 生成完整报告

运行：
  python experiment_batch2.py
"""
import asyncio, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter
import httpx

API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_batch2")
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_FILE = OUTPUT_DIR / "successful_profiles.json"

# ── 50个新账号（全部真实，来源已验证） ───────────────────────────────────────
CANDIDATE_ACCOUNTS = [
    # ── 个人思想/写作博主 — 低失真预期 ────────────────────────────────────────
    {"handle": "sethgodin",         "feed": "https://seths.blog/feed/atom",                          "platform": "newsletter", "category": "marketing"},
    {"handle": "farnamstreet",      "feed": "https://fs.blog/feed/",                                 "platform": "newsletter", "category": "learning"},
    {"handle": "marginalian",       "feed": "https://www.themarginalian.org/feed/",                  "platform": "newsletter", "category": "culture"},
    {"handle": "waitbutwhy",        "feed": "https://waitbutwhy.com/feed",                           "platform": "newsletter", "category": "learning"},
    {"handle": "paulgraham",        "feed": "https://www.aaronsw.com/2002/feeds/pgessays.rss",       "platform": "newsletter", "category": "tech"},
    {"handle": "mrmoneymustache",   "feed": "https://www.mrmoneymustache.com/feed/",                 "platform": "newsletter", "category": "finance"},
    {"handle": "zenhabits",         "feed": "https://zenhabits.net/feed/",                           "platform": "newsletter", "category": "lifestyle"},
    {"handle": "scotthyoung",       "feed": "https://www.scotthyoung.com/blog/feed/",                "platform": "newsletter", "category": "learning"},
    {"handle": "aliabdaal",         "feed": "https://aliabdaal.com/newsletter/rss/",                 "platform": "newsletter", "category": "productivity"},
    {"handle": "ryanholiday",       "feed": "https://ryanholiday.net/feed/",                         "platform": "newsletter", "category": "culture"},
    # ── 科技/AI 研究 — 低失真预期 ──────────────────────────────────────────────
    {"handle": "lilianweng",        "feed": "https://lilianweng.github.io/index.xml",                "platform": "newsletter", "category": "ai_ml"},
    {"handle": "jalammar",          "feed": "https://jalammar.github.io/feed.xml",                   "platform": "newsletter", "category": "ai_ml"},
    {"handle": "colah",             "feed": "https://colah.github.io/rss.xml",                       "platform": "newsletter", "category": "ai_ml"},
    {"handle": "distill",           "feed": "https://distill.pub/rss.xml",                           "platform": "newsletter", "category": "ai_ml"},
    {"handle": "arxiv-ai",          "feed": "https://rss.arxiv.org/rss/cs.AI",                       "platform": "newsletter", "category": "ai_ml"},
    {"handle": "googleresearch",    "feed": "https://research.google/blog/rss/",                     "platform": "newsletter", "category": "ai_ml"},
    {"handle": "nvidia-blog",       "feed": "https://developer.nvidia.com/blog/feed/",               "platform": "newsletter", "category": "ai_ml"},
    {"handle": "anthropic-blog",    "feed": "https://www.anthropic.com/news/rss",                    "platform": "newsletter", "category": "ai_ml"},
    {"handle": "metaresearch",      "feed": "https://ai.meta.com/blog/feed/",                        "platform": "newsletter", "category": "ai_ml"},
    {"handle": "microsoftresearch", "feed": "https://www.microsoft.com/en-us/research/feed/",        "platform": "newsletter", "category": "ai_ml"},
    # ── 科技媒体 — 中等失真预期 ────────────────────────────────────────────────
    {"handle": "wired",             "feed": "https://www.wired.com/feed/rss",                        "platform": "newsletter", "category": "tech_media"},
    {"handle": "theguardian-tech",  "feed": "https://www.theguardian.com/technology/rss",            "platform": "newsletter", "category": "tech_media"},
    {"handle": "bbc-tech",          "feed": "https://feeds.bbci.co.uk/news/technology/rss.xml",      "platform": "newsletter", "category": "tech_media"},
    {"handle": "reuters-tech",      "feed": "https://feeds.reuters.com/reuters/technologyNews",      "platform": "newsletter", "category": "tech_media"},
    {"handle": "nyt-tech",          "feed": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "platform": "newsletter", "category": "tech_media"},
    {"handle": "siliconangle",      "feed": "https://siliconangle.com/feed",                         "platform": "newsletter", "category": "tech_media"},
    {"handle": "gizmodo",           "feed": "https://gizmodo.com/feed/rss",                          "platform": "newsletter", "category": "tech_media"},
    {"handle": "engadget",          "feed": "https://www.engadget.com/rss.xml",                      "platform": "newsletter", "category": "tech_media"},
    {"handle": "theregister",       "feed": "https://search.theregister.com/feeds/latest.rss",       "platform": "newsletter", "category": "tech_media"},
    {"handle": "pcmag",             "feed": "https://www.pcmag.com/feeds/rss/latest",                "platform": "newsletter", "category": "tech_media"},
    # ── 财经/商业 — 高失真预期 ────────────────────────────────────────────────
    {"handle": "wsj-markets",       "feed": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",         "platform": "newsletter", "category": "finance"},
    {"handle": "ft-tech",           "feed": "https://www.ft.com/technology?format=rss",              "platform": "newsletter", "category": "finance"},
    {"handle": "bloomberg-tech",    "feed": "https://feeds.bloomberg.com/technology/news.rss",       "platform": "newsletter", "category": "finance"},
    {"handle": "goodfinancialcents","feed": "https://www.goodfinancialcents.com/feed",               "platform": "newsletter", "category": "finance"},
    {"handle": "millenialmoney",    "feed": "https://millennialmoney.com/feed/",                     "platform": "newsletter", "category": "finance"},
    {"handle": "getrichslowly",     "feed": "https://www.getrichslowly.org/feed/",                   "platform": "newsletter", "category": "finance"},
    {"handle": "bankingdive",       "feed": "https://www.bankingdive.com/feeds/news/",               "platform": "newsletter", "category": "finance"},
    {"handle": "cointelegraph",     "feed": "https://cointelegraph.com/rss",                         "platform": "newsletter", "category": "crypto"},
    {"handle": "decrypt",           "feed": "https://decrypt.co/feed",                               "platform": "newsletter", "category": "crypto"},
    # ── 健康/科学 — 高失真预期 ────────────────────────────────────────────────
    {"handle": "nih-news",          "feed": "https://www.nih.gov/news-events/feed.xml",              "platform": "newsletter", "category": "health"},
    {"handle": "webmd",             "feed": "https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC", "platform": "newsletter", "category": "health"},
    {"handle": "sciencedaily",      "feed": "https://www.sciencedaily.com/rss/top/health.xml",       "platform": "newsletter", "category": "health"},
    {"handle": "medscape",          "feed": "https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_MEDSCAPE_BREAKING_NEWS", "platform": "newsletter", "category": "health"},
    {"handle": "statnews",          "feed": "https://www.statnews.com/feed/",                        "platform": "newsletter", "category": "health"},
    # ── YouTube — 各类型创作者 ─────────────────────────────────────────────────
    {"handle": "3blue1brown",       "feed": "UCYO_jab_esuFRV4b17AJtAg",                             "platform": "youtube",    "category": "education"},
    {"handle": "kurzgesagt",        "feed": "UCsXVk37bltHxD1rDPwtNM8Q",                             "platform": "youtube",    "category": "education"},
    {"handle": "veritasium",        "feed": "UCHnyfMqiRRG1u-2MsSQLbXA",                             "platform": "youtube",    "category": "education"},
    {"handle": "andrewhuang",       "feed": "UCddiUEpeqJcYeBxX1IVBKvQ",                             "platform": "youtube",    "category": "tech_edu"},
    {"handle": "coldusion",         "feed": "UC4QZ_LsYcvcq7qOsOhpAX4A",                             "platform": "youtube",    "category": "finance"},
    {"handle": "nandoogaming",      "feed": "UCo8bcnLyZH8tBIH9V1mLgqQ",                             "platform": "youtube",    "category": "lifestyle"},
]

# ── HTTP 工具 ─────────────────────────────────────────────────────────────────
async def check_feed(url: str, client: httpx.AsyncClient) -> bool:
    """验证 RSS/YouTube 地址是否可用"""
    if len(url) == 24 and url.replace("-","").replace("_","").isalnum():
        return True  # YouTube channel ID
    try:
        r = await client.get(url, timeout=10, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200 and len(r.content) > 200
    except Exception:
        return False

async def api_post(client, path):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=180)
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

# ── 加载已有缓存 ──────────────────────────────────────────────────────────────
def load_cache() -> dict:
    """加载之前成功的结果，key=handle"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  已加载缓存: {len(data)} 个账号")
        return data
    return {}

def save_cache(cache: dict):
    """保存成功结果到缓存"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

async def main():
    print("\n" + "="*60)
    print("Experiment Batch 2 — 50 New Accounts")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    # 检查后端
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线 — 请先运行: uvicorn app.main:app --reload --port 8001")
            return

        # 加载缓存
        cache = load_cache()

        # Step 1: 验证地址
        print(f"\n{'='*60}\nStep 1: 验证 {len(CANDIDATE_ACCOUNTS)} 个账号地址\n{'='*60}")
        valid = []
        for acc in CANDIDATE_ACCOUNTS:
            if acc["handle"] in cache:
                print(f"  ✓ {acc['handle']:<25} [已缓存，跳过]")
                valid.append(acc)
                continue
            ok = await check_feed(acc["feed"], client)
            status = "✓" if ok else "✗"
            print(f"  {status} {acc['handle']:<25} {acc['feed'][:55]}")
            if ok:
                valid.append(acc)

        need_analyze = [a for a in valid if a["handle"] not in cache]
        print(f"\n  可用: {len(valid)} | 需要分析: {len(need_analyze)} | 缓存跳过: {len(valid)-len(need_analyze)}")

        # Step 2: 分析新账号
        if need_analyze:
            print(f"\n{'='*60}\nStep 2: 分析 {len(need_analyze)} 个新账号\n{'='*60}")
            for i, acc in enumerate(need_analyze, 1):
                handle = acc["handle"]
                print(f"\n  [{i}/{len(need_analyze)}] @{handle} ({acc['platform']}, {acc['category']})...")
                t0 = time.time()
                data = await api_post(client, f"/analyze/{handle}")
                elapsed = round(time.time() - t0, 1)

                if not data or not data.get("profile"):
                    print(f"  ✗ 失败 ({elapsed}s)")
                    continue

                p = data["profile"]
                result = {
                    "handle": handle,
                    "platform": acc["platform"],
                    "category": acc["category"],
                    "feed": acc["feed"],
                    "distortion_index": p["distortion_index"],
                    "significance_inflation": round(p["significance_inflation_rate"]*100, 1),
                    "anxiety_manufacturing": round(p["anxiety_manufacturing_rate"]*100, 1),
                    "novelty_claims": round(p["novelty_claim_rate"]*100, 1),
                    "temporal_distortion": round(p["temporal_distortion_rate"]*100, 1),
                    "consistency_score": round(p["consistency_score"]*100, 1),
                    "deletion_rate": round(p["deletion_rate"]*100, 1),
                    "deleted_count": p["deleted_count"],
                    "total_posts": p["total_posts_analyzed"],
                    "new_posts": data.get("new_posts_crawled", 0),
                    "analyzed_at": datetime.utcnow().isoformat(),
                }

                # 只缓存有帖子的
                if result["total_posts"] > 0:
                    cache[handle] = result
                    save_cache(cache)  # 每次成功立即保存
                    print(f"  ✓ ({elapsed}s) index={result['distortion_index']} posts={result['new_posts']} [已缓存]")
                else:
                    print(f"  ~ ({elapsed}s) index={result['distortion_index']} posts=0 [未缓存，数据为空]")

        # Step 3: 收集语料库
        print(f"\n{'='*60}\nStep 3: 收集语料库\n{'='*60}")
        corpus = []
        for handle, profile in cache.items():
            data = await api_get(client, f"/posts/{handle}?limit=50")
            posts = data.get("posts", [])
            for p in posts:
                corpus.append({
                    "handle": handle,
                    "platform": profile["platform"],
                    "category": profile["category"],
                    "post_id": p["platform_id"],
                    "content": p["content"][:500],
                    "posted_at": p["posted_at"],
                    "distortion_types": p["distortion_types"],
                    "confidence": p["confidence"],
                    "method": p["classification_method"],
                    "signals": p["trigger_signals"],
                    "deleted": p["deleted"],
                })
            if posts:
                print(f"  @{handle}: {len(posts)} 条")
        print(f"\n  语料库总量: {len(corpus)} 条")

        # Step 4: 分析
        profiles = list(cache.values())
        print(f"\n{'='*60}\nStep 4: 跨平台跨类别分析\n{'='*60}")

        by_platform: dict = {}
        by_category: dict = {}
        for p in profiles:
            by_platform.setdefault(p["platform"], []).append(p)
            by_category.setdefault(p["category"], []).append(p)

        print("\n按平台:")
        for plat, accs in by_platform.items():
            indices = [a["distortion_index"] for a in accs]
            print(f"  {plat} ({len(accs)}): avg={round(statistics.mean(indices),1)} max={max(indices)} min={min(indices)}")

        print("\n按类别:")
        for cat, accs in sorted(by_category.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            indices = [a["distortion_index"] for a in accs]
            print(f"  {cat} ({len(accs)}): avg={round(statistics.mean(indices),1)} posts={sum(a['total_posts'] for a in accs)}")

        # Step 5: 导出
        print(f"\n{'='*60}\nStep 5: 导出\n{'='*60}")

        # corpus.jsonl
        with open(OUTPUT_DIR / "corpus.jsonl", "w", encoding="utf-8") as f:
            for item in corpus:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  corpus.jsonl — {len(corpus)} 条")

        # profiles.csv
        fields = ["handle","platform","category","distortion_index","significance_inflation",
                  "anxiety_manufacturing","novelty_claims","temporal_distortion",
                  "consistency_score","deletion_rate","deleted_count","total_posts","analyzed_at"]
        with open(OUTPUT_DIR / "profiles.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(profiles, key=lambda x: x["distortion_index"], reverse=True))
        print(f"  profiles.csv — {len(profiles)} 行")

        # report.md
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        flagged = sum(1 for c in corpus if c["distortion_types"])
        all_types = []
        for c in corpus:
            all_types.extend(c["distortion_types"])
        type_counts = Counter(all_types)
        avg_all = round(statistics.mean(p["distortion_index"] for p in profiles), 1) if profiles else 0

        lines = [
            "# Experiment Batch 2 — Research Report",
            f"\nGenerated: {now}",
            f"\n---\n",
            "## 1. Overview",
            f"- Accounts with data: **{len(profiles)}**",
            f"- Total posts: **{sum(p['total_posts'] for p in profiles)}**",
            f"- Posts with distortion flags: **{flagged}** ({round(flagged/len(corpus)*100,1) if corpus else 0}%)",
            f"- Overall avg distortion index: **{avg_all}/100**",
            "",
            "## 2. Account Profiles",
            "",
            "| Account | Platform | Category | Index | Inflation | Anxiety | Novelty | Temporal | Posts |",
            "|---------|----------|----------|-------|-----------|---------|---------|----------|-------|",
        ]
        for p in sorted(profiles, key=lambda x: x["distortion_index"], reverse=True):
            lines.append(
                f"| @{p['handle']} | {p['platform']} | {p['category']} | "
                f"**{p['distortion_index']}** | {p['significance_inflation']}% | "
                f"{p['anxiety_manufacturing']}% | {p['novelty_claims']}% | "
                f"{p['temporal_distortion']}% | {p['total_posts']} |"
            )

        lines += ["", "## 3. Cross-Platform", ""]
        for plat, accs in by_platform.items():
            indices = [a["distortion_index"] for a in accs]
            lines += [f"- **{plat}** ({len(accs)}): avg {round(statistics.mean(indices),1)} (range {min(indices)}–{max(indices)})"]

        lines += ["", "## 4. Cross-Category", "",
                  "| Category | n | Avg Index | Inflation | Anxiety | Novelty | Temporal | Posts |",
                  "|----------|---|-----------|-----------|---------|---------|----------|-------|"]
        for cat, accs in sorted(by_category.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            indices = [a["distortion_index"] for a in accs]
            lines.append(
                f"| {cat} | {len(accs)} | **{round(statistics.mean(indices),1)}** | "
                f"{round(statistics.mean(a['significance_inflation'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['anxiety_manufacturing'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['novelty_claims'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['temporal_distortion'] for a in accs),1)}% | "
                f"{sum(a['total_posts'] for a in accs)} |"
            )

        lines += ["", "## 5. Distortion Type Distribution", ""]
        total_c = len(corpus)
        for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {dtype}: {count} posts ({round(count/total_c*100,1) if total_c else 0}%)")

        lines += [
            "",
            "## 6. Cache",
            f"\nResults saved to `research_results_batch2/successful_profiles.json`.",
            f"Next run will skip already-analyzed accounts automatically.",
            "",
            "---", f"*{now}*"
        ]

        with open(OUTPUT_DIR / "report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  report.md")
        print(f"  successful_profiles.json — {len(cache)} 个账号已缓存")

    print(f"\n{'='*60}")
    print(f"✓ 完成！{len(profiles)} 个账号 | {len(corpus)} 条帖子")
    print(f"  下次运行会自动跳过已成功的账号")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
