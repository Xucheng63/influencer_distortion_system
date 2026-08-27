"""
app/services/classifier.py  —  规则 + GPT-4o-mini 三级分类器

流程：
  1. 规则分类（强/弱信号，快速高召回）
  2. 负向过滤正则（粗过滤，排除明显误报）
  3. GPT-4o-mini 核实（精过滤，两个场景都用）
     a. 规则置信度 < 0.70 → GPT 判断是否真的是失真
     b. 规则置信度 >= 0.70 → GPT 仍做误报核实（verify 模式）

维度（v2，5维度）：
  inflate        → significance_inflation   (Logos 失真，Entman 1993)
  anxiety        → anxiety_manufacturing    (Pathos 失真，Witte & Allen 2000)
  novelty        → novelty_claims           (Ethos 失真，Da San Martino 2019)
  loaded_language→ loaded_language          (Pathos 失真，Da San Martino 2019)
  temporal       → temporal_distortion      (Logos 失真，Wang & Strong 1996)
"""
from __future__ import annotations
import os, json, re, logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("distortion.classifier")


def strip_lone_surrogates(text: str) -> str:
    """
    去除孤立的 UTF-16 代理码点 (U+D800–U+DFFF)。

    抓取到的文本（尤其 YouTube 自动字幕/标题被 [:N] 截断时）可能残留半个 emoji
    的高位代理码点。这类孤立代理经 json.dumps 会编码成未配对的 \\udXXX 转义，
    OpenAI 服务端 JSON 解析器会以 400 "no low surrogate in string" 拒绝请求。
    合法 emoji 是 BMP 外的单一码点，不在该区间，原样保留。
    """
    if not text:
        return text
    return text.encode("utf-8", "ignore").decode("utf-8")


# ── 强信号规则 ──────────────────────────────────────────────────────────────────
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
        # 政治/宣传式夸大（Trump 风格）
        r"\b(greatest|best|biggest).{0,10}(ever|in history|of all time)\b",
        r"\b(record.breaking|all.time record)\b",
    ],
    "anxiety": [
        r"you('ll| will) (regret|miss|be left behind)",
        r"(unemploy|irrelevant|obsolete).{0,30}(you|your|we|everyone)",
        r"won'?t see it coming",
        r"running out of time",
        r"(left behind|fall behind).{0,20}(if|unless|who)",
        r"(6|12|18|24) months?.{0,20}(unemploy|irrelevant|obsolete|over)",
        # 政治式恐惧制造（Trump 风格）
        r"(destroying|ruining).{0,20}(our country|America|everything)",
        r"never seen anything like this in history",
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
        # 英文强情感词（Da San Martino et al. 2019；Weston 2018）
        r"\b(devastating|catastrophic|apocalyptic|horrifying|terrifying)\b",
        r"\b(disastrous|catastrophically|utterly (broken|failed|destroyed))\b",
        r"\b(explosive|bombshell|earth.?shattering|mind.?blowing)\b",
        r"\b(insane(ly)?|insanity|absolutely (insane|insanely))\b",
        r"\b(dead|dying|killed|destroying|obliterating).{0,20}(industry|economy|job|career|future)\b",
        # 中文强情感词
        r"震惊|骇人|毁灭性|爆炸性|颠覆性|惊天|惨烈|恐怖的|极度震惊",
        # 政治/宣传式命令强调与贬损（Trump 风格）
        r"\b(MUST WATCH|MUST SEE|MUST READ)\b",
        r"\b(Radical Left|Fake News|RINO|witch hunt|enemy of the people)\b",
        r"\b(Scum|thugs|vermin)\b",
    ],
    "temporal": [
        r"\bbreaking\b.{0,30}(news|report|development|announcement)",
        r"just (dropped|announced|released|published).{0,20}(today|this|new)",
        r"(brand.new|brand new).{0,20}(tool|study|report|paper|model)",
        r"latest (breaking|urgent|exclusive)",
    ],
}

# ── 弱信号规则（需 ≥2 个才触发） ────────────────────────────────────────────────
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
        r"\b[A-Z]{4,}\b",   # 全大写词（如 INSANE、MUST SEE）
        r"!{2,}",           # 连续感叹号
        # 政治/宣传式弱信号（全大写强调 + 危机化框架）
        r"\b(AMAZING|INCREDIBLE|BEAUTIFUL|PERFECT|TREMENDOUS)\b",
        r"\b(disaster|catastrophe|chaos|crisis)\b",
        # 中文弱信号
        r"惊人|震撼|爆款|刷屏|炸裂|疯狂|狂飙|狂热|极致|超乎想象",
    ],
    "temporal": [
        r"just (dropped|announced|released|published)",
        r"(happening|unfolding) (right )?now",
        r"latest (news|development|update)",
    ],
}

