#!/usr/bin/env python3
"""
experiment_bluesky.py — Bluesky 平台批量实验脚本

功能：
  1. 自动验证账号是否存在（Bluesky 公开 API）
  2. 已分析过的账号直接读缓存，不重复分析
  3. 批量分析，结果自动保存
  4. 生成跨平台对比报告（与 RSS/YouTube 批次合并）

运行：
  python experiment_bluesky.py

输出：research_results_bluesky/
"""
import asyncio, json, csv, time, statistics
from datetime import datetime
from pathlib import Path
from collections import Counter
import httpx

API_BASE    = "http://localhost:8001/api"
BSKY_API    = "https://public.api.bsky.app/xrpc"
OUTPUT_DIR  = Path("research_results_bluesky")
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_FILE  = OUTPUT_DIR / "successful_profiles.json"

# ── 50个 Bluesky 真实账号候选 ─────────────────────────────────────────────────
# handle 格式：不带 @ 前缀，系统自动补全 .bsky.social
# 覆盖 tech/AI/media/finance/lifestyle 多类别
CANDIDATE_ACCOUNTS = [
    # ── 科技/AI — 低失真预期 ──────────────────────────────────────────────
    {"handle": "simonw.bsky.social",          "category": "tech",      "expected": "low"},
    {"handle": "mmitchell.bsky.social",       "category": "ai_ml",     "expected": "low"},
    {"handle": "derspiegel.bsky.social",      "category": "media",     "expected": "low"},
    {"handle": "quanta.bsky.social",          "category": "science",   "expected": "low"},
    {"handle": "ashishkjha.bsky.social",      "category": "health",    "expected": "low"},
    {"handle": "calculatedrisk.bsky.social",  "category": "finance",   "expected": "low"},
    {"handle": "patrickrhone.bsky.social",    "category": "lifestyle", "expected": "low"},
    {"handle": "amandapalmer.bsky.social",    "category": "culture",   "expected": "moderate"},
    {"handle": "climatepower.bsky.social",    "category": "science",   "expected": "moderate"},
    {"handle": "brianstelter.bsky.social",    "category": "media",     "expected": "moderate"},
    # ── 媒体机构 — 低/中失真预期 ─────────────────────────────────────────
    {"handle": "politico.com",                "category": "politics",  "expected": "moderate"},
    {"handle": "reuters.com",                 "category": "media",     "expected": "low"},
    {"handle": "apnews.com",                  "category": "media",     "expected": "low"},
    {"handle": "motherjones.com",             "category": "politics",  "expected": "moderate"},
    {"handle": "theintercept.com",            "category": "politics",  "expected": "high"},
    {"handle": "newrepublic.com",             "category": "politics",  "expected": "moderate"},
    {"handle": "slate.com",                   "category": "media",     "expected": "moderate"},
    # ── 政治/文化大V — 中/高失真预期 ─────────────────────────────────────
    {"handle": "mollyjongfast.bsky.social",   "category": "media",     "expected": "high"},
    {"handle": "chrislhayes.bsky.social",     "category": "media",     "expected": "moderate"},
    {"handle": "juddlegum.bsky.social",       "category": "media",     "expected": "moderate"},
    {"handle": "oliverdarcy.bsky.social",     "category": "media",     "expected": "moderate"},
    {"handle": "taylorlorenz.bsky.social",    "category": "tech_media","expected": "high"},
    {"handle": "katienotopoulos.bsky.social", "category": "tech_media","expected": "moderate"},
    {"handle": "johncusack.bsky.social",      "category": "culture",   "expected": "high"},
    {"handle": "michaelmann.bsky.social",     "category": "science",   "expected": "moderate"},
    {"handle": "noahpinion.bsky.social",      "category": "finance",   "expected": "moderate"},
]


