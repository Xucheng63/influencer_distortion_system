#!/usr/bin/env python3
"""
reclassify_weibo.py
读取 research_results_weibo/successful_profiles.json（69个账号，3240条帖子）
用五维度新规则 → 负向过滤 → GPT-4o-mini 核实 重新打分。

运行：
  cd ~/Desktop/ischool/distortion-full-project/distortion-backend
  conda activate ischool
  python reclassify_weibo.py

输出（research_results_weibo/ 目录下）：
  profiles_v2.json     ← 账号级，含新 DI + 五维度比率 + posts（带分类结果）
  corpus_v2.jsonl      ← 帖子级，每行一条，方便跨平台合并
  profiles_v2.csv      ← 汇总表，直接导入 Excel / R
  report_v2.md         ← 可读报告

中断后重跑：已完成的账号自动跳过。
"""
import asyncio, json, os, re, csv, time, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── 路径 ──────────────────────────────────────────────────────────────────────
INPUT_FILE  = Path("research_results_weibo/successful_profiles.json")
OUTPUT_DIR  = Path("research_results_weibo")
OUT_JSON    = OUTPUT_DIR / "profiles_v2.json"
OUT_JSONL   = OUTPUT_DIR / "corpus_v2.jsonl"
OUT_CSV     = OUTPUT_DIR / "profiles_v2.csv"
OUT_REPORT  = OUTPUT_DIR / "report_v2.md"

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
        # 英文强情感词
        r"\b(devastating|catastrophic|apocalyptic|horrifying|terrifying)\b",
        r"\b(disastrous|catastrophically|utterly (broken|failed|destroyed))\b",
        r"\b(explosive|bombshell|earth.?shattering|mind.?blowing)\b",
        r"\b(insane(ly)?|insanity|absolutely (insane|insanely))\b",
        r"\b(dead|dying|killed|destroying|obliterating).{0,20}(industry|economy|job|career|future)\b",
        # 中文强情感词（微博高频失真信号）
        r"震惊|骇人|毁灭性|爆炸性|颠覆性|惊天|惨烈|恐怖的|极度震惊",
    ],
    "temporal": [
        r"\bbreaking\b.{0,30}(news|report|development|announcement)",
        r"just (dropped|announced|released|published).{0,20}(today|this|new)",
        r"(brand.new|brand new).{0,20}(tool|study|report|paper|model)",
        r"latest (breaking|urgent|exclusive)",
        # 中文时间失真
        r"突发[！!]|【突发】|紧急[！!]|【紧急】",
        r"刚刚[！!：:]|【刚刚】",
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
        # 中文膨胀弱信号
        r"重磅|重大|史上|历史性|里程碑|划时代|前所未有|创纪录|最强|最大|最高",
    ],
    "anxiety": [
        r"\b(panic|panicking)\b",
        r"too late",
        r"(threat|danger|crisis).{0,20}(career|job|future)",
        r"(survival|survive).{0,20}(this|change)",
        r"(left behind|fall behind)",
        # 中文焦虑弱信号
        r"危机|崩溃|末日|完了|倒塌|恐慌|崩了|警惕|危险信号",
    ],
    "novelty": [
        r"i (found|discovered|built|created|invented)",
        r"(secret|hidden|buried).{0,20}(truth|fact|insight|technique)",
        r"nobody (is |was )?(talking|writing)",
        # 中文新颖弱信号
        r"独家|首发|全球首|首次|第一次|史无前例|曝光|揭秘|内幕",
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
        # 中文情感弱信号
        r"惊人|震撼|爆款|刷屏|炸裂|疯狂|狂飙|狂热|极致|超乎想象",
        r"太牛了|绝了|OMG|天啊|我的天|不可思议|刷新认知",
    ],
    "temporal": [
        r"just (dropped|announced|released|published)",
        r"(happening|unfolding) (right )?now",
        r"latest (news|development|update)",
        # 中文时间失真弱信号
        r"最新[！!]|最新消息|最新进展|速报|快讯",
    ],
}

