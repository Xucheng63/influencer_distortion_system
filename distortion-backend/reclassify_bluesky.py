#!/usr/bin/env python3
"""
reclassify_bluesky.py
读取 research_results_bluesky/corpus.jsonl（54个账号，2680条帖子）
用五维度新规则 → 负向过滤 → GPT-4o-mini 核实 重新打分。

运行：
  cd ~/Desktop/ischool/distortion-full-project/distortion-backend
  conda activate ischool
  python reclassify_bluesky.py

输出（research_results_bluesky/ 目录下）：
  corpus_v2.jsonl          ← 帖子级，覆盖旧分类结果
  profiles_v2.json         ← 账号级汇总（含五维度比率 + 新 DI）
  profiles_v2.csv          ← 汇总表
  report_v2.md             ← 可读报告

中断后重跑：已完成的 post_id 自动跳过。
"""
import asyncio, json, os, re, csv, time, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── 路径 ──────────────────────────────────────────────────────────────────────
INPUT_CORPUS   = Path("research_results_bluesky/corpus.jsonl")
INPUT_PROFILES = Path("research_results_bluesky/successful_profiles.json")
OUTPUT_DIR     = Path("research_results_bluesky")
OUT_JSONL      = OUTPUT_DIR / "corpus_v2.jsonl"
OUT_JSON       = OUTPUT_DIR / "profiles_v2.json"
OUT_CSV        = OUTPUT_DIR / "profiles_v2.csv"
OUT_REPORT     = OUTPUT_DIR / "report_v2.md"
PROGRESS_FILE  = OUTPUT_DIR / "progress_v2.json"

# ══════════════════════════════════════════════════════════════════════════════
# 五维度规则（与新版 classifier.py 完全一致）
# ══════════════════════════════════════════════════════════════════════════════
STRONG_PATTERNS = {
    "inflate": [
        r"change[sd]? everything",
        r"changes? the (world|game|industry|future)",
        r"once.in.a.generation",
        r"end of (an? )?(era|age|chapter)",
        r"signals? the (end|death|collapse)",
        r"\bEVERYTHING\b",
        r"unlike anything (i'?ve|we'?ve) (ever )?seen",
        r"history.{0,10}making",
        r"never (seen|been) (anything )?like this",
    ],
    "anxiety": [
        r"you('ll| will) (regret|miss|be left behind)",
        r"(unemploy|irrelevant|obsolete).{0,30}(you|your|we|everyone)",
        r"won'?t see it coming",
        r"running out of time",
        r"(left behind|fall behind).{0,20}(if|unless|who)",
        r"(6|12|18|24) months?.{0,20}(unemploy|irrelevant|obsolete|over)",
    ],
    "novelty": [
        r"nobody (is |was )?(talking|writing|covering) (about )?this",
        r"no one (is |was )?(talking|knows) (about )?this",
        r"exclusive (first look|access|preview)",
        r"before (anyone|everybody|the world) (else )?knows",
        r"first (person|one) to (discover|build|create|reveal)",
        r"I'?ve been (saying|warning|predicting) (this|it) (for|since) \d",
    ],
    "loaded_language": [
        r"\b(devastating|catastrophic|apocalyptic|horrifying|terrifying)\b",
        r"\b(disastrous|catastrophically|utterly (broken|failed|destroyed))\b",
        r"\b(explosive|bombshell|earth.?shattering|mind.?blowing)\b",
        r"\b(insane(ly)?|insanity|absolutely (insane|insanely))\b",
        r"\b(dead|dying|killed|destroying|obliterating).{0,20}(industry|economy|job|career|future)\b",
        r"震惊|骇人|毁灭性|爆炸性|颠覆性|惊天|惨烈|恐怖的|极度震惊",
    ],
    "temporal": [
        r"\bbreaking\b.{0,30}(news|report|development|announcement)",
        r"just (dropped|announced|released|published).{0,20}(today|this|new)",
        r"(brand.new|brand new).{0,20}(tool|study|report|paper|model)",
        r"latest (breaking|urgent|exclusive)",
    ],
}

