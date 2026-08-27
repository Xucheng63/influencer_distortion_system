#!/usr/bin/env python3
"""
run_experiment_50.py — 50账号批量研究实验脚本

功能：
  1. 自动验证 RSS 地址是否可用（跳过失败的）
  2. 已分析过的账号直接读缓存，不重复分析
  3. 批量分析全部可用账号
  4. 收集语料库、跨平台对比、导出完整报告

运行：
  python3 run_experiment_50.py

输出：research_results_50/
"""

import asyncio, json, csv, os, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter
import httpx

# ── 配置 ──────────────────────────────────────────────────────────────────────
API_BASE   = "http://localhost:8001/api"
OUTPUT_DIR = Path("research_results_50")
OUTPUT_DIR.mkdir(exist_ok=True)

# 已完成的账号（直接合并，不重新分析）
DONE_ACCOUNTS = [
    {"handle": "simonwillison", "platform": "newsletter", "category": "tech",        "distortion_index": 14, "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 3.3,  "temporal_distortion": 3.3,  "consistency_score": 86.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 30, "status": "done"},
    {"handle": "dhh",           "platform": "newsletter", "category": "tech",        "distortion_index": 15, "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 9,  "status": "done"},
    {"handle": "ruanyifeng",    "platform": "newsletter", "category": "tech_cn",     "distortion_index": 15, "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 6,  "status": "done"},
    {"handle": "lesswrong",     "platform": "newsletter", "category": "rationalism", "distortion_index": 8,  "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10, "status": "done"},
    {"handle": "astralcodexten","platform": "newsletter", "category": "rationalism", "distortion_index": 15, "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 100.0, "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20, "status": "done"},
    {"handle": "karpathy",      "platform": "newsletter", "category": "ai_ml",       "distortion_index": 0,  "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 0.0,   "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 10, "status": "done"},
    {"handle": "fireship",      "platform": "youtube",    "category": "tech_edu",    "distortion_index": 11, "significance_inflation": 5.0, "anxiety_manufacturing": 0.0, "novelty_claims": 5.0,  "temporal_distortion": 10.0, "consistency_score": 50.0,  "deletion_rate": 4.8, "deleted_count": 1, "total_posts": 20, "status": "done"},
    {"handle": "ycombinator",   "platform": "youtube",    "category": "startup",     "distortion_index": 8,  "significance_inflation": 0.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20, "status": "done"},
    {"handle": "lexfridman",    "platform": "youtube",    "category": "ai_ml",       "distortion_index": 9,  "significance_inflation": 5.0, "anxiety_manufacturing": 0.0, "novelty_claims": 0.0,  "temporal_distortion": 0.0,  "consistency_score": 50.0,  "deletion_rate": 0.0, "deleted_count": 0, "total_posts": 20, "status": "done"},
]

# 50个新账号候选（分四类：tech/AI低失真、媒体中失真、财经高失真、健康/生活类）
CANDIDATE_ACCOUNTS = [
    # ── Tech / AI 个人博主 — 低失真预期 ───────────────────────────────────────
    {"handle": "paulgraham",        "feed": "https://www.aaronsw.com/2002/feeds/pgessays.rss",           "platform": "newsletter", "category": "tech"},
    {"handle": "martinfowler",      "feed": "https://martinfowler.com/feed.atom",                         "platform": "newsletter", "category": "tech"},
    {"handle": "joelonsoftware",    "feed": "https://www.joelonsoftware.com/feed/",                       "platform": "newsletter", "category": "tech"},
    {"handle": "overreacted",       "feed": "https://overreacted.io/rss.xml",                             "platform": "newsletter", "category": "tech"},
    {"handle": "sebastianraschka",  "feed": "https://sebastianraschka.com/rss_feed.xml",                 "platform": "newsletter", "category": "ai_ml"},
    {"handle": "swyx",              "feed": "https://www.swyx.io/rss.xml",                               "platform": "newsletter", "category": "tech"},
    {"handle": "stratechery",       "feed": "https://stratechery.com/feed/",                             "platform": "newsletter", "category": "tech"},
    {"handle": "oneusefulthing",    "feed": "https://oneusefulthing.substack.com/feed",                  "platform": "newsletter", "category": "ai_ml"},
    {"handle": "latentspace",       "feed": "https://latent.space/feed",                                 "platform": "newsletter", "category": "ai_ml"},
    {"handle": "importai",          "feed": "https://importai.substack.com/feed",                        "platform": "newsletter", "category": "ai_ml"},
    {"handle": "pragmaticengineer", "feed": "https://newsletter.pragmaticengineer.com/feed",             "platform": "newsletter", "category": "tech"},
    {"handle": "benbites",          "feed": "https://bensbites.beehiiv.com/feed",                        "platform": "newsletter", "category": "ai_ml"},
    {"handle": "timferriss",        "feed": "https://tim.blog/feed",                                     "platform": "newsletter", "category": "lifestyle"},
    {"handle": "coolshell",         "feed": "https://coolshell.cn/feed",                                 "platform": "newsletter", "category": "tech_cn"},
    {"handle": "sspai",             "feed": "https://sspai.com/feed",                                    "platform": "newsletter", "category": "tech_cn"},
    # ── Tech Media — 中等失真预期 ──────────────────────────────────────────────
    {"handle": "techcrunch",        "feed": "https://techcrunch.com/feed/",                              "platform": "newsletter", "category": "tech_media"},
    {"handle": "theverge",          "feed": "https://www.theverge.com/rss/index.xml",                    "platform": "newsletter", "category": "tech_media"},
    {"handle": "wired-ai",          "feed": "https://www.wired.com/feed/tag/ai/latest/rss",              "platform": "newsletter", "category": "tech_media"},
    {"handle": "arstechnica",       "feed": "https://feeds.arstechnica.com/arstechnica/index",           "platform": "newsletter", "category": "tech_media"},
    {"handle": "thenextweb",        "feed": "https://thenextweb.com/feed/",                              "platform": "newsletter", "category": "tech_media"},
    {"handle": "venturebeat",       "feed": "https://venturebeat.com/feed/",                             "platform": "newsletter", "category": "tech_media"},
    {"handle": "zdnet",             "feed": "https://www.zdnet.com/news/rss.xml",                        "platform": "newsletter", "category": "tech_media"},
    {"handle": "hackernews",        "feed": "https://news.ycombinator.com/rss",                          "platform": "newsletter", "category": "tech_media"},
    {"handle": "mit-tech-review",   "feed": "https://www.technologyreview.com/feed/",                   "platform": "newsletter", "category": "tech_media"},
    {"handle": "bigtechnology",     "feed": "https://bigtechnology.substack.com/feed",                   "platform": "newsletter", "category": "tech_media"},
    {"handle": "huggingface",       "feed": "https://huggingface.co/blog/feed.xml",                      "platform": "newsletter", "category": "ai_ml"},
    {"handle": "openai-news",       "feed": "https://openai.com/news/rss.xml",                           "platform": "newsletter", "category": "ai_ml"},
    {"handle": "deepmind",          "feed": "https://deepmind.google/blog/feed",                         "platform": "newsletter", "category": "ai_ml"},
    {"handle": "marktechpost",      "feed": "https://www.marktechpost.com/feed/",                        "platform": "newsletter", "category": "ai_ml"},
    {"handle": "the-decoder",       "feed": "https://the-decoder.com/feed/",                             "platform": "newsletter", "category": "ai_ml"},
    # ── Finance / Business — 高失真预期 ───────────────────────────────────────
    {"handle": "morningbrew",       "feed": "https://feeds.morningbrew.com/morningbrew",                 "platform": "newsletter", "category": "finance"},
    {"handle": "marketwatch",       "feed": "https://www.marketwatch.com/rss/topstories",               "platform": "newsletter", "category": "finance"},
    {"handle": "businessinsider",   "feed": "https://feeds.businessinsider.com/custom/all",              "platform": "newsletter", "category": "finance"},
    {"handle": "financialsamurai",  "feed": "https://financialsamurai.com/feed",                         "platform": "newsletter", "category": "finance"},
    {"handle": "coindesk",          "feed": "https://www.coindesk.com/arc/outboundfeeds/rss/",           "platform": "newsletter", "category": "crypto"},
    {"handle": "bankless",          "feed": "https://banklesshq.substack.com/feed",                      "platform": "newsletter", "category": "crypto"},
    {"handle": "notboring",         "feed": "https://www.notboring.co/feed",                             "platform": "newsletter", "category": "finance"},
    {"handle": "pennyhoarder",      "feed": "https://www.thepennyhoarder.com/rss",                       "platform": "newsletter", "category": "finance"},
    {"handle": "foundr",            "feed": "https://foundr.com/articles/feed",                          "platform": "newsletter", "category": "startup"},
    # ── Health / Lifestyle — 高失真预期 ───────────────────────────────────────
    {"handle": "peterattiamd",      "feed": "https://peterattiamd.com/feed/",                            "platform": "newsletter", "category": "health"},
    {"handle": "markmanson",        "feed": "https://markmanson.net/feed",                               "platform": "newsletter", "category": "lifestyle"},
    {"handle": "jamesclear",        "feed": "https://jamesclear.com/feed",                               "platform": "newsletter", "category": "lifestyle"},
    {"handle": "becomingminimalist","feed": "https://www.becomingminimalist.com/feed/",                  "platform": "newsletter", "category": "lifestyle"},
    {"handle": "sidehustlenation",  "feed": "https://sidehustlenation.com/feed",                         "platform": "newsletter", "category": "finance"},
    {"handle": "clevergirlfinance", "feed": "https://www.clevergirlfinance.com/feed",                    "platform": "newsletter", "category": "finance"},
    # ── YouTube — 混合失真预期 ─────────────────────────────────────────────────
    {"handle": "mkbhd",             "feed": "UCBcRF18a7Qf58cCRy5xuWwQ",                                 "platform": "youtube",    "category": "tech_edu"},
    {"handle": "aiexplained",       "feed": "UCNJ1Ymd5yFuUPtn21xtRbbw",                                 "platform": "youtube",    "category": "ai_ml"},
    {"handle": "twocentspbs",       "feed": "UCzWQYUVCpZqtN93H8RR44Qw",                                 "platform": "youtube",    "category": "finance"},
    {"handle": "grahamstephan",     "feed": "UCa-ckhlKL98F8YXKQ-BALiw",                                 "platform": "youtube",    "category": "finance"},
]

# ── HTTP 工具 ─────────────────────────────────────────────────────────────────
async def check_rss(url: str, client: httpx.AsyncClient) -> bool:
    """验证 RSS 地址是否返回有效内容"""
    if len(url) == 24 and url.isalnum():  # YouTube channel ID
        return True
    try:
        r = await client.get(url, timeout=10, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 500:
            return True
    except Exception:
        pass
    return False

async def api_post(client: httpx.AsyncClient, path: str, **kwargs) -> dict:
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=300, **kwargs)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"  [error] POST {path}: {type(e).__name__}")
        return {}

async def api_get(client: httpx.AsyncClient, path: str) -> dict:
    try:
        r = await client.get(f"{API_BASE}{path}", timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

# ── Step 1: 验证 RSS 地址 ──────────────────────────────────────────────────────
async def validate_feeds(candidates: list[dict]) -> list[dict]:
    print("\n" + "="*60)
    print("Step 1: 验证 RSS/YouTube 地址可用性")
    print("="*60)
    valid = []
    invalid = []
    async with httpx.AsyncClient() as client:
        tasks = [(acc, check_rss(acc["feed"], client)) for acc in candidates]
        for acc, coro in tasks:
            ok = await coro
            if ok:
                valid.append(acc)
                print(f"  ✓ {acc['handle']:<25} {acc['feed'][:60]}")
            else:
                invalid.append(acc)
                print(f"  ✗ {acc['handle']:<25} {acc['feed'][:60]}")

    print(f"\n  可用: {len(valid)} / 失败: {len(invalid)}")
    return valid

# ── Step 2: 批量分析 ──────────────────────────────────────────────────────────
async def analyze_accounts(accounts: list[dict], client: httpx.AsyncClient) -> list[dict]:
    print("\n" + "="*60)
    print(f"Step 2: 批量分析 {len(accounts)} 个账号")
    print("="*60)
    results = []
    for i, acc in enumerate(accounts, 1):
        handle = acc["handle"]
        print(f"\n  [{i}/{len(accounts)}] @{handle} ({acc['platform']}, {acc['category']})...")
        t0 = time.time()
        data = await api_post(client, f"/analyze/{handle}")
        elapsed = round(time.time() - t0, 1)
        if not data or not data.get("profile"):
            print(f"  ✗ 失败 ({elapsed}s)")
            results.append({**acc, "status": "failed", "distortion_index": None,
                            "total_posts": 0, "elapsed_s": elapsed})
            continue
        p = data["profile"]
        result = {
            **acc,
            "status": "success",
            "elapsed_s": elapsed,
            "new_posts": data.get("new_posts_crawled", 0),
            "distortion_index": p["distortion_index"],
            "significance_inflation": round(p["significance_inflation_rate"] * 100, 1),
            "anxiety_manufacturing": round(p["anxiety_manufacturing_rate"] * 100, 1),
            "novelty_claims": round(p["novelty_claim_rate"] * 100, 1),
            "temporal_distortion": round(p["temporal_distortion_rate"] * 100, 1),
            "consistency_score": round(p["consistency_score"] * 100, 1),
            "deletion_rate": round(p["deletion_rate"] * 100, 1),
            "deleted_count": p["deleted_count"],
            "total_posts": p["total_posts_analyzed"],
        }
        results.append(result)
        print(f"  ✓ 完成 ({elapsed}s) | index={result['distortion_index']} | posts={result['new_posts']}")
    return results

# ── Step 3: 收集语料库 ─────────────────────────────────────────────────────────
async def collect_corpus(accounts: list[dict], client: httpx.AsyncClient) -> list[dict]:
    print("\n" + "="*60)
    print("Step 3: 收集标注语料库")
    print("="*60)
    corpus = []
    for acc in accounts:
        if acc.get("status") not in ("success", "done"):
            continue
        handle = acc["handle"]
        data = await api_get(client, f"/posts/{handle}?limit=50")
        posts = data.get("posts", [])
        for p in posts:
            corpus.append({
                "handle": handle,
                "platform": acc["platform"],
                "category": acc["category"],
                "post_id": p["platform_id"],
                "content": p["content"][:500],
                "posted_at": p["posted_at"],
                "distortion_types": p["distortion_types"],
                "confidence": p["confidence"],
                "method": p["classification_method"],
                "signals": p["trigger_signals"],
                "deleted": p["deleted"],
                "temporal_gap_days": p.get("temporal_gap_days"),
            })
        if posts:
            print(f"  @{handle}: {len(posts)} 条")
    print(f"\n  语料库总量: {len(corpus)} 条")
    return corpus

# ── Step 4: 跨平台 & 跨类别对比 ──────────────────────────────────────────────
def cross_analysis(all_profiles: list[dict]) -> dict:
    print("\n" + "="*60)
    print("Step 4: 跨平台 & 跨类别分析")
    print("="*60)
    success = [p for p in all_profiles if p.get("distortion_index") is not None]

    # 按平台
    by_platform: dict[str, list] = {}
    for p in success:
        by_platform.setdefault(p["platform"], []).append(p)

    # 按类别
    by_category: dict[str, list] = {}
    for p in success:
        by_category.setdefault(p["category"], []).append(p)

    result = {"platform": {}, "category": {}}
    for dim, groups in [("platform", by_platform), ("category", by_category)]:
        for key, accs in groups.items():
            indices = [a["distortion_index"] for a in accs]
            result[dim][key] = {
                "count": len(accs),
                "avg_index": round(statistics.mean(indices), 1),
                "median_index": round(statistics.median(indices), 1),
                "max_index": max(indices),
                "min_index": min(indices),
                "avg_inflation": round(statistics.mean(a["significance_inflation"] for a in accs), 1),
                "avg_anxiety": round(statistics.mean(a["anxiety_manufacturing"] for a in accs), 1),
                "avg_novelty": round(statistics.mean(a["novelty_claims"] for a in accs), 1),
                "avg_temporal": round(statistics.mean(a["temporal_distortion"] for a in accs), 1),
                "total_posts": sum(a["total_posts"] for a in accs),
                "accounts": [a["handle"] for a in accs],
            }
            print(f"\n  [{dim}] {key} ({len(accs)} 账号):")
            print(f"    平均失真指数: {result[dim][key]['avg_index']}")
            print(f"    最高: {result[dim][key]['max_index']} / 最低: {result[dim][key]['min_index']}")
    return result

# ── Step 5: 导出 ──────────────────────────────────────────────────────────────
def export_all(all_profiles, corpus, cross, behavior_logs):
    print("\n" + "="*60)
    print("Step 5: 导出结果文件")
    print("="*60)

    # corpus.jsonl
    p = OUTPUT_DIR / "corpus.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for item in corpus:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  corpus.jsonl — {len(corpus)} 条")

    # profiles.csv
    success = [p for p in all_profiles if p.get("distortion_index") is not None]
    p = OUTPUT_DIR / "profiles.csv"
    fields = ["handle","platform","category","status","distortion_index",
              "significance_inflation","anxiety_manufacturing","novelty_claims",
              "temporal_distortion","consistency_score","deletion_rate",
              "deleted_count","total_posts"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(success)
    print(f"  profiles.csv — {len(success)} 行")

    # cross_analysis.json
    p = OUTPUT_DIR / "cross_analysis.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cross, f, ensure_ascii=False, indent=2)
    print(f"  cross_analysis.json")

    # behavior_log.csv (真实API数据)
    p = OUTPUT_DIR / "behavior_log.csv"
    if behavior_logs:
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(behavior_logs[0].keys()))
            w.writeheader(); w.writerows(behavior_logs)
        print(f"  behavior_log.csv — {len(behavior_logs)} 行")

    # report.md
    _write_report(all_profiles, corpus, cross, behavior_logs)
    print(f"  report.md")

def _write_report(all_profiles, corpus, cross, behavior_logs):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    success = [p for p in all_profiles if p.get("distortion_index") is not None]
    flagged = sum(1 for c in corpus if c["distortion_types"])
    all_types = []
    for c in corpus:
        all_types.extend(c["distortion_types"])
    type_counts = Counter(all_types)
    behavior_counts = Counter(b["response"] for b in behavior_logs)
    total_b = len(behavior_logs)

    lines = [
        "# Influencer Distortion Detection — Research Report (50-Account Experiment)",
        f"\nGenerated: {now}",
        f"\n---\n",
        "## 1. Corpus Overview",
        f"- Accounts attempted: **{len(all_profiles)}**",
        f"- Accounts successfully analyzed: **{len(success)}**",
        f"- Total posts in corpus: **{sum(p['total_posts'] for p in success)}**",
        f"- Platforms covered: {', '.join(set(p['platform'] for p in success))}",
        f"- Categories: {', '.join(sorted(set(p['category'] for p in success)))}",
        f"- Languages: English, Chinese",
        f"- Posts with distortion flags: **{flagged}** ({round(flagged/len(corpus)*100,1) if corpus else 0}%)",
        f"- Deleted posts detected: **{sum(p['deleted_count'] for p in success)}**",
        "",
        "## 2. Account Distortion Profiles (sorted by index)",
        "",
        "| Account | Platform | Category | Index | Inflation | Anxiety | Novelty | Temporal | Consistency | Posts |",
        "|---------|----------|----------|-------|-----------|---------|---------|----------|-------------|-------|",
    ]
    for p in sorted(success, key=lambda x: x["distortion_index"], reverse=True):
        lines.append(
            f"| @{p['handle']} | {p['platform']} | {p['category']} | "
            f"**{p['distortion_index']}** | {p['significance_inflation']}% | "
            f"{p['anxiety_manufacturing']}% | {p['novelty_claims']}% | "
            f"{p['temporal_distortion']}% | {p['consistency_score']} | {p['total_posts']} |"
        )

    lines += ["", "## 3. Cross-Platform Comparison", ""]
    for plat, data in cross.get("platform", {}).items():
        lines.append(f"### {plat} ({data['count']} accounts)")
        lines.append(f"- Avg distortion index: **{data['avg_index']}** (range {data['min_index']}–{data['max_index']})")
        lines.append(f"- Avg consistency score: {data['avg_temporal']}")
        lines.append(f"- Total posts analyzed: {data['total_posts']}")
        lines.append("")

    lines += ["## 4. Cross-Category Comparison", ""]
    lines += ["| Category | Accounts | Avg Index | Avg Inflation | Avg Anxiety | Avg Novelty | Avg Temporal |",
              "|----------|----------|-----------|---------------|-------------|-------------|--------------|"]
    for cat, data in sorted(cross.get("category", {}).items(), key=lambda x: -x[1]["avg_index"]):
        lines.append(
            f"| {cat} | {data['count']} | **{data['avg_index']}** | "
            f"{data['avg_inflation']}% | {data['avg_anxiety']}% | "
            f"{data['avg_novelty']}% | {data['avg_temporal']}% |"
        )

    lines += [
        "",
        "## 5. Key Findings",
        "",
    ]
    if success:
        avg = round(statistics.mean(p["distortion_index"] for p in success), 1)
        lo = min(success, key=lambda x: x["distortion_index"])
        hi = max(success, key=lambda x: x["distortion_index"])
        above30 = [p for p in success if p["distortion_index"] >= 30]
        lines += [
            f"- Overall average distortion index: **{avg}/100**",
            f"- Lowest: @{lo['handle']} ({lo['distortion_index']}) — {lo['category']}",
            f"- Highest: @{hi['handle']} ({hi['distortion_index']}) — {hi['category']}",
            f"- Accounts with index ≥ 30 (high distortion): **{len(above30)}**",
            f"- Accounts with deleted posts detected: {sum(1 for p in success if p['deleted_count'] > 0)}",
            "",
        ]

    lines += [
        "## 6. Annotated Corpus Statistics",
        "",
        f"- Total posts: {len(corpus)}",
        f"- Auto-annotated (≥70% confidence): {sum(1 for c in corpus if c['confidence'] >= 0.70)}",
        f"- Pending human review (<70%): {sum(1 for c in corpus if c['confidence'] < 0.70)}",
        "",
        "### Distortion type distribution",
        "",
    ]
    for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = round(count/len(corpus)*100, 1) if corpus else 0
        lines.append(f"- {dtype}: {count} posts ({pct}%)")

    lines += [
        "",
        "## 7. Behavior Change Experiment (Research Tab — Real User Data)",
        "",
        "> Core research question: Does exposure to distortion profiles change",
        "> how people process and trust information from those accounts?",
        "",
    ]
    if total_b > 0:
        lines += [
            f"Total responses logged via Research tab: **{total_b}**",
            "",
            "| Response | Count | % |",
            "|----------|-------|---|",
        ]
        for resp in ["less", "same", "more", "unfollow"]:
            n = behavior_counts.get(resp, 0)
            label = {"less": "I'll trust this account less", "same": "My reading habits won't change",
                     "more": "I still find the content useful", "unfollow": "I'll unfollow"}[resp]
            lines.append(f"| {label} | {n} | {round(n/total_b*100)}% |")
    else:
        lines.append("> No real user responses collected yet.")
        lines.append("> Open the Research tab in the web UI and fill in the behavior questionnaire after viewing each account's profile.")

    lines += [
        "",
        "## 8. Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `corpus.jsonl` | Full annotated corpus (JSONL) |",
        "| `profiles.csv` | Account-level distortion profiles |",
        "| `cross_analysis.json` | Cross-platform and cross-category stats |",
        "| `behavior_log.csv` | Real user behavior responses |",
        "| `report.md` | This report |",
        "",
        "---",
        f"*Generated by Influencer Distortion Detection System — {now}*",
    ]

    with open(OUTPUT_DIR / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ── 主流程 ────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "="*60)
    print("Influencer Distortion Detection — 50-Account Experiment")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"候选账号: {len(CANDIDATE_ACCOUNTS)} | 已完成: {len(DONE_ACCOUNTS)}")
    print("="*60)

    # 检查后端
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线，请先运行: uvicorn app.main:app --reload --port 8001")
            return

        # Step 1: 验证地址
        valid_accounts = await validate_feeds(CANDIDATE_ACCOUNTS)

        # Step 2: 分析可用账号
        new_profiles = await analyze_accounts(valid_accounts, client)

        # 合并历史数据
        all_profiles = DONE_ACCOUNTS + new_profiles
        print(f"\n  总账号数: {len(all_profiles)} ({len(DONE_ACCOUNTS)} 历史 + {len(new_profiles)} 新)")

        # Step 3: 收集语料库（包含历史账号）
        corpus = await collect_corpus(all_profiles, client)

        # Step 4: 跨平台分析
        cross = cross_analysis(all_profiles)

        # 读取真实行为数据
        behavior_data = await api_get(client, "/behavior-log/summary")
        behavior_logs = []
        if behavior_data.get("breakdown"):
            for resp, n in behavior_data["breakdown"].items():
                for _ in range(n):
                    behavior_logs.append({"response": resp, "type": "real"})
        print(f"\n  真实用户行为记录: {len(behavior_logs)} 条")

    # Step 5: 导出
    export_all(all_profiles, corpus, cross, behavior_logs)

    print("\n" + "="*60)
    success = [p for p in all_profiles if p.get("distortion_index") is not None]
    print(f"✓ 实验完成！结果保存在 {OUTPUT_DIR}/")
    print(f"  成功分析: {len(success)} 个账号")
    print(f"  语料库:   {len(corpus)} 条帖子")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