EXCLUSION_PATTERNS = {
    "temporal": [
        r"this (morning|week|hour).{0,30}(i |my |we |had |read |went |saw |met |did |got |was )",
        r"(good|great|nice|lovely|wonderful|bad|rough|tough|long|short) (morning|week|day|hour)",
        r"this (morning|week)\s*[.!?]?\s*$",
        # 中文排除：历史回顾类（非假装突发）
        r"历史上的今天|回顾|当年|多年前|年前的今天|周年",
    ],
    "anxiety": [
        r"(never )?too late to (learn|start|try|change|grow|improve)",
        r"it'?s (not |never )?too late",
        # 中文排除：鼓励性表达
        r"不要慌|不必担心|无需恐慌|保持冷静|理性看待",
    ],
    "loaded_language": [
        # 技术/专业术语（非情感滥用）
        r"(critical|severe|high).{0,10}(vulnerability|bug|error|issue|flaw)",
        r"(aggressive|brutal).{0,10}(optimization|compression|training|schedule)",
        # 量化的增长描述（有数据支撑，非夸张）
        r"(explosive|exponential).{0,10}(growth|increase|rise).{0,20}(in|of|for)\s+\w+\s+(users|revenue|traffic|metrics)",
        # 引号内他人说的话
        r'["\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f].{0,200}'
        r'(shocking|devastating|explosive|insane|震惊|炸裂).{0,200}'
        r'["\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f]',
        # 体育赛事语境
        r"(game|match|season|playoff|championship|比赛|球赛|赛事).{0,30}(insane|crazy|incredible|unbelievable|精彩|惊天)",
        # 中文：带数据的客观陈述
        r"(增长|上涨|下跌|跌幅|涨幅).{0,10}[\d\.]+[%％]",
    ],
    "novelty": [
        # 中文排除：官方通报/正式发布用语（非"独家揭秘"）
        r"官方(发布|公告|通报|声明|宣布)",
        r"(新华社|人民日报|央视|官媒).{0,10}(报道|消息|发布)",
    ],
}

# 编译正则
_s = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in STRONG_PATTERNS.items()}
_w = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in WEAK_PATTERNS.items()}
_e = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in EXCLUSION_PATTERNS.items()}

STRONG_WEIGHT  = 0.35
WEAK_WEIGHT    = 0.15
WEAK_MIN       = 2
CONFIDENCE_CAP = 0.95
LLM_THRESHOLD  = 0.70
VERIFY_ALL     = True

# ── 引用检测 ───────────────────────────────────────────────────────────────────
_QUOTE_RE = [
    re.compile(r'"([^"]{10,300})"'),
    re.compile(r'\u201c([^\u201d]{10,300})\u201d'),   # " "
    re.compile(r'\u300c([^\u300d]{5,200})\u300d'),    # 「 」（日文/中文引号）
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


# ══════════════════════════════════════════════════════════════════════════════
# 三级分类流水线
# ══════════════════════════════════════════════════════════════════════════════
def classify_rules(content: str) -> dict:
    author_text, quoted_text = _strip_quotes(content)
    types, signals, excluded = [], [], []
    conf = 0.0

    for dtype in ("inflate", "anxiety", "novelty", "loaded_language", "temporal"):
        sh_a = [m.group(0) for p in _s.get(dtype, []) for m in [p.search(author_text)] if m]
        wh_a = [m.group(0) for p in _w.get(dtype, []) for m in [p.search(author_text)] if m]
        sh_q = ([m.group(0) for p in _s.get(dtype, []) for m in [p.search(quoted_text)] if m]
                if quoted_text else [])

        # 负向过滤（只对作者文字）
        if any(p.search(author_text) for p in _e.get(dtype, [])):
            excluded.append(dtype)
            continue

        triggered, tc = False, 0.0
        if sh_a:
            triggered = True
            tc += len(sh_a) * STRONG_WEIGHT
            signals.extend(sh_a)
        if len(wh_a) >= WEAK_MIN:
            triggered = True
            tc += len(wh_a) * WEAK_WEIGHT
            signals.extend(wh_a)
        elif wh_a and sh_a:
            tc += len(wh_a) * WEAK_WEIGHT
            signals.extend(wh_a)
        if len(sh_q) >= WEAK_MIN and not triggered:
            triggered = True
            tc += len(sh_q) * WEAK_WEIGHT
            signals.extend(f'[quoted] {s}' for s in sh_q)

        if triggered:
            types.append(dtype)
            conf += tc

    if not types:
        conf = 1.0

    return {
        "types":            types,
        "excluded_by_regex": excluded,
        "confidence":       round(min(conf, CONFIDENCE_CAP), 3),
        "signals":          list(dict.fromkeys(signals)),
        "method":           "rules_v2",
    }


def _get_client():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return None
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=key)