WEAK_PATTERNS = {
    "inflate": [
        r"most important",
        r"biggest (thing|shift|move|development)",
        r"massive (shift|change|implications|opportunity)",
        r"game.changer",
        r"revolutionary",
        r"unprecedented",
    ],
    "anxiety": [
        r"\b(panic|panicking)\b",
        r"too late",
        r"(threat|danger|crisis).{0,20}(career|job|future)",
        r"(survival|survive).{0,20}(this|change)",
        r"(left behind|fall behind)",
    ],
    "novelty": [
        r"i (found|discovered|built|created|invented)",
        r"(secret|hidden|buried).{0,20}(truth|fact|insight|technique)",
        r"nobody (is |was )?(talking|writing)",
    ],
    "loaded_language": [
        r"\b(shocking|outrageous)\b",
        r"\b(incredible|unbelievable|unreal|jaw.?dropping)\b",
        r"\b(brutal(ly)?|savage(ly)?)\b",
        r"\b(epic|legendary|monumental|massive(ly)?)\b",
        r"\b(terrifying|horrifying|scary|alarming)\b",
        r"\b(stunning(ly)?|staggering(ly)?|astounding(ly)?)\b",
        r"\b(insane|crazy|absurd|ridiculous).{0,10}(amount|level|number|degree)\b",
        r"\b(absolutely|completely|totally|utterly).{0,10}(wrong|broken|failed|ruined)\b",
        r"\b[A-Z]{4,}\b",
        r"!{2,}",
        r"惊人|震撼|爆款|刷屏|炸裂|疯狂|狂飙|狂热|极致|超乎想象",
    ],
    "temporal": [
        r"just (dropped|announced|released|published)",
        r"(happening|unfolding) (right )?now",
        r"latest (news|development|update)",
    ],
}

EXCLUSION_PATTERNS = {
    "temporal": [
        r"this (morning|week|hour).{0,30}(i |my |we |had |read |went |saw |met |did |got |was )",
        r"(good|great|nice|lovely|wonderful|bad|rough|tough|long|short) (morning|week|day|hour)",
        r"this (morning|week)\s*[.!?]?\s*$",
    ],
    "anxiety": [
        r"(never )?too late to (learn|start|try|change|grow|improve)",
        r"it'?s (not |never )?too late",
    ],
        "loaded_language": [
        r"(critical|severe|high).{0,10}(vulnerability|bug|error|issue|flaw)",
        r"(aggressive|brutal).{0,10}(optimization|compression|training|schedule)",
        r"(explosive|exponential).{0,10}(growth|increase|rise).{0,20}(in|of|for)\s+\w+\s+(users|revenue|traffic|metrics)",
        r'["\u201c\u201d\u2018\u2019].{0,200}(shocking|devastating|explosive|insane).{0,200}["\u201c\u201d\u2018\u2019]',
        r"(game|match|season|playoff|championship).{0,30}(insane|crazy|incredible|unbelievable)",
    ],
}

_s = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in STRONG_PATTERNS.items()}
_w = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in WEAK_PATTERNS.items()}
_e = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in EXCLUSION_PATTERNS.items()}

STRONG_WEIGHT  = 0.35
WEAK_WEIGHT    = 0.15
WEAK_MIN       = 2
CONFIDENCE_CAP = 0.95
LLM_THRESHOLD  = 0.70
VERIFY_ALL     = True

_QUOTE_RE = [
    re.compile(r'"([^"]{10,300})"'),
    re.compile(r'\u201c([^\u201d]{10,300})\u201d'),
    re.compile(r'(?:via|from|—|–|-)\s+\w[\w\s]+:', re.IGNORECASE),
    re.compile(r'^>\s+.+$', re.MULTILINE),
]

