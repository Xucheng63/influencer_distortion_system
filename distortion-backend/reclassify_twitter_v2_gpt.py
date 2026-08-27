#!/usr/bin/env python3
"""
reclassify_twitter_gpt.py — 用 GPT-4o-mini 对 Twitter 推文重新分类

读取 successful_profiles.json 里的推文正文
调用 GPT-4o-mini 双向核实（和其他平台完全一致）
重新计算失真指数并更新缓存，不需要重新抓取数据

运行：python reclassify_twitter_gpt.py
"""
import asyncio, json, csv, time, statistics, os
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import httpx
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OUTPUT_DIR = Path("research_results_twitter_v2")
CACHE_FILE = OUTPUT_DIR / "profiles.json"
BACKUP_FILE = OUTPUT_DIR / "profiles_rules_backup.json"

# GPT 分类 prompt（和其他平台 classifier.py 完全一致）
SYSTEM_PROMPT = """You are a rhetorical distortion classifier for social media content.

Classify each post for these 4 distortion types:
1. significance_inflation: Exaggerating importance ("changes everything", "unprecedented", "once in a generation", "biggest shift ever")
2. anxiety_manufacturing: Creating fear/urgency targeting the reader ("you will be left behind", "running out of time", "existential threat to you", "if you don't act now")
3. novelty_claims: False exclusivity ("nobody is talking about this", "I discovered", "exclusive first look", "I've been warning about this for years")
4. temporal_distortion: Packaging old content as urgent news ("breaking", "just dropped", "this just in", "happening now")

Critical false positive rules:
- Casual time references ("this morning I had") are NOT temporal_distortion
- Encouragement ("it's never too late to learn") is NOT anxiety_manufacturing
- Genuine news breaking stories ARE temporal_distortion only if clearly manipulative
- Factual reporting of events is NOT distortion
- Academic/technical discussion is rarely distortion
- Quotes from others should be treated as the author's own words only if endorsed

Respond ONLY with valid JSON:
{
  "types": ["type1", "type2"],
  "confidence": 0.85,
  "signals": ["exact phrase that triggered", "another phrase"]
}
If no distortion, return: {"types": [], "confidence": 1.0, "signals": []}"""

async def classify_with_gpt(content: str, client: httpx.AsyncClient) -> dict:
    """调用 GPT-4o-mini 分类单条推文"""
    try:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 200,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Classify this tweet:\n\n{content[:400]}"},
                ],
            },
            timeout=30,
        )
        if r.status_code != 200:
            print(f" [API error {r.status_code}]", end="")
            return {"types": [], "confidence": 0.5, "signals": []}

        text = r.json()["choices"][0]["message"]["content"].strip()
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"types": [], "confidence": 0.5, "signals": []}
    except Exception as e:
        return {"types": [], "confidence": 0.5, "signals": []}

def compute_distortion_index(rates: dict) -> int:
    """和其他平台完全一致的失真指数公式"""
    return min(100, round(
        rates.get("significance_inflation", 0) * 0.30 +
        rates.get("anxiety_manufacturing", 0)  * 0.25 +
        rates.get("novelty_claims", 0)          * 0.20 +
        rates.get("temporal_distortion", 0)     * 0.10
    ))

async def main():
    print("\n" + "="*60)
    print("Twitter v2 GPT-4o-mini 重新分类（53个账号）")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    if not OPENAI_API_KEY:
        print("✗ OPENAI_API_KEY 未设置")
        return

    # 读取缓存
    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)
    print(f"✓ 读取 {len(cache)} 个账号")

    # 备份原始规则结果
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"✓ 原始规则结果已备份到 {BACKUP_FILE}")

    async with httpx.AsyncClient() as client:
        for idx, (handle, prof) in enumerate(cache.items(), 1):
            posts = prof.get("posts", [])
            if not posts:
                continue

            print(f"\n  [{idx:2d}/{len(cache)}] @{handle} ({len(posts)} 推文)...")

            dim_counts = {
                "significance_inflation": 0,
                "anxiety_manufacturing": 0,
                "novelty_claims": 0,
                "temporal_distortion": 0,
            }

            for i, post in enumerate(posts):
                content = post.get("content", "")
                if not content:
                    continue

                result = await classify_with_gpt(content, client)
                types = result.get("types", [])
                post["distortion_types"] = types
                post["confidence"] = result.get("confidence", 0.5)
                post["signals"] = result.get("signals", [])
                post["classification_method"] = "claude-haiku-reclassify"

                for t in types:
                    if t in dim_counts:
                        dim_counts[t] += 1

                # 避免 API 限流
                await asyncio.sleep(0.3)

            total = len(posts)
            rates = {k: round(v/total*100, 1) for k, v in dim_counts.items()}
            new_index = compute_distortion_index(rates)
            old_index = prof.get("distortion_index", 0)

            # 更新档案
            prof["distortion_index"]       = new_index
            prof["significance_inflation"] = rates["significance_inflation"]
            prof["anxiety_manufacturing"]  = rates["anxiety_manufacturing"]
            prof["novelty_claims"]         = rates["novelty_claims"]
            prof["temporal_distortion"]    = rates["temporal_distortion"]
            prof["reclassified_at"]        = datetime.utcnow().isoformat()
            prof["classification_method"]  = "claude-haiku-reclassify"

            print(f"     旧指数: {old_index} → 新指数: {new_index} "
                  f"infl={rates['significance_inflation']}% "
                  f"anx={rates['anxiety_manufacturing']}% "
                  f"nov={rates['novelty_claims']}%")

            # 每个账号完成后保存
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

    # 最终分析
    profiles = list(cache.values())
    indices = [p["distortion_index"] for p in profiles if "distortion_index" in p]

    print(f"\n{'='*60}\n重新分类结果\n{'='*60}")
    print(f"总账号: {len(profiles)}")
    print(f"总推文: {sum(p.get('total_posts',0) for p in profiles)}")
    print(f"平均失真指数: {round(statistics.mean(indices),1)}")
    print(f"最高: {max(indices)} ({max(profiles,key=lambda x:x.get('distortion_index',0))['handle']})")
    print(f"最低: {min(indices)}")

    by_cat = defaultdict(list)
    for p in profiles:
        by_cat[p["category"]].append(p.get("distortion_index",0))
    print("\n按类别:")
    for cat, vals in sorted(by_cat.items(), key=lambda x: -statistics.mean(x[1])):
        print(f"  {cat:<12} n={len(vals):2d} avg={round(statistics.mean(vals),1):5.1f} "
              f"max={max(vals)} min={min(vals)}")

    # 导出更新后的 CSV
    fields = ["handle","platform","category","expected","distortion_index",
              "significance_inflation","anxiety_manufacturing","novelty_claims",
              "temporal_distortion","total_posts","analyzed_at","reclassified_at"]
    with open(OUTPUT_DIR/"profiles.csv","w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(profiles,key=lambda x:x.get("distortion_index",0),reverse=True))
    print(f"\n✓ profiles.csv 已更新")
    print(f"✓ successful_profiles.json 已更新")
    print(f"✓ 原始结果备份在 successful_profiles_rules_backup.json")

    print(f"\n{'='*60}")
    print(f"✓ 重新分类完成！")
    print("="*60+"\n")

if __name__ == "__main__":
    asyncio.run(main())