# ── HTTP 工具 ─────────────────────────────────────────────────────────────────
async def verify_bluesky(handle: str, client: httpx.AsyncClient) -> tuple[bool, str]:
    """
    验证 Bluesky 账号是否存在，返回 (存在?, 显示名)
    """
    h = handle.lstrip("@").lower()
    if "." not in h:
        h = f"{h}.bsky.social"
    try:
        r = await client.get(
            f"{BSKY_API}/app.bsky.actor.getProfile",
            params={"actor": h},
            timeout=httpx.Timeout(10.0),
        )
        if r.status_code == 200:
            data = r.json()
            display = data.get("displayName") or h
            followers = data.get("followersCount", 0)
            posts_count = data.get("postsCount", 0)
            return True, f"{display} ({followers} followers, {posts_count} posts)"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:50]

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
    print("Bluesky Platform Experiment")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"候选账号: {len(CANDIDATE_ACCOUNTS)}")
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

        # Step 1: 验证账号
        print(f"\n{'='*60}\nStep 1: 验证 {len(CANDIDATE_ACCOUNTS)} 个 Bluesky 账号\n{'='*60}")
        valid = []
        for acc in CANDIDATE_ACCOUNTS:
            handle = acc["handle"]
            if handle in cache:
                print(f"  ✓ {handle:<40} [已缓存，跳过]")
                valid.append(acc)
                continue
            ok, info = await verify_bluesky(handle, client)
            status = "✓" if ok else "✗"
            print(f"  {status} {handle:<40} {info}")
            if ok:
                valid.append(acc)

        need_analyze = [a for a in valid if a["handle"] not in cache]
        print(f"\n  验证通过: {len(valid)} | 需分析: {len(need_analyze)} | 缓存跳过: {len(valid)-len(need_analyze)}")

        # Step 2: 批量分析
        if need_analyze:
            print(f"\n{'='*60}\nStep 2: 分析 {len(need_analyze)} 个账号\n{'='*60}")
            for i, acc in enumerate(need_analyze, 1):
                handle = acc["handle"]
                print(f"\n  [{i}/{len(need_analyze)}] @{handle} ({acc['category']})...")
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
                    "platform": "bluesky",
                    "category": acc["category"],
                    "expected": acc["expected"],
                    "distortion_index":        p["distortion_index"],
                    "significance_inflation":  round(p["significance_inflation_rate"]*100, 1),
                    "anxiety_manufacturing":   round(p["anxiety_manufacturing_rate"]*100, 1),
                    "novelty_claims":          round(p["novelty_claim_rate"]*100, 1),
                    "temporal_distortion":     round(p["temporal_distortion_rate"]*100, 1),
                    "consistency_score":       round(p["consistency_score"]*100, 1),
                    "deletion_rate":           round(p["deletion_rate"]*100, 1),
                    "deleted_count":           p["deleted_count"],
                    "total_posts":             p["total_posts_analyzed"],
                    "new_posts":               new_posts,
                    "analyzed_at":             datetime.utcnow().isoformat(),
                }

                if result["total_posts"] > 0:
                    cache[handle] = result
                    save_cache(cache)
                    print(f"  ✓ ({elapsed}s) index={result['distortion_index']} posts={new_posts} [已缓存]")
                else:
                    print(f"  ~ ({elapsed}s) index=0 posts=0 [数据为空，未缓存]")

        # Step 3: 收集语料库
        print(f"\n{'='*60}\nStep 3: 收集语料库\n{'='*60}")
        corpus = []
        for handle, profile in cache.items():
            data = await api_get(client, f"/posts/{handle}?limit=50")
            posts = data.get("posts", [])
            for p in posts:
                corpus.append({
                    "handle":          handle,
                    "platform":        "bluesky",
                    "category":        profile["category"],
                    "post_id":         p["platform_id"],
                    "content":         p["content"][:500],
                    "posted_at":       p["posted_at"],
                    "distortion_types":p["distortion_types"],
                    "confidence":      p["confidence"],
                    "method":          p["classification_method"],
                    "signals":         p["trigger_signals"],
                    "deleted":         p["deleted"],
                })
            if posts:
                print(f"  @{handle}: {len(posts)} 条")
        print(f"\n  语料库总量: {len(corpus)} 条")

        # Step 4: 分析
        profiles = list(cache.values())
        if not profiles:
            print("\n没有成功的账号数据，退出")
            return

        print(f"\n{'='*60}\nStep 4: 分析结果\n{'='*60}")

        indices = [p["distortion_index"] for p in profiles]
        print(f"\n总账号数: {len(profiles)}")
        print(f"总帖子数: {sum(p['total_posts'] for p in profiles)}")
        print(f"平均失真指数: {round(statistics.mean(indices),1)}")
        print(f"中位数: {round(statistics.median(indices),1)}")
        print(f"最高: {max(indices)} (@{max(profiles, key=lambda x: x['distortion_index'])['handle']})")
        print(f"最低: {min(indices)}")

        # 与预期对比
        correct = sum(1 for p in profiles if
            (p["expected"]=="low" and p["distortion_index"]<=15) or
            (p["expected"]=="moderate" and 8<=p["distortion_index"]<=25) or
            (p["expected"]=="high" and p["distortion_index"]>=15))
        print(f"\n预期方向正确: {correct}/{len(profiles)} ({round(correct/len(profiles)*100)}%)")

        # 按类别
        from collections import defaultdict
        by_cat = defaultdict(list)
        for p in profiles:
            by_cat[p["category"]].append(p)
        print("\n按类别:")
        for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            idx = [a["distortion_index"] for a in accs]
            print(f"  {cat:<15} n={len(accs):2d} avg={round(statistics.mean(idx),1):5.1f} max={max(idx)} min={min(idx)}")

        # 五维度
        print("\n五维度触发情况:")
        for dim in ["temporal_distortion","significance_inflation","anxiety_manufacturing","novelty_claims"]:
            flagged = [p for p in profiles if p[dim] > 0]
            if flagged:
                print(f"  {dim}: {len(flagged)}个账号触发，最高 {max(p[dim] for p in flagged)}%")
                for p in sorted(flagged, key=lambda x: -x[dim])[:3]:
                    print(f"    @{p['handle']}: {p[dim]}%")
            else:
                print(f"  {dim}: 0个账号触发")

        # Step 5: 导出
        print(f"\n{'='*60}\nStep 5: 导出\n{'='*60}")

        # corpus.jsonl
        with open(OUTPUT_DIR/"corpus.jsonl", "w", encoding="utf-8") as f:
            for item in corpus:
                f.write(json.dumps(item, ensure_ascii=False)+"\n")
        print(f"  corpus.jsonl — {len(corpus)} 条")

        # profiles.csv
        fields = ["handle","platform","category","expected","distortion_index",
                  "significance_inflation","anxiety_manufacturing","novelty_claims",
                  "temporal_distortion","consistency_score","deletion_rate",
                  "deleted_count","total_posts","analyzed_at"]
        with open(OUTPUT_DIR/"profiles.csv","w",newline="",encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(profiles, key=lambda x: x["distortion_index"], reverse=True))
        print(f"  profiles.csv — {len(profiles)} 行")

        # report.md
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        flagged_posts = sum(1 for c in corpus if c["distortion_types"])
        all_types = []
        for c in corpus:
            all_types.extend(c["distortion_types"])
        type_counts = Counter(all_types)

        lines = [
            "# Bluesky Platform Experiment — Research Report",
            f"\nGenerated: {now}",
            f"\n---\n",
            "## 1. Overview",
            f"- Platform: **Bluesky** (short-form social, ~300 char limit)",
            f"- Accounts analyzed: **{len(profiles)}**",
            f"- Total posts: **{sum(p['total_posts'] for p in profiles)}**",
            f"- Avg distortion index: **{round(statistics.mean(indices),1)}/100**",
            f"- Median: {round(statistics.median(indices),1)}",
            f"- Posts with distortion flags: **{flagged_posts}** ({round(flagged_posts/len(corpus)*100,1) if corpus else 0}%)",
            "",
            "## 2. Comparison with Previous Batches",
            "",
            "| Platform | Accounts | Avg Index | Format |",
            "|----------|----------|-----------|--------|",
            f"| RSS/Newsletter | 65 | 10.4 | Long-form |",
            f"| YouTube | 10 | 9.0 | Video transcript |",
            f"| **Bluesky** | **{len(profiles)}** | **{round(statistics.mean(indices),1)}** | **Short-form social** |",
            "",
            "## 3. Account Profiles",
            "",
            "| Account | Category | Expected | Index | Inflation | Anxiety | Novelty | Temporal | Posts |",
            "|---------|----------|----------|-------|-----------|---------|---------|----------|-------|",
        ]
        for p in sorted(profiles, key=lambda x: x["distortion_index"], reverse=True):
            match = "✓" if (
                (p["expected"]=="low" and p["distortion_index"]<=15) or
                (p["expected"]=="moderate" and 8<=p["distortion_index"]<=25) or
                (p["expected"]=="high" and p["distortion_index"]>=15)
            ) else "✗"
            lines.append(
                f"| @{p['handle']} | {p['category']} | {p['expected']} {match} | "
                f"**{p['distortion_index']}** | {p['significance_inflation']}% | "
                f"{p['anxiety_manufacturing']}% | {p['novelty_claims']}% | "
                f"{p['temporal_distortion']}% | {p['total_posts']} |"
            )

        lines += ["", "## 4. Cross-Category", "",
                  "| Category | n | Avg Index | Inflation | Anxiety | Novelty | Temporal |",
                  "|----------|---|-----------|-----------|---------|---------|----------|"]
        for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
            idx = [a["distortion_index"] for a in accs]
            lines.append(
                f"| {cat} | {len(accs)} | **{round(statistics.mean(idx),1)}** | "
                f"{round(statistics.mean(a['significance_inflation'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['anxiety_manufacturing'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['novelty_claims'] for a in accs),1)}% | "
                f"{round(statistics.mean(a['temporal_distortion'] for a in accs),1)}% |"
            )

        lines += ["", "## 5. Distortion Type Distribution", ""]
        total_c = len(corpus)
        for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {dtype}: {count} posts ({round(count/total_c*100,1) if total_c else 0}%)")

        lines += [
            "",
            "## 6. Key Finding: Short-form vs Long-form",
            "",
            "> This batch tests **short-form social content** (Bluesky, ~300 chars/post)",
            "> vs previous batches which were all long-form (newsletters, blog posts, videos).",
            "> The distortion pattern difference between formats is the core research question.",
            "",
            "---", f"*{now}*"
        ]

        with open(OUTPUT_DIR/"report.md","w",encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  report.md")
        print(f"  successful_profiles.json — {len(cache)} 个账号")

    print(f"\n{'='*60}")
    print(f"✓ 完成！{len(profiles)} 个账号 | {len(corpus)} 条帖子")
    print(f"  结果保存在 {OUTPUT_DIR}/")
    print(f"  下次运行自动跳过已成功的账号")
    print("="*60+"\n")

if __name__ == "__main__":
    asyncio.run(main())