def _strip_quotes(text: str) -> tuple[str, str]:
    quoted, author = [], text
    for pat in _QUOTE_RE:
        for m in pat.finditer(text):
            quoted.append(m.group(0))
        author = pat.sub(' ', author)
    return ' '.join(author.split()), ' '.join(quoted)


def classify_rules(content: str) -> dict:
    author_text, quoted_text = _strip_quotes(content)
    types, signals, excluded = [], [], []
    conf = 0.0

    for dtype in ("inflate", "anxiety", "novelty", "loaded_language", "temporal"):
        sh_a = [m.group(0) for p in _s.get(dtype, []) for m in [p.search(author_text)] if m]
        wh_a = [m.group(0) for p in _w.get(dtype, []) for m in [p.search(author_text)] if m]
        sh_q = ([m.group(0) for p in _s.get(dtype, []) for m in [p.search(quoted_text)] if m]
                if quoted_text else [])

        if any(p.search(author_text) for p in _e.get(dtype, [])):
            excluded.append(dtype)
            continue

        triggered, tc = False, 0.0
        if sh_a:
            triggered = True; tc += len(sh_a) * STRONG_WEIGHT; signals.extend(sh_a)
        if len(wh_a) >= WEAK_MIN:
            triggered = True; tc += len(wh_a) * WEAK_WEIGHT; signals.extend(wh_a)
        elif wh_a and sh_a:
            tc += len(wh_a) * WEAK_WEIGHT; signals.extend(wh_a)
        if len(sh_q) >= WEAK_MIN and not triggered:
            triggered = True; tc += len(sh_q) * WEAK_WEIGHT
            signals.extend(f'[quoted] {s}' for s in sh_q)

        if triggered:
            types.append(dtype); conf += tc

    if not types:
        conf = 1.0

    return {
        "types": types,
        "excluded_by_regex": excluded,
        "confidence": round(min(conf, CONFIDENCE_CAP), 3),
        "signals": list(dict.fromkeys(signals)),
        "method": "rules_v2",
    }


def _get_client():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return None
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=key)


_SYS_VERIFY = """You are a precise classifier verifying distortion detection in social media posts.

Distortion types:
- inflate: exaggerates significance ("changes everything", "once in a generation", "EVERYTHING is broken")
- anxiety: manufactures fear about career/life ("you'll be left behind", "unemployable in 6 months")
- novelty: falsely claims first/exclusive ("nobody talking about this", "I discovered a secret technique")
- loaded_language: emotionally charged words beyond what content warrants ("catastrophic", "devastating", excessive ALL-CAPS, !!!)
- temporal: frames old content as breaking/new ("Breaking news" on an old story)

False-positive guards:
- Casual time refs ("this morning", "last week") → NOT temporal
- Encouragement ("never too late to learn") → NOT anxiety
- Technical terms ("critical vulnerability", "severe bug") → NOT loaded_language
- Quantified growth stats → NOT loaded_language
- Sports/game context → NOT loaded_language

Return ONLY valid JSON:
{"types":[...],"confidence":0.85,"signals":[...],"corrections":{"removed":[...],"added":[]}}"""

_SYS_FRESH = """You are a classifier for rhetorical distortion in social media posts.

Types: inflate | anxiety | novelty | loaded_language | temporal
- inflate: exaggerates significance of ordinary events
- anxiety: manufactures fear about career/life consequences
- novelty: falsely claims to be first/exclusive/undiscovered
- loaded_language: emotionally charged words disproportionate to content (ALL-CAPS, !!!, "catastrophic", "devastating")
- temporal: frames old content as breaking or new

Critical false-positive rules:
- Casual time refs → NOT temporal; encouragement → NOT anxiety
- Technical severity terms → NOT loaded_language; quantified facts → NOT loaded_language
- Only flag clear manipulative intent

Return ONLY JSON: {"types":[...],"confidence":0.0-1.0,"signals":["phrase"]}"""