# ── 负向过滤正则（粗过滤，GPT 会再核实一遍） ────────────────────────────────────
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
        # 技术领域专业词汇（非情感滥用）
        r"(critical|severe|high).{0,10}(vulnerability|bug|error|issue|flaw)",
        r"(aggressive|brutal).{0,10}(optimization|compression|training|schedule)",
        # 用数据修饰的增长描述（非夸张）
        r"(explosive|exponential).{0,10}(growth|increase|rise).{0,20}(in|of|for)\s+\w+\s+(users|revenue|traffic|metrics)",
        # 引用他人说的话（作者自己没在用）
        r'["\u201c\u201d\u2018\u2019].{0,200}(shocking|devastating|explosive|insane).{0,200}["\u201c\u201d\u2018\u2019]',
        # 体育比赛语境（合理用语）
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

# GPT 核实开关：True = 所有规则命中都经过 GPT 核实（更准确，消耗更多 token）
VERIFY_ALL = True


# ── 引用检测：识别并降权引用内容 ──────────────────────────────────────────────

import re as _re_quote

_QUOTE_PATTERNS = [
    # "quoted text" or 'quoted text' (短引用)
    _re_quote.compile(r'"([^"]{10,300})"'),
    _re_quote.compile(r'\u201c([^\u201d]{10,300})\u201d'),   # Unicode " "
    # 引用来源标记：Via X, — Author, (Source)
    _re_quote.compile(r'(?:via|from|—|–|-)\s+\w[\w\s]+:', _re_quote.IGNORECASE),
    # Blockquote 风格："> text"
    _re_quote.compile(r'^>\s+.+$', _re_quote.MULTILINE),
]

def _strip_quotes(content: str) -> tuple[str, str]:
    """
    将内容分成：作者自己的文字 vs 引用他人的文字。
    返回 (author_text, quoted_text)
    分类器主要基于 author_text，quoted_text 只做弱信号。
    """
    quoted_parts = []
    author_text = content

    for pat in _QUOTE_PATTERNS:
        for m in pat.finditer(content):
            quoted_parts.append(m.group(0))
        # 从 author_text 中移除引用部分
        author_text = pat.sub(' ', author_text)

    author_text = ' '.join(author_text.split())   # 清理多余空格
    quoted_text = ' '.join(quoted_parts)
    return author_text, quoted_text


def classify_rules(content: str) -> dict:
    """纯规则分类，含引用检测 + 负向过滤正则。"""
    # ── 引用检测：分离作者文字和引用文字 ──────────────────────────
    author_text, quoted_text = _strip_quotes(content)

    types, signals = [], []
    excluded_types = []
    conf = 0.0

    for dtype in ("inflate", "anxiety", "novelty", "loaded_language", "temporal"):
        # 在作者文字中检测强/弱信号
        sh_author = [m.group(0) for p in _s.get(dtype, []) for m in [p.search(author_text)] if m]
        wh_author = [m.group(0) for p in _w.get(dtype, []) for m in [p.search(author_text)] if m]
        # 在引用文字中检测（降权：强信号当弱信号处理）
        sh_quoted = [m.group(0) for p in _s.get(dtype, []) for m in [p.search(quoted_text)] if m] if quoted_text else []

        # 负向过滤正则（只对作者文字做排除）
        excl = any(p.search(author_text) for p in _e.get(dtype, []))
        if excl:
            excluded_types.append(dtype)
            continue

        triggered = False
        tc = 0.0

        # 作者文字的强信号
        if sh_author:
            triggered = True
            tc += len(sh_author) * STRONG_WEIGHT
            signals.extend(sh_author)

        # 作者文字的弱信号
        if len(wh_author) >= WEAK_MIN:
            triggered = True
            tc += len(wh_author) * WEAK_WEIGHT
            signals.extend(wh_author)
        elif wh_author and sh_author:
            tc += len(wh_author) * WEAK_WEIGHT
            signals.extend(wh_author)

        # 引用文字的信号（强信号降为弱信号，需要多个才触发）
        if len(sh_quoted) >= WEAK_MIN and not triggered:
            triggered = True
            tc += len(sh_quoted) * WEAK_WEIGHT
            signals.extend([f'[quoted] {s}' for s in sh_quoted])

        if triggered:
            types.append(dtype)
            conf += tc

    if not types:
        conf = 1.0

    return {
        "types": types,
        "excluded_by_regex": excluded_types,   # 记录被正则排除的类型，供 GPT 核实
        "confidence": round(min(conf, CONFIDENCE_CAP), 3),
        "signals": list(dict.fromkeys(signals)),
        "method": "rules_v2",
    }


