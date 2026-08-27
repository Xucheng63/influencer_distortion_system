#!/usr/bin/env python3
"""
experiment_reddit.py — Reddit 平台实验脚本

方式1：测试 Subreddit（版块）— handle 格式：r/subreddit
方式2：测试 Reddit 用户   — handle 格式：u/username

功能：
  1. 自动验证账号/版块是否存在
  2. 已成功的账号读缓存，不重复分析
  3. 每次成功立即保存缓存
  4. 生成跨平台对比报告

运行：
  python experiment_reddit.py
"""
import asyncio, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict
import httpx

API_BASE   = "http://localhost:8001/api"
REDDIT_API = "https://www.reddit.com"
OUTPUT_DIR = Path("research_results_reddit")
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_FILE = OUTPUT_DIR / "successful_profiles.json"

REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DistortionResearch/1.0; academic)",
    "Accept": "application/json",
}

# ── 方式1：Subreddit 候选列表 ─────────────────────────────────────────────────
SUBREDDIT_ACCOUNTS = [
    # ── 低失真预期 ────────────────────────────────────────────────────────
    {"handle": "r/science",             "category": "science",   "expected": "low"},
    {"handle": "r/askscience",          "category": "science",   "expected": "low"},
    {"handle": "r/explainlikeimfive",   "category": "learning",  "expected": "low"},
    {"handle": "r/todayilearned",       "category": "learning",  "expected": "low"},
    {"handle": "r/technology",          "category": "tech",      "expected": "low"},
    {"handle": "r/programming",         "category": "tech",      "expected": "low"},
    {"handle": "r/machinelearning",     "category": "ai_ml",     "expected": "low"},
    {"handle": "r/datascience",         "category": "ai_ml",     "expected": "low"},
    {"handle": "r/personalfinance",     "category": "finance",   "expected": "low"},
    {"handle": "r/frugal",              "category": "lifestyle", "expected": "low"},
    {"handle": "r/cscareerquestions",   "category": "tech",      "expected": "low"},
    {"handle": "r/AskHistorians",       "category": "learning",  "expected": "low"},
    {"handle": "r/space",               "category": "science",   "expected": "low"},
    {"handle": "r/Physics",             "category": "science",   "expected": "low"},
    {"handle": "r/nutrition",           "category": "health",    "expected": "low"},
    {"handle": "r/mildlyinteresting",   "category": "culture",   "expected": "low"},
    {"handle": "r/changemyview",        "category": "politics",  "expected": "moderate"},
    # ── 中等失真预期 ──────────────────────────────────────────────────────
    {"handle": "r/worldnews",           "category": "media",     "expected": "moderate"},
    {"handle": "r/news",                "category": "media",     "expected": "moderate"},
    {"handle": "r/politics",            "category": "politics",  "expected": "moderate"},
    {"handle": "r/economics",           "category": "finance",   "expected": "moderate"},
    {"handle": "r/investing",           "category": "finance",   "expected": "moderate"},
    {"handle": "r/environment",         "category": "science",   "expected": "moderate"},
    {"handle": "r/climate",             "category": "science",   "expected": "moderate"},
    {"handle": "r/artificial",          "category": "ai_ml",     "expected": "moderate"},
    {"handle": "r/futurology",          "category": "tech",      "expected": "moderate"},
    {"handle": "r/nosurf",              "category": "lifestyle", "expected": "moderate"},
    {"handle": "r/legaladvice",         "category": "finance",   "expected": "moderate"},
    {"handle": "r/askreddit",           "category": "culture",   "expected": "moderate"},
    {"handle": "r/interestingasfuck",   "category": "culture",   "expected": "moderate"},
    {"handle": "r/entrepreneur",        "category": "startup",   "expected": "high"},
    {"handle": "r/economy",             "category": "finance",   "expected": "moderate"},
    {"handle": "r/geopolitics",         "category": "politics",  "expected": "moderate"},
    {"handle": "r/StockMarket",         "category": "finance",   "expected": "moderate"},
    {"handle": "r/investing_discussion","category": "finance",   "expected": "moderate"},
    # ── 高失真预期 ────────────────────────────────────────────────────────
    {"handle": "r/singularity",         "category": "ai_ml",     "expected": "high"},
    {"handle": "r/wallstreetbets",      "category": "finance",   "expected": "high"},
    {"handle": "r/conspiracy",          "category": "politics",  "expected": "high"},
    {"handle": "r/conservative",        "category": "politics",  "expected": "high"},
    {"handle": "r/liberal",             "category": "politics",  "expected": "high"},
    {"handle": "r/antiwork",            "category": "lifestyle", "expected": "high"},
    {"handle": "r/superstonk",          "category": "finance",   "expected": "high"},
    {"handle": "r/preppers",            "category": "lifestyle", "expected": "high"},
    {"handle": "r/collapse",            "category": "science",   "expected": "high"},
    {"handle": "r/unpopularopinion",    "category": "politics",  "expected": "high"},
    {"handle": "r/crypto",              "category": "crypto",    "expected": "high"},
    {"handle": "r/ChatGPT",             "category": "ai_ml",     "expected": "high"},
    {"handle": "r/OpenAI",              "category": "ai_ml",     "expected": "high"},
    {"handle": "r/CryptoCurrency",      "category": "crypto",    "expected": "high"},
    {"handle": "r/Bitcoin",             "category": "crypto",    "expected": "high"},
    {"handle": "r/worldpolitics",       "category": "politics",  "expected": "high"},
]