async def verify_with_gpt(content: str, rule_result: dict) -> dict:
    client = _get_client()
    if not client:
        return rule_result
    detected = rule_result["types"]
    excluded = rule_result.get("excluded_by_regex", [])
    signals  = rule_result["signals"]
    parts    = []
    if detected:
        parts.append(f"Flagged: {', '.join(detected)}\nSignals: {', '.join(signals) or 'none'}\n→ Correct or false positives?")
    if excluded:
        parts.append(f"EXCLUDED: {', '.join(excluded)}\n→ Any false negatives?")
    if not parts:
        return rule_result
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=300,
            messages=[
                {"role": "system", "content": _SYS_VERIFY},
                {"role": "user",   "content": f'Post: "{content[:600]}"\n\n' + "\n".join(parts)},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["method"] = "gpt-4o-mini-verify"
        result.pop("corrections", None)
        return result
    except Exception as e:
        rule_result["method"] = f"rules_v2_gpt_error:{e}"
        return rule_result


async def classify_llm_fresh(content: str) -> dict:
    client = _get_client()
    if not client:
        return {"types": [], "confidence": 0.5, "signals": [], "method": "llm_unavailable"}
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=200,
            messages=[
                {"role": "system", "content": _SYS_FRESH},
                {"role": "user",   "content": f"Classify:\n\n{content[:600]}"},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["method"] = "gpt-4o-mini"
        return result
    except Exception as e:
        return {"types": [], "confidence": 0.5, "signals": [], "method": f"llm_error:{e}"}


async def classify(content: str) -> dict:
    r = classify_rules(content)
    if r["types"] and r["confidence"] < LLM_THRESHOLD:
        return await classify_llm_fresh(content)
    if VERIFY_ALL and (r["types"] or r.get("excluded_by_regex")):
        return await verify_with_gpt(content, r)
    return r


def compute_distortion_index(rates: dict) -> int:
    w = {"significance_inflation": 0.30, "anxiety_manufacturing": 0.25,
         "novelty_claims": 0.20, "loaded_language": 0.15, "temporal_distortion": 0.10}
    return min(100, round(sum(rates.get(k, 0) * v for k, v in w.items()) * 100))


# ══════════════════════════════════════════════════════════════════════════════
async def main():
    print("\n" + "="*60)
    print("Bluesky 重新分类 — 五维度 v2")
    print(f"输入: {INPUT_CORPUS}")
    print(f"GPT 核实: {'✓ 开启' if os.getenv('OPENAI_API_KEY') else '✗ 关闭（仅规则层）'}")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    # 读取所有帖子
    all_posts = []
    with open(INPUT_CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_posts.append(json.loads(line))
    print(f"读取 {len(all_posts)} 条帖子\n")

    # 读取旧账号 meta（category / expected 等）
    old_meta = {}
    if INPUT_PROFILES.exists():
        with open(INPUT_PROFILES, encoding="utf-8") as f:
            old_meta = json.load(f)

    # 断点续跑
    done_ids: set = set()
    if PROGRESS_FILE.exists():
        done_ids = set(json.loads(PROGRESS_FILE.read_text()).get("done_ids", []))
    print(f"已完成: {len(done_ids)} 条，剩余: {len(all_posts) - len(done_ids)} 条\n")

    # 输出文件（追加模式）
    out_rows: list[dict] = []
    if OUT_JSONL.exists():
        with open(OUT_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out_rows.append(json.loads(line))

    # ── 按 handle 分组 ────────────────────────────────────────────────────────
    from collections import OrderedDict
    handle_posts: dict = OrderedDict()
    for post in all_posts:
        h = post.get("handle", "unknown")
        handle_posts.setdefault(h, []).append(post)
    total_accounts = len(handle_posts)
    done_accounts  = sum(1 for posts in handle_posts.values()
                         if all(str(p.get("post_id","")) in done_ids for p in posts))
    print(f"账号数: {total_accounts}  已完成账号: {done_accounts}\n")

    # ── 逐账号分类（和 Weibo/Twitter 显示方式一致） ───────────────────────────
    with open(OUT_JSONL, "a", encoding="utf-8") as out_fh:
        for acc_idx, (handle, posts) in enumerate(handle_posts.items(), 1):
            # 检查该账号是否全部完成
            pending = [p for p in posts if str(p.get("post_id","")) not in done_ids]
            if not pending:
                for p in posts:
                    out_rows.append(p)
                continue

            print(f"  [{acc_idx:3d}/{total_accounts}] {handle:<28} ({len(posts)} 帖)...", end="", flush=True)
            t0 = time.time()
            dim_counts = defaultdict(int)
            acc_rows   = []

            for post in posts:
                pid     = str(post.get("post_id", ""))
                content = post.get("content", "").strip()

                if pid in done_ids:
                    acc_rows.append(post)
                    for t in post.get("distortion_types", []):
                        dim_counts[t] += 1
                    continue

                result = await classify(content[:800])
                await asyncio.sleep(0.15)

                row = {
                    **post,
                    "distortion_types": result.get("types", []),
                    "confidence":       result.get("confidence", 0),
                    "signals":          result.get("signals", []),
                    "method":           result.get("method", ""),
                    "reclassified_at":  datetime.utcnow().isoformat(),
                }
                out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                out_fh.flush()
                acc_rows.append(row)
                done_ids.add(pid)
                for t in result.get("types", []):
                    dim_counts[t] += 1

            out_rows.extend(acc_rows)
            PROGRESS_FILE.write_text(json.dumps({"done_ids": list(done_ids)}))

            n = len(posts)
            rates = {
                "significance_inflation": dim_counts["inflate"] / n,
                "anxiety_manufacturing":  dim_counts["anxiety"] / n,
                "novelty_claims":         dim_counts["novelty"] / n,
                "loaded_language":        dim_counts["loaded_language"] / n,
                "temporal_distortion":    dim_counts["temporal"] / n,
            }
            di      = compute_distortion_index(rates)
            elapsed = round(time.time() - t0, 1)
            print(
                f" ({elapsed}s)  DI={di}"
                f"  infl={rates['significance_inflation']*100:.1f}%"
                f"  anx={rates['anxiety_manufacturing']*100:.1f}%"
                f"  LL={rates['loaded_language']*100:.1f}%"
                f"  [已保存]"
            )

    print(f"\n  帖子分类完成，共 {len(out_rows)} 条")

    # ── 按账号聚合 DI ──────────────────────────────────────────────────────────
    account_posts: dict[str, list] = defaultdict(list)
    for row in out_rows:
        account_posts[row["handle"]].append(row)

    profiles = []
    for handle, posts in account_posts.items():
        n = len(posts)
        dim = defaultdict(int)
        for p in posts:
            for t in p.get("distortion_types", []):
                dim[t] += 1
        rates = {
            "significance_inflation": dim["inflate"] / n,
            "anxiety_manufacturing":  dim["anxiety"] / n,
            "novelty_claims":         dim["novelty"] / n,
            "loaded_language":        dim["loaded_language"] / n,
            "temporal_distortion":    dim["temporal"] / n,
        }
        di = compute_distortion_index(rates)
        meta = old_meta.get(handle, {})
        profiles.append({
            "handle":   handle,
            "platform": "bluesky",
            "category": posts[0].get("category", meta.get("category", "")),
            "expected": meta.get("expected", ""),
            "distortion_index": di,
            "significance_inflation_rate": round(rates["significance_inflation"] * 100, 2),
            "anxiety_manufacturing_rate":  round(rates["anxiety_manufacturing"] * 100, 2),
            "novelty_claims_rate":         round(rates["novelty_claims"] * 100, 2),
            "loaded_language_rate":        round(rates["loaded_language"] * 100, 2),
            "temporal_distortion_rate":    round(rates["temporal_distortion"] * 100, 2),
            "total_posts":    n,
            "reclassified_at": datetime.utcnow().isoformat(),
        })

    # 保存账号级 JSON
    OUT_JSON.write_text(json.dumps({p["handle"]: p for p in profiles}, ensure_ascii=False, indent=2))

    # ── 汇总打印 ───────────────────────────────────────────────────────────────
    indices = [p["distortion_index"] for p in profiles]
    print(f"\n{'='*60}")
    print(f"账号={len(profiles)}  帖子={len(out_rows)}  平均DI={round(statistics.mean(indices),1)}")
    print(f"最高: {max(indices)} ({max(profiles, key=lambda x: x['distortion_index'])['handle']})")
    print(f"最低: {min(indices)} ({min(profiles, key=lambda x: x['distortion_index'])['handle']})")

    by_cat = defaultdict(list)
    for p in profiles:
        by_cat[p["category"]].append(p)
    print(f"\n{'类别':20s} {'n':>3}  {'avgDI':>6}  {'infl%':>6}  {'anx%':>5}  {'LL%':>5}  {'td%':>5}")
    print("-"*58)
    for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
        di   = statistics.mean(a["distortion_index"] for a in accs)
        infl = statistics.mean(a["significance_inflation_rate"] for a in accs)
        anx  = statistics.mean(a["anxiety_manufacturing_rate"] for a in accs)
        ll   = statistics.mean(a["loaded_language_rate"] for a in accs)
        td   = statistics.mean(a["temporal_distortion_rate"] for a in accs)
        print(f"{cat:20s} {len(accs):3d}  {di:6.1f}  {infl:6.2f}  {anx:5.2f}  {ll:5.2f}  {td:5.2f}")

    # ── CSV ────────────────────────────────────────────────────────────────────
    fields = ["handle","platform","category","expected","distortion_index",
              "significance_inflation_rate","anxiety_manufacturing_rate",
              "novelty_claims_rate","loaded_language_rate","temporal_distortion_rate",
              "total_posts","reclassified_at"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(profiles, key=lambda x: x["distortion_index"], reverse=True))
    print(f"\n✓ corpus_v2.jsonl — {len(out_rows)} 条")
    print(f"✓ profiles_v2.json — {len(profiles)} 个账号")
    print(f"✓ profiles_v2.csv")

    # ── Markdown 报告 ──────────────────────────────────────────────────────────
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    avg = round(statistics.mean(indices), 1)
    lines = [
        "# Bluesky 重分类报告（五维度 v2）",
        f"\n生成时间: {now}",
        "\n公式: `DI = SI×0.30 + AM×0.25 + NC×0.20 + LL×0.15 + TD×0.10`\n",
        "---\n## 概览",
        f"- 账号数: **{len(profiles)}**  帖子数: **{len(out_rows)}**  平均DI: **{avg}**",
        f"- 最高: **{max(indices)}** ({max(profiles, key=lambda x:x['distortion_index'])['handle']})",
        f"- 最低: **{min(indices)}** ({min(profiles, key=lambda x:x['distortion_index'])['handle']})\n",
        "## 账号档案（按DI降序）\n",
        "| 账号 | 类别 | 预期 | DI | 膨胀% | 焦虑% | 新颖% | LL% | 时间% | 帖数 |",
        "|------|------|------|-----|-------|-------|-------|-----|-------|------|",
    ]
    for p in sorted(profiles, key=lambda x: x["distortion_index"], reverse=True):
        lines.append(
            f"| {p['handle']} | {p['category']} | {p.get('expected','')} "
            f"| **{p['distortion_index']}** "
            f"| {p['significance_inflation_rate']} | {p['anxiety_manufacturing_rate']} "
            f"| {p['novelty_claims_rate']} | {p['loaded_language_rate']} "
            f"| {p['temporal_distortion_rate']} | {p['total_posts']} |"
        )
    lines += ["", "---", f"*{now}*"]
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ report_v2.md")
    print(f"\n输出目录: {OUTPUT_DIR.resolve()}/")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