def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=api_key)


async def verify_with_gpt(content: str, rule_result: dict) -> dict:
    """
    GPT 核实模式：对规则已有结论的帖子做误报检查。

    两个任务：
    1. 检查规则标记的类型是否真的是失真（排除误报）
    2. 检查被正则负向过滤掉的类型是否其实是真实失真（排除漏报）
    """
    client = _get_openai_client()
    if not client:
        return rule_result

    detected = rule_result["types"]
    excluded = rule_result.get("excluded_by_regex", [])
    signals  = rule_result["signals"]

    # 构建核实任务描述
    task_parts = []
    if detected:
        task_parts.append(
            f"The rule system flagged this post as: {', '.join(detected)}\n"
            f"Triggered signals: {', '.join(signals) if signals else 'none'}\n"
            f"→ Verify: are these correct, or are some false positives?"
        )
    if excluded:
        task_parts.append(
            f"The rule system EXCLUDED these types due to negative filters: {', '.join(excluded)}\n"
            f"→ Verify: were any of these actually real distortion (false negatives)?"
        )

    if not task_parts:
        return rule_result

    system_prompt = """You are a precise classifier verifying distortion detection in social media posts.

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

    user_message = f"""Post content:
\"{content}\"

Rule system verdict:
{chr(10).join(task_parts)}

Please verify and return the corrected classification."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=300,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        result["method"] = "gpt-4o-mini-verify"
        # 去掉内部字段，保持和其他返回一致
        result.pop("corrections", None)
        return result

    except Exception as e:
        # GPT 失败时降级到规则结果
        logger.warning("verify_with_gpt failed, falling back to rules: %s", e)
        rule_result["method"] = f"rules_v2_gpt_error:{e}"
        return rule_result


async def classify_llm_fresh(content: str) -> dict:
    """
    GPT 从零分类模式：规则置信度低但有命中时，让 GPT 重新判断。
    """
    client = _get_openai_client()
    if not client:
        return {"types": [], "confidence": 0.5, "signals": [], "method": "llm_unavailable"}

    system_prompt = """You are a classifier for rhetorical distortion in social media posts.

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

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Classify this post:\n\n{content}"},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        result["method"] = "gpt-4o-mini"
        return result
    except Exception as e:
        logger.warning("classify_llm_fresh failed, returning empty result: %s", e)
        return {"types": [], "confidence": 0.5, "signals": [], "method": f"llm_error:{e}"}


async def classify(content: str) -> dict:
    """
    主入口。三级流水线：
      规则 → (负向正则过滤) → GPT 核实/补充
    """
    # 清除孤立代理码点，避免发往 OpenAI 的请求体触发 400 "no low surrogate in string"
    content = strip_lone_surrogates(content)
    rule_result = classify_rules(content)
    has_types    = bool(rule_result["types"])
    has_excluded = bool(rule_result.get("excluded_by_regex"))
    conf         = rule_result["confidence"]

    # 场景 A：规则置信度低但有命中 → GPT 从零重判
    if has_types and conf < LLM_THRESHOLD:
        return await classify_llm_fresh(content)

    # 场景 B：规则有命中 或 有被正则排除的类型 → GPT 核实误报/漏报
    if VERIFY_ALL and (has_types or has_excluded):
        return await verify_with_gpt(content, rule_result)

    # 场景 C：规则无命中且无排除 → 直接返回（置信度 1.0，无需 GPT）
    return rule_result


def compute_distortion_index(profile: dict) -> int:
    """
    五维度加权公式（v2），CS 已移出公式，作为独立置信度指标。

    权重理论依据：
      SI 0.30 — Entman(1993) salience 操纵影响最持久
      AM 0.25 — Witte & Allen(2000) EPPM meta-analysis 效果量最大
      NC 0.20 — 影响信源评估，间接影响行为
      LL 0.15 — 情感激活短期效果，频率高但深度较低（Da San Martino 2019）
      TD 0.10 — 受众最易识别，效果随时间衰减

    CS（一致性分数）单独报告：CS < 0.30 时标注低置信度，不参与跨平台比较。
    """
    w = {
        "significance_inflation_rate": 0.30,
        "anxiety_manufacturing_rate":  0.25,
        "novelty_claim_rate":          0.20,
        "loaded_language_rate":        0.15,  # 新增 LL 维度
        "temporal_distortion_rate":    0.10,
    }
    score = sum(profile.get(k, 0) * v for k, v in w.items())
    return min(100, round(score * 100))