_SYS_VERIFY = """You are a precise classifier that verifies distortion detection in social media posts.
The posts may be in Chinese or English.

Distortion types:
- inflate: exaggerates significance ("changes everything", 重磅/史上最/震惊)
- anxiety: manufactures fear about career/life ("you'll be left behind", 崩溃/危机/完了)
- novelty: falsely claims first/exclusive ("nobody talking about this", 独家/首次/曝光)
- loaded_language: emotionally charged words beyond what content warrants (catastrophic, 炸裂/疯狂/绝了, !!!, ALL-CAPS)
- temporal: frames old content as breaking ("Breaking news", 突发/刚刚 on old story)

False-positive guards:
- 历史上的今天 / 回顾 → NOT temporal (it's explicitly historical)
- 官方发布 / 新华社报道 → NOT novelty (it's a legitimate announcement)
- 不要慌 / 理性看待 → NOT anxiety (it's calming language)
- Numbers with % data → NOT loaded_language (quantified facts)
- Sports/game context → NOT loaded_language

Return ONLY valid JSON:
{"types":[...],"confidence":0.85,"signals":[...],"corrections":{"removed":[...],"added":[...]}}"""

_SYS_FRESH = """You are a classifier for rhetorical distortion in social media posts (Chinese or English).

Types: inflate | anxiety | novelty | loaded_language | temporal

- inflate: exaggerates significance (重磅/史上/震惊 or "changes everything")
- anxiety: manufactures fear about career/life (崩溃/危机/完了 or "you'll be left behind")
- novelty: falsely claims first/exclusive (独家/首次/曝光 or "nobody talking about this")
- loaded_language: emotionally charged words beyond content (炸裂/疯狂/绝了/!!!/ALL-CAPS or "catastrophic")
- temporal: frames old content as breaking/new (突发/刚刚 on old news or "Breaking")

False-positive rules:
- 历史回顾 → NOT temporal; 官方通报 → NOT novelty
- Calming language → NOT anxiety; quantified stats → NOT loaded_language
- Only flag clear manipulative rhetorical intent

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
    """
    等权重算术平均（方案C）。
    五个维度各自独立报告为主要结果；
    DI 作为辅助汇总指标，采用等权重以避免主观权重假设。
    参考：Wang & Strong (1996) 多维度信息质量等权重框架。
    """
    dims = [
        rates.get("significance_inflation", 0),
        rates.get("anxiety_manufacturing",  0),
        rates.get("novelty_claims",         0),
        rates.get("loaded_language",        0),
        rates.get("temporal_distortion",    0),
    ]
    return min(100, round(sum(dims) / len(dims) * 100))


# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    print("\n" + "="*60)
    print("微博平台重新分类 — 五维度 v2")
    print(f"输入: {INPUT_FILE}")
    print(f"GPT 核实: {'✓ 开启' if os.getenv('OPENAI_API_KEY') else '✗ 关闭（仅规则层）'}")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*60)

    if not INPUT_FILE.exists():
        print(f"✗ 找不到输入文件: {INPUT_FILE}")
        return

    # 读取原始数据
    with open(INPUT_FILE, encoding="utf-8") as f:
        raw_data = json.load(f)

    total_accounts = len(raw_data)
    total_posts    = sum(len(v.get("posts", [])) for v in raw_data.values())
    print(f"读取 {total_accounts} 个账号，{total_posts} 条帖子\n")

    # 断点续跑：读取已有输出
    result_data: dict = {}
    if OUT_JSON.exists():
        with open(OUT_JSON, encoding="utf-8") as f:
            result_data = json.load(f)
        print(f"检测到已有输出，已完成 {len(result_data)} 个账号，跳过\n")

    done_handles = set(result_data.keys())

    # ── 逐账号分类 ─────────────────────────────────────────────────────────────
    for acc_idx, (handle, prof) in enumerate(raw_data.items(), 1):
        if handle in done_handles:
            continue

        posts = prof.get("posts", [])
        name  = prof.get("name", handle)

        if not posts:
            print(f"  [{acc_idx:3d}/{total_accounts}] {name} — 无帖子，跳过")
            continue

        print(f"  [{acc_idx:3d}/{total_accounts}] {name:<14} ({len(posts)} 帖)...", end="", flush=True)
        t0 = time.time()

        dim_counts = defaultdict(int)
        new_posts  = []

        for post in posts:
            content = post.get("content", "").strip()
            if not content:
                new_posts.append({**post, "distortion_types": [], "confidence": 1.0,
                                  "signals": [], "classification_method": "skip_empty"})
                continue

            result = await classify(content)
            await asyncio.sleep(0.15)   # 避免 API 限流

            new_posts.append({
                **post,
                "distortion_types":      result.get("types", []),
                "confidence":            result.get("confidence", 0),
                "signals":               result.get("signals", []),
                "classification_method": result.get("method", ""),
            })
            for t in result.get("types", []):
                dim_counts[t] += 1

        # 计算五维度比率 + DI
        n = len(posts)
        rates = {
            "significance_inflation": dim_counts["inflate"] / n,
            "anxiety_manufacturing":  dim_counts["anxiety"] / n,
            "novelty_claims":         dim_counts["novelty"] / n,
            "loaded_language":        dim_counts["loaded_language"] / n,
            "temporal_distortion":    dim_counts["temporal"] / n,
        }
        di      = compute_distortion_index(rates)
        old_di  = prof.get("distortion_index", "?")
        elapsed = round(time.time() - t0, 1)

        # 写入结果（保留原始字段，更新分类相关字段）
        result_data[handle] = {
            # 保留原始 meta
            "handle":   handle,
            "name":     prof.get("name", ""),
            "platform": "weibo",
            "category": prof.get("category", ""),
            "expected": prof.get("expected", ""),
            "uid":      prof.get("uid", ""),
            # 新分类结果
            "distortion_index":           di,
            "significance_inflation_rate": round(rates["significance_inflation"] * 100, 2),
            "anxiety_manufacturing_rate":  round(rates["anxiety_manufacturing"] * 100, 2),
            "novelty_claims_rate":         round(rates["novelty_claims"] * 100, 2),
            "loaded_language_rate":        round(rates["loaded_language"] * 100, 2),
            "temporal_distortion_rate":    round(rates["temporal_distortion"] * 100, 2),
            "total_posts":                 n,
            "analyzed_at":                prof.get("analyzed_at", ""),
            "reclassified_at":            datetime.utcnow().isoformat(),
            "classification_method":      "rules_v2+gpt4o-mini_5dim",
            # 帖子（含新分类结果）
            "posts": new_posts,
        }

        # 每个账号完成后立即写入（中断可续）
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(
            f" ({elapsed}s)  DI: {old_di}→{di}"
            f"  infl={rates['significance_inflation']*100:.1f}%"
            f"  anx={rates['anxiety_manufacturing']*100:.1f}%"
            f"  LL={rates['loaded_language']*100:.1f}%"
            f"  [已保存]"
        )

    # ── 汇总 ────────────────────────────────────────────────────────────────────
    profiles = list(result_data.values())
    indices  = [p["distortion_index"] for p in profiles]
    all_posts_count = sum(len(p.get("posts", [])) for p in profiles)

    print(f"\n{'='*60}")
    print(f"重分类完成！  账号={len(profiles)}  帖子={all_posts_count}")
    print(f"平均 DI:  {round(statistics.mean(indices), 1)}")
    print(f"最高:     {max(indices)} ({max(profiles, key=lambda x: x['distortion_index'])['name']})")
    print(f"最低:     {min(indices)} ({min(profiles, key=lambda x: x['distortion_index'])['name']})")

    by_cat = defaultdict(list)
    for p in profiles:
        by_cat[p["category"]].append(p)
    print("\n按类别 (降序):")
    print(f"  {'类别':16s} {'n':>3}  {'avgDI':>6}  {'infl%':>6}  {'anx%':>5}  {'LL%':>5}  {'td%':>5}")
    print("  " + "-"*60)
    for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
        dis  = [a["distortion_index"] for a in accs]
        infl = statistics.mean(a["significance_inflation_rate"] for a in accs)
        anx  = statistics.mean(a["anxiety_manufacturing_rate"] for a in accs)
        ll   = statistics.mean(a["loaded_language_rate"] for a in accs)
        td   = statistics.mean(a["temporal_distortion_rate"] for a in accs)
        print(f"  {cat:16s} {len(accs):3d}  {statistics.mean(dis):6.1f}  {infl:6.1f}  {anx:5.1f}  {ll:5.1f}  {td:5.1f}")

    # ── corpus_v2.jsonl（帖子级，去掉 posts 嵌套，方便跨平台合并）
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for prof in profiles:
            for post in prof.get("posts", []):
                row = {
                    "handle":          prof["handle"],
                    "name":            prof.get("name", ""),
                    "platform":        "weibo",
                    "category":        prof.get("category", ""),
                    "post_id":         post.get("platform_id", ""),
                    "content":         post.get("content", ""),
                    "posted_at":       post.get("posted_at", ""),
                    "likes":           post.get("likes", 0),
                    "comments":        post.get("comments", 0),
                    "reposts":         post.get("reposts", 0),
                    "distortion_types":   post.get("distortion_types", []),
                    "confidence":         post.get("confidence", 0),
                    "signals":            post.get("signals", []),
                    "classification_method": post.get("classification_method", ""),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n✓ corpus_v2.jsonl — {all_posts_count} 条")

    # ── profiles_v2.csv
    fields = [
        "handle", "name", "platform", "category", "expected",
        "distortion_index",
        "significance_inflation_rate", "anxiety_manufacturing_rate",
        "novelty_claims_rate", "loaded_language_rate", "temporal_distortion_rate",
        "total_posts", "reclassified_at",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(profiles, key=lambda x: x["distortion_index"], reverse=True))
    print(f"✓ profiles_v2.csv — {len(profiles)} 行")

    # ── report_v2.md
    now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    avg  = round(statistics.mean(indices), 1)
    lines = [
        "# 微博平台重分类报告（五维度 v2）",
        f"\n生成时间: {now}",
        f"\n公式: `DI = SI×0.30 + AM×0.25 + NC×0.20 + LL×0.15 + TD×0.10`\n",
        "---\n",
        "## 概览",
        f"- 账号数: **{len(profiles)}**",
        f"- 总帖子数: **{all_posts_count}**",
        f"- 平均 DI: **{avg}**",
        f"- 最高 DI: **{max(indices)}** （{max(profiles, key=lambda x: x['distortion_index'])['name']}）",
        f"- 最低 DI: **{min(indices)}** （{min(profiles, key=lambda x: x['distortion_index'])['name']}）\n",
        "## 账号档案（按 DI 降序）\n",
        "| 账号 | 类别 | 预期 | DI | 膨胀% | 焦虑% | 新颖% | LL% | 时间% | 帖数 |",
        "|------|------|------|-----|-------|-------|-------|-----|-------|------|",
    ]
    for p in sorted(profiles, key=lambda x: x["distortion_index"], reverse=True):
        lines.append(
            f"| {p.get('name', p['handle'])} | {p['category']} | {p.get('expected','')} "
            f"| **{p['distortion_index']}** "
            f"| {p['significance_inflation_rate']} | {p['anxiety_manufacturing_rate']} "
            f"| {p['novelty_claims_rate']} | {p['loaded_language_rate']} "
            f"| {p['temporal_distortion_rate']} | {p['total_posts']} |"
        )

    lines += [
        "\n## 按类别汇总\n",
        "| 类别 | 账号数 | 平均DI | 膨胀% | 焦虑% | LL% | 时间% |",
        "|------|--------|--------|-------|-------|-----|-------|",
    ]
    for cat, accs in sorted(by_cat.items(), key=lambda x: -statistics.mean(a["distortion_index"] for a in x[1])):
        dis  = statistics.mean(a["distortion_index"] for a in accs)
        infl = statistics.mean(a["significance_inflation_rate"] for a in accs)
        anx  = statistics.mean(a["anxiety_manufacturing_rate"] for a in accs)
        ll   = statistics.mean(a["loaded_language_rate"] for a in accs)
        td   = statistics.mean(a["temporal_distortion_rate"] for a in accs)
        lines.append(f"| {cat} | {len(accs)} | {dis:.1f} | {infl:.1f} | {anx:.1f} | {ll:.1f} | {td:.1f} |")

    lines += ["", "---", f"*{now}*"]
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ report_v2.md")

    print(f"\n{'='*60}")
    print(f"所有输出保存在: {OUTPUT_DIR.resolve()}/")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