# ── 方式2：Reddit 用户候选列表 ────────────────────────────────────────────────
USER_ACCOUNTS = [
    {"handle": "u/spez",             "category": "tech",    "expected": "moderate"},
    {"handle": "u/gallowboob",       "category": "culture", "expected": "moderate"},
    {"handle": "u/mvea",             "category": "science", "expected": "low"},
    {"handle": "u/madazzahatter",    "category": "culture", "expected": "moderate"},
    {"handle": "u/SchuminWeb",       "category": "culture", "expected": "low"},
    {"handle": "u/Gauntlet_of_Might","category": "culture", "expected": "moderate"},
    {"handle": "u/GallowBoob",       "category": "culture", "expected": "moderate"},
]


# 合并两个列表
CANDIDATE_ACCOUNTS = SUBREDDIT_ACCOUNTS + USER_ACCOUNTS

# ── 工具函数 ──────────────────────────────────────────────────────────────────
async def verify_reddit(handle: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    """
    验证 Reddit 账号格式是否正确。
    注意：Reddit API 直接请求返回 403，验证改为只检查格式，
    实际抓取由 Playwright 浏览器完成（绕过 403）。
    """
    h = handle.lstrip("@").lower()
    if h.startswith("r/") and len(h) > 2:
        return True, f"{h} [格式正确，Playwright 抓取]"
    elif h.startswith("u/") and len(h) > 2:
        return True, f"{h} [格式正确，Playwright 抓取]"
    return False, "格式错误（需要 r/ 或 u/ 前缀）"

async def api_post(client, path):
    try:
        r = await client.post(f"{API_BASE}{path}", timeout=240)
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
    print("Reddit Platform Experiment")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"候选账号: {len(CANDIDATE_ACCOUNTS)} ({len(SUBREDDIT_ACCOUNTS)} subreddits + {len(USER_ACCOUNTS)} users)")
    print("="*60)

    async with httpx.AsyncClient() as client:
        # 检查后端
        try:
            r = await client.get(f"{API_BASE.replace('/api','')}/health", timeout=5)
            assert r.status_code == 200
            print("\n✓ 后端在线")
        except Exception:
            print("\n✗ 后端不在线 — 请先运行: uvicorn app.main:app --reload --port 8001")
            return

        cache = load_cache()

        # Step 1: 验证
        print(f"\n{'='*60}\nStep 1: 验证 {len(CANDIDATE_ACCOUNTS)} 个 Reddit 账号\n{'='*60}")
        print("\n--- Subreddits ---")
        valid = []
        for acc in CANDIDATE_ACCOUNTS:
            handle = acc["handle"]
            if handle in cache:
                print(f"  ✓ {handle:<40} [已缓存，跳过]")
                valid.append(acc)
                continue
            ok, info = await verify_reddit(handle, client)
            print(f"  {'✓' if ok else '✗'} {handle:<40} {info}")
            if ok:
                valid.append(acc)
            # 小延迟避免限流
            await asyncio.sleep(0.3)

        need = [a for a in valid if a["handle"] not in cache]
        print(f"\n  验证通过: {len(valid)} | 需分析: {len(need)} | 缓存跳过: {len(valid)-len(need)}")

        # Step 2: 分析
        if need:
            print(f"\n{'='*60}\nStep 2: 分析 {len(need)} 个账号\n{'='*60}")
            for i, acc in enumerate(need, 1):
                handle = acc["handle"]
                kind = "subreddit" if handle.startswith("r/") else "user"
                print(f"\n  [{i}/{len(need)}] {handle} ({kind}, {acc['category']})...")
                t0 = time.time()
                data = await api_post(client, f"/analyze/{handle}")
                elapsed = round(time.time() - t0, 1)

                if not data or not data.get("profile"):
                    print(f"  ✗ 失败 ({elapsed}s)")
                    continue

                p = data["profile"]
                new_posts = data.get("new_posts_crawled", 0)
                result = {
                    "handle":   handle,
                    "type":     kind,
                    "platform": "reddit",
                    "category": acc["category"],
                    "expected": acc["expected"],
                    "distortion_index":       p["distortion_index"],
                    "significance_inflation": round(p["significance_inflation_rate"]*100, 1),
                    "anxiety_manufacturing":  round(p["anxiety_manufacturing_rate"]*100, 1),
                    "novelty_claims":         round(p["novelty_claim_rate"]*100, 1),
                    "temporal_distortion":    round(p["temporal_distortion_rate"]*100, 1),
                    "consistency_score":      round(p["consistency_score"]*100, 1),
                    "deletion_rate":          round(p["deletion_rate"]*100, 1),
                    "deleted_count":          p["deleted_count"],
                    "total_posts":            p["total_posts_analyzed"],
                    "new_posts":              new_posts,
                    "analyzed_at":            datetime.utcnow().isoformat(),
                }

                if result["total_posts"] > 0:
                    cache[handle] = result
                    save_cache(cache)
                    print(f"  ✓ ({elapsed}s) index={result['distortion_index']} posts={new_posts} [已缓存]")
                else:
                    print(f"  ~ ({elapsed}s) posts=0 [数据为空，未缓存]")

        # Step 3: 语料库
        print(f"\n{'='*60}\nStep 3: 收集语料库\n{'='*60}")
        corpus = []
        for handle, prof in cache.items():
            data = await api_get(client, f"/posts/{handle}?limit=50")
            posts = data.get("posts", [])
            for p in posts:
                corpus.append({
                    "handle":           handle,
                    "type":             prof.get("type", "subreddit"),
                    "platform":         "reddit",
                    "category":         prof["category"],
                    "post_id":          p["platform_id"],
                    "content":          p["content"][:500],
                    "posted_at":        p["posted_at"],
                    "distortion_types": p["distortion_types"],
                    "confidence":       p["confidence"],
                    "method":           p["classification_method"],
                    "signals":          p["trigger_signals"],
                    "deleted":          p["deleted"],
                })
            if posts:
                print(f"  {handle}: {len(posts)} 条")
        print(f"\n  语料库总量: {len(corpus)} 条")

        # Step 4: 分析
        profiles = list(cache.values())
        if not profiles:
            print("\n没有成功数据")
            return

        print(f"\n{'='*60}\nStep 4: 分析结果\n{'='*60}")
        indices = [p["distortion_index"] for p in profiles]
        subs = [p for p in profiles if p.get("type") == "subreddit"]
        users = [p for p in profiles if p.get("type") == "user"]

        print(f"\n总账号: {len(profiles)} ({len(subs)} subreddits + {len(users)} users)")
        print(f"总帖子: {sum(p['total_posts'] for p in profiles)}")
        print(f"平均失真指数: {round(statistics.mean(indices),1)}")
        print(f"最高: {max(indices)} ({max(profiles,key=lambda x:x['distortion_index'])['handle']})")
        print(f"最低: {min(indices)} ({min(profiles,key=lambda x:x['distortion_index'])['handle']})")

        if subs and users:
            si = [p["distortion_index"] for p in subs]
            ui = [p["distortion_index"] for p in users]
            print(f"\nSubreddit 平均: {round(statistics.mean(si),1)}")
            print(f"User 平均:      {round(statistics.mean(ui),1)}")

        by_expected = defaultdict(list)
        for p in profiles:
            by_expected[p["expected"]].append(p["distortion_index"])
        print("\n按预期失真:")
        for exp in ["low","moderate","high"]:
            if exp in by_expected:
                vals = by_expected[exp]
                print(f"  {exp}: n={len(vals)} avg={round(statistics.mean(vals),1)} max={max(vals)}")

        by_cat = defaultdict(list)
        for p in profiles:
            by_cat[p["category"]].append(p)
        print("\n按类别:")
        for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            idx = [a["distortion_index"] for a in accs]
            print(f"  {cat:<15} n={len(accs):2d} avg={round(statistics.mean(idx),1):5.1f} max={max(idx)} min={min(idx)}")

        print("\n五维度触发:")
        for dim in ["anxiety_manufacturing","significance_inflation","novelty_claims","temporal_distortion"]:
            flagged = sorted([p for p in profiles if p[dim] > 0], key=lambda x: -x[dim])
            if flagged:
                print(f"  {dim}: {len(flagged)}个账号触发，最高 {flagged[0][dim]}%")
                for p in flagged[:5]:
                    print(f"    {p['handle']}: {p[dim]}%")

        # Step 5: 导出
        print(f"\n{'='*60}\nStep 5: 导出\n{'='*60}")

        with open(OUTPUT_DIR/"corpus.jsonl","w",encoding="utf-8") as f:
            for item in corpus:
                f.write(json.dumps(item,ensure_ascii=False)+"\n")
        print(f"  corpus.jsonl — {len(corpus)} 条")

        fields = ["handle","type","platform","category","expected","distortion_index",
                  "significance_inflation","anxiety_manufacturing","novelty_claims",
                  "temporal_distortion","consistency_score","deletion_rate",
                  "deleted_count","total_posts","analyzed_at"]
        with open(OUTPUT_DIR/"profiles.csv","w",newline="",encoding="utf-8") as f:
            w = csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(profiles,key=lambda x:x["distortion_index"],reverse=True))
        print(f"  profiles.csv — {len(profiles)} 行")

        # report.md
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        flagged_posts = sum(1 for c in corpus if c["distortion_types"])
        all_types = []
        for c in corpus:
            all_types.extend(c["distortion_types"])
        type_counts = Counter(all_types)

        lines = [
            "# Reddit Platform Experiment — Research Report",
            f"\nGenerated: {now}\n---\n",
            "## 1. Overview",
            f"- Platform: **Reddit** (subreddits + individual users)",
            f"- Subreddits analyzed: **{len(subs)}**",
            f"- Users analyzed: **{len(users)}**",
            f"- Total posts: **{sum(p['total_posts'] for p in profiles)}**",
            f"- Avg distortion index: **{round(statistics.mean(indices),1)}/100**",
            f"- Posts with distortion flags: **{flagged_posts}** ({round(flagged_posts/len(corpus)*100,1) if corpus else 0}%)",
            "",
            "## 2. Key Finding: Expected vs Actual Distortion",
            "",
            "| Expected | n | Avg Index | Description |",
            "|----------|---|-----------|-------------|",
        ]
        for exp, label in [("low","客观信息类"),("moderate","新闻评论类"),("high","情绪化内容")]:
            if exp in by_expected:
                vals = by_expected[exp]
                lines.append(f"| {exp} | {len(vals)} | {round(statistics.mean(vals),1)} | {label} |")

        lines += ["","## 3. Subreddit vs User Comparison",""]
        if subs:
            si = [p["distortion_index"] for p in subs]
            lines.append(f"- **Subreddits** (n={len(subs)}): avg {round(statistics.mean(si),1)}, range {min(si)}–{max(si)}")
        if users:
            ui = [p["distortion_index"] for p in users]
            lines.append(f"- **Users** (n={len(users)}): avg {round(statistics.mean(ui),1)}, range {min(ui)}–{max(ui)}")

        lines += ["","## 4. All Profiles (sorted by index)","",
                  "| Handle | Type | Category | Expected | Index | Inflation | Anxiety | Novelty | Temporal | Posts |",
                  "|--------|------|----------|----------|-------|-----------|---------|---------|----------|-------|"]
        for p in sorted(profiles,key=lambda x:x["distortion_index"],reverse=True):
            lines.append(
                f"| {p['handle']} | {p.get('type','-')} | {p['category']} | {p['expected']} | "
                f"**{p['distortion_index']}** | {p['significance_inflation']}% | "
                f"{p['anxiety_manufacturing']}% | {p['novelty_claims']}% | "
                f"{p['temporal_distortion']}% | {p['total_posts']} |"
            )

        lines += ["","## 5. Distortion Type Distribution",""]
        total_c = len(corpus)
        for dtype, count in sorted(type_counts.items(),key=lambda x:-x[1]):
            lines.append(f"- {dtype}: {count} posts ({round(count/total_c*100,1) if total_c else 0}%)")

        lines += ["","## 6. Platform Comparison (vs RSS & Bluesky)","",
                  "| Platform | Format | Avg Index | Anxiety % | Notes |",
                  "|----------|--------|-----------|-----------|-------|",
                  "| RSS/Newsletter | Long-form | 10.4 | ~0% | Professional creators |",
                  "| YouTube | Video transcript | 9.0 | ~0% | Educational content |",
                  f"| Bluesky | Short-form social | 13.8 | ~2% | Journalists & activists |",
                  f"| **Reddit** | **Community posts** | **{round(statistics.mean(indices),1)}** | **TBD** | **Subreddits & users** |",
                  "","---",f"*{now}*"]

        with open(OUTPUT_DIR/"report.md","w",encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  report.md")
        print(f"  successful_profiles.json — {len(cache)} 个账号")

    print(f"\n{'='*60}")
    print(f"✓ 完成！{len(profiles)} 个账号 | {len(corpus)} 条帖子")
    print(f"  结果保存在 {OUTPUT_DIR}/")
    print(f"  下次运行自动跳过已成功账号")
    print("="*60+"\n")

if __name__ == "__main__":
    asyncio.run(main())
