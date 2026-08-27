"""
app/services/scraper.py  —  多平台抓取器 v2
支持: RSS/Newsletter、YouTube字幕(yt-dlp)、Twitter/X API v2
"""
from __future__ import annotations
import hashlib, os, asyncio
from datetime import datetime, timezone
from typing import Optional
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}
_TIMEOUT = httpx.Timeout(20.0)

# Chromium 启动参数（内存精简版）。
# --no-sandbox / --disable-setuid-sandbox: 容器内以 root 运行必需。
# 其余为降低常驻内存的项：在 Render starter（512MB）上，两个浏览器并发会
# 触发 OOM Kill（exit 137 / SIGKILL）。配合 routes.py 的并发信号量，
# 单实例足以稳定运行。
CHROMIUM_LEAN_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",          # 不用容器里过小的 /dev/shm，改用磁盘
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--mute-audio",
    "--no-first-run",
    "--disable-features=site-per-process,TranslateUI",
]
# 注意：曾加过 --single-process / --no-zygote 省内存，但它们会让 x.com 这类
# 重型 SPA 在容器里渲染失败（推文选择器超时、抓到 0 帖）。既然 analyze 已由
# 信号量串行化（单浏览器足以放进 512MB），这里移除这两个高风险参数。

FEED_MAP: dict[str, dict] = {
    # RSS/Newsletter — English
    "simonwillison":    {"feed": "https://simonwillison.net/atom/everything/",        "display": "Simon Willison",    "type": "rss"},
    "dhh":              {"feed": "https://world.hey.com/dhh/feed.atom",               "display": "DHH",               "type": "rss"},
    "astralcodexten":   {"feed": "https://www.astralcodexten.com/feed",               "display": "Astral Codex Ten",  "type": "rss"},
    "lesswrong":        {"feed": "https://www.lesswrong.com/feed.xml?view=frontpage", "display": "LessWrong",         "type": "rss"},
    "paulgraham":       {"feed": "https://www.aaronsw.com/2002/feeds/pgessays.rss",   "display": "Paul Graham",       "type": "rss"},
    "hackernewsletter": {"feed": "https://hackernewsletter.com/issues.rss",           "display": "Hacker Newsletter", "type": "rss"},
    "karpathy":         {"feed": "https://karpathy.github.io/feed.xml",              "display": "Andrej Karpathy",   "type": "rss"},
    "eugeneyan":        {"feed": "https://eugeneyan.substack.com/feed",               "display": "Eugene Yan",        "type": "rss"},
    "sebastianraschka": {"feed": "https://sebastianraschka.com/rss_feed.xml",        "display": "Sebastian Raschka", "type": "rss"},
    "swyx":             {"feed": "https://www.swyx.io/rss.xml",                      "display": "swyx",              "type": "rss"},
    # Tech bloggers
    "martinfowler":     {"feed": "https://martinfowler.com/feed.atom",               "display": "Martin Fowler",     "type": "rss"},
    "joelonsoftware":   {"feed": "https://www.joelonsoftware.com/feed/",             "display": "Joel on Software",  "type": "rss"},
    "overreacted":      {"feed": "https://overreacted.io/rss.xml",                   "display": "Dan Abramov",       "type": "rss"},
    "stratechery":      {"feed": "https://stratechery.com/feed/",                    "display": "Stratechery",       "type": "rss"},
    "latentspace":      {"feed": "https://latent.space/feed",                        "display": "Latent Space",      "type": "rss"},
    "pragmaticengineer":{"feed": "https://newsletter.pragmaticengineer.com/feed",    "display": "Pragmatic Engineer","type": "rss"},
    "timferriss":       {"feed": "https://tim.blog/feed",                            "display": "Tim Ferriss",       "type": "rss"},
    # Tech Media
    "techcrunch":       {"feed": "https://techcrunch.com/feed/",                     "display": "TechCrunch",        "type": "rss"},
    "theverge":         {"feed": "https://www.theverge.com/rss/index.xml",           "display": "The Verge",         "type": "rss"},
    "wired-ai":         {"feed": "https://www.wired.com/feed/tag/ai/latest/rss",     "display": "WIRED AI",          "type": "rss"},
    "arstechnica":      {"feed": "https://feeds.arstechnica.com/arstechnica/index",  "display": "Ars Technica",      "type": "rss"},
    "thenextweb":       {"feed": "https://thenextweb.com/feed/",                     "display": "The Next Web",      "type": "rss"},
    "venturebeat":      {"feed": "https://venturebeat.com/feed/",                    "display": "VentureBeat",       "type": "rss"},
    "zdnet":            {"feed": "https://www.zdnet.com/news/rss.xml",               "display": "ZDNet",             "type": "rss"},
    "hackernews":       {"feed": "https://news.ycombinator.com/rss",                 "display": "Hacker News",       "type": "rss"},
    "mit-tech-review":  {"feed": "https://www.technologyreview.com/feed/",           "display": "MIT Tech Review",   "type": "rss"},
    "huggingface":      {"feed": "https://huggingface.co/blog/feed.xml",             "display": "Hugging Face",      "type": "rss"},
    "openai-news":      {"feed": "https://openai.com/news/rss.xml",                  "display": "OpenAI News",       "type": "rss"},
    "deepmind":         {"feed": "https://deepmind.google/blog/feed",                "display": "DeepMind",          "type": "rss"},
    "marktechpost":     {"feed": "https://www.marktechpost.com/feed/",               "display": "MarkTechPost",      "type": "rss"},
    "the-decoder":      {"feed": "https://the-decoder.com/feed/",                    "display": "The Decoder",       "type": "rss"},
    # Finance
    "marketwatch":      {"feed": "https://www.marketwatch.com/rss/topstories",       "display": "MarketWatch",       "type": "rss"},
    "businessinsider":  {"feed": "https://feeds.businessinsider.com/custom/all",     "display": "Business Insider",  "type": "rss"},
    "financialsamurai": {"feed": "https://financialsamurai.com/feed",                "display": "Financial Samurai", "type": "rss"},
    "coindesk":         {"feed": "https://www.coindesk.com/arc/outboundfeeds/rss/",  "display": "CoinDesk",          "type": "rss"},
    "notboring":        {"feed": "https://www.notboring.co/feed",                    "display": "Not Boring",        "type": "rss"},
    "sidehustlenation": {"feed": "https://sidehustlenation.com/feed",                "display": "Side Hustle Nation","type": "rss"},
    "clevergirlfinance":{"feed": "https://www.clevergirlfinance.com/feed",           "display": "Clever Girl Finance","type": "rss"},
    # Health / Lifestyle
    "peterattiamd":     {"feed": "https://peterattiamd.com/feed/",                   "display": "Peter Attia MD",    "type": "rss"},
    "markmanson":       {"feed": "https://markmanson.net/feed",                      "display": "Mark Manson",       "type": "rss"},
    "jamesclear":       {"feed": "https://jamesclear.com/feed",                      "display": "James Clear",       "type": "rss"},
    "becomingminimalist":{"feed": "https://www.becomingminimalist.com/feed/",        "display": "Becoming Minimalist","type": "rss"},
    # Chinese
    "ruanyifeng":       {"feed": "https://feeds.feedburner.com/ruanyifeng",          "display": "阮一峰",             "type": "rss"},
    "coolshell":        {"feed": "https://coolshell.cn/feed",                        "display": "酷壳 CoolShell",    "type": "rss"},
    "sspai":            {"feed": "https://sspai.com/feed",                           "display": "少数派",             "type": "rss"},
    "geekpark":         {"feed": "https://rsshub.app/geekpark/informations",         "display": "极客公园",           "type": "rss"},
    # YouTube (channel ID)
    "ycombinator":      {"feed": "UCxIJaCMEptJjxmmQgGFsnCg", "display": "Y Combinator",  "type": "youtube"},
    "lexfridman":       {"feed": "UCSHZKyawb77ixDdsGog4iWA", "display": "Lex Fridman",   "type": "youtube"},
    "fireship":         {"feed": "UCsBjURrPoezykLs9EqgamOA", "display": "Fireship",       "type": "youtube"},
    "mkbhd":            {"feed": "UCBcRF18a7Qf58cCRy5xuWwQ", "display": "MKBHD",         "type": "youtube"},
    "aiexplained":      {"feed": "UCNJ1Ymd5yFuUPtn21xtRbbw", "display": "AI Explained",  "type": "youtube"},
    "twocentspbs":      {"feed": "UCzWQYUVCpZqtN93H8RR44Qw", "display": "Two Cents PBS", "type": "youtube"},
}

# ── 日期工具 ───────────────────────────────────────────────────────────────────
def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return _to_naive_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except Exception:
        pass
    try:
        return _to_naive_utc(parsedate_to_datetime(raw))
    except Exception:
        pass
    return None

def _extract_text(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)[:1000]

# ── RSS / Atom ─────────────────────────────────────────────────────────────────
def _parse_rss(xml: str) -> list[dict]:
    soup = BeautifulSoup(xml, "xml")
    items = []
    for item in soup.find_all("item"):
        title   = item.find("title")
        desc    = item.find("description") or item.find("content:encoded")
        link    = item.find("link")
        pubdate = item.find("pubDate") or item.find("dc:date")
        title_t = title.get_text(strip=True) if title else ""
        desc_t  = _extract_text(desc.get_text(strip=True) if desc else "")
        content = f"{title_t}. {desc_t[:300]}" if desc_t else title_t
        if not content.strip():
            continue
        items.append({
            "platform_id": hashlib.md5(content[:100].encode()).hexdigest()[:12],
            "content":     content,
            "posted_at":   _parse_date(pubdate.get_text(strip=True) if pubdate else "") or datetime.utcnow(),
            "linked_url":  link.get_text(strip=True) if link else None,
        })
    return items

def _parse_atom(xml: str) -> list[dict]:
    soup = BeautifulSoup(xml, "xml")
    items = []
    for entry in soup.find_all("entry"):
        title   = entry.find("title")
        summary = entry.find("summary") or entry.find("content")
        link    = entry.find("link")
        updated = entry.find("updated") or entry.find("published")
        title_t = title.get_text(strip=True) if title else ""
        sum_t   = _extract_text(summary.get_text(strip=True) if summary else "")
        content = f"{title_t}. {sum_t[:300]}" if sum_t else title_t
        if not content.strip():
            continue
        items.append({
            "platform_id": hashlib.md5(content[:100].encode()).hexdigest()[:12],
            "content":     content,
            "posted_at":   _parse_date(updated.get_text(strip=True) if updated else "") or datetime.utcnow(),
            "linked_url":  link.get("href") if link else None,
        })
    return items

async def _fetch_rss(url: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=HEADERS, timeout=_TIMEOUT, follow_redirects=True)
            if r.status_code != 200:
                return []
            xml = r.text
        except Exception:
            return []
    if "<entry>" in xml or 'xmlns="http://www.w3.org/2005/Atom"' in xml:
        return _parse_atom(xml)
    return _parse_rss(xml)

# ── YouTube（yt-dlp，免费）────────────────────────────────────────────────────
async def _fetch_youtube(channel_id: str, max_videos: int = 20) -> list[dict]:
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        print("[scraper] yt-dlp not installed. Run: pip install yt-dlp")
        return []

    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
    list_opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": max_videos}

    try:
        loop = asyncio.get_event_loop()
        def _list():
            with yt_dlp.YoutubeDL(list_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                return info.get("entries", [])
        entries = await loop.run_in_executor(None, _list)
    except Exception as e:
        print(f"[scraper] YouTube list error: {e}")
        return []

    import glob, re as _re

    def _clean_vtt(raw: str) -> str:
        """
        Clean YouTube VTT subtitle file:
        1. Remove WEBVTT header and metadata lines
        2. Remove timestamp lines (00:00:00.000 --> 00:00:03.000)
        3. Strip HTML tags (<c>, <b>, timestamps inside cues)
        4. Deduplicate consecutive repeated lines (VTT overlap artifact)
        5. Return clean plain text up to 800 chars
        """
        # Remove WEBVTT header block (everything before first blank line after header)
        raw = _re.sub(r'^WEBVTT.*?\n\n', '', raw, flags=_re.DOTALL)
        # Remove cue metadata lines: Kind:, Language:, NOTE, STYLE blocks
        raw = _re.sub(r'^(Kind|Language|NOTE|STYLE|REGION).*$', '', raw, flags=_re.MULTILINE)
        # Remove timestamp lines with optional positioning
        raw = _re.sub(r'^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*$', '', raw, flags=_re.MULTILINE)
        # Remove cue ID lines (pure numbers)
        raw = _re.sub(r'^\d+\s*$', '', raw, flags=_re.MULTILINE)
        # Strip HTML/VTT inline tags: <c>, <b>, <i>, <00:00:01.000>, etc.
        raw = _re.sub(r'<[^>]+>', '', raw)
        # Collapse multiple blank lines
        raw = _re.sub(r'\n{2,}', '\n', raw)

        # Split into lines and deduplicate consecutive repeats
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        deduped = []
        seen_window: list[str] = []
        for line in lines:
            # Skip if this line is a near-duplicate of any line in recent window (last 3)
            if line not in seen_window:
                deduped.append(line)
            seen_window.append(line)
            if len(seen_window) > 3:
                seen_window.pop(0)

        text = ' '.join(deduped)
        # Collapse repeated phrase patterns (e.g. "foo foo foo" → "foo")
        text = _re.sub(r'\b(.{10,60}?) \1\b', r'\1', text)
        return text[:800].strip()

    posts = []
    sub_opts = {
        "quiet": True, "no_warnings": True,
        "writeautomaticsub": True, "subtitleslangs": ["en"],
        "skip_download": True, "subtitlesformat": "vtt",
        "outtmpl": "/tmp/yt_%(id)s.%(ext)s",
    }

    for entry in entries[:max_videos]:
        video_id  = entry.get("id", "")
        title     = entry.get("title", "")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        upload_dt = None
        if entry.get("upload_date"):
            try:
                upload_dt = datetime.strptime(entry["upload_date"], "%Y%m%d")
            except Exception:
                pass

        subtitle_text = ""
        try:
            def _sub():
                with yt_dlp.YoutubeDL(sub_opts) as ydl:
                    ydl.extract_info(video_url, download=True)
                vtt_files = glob.glob(f"/tmp/yt_{video_id}*.vtt")
                if vtt_files:
                    raw = open(vtt_files[0], encoding="utf-8", errors="ignore").read()
                    cleaned = _clean_vtt(raw)
                    for f in vtt_files:
                        try:
                            os.remove(f)
                        except Exception:
                            pass
                    return cleaned
                return ""
            subtitle_text = await asyncio.get_event_loop().run_in_executor(None, _sub)
        except Exception as e:
            print(f"[scraper] subtitle error for {video_id}: {e}")

        content = f"{title}. {subtitle_text}" if subtitle_text else title
        if not content.strip():
            continue
        posts.append({
            "platform_id": video_id or hashlib.md5(title.encode()).hexdigest()[:12],
            "content":     content,
            "posted_at":   upload_dt or datetime.utcnow(),
            "linked_url":  video_url,
        })
    return posts

# ── Twitter/X Playwright + Cookie 浏览器抓取（无需 API key）─────────────────
# Cookie 从浏览器 DevTools → Application → Cookies → x.com 复制
# auth_token 和 ct0 两个字段填入 .env 文件：
#   TWITTER_AUTH_TOKEN=your_auth_token
#   TWITTER_CT0=your_ct0

def _make_twitter_context(p):
    """创建带 Cookie 的浏览器 context，屏蔽 webdriver 检测"""
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "")
    ct0        = os.getenv("TWITTER_CT0", "")

    browser = p.chromium.launch(
        headless=True,
        args=[*CHROMIUM_LEAN_ARGS, "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    # 屏蔽 webdriver 检测
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    # 注入 Cookie（登录态）
    if auth_token and ct0:
        context.add_cookies([
            {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
            {"name": "ct0",        "value": ct0,        "domain": ".x.com", "path": "/"},
        ])
    return browser, context


def _scrape_twitter_sync(username: str, max_tweets: int = 50) -> list[dict]:
    """
    用 Playwright 浏览器 + Cookie 抓取推文。
    需要 .env 里配置 TWITTER_AUTH_TOKEN 和 TWITTER_CT0。
    """
    import time as _time
    from playwright.sync_api import sync_playwright

    tweets = []

    with sync_playwright() as p:
        browser, context = _make_twitter_context(p)
        page = context.new_page()
        try:
            url = f"https://x.com/{username}"
            page.goto(url, wait_until="domcontentloaded", timeout=120000)

            # 诊断：记录落地 URL / 标题，便于区分「数据中心 IP 被拦」与「渲染失败」
            has_cookies = bool(os.getenv("TWITTER_AUTH_TOKEN")) and bool(os.getenv("TWITTER_CT0"))
            try:
                _title = page.title()
            except Exception:
                _title = "<title unavailable>"
            print(f"[scraper] Twitter @{username}: cookies={has_cookies} "
                  f"landed_url={page.url!r} title={_title!r}")

            # 检测是否被重定向到登录页
            if "login" in page.url or "onboarding" in page.url or "flow" in page.url:
                print(f"[scraper] Twitter: not logged in for @{username} "
                      f"(redirected to {page.url!r}) — cookie likely invalid or IP blocked")
                return []

            # 等待推文元素出现
            try:
                page.wait_for_selector('article[data-testid="tweet"]', timeout=15000)
            except Exception:
                # 诊断：selector 超时 → 页面没渲染出推文。记录文章数与 body 片段。
                try:
                    _arts = page.eval_on_selector_all("article", "els => els.length")
                    _body = (page.inner_text("body") or "")[:280].replace("\n", " ")
                except Exception as _e:
                    _arts, _body = "?", f"<body read failed: {_e}>"
                print(f"[scraper] Twitter @{username}: tweet selector timeout — "
                      f"articles={_arts} body_snippet={_body!r}")
                return []
            _time.sleep(2)

            # X 采用虚拟滚动：向下滚动后，顶部（最新）推文会被移出 DOM。
            # 旧逻辑「先滚动 6 次再一次性提取」只会拿到较旧的推文，丢失最新几条。
            # 修复：边滚边累积——每次滚动后立即提取当前 DOM 内的推文并按 url 去重。
            _EXTRACT_JS = """
                () => {
                    const out = [];
                    const articles = document.querySelectorAll('article[data-testid="tweet"]');
                    for (const article of articles) {
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.innerText.trim() : '';
                        if (!text) continue;
                        const timeEl = article.querySelector('time');
                        const date = timeEl ? (timeEl.getAttribute('datetime') || '') : '';
                        const linkEl = timeEl ? timeEl.closest('a') : null;
                        const url = linkEl ? 'https://x.com' + linkEl.getAttribute('href') : '';
                        if (!url) continue;
                        out.push({text, date, url});
                    }
                    return out;
                }
            """
            collected: dict = {}   # url -> {text,date,url}，保持插入顺序

            def _harvest():
                for it in (page.evaluate(_EXTRACT_JS) or []):
                    u = it.get("url")
                    if u and u not in collected:
                        collected[u] = it

            _harvest()                         # 先抓取顶部最新推文（滚动前）
            for _ in range(20):
                if len(collected) >= max_tweets:
                    break
                page.evaluate("window.scrollBy(0, 1200)")
                _time.sleep(1.5)
                _harvest()

            # 按发布时间倒序（最新优先），日期缺失的排最后
            raw = sorted(
                collected.values(),
                key=lambda x: x.get("date") or "",
                reverse=True,
            )[:max_tweets]

            # 逐条进入详情页获取完整正文（含线程）
            for item in (raw or []):
                text     = item.get("text", "").strip()
                post_url = item.get("url", "")
                if not text or not post_url:
                    continue

                full_text = text
                try:
                    page.goto(post_url, wait_until="commit", timeout=120000)
                    _time.sleep(2)
                    detail = page.evaluate("""
                        () => {
                            const articles = Array.from(
                                document.querySelectorAll('article[data-testid="tweet"]')
                            );
                            if (!articles.length) return '';
                            const mainAuthorEl = articles[0].querySelector(
                                '[data-testid="User-Name"] a[href^="/"]');
                            const mainAuthor = mainAuthorEl
                                ? mainAuthorEl.getAttribute('href').replace('/', '').toLowerCase()
                                : '';
                            const parts = [];
                            for (const article of articles) {
                                const authorEl = article.querySelector(
                                    '[data-testid="User-Name"] a[href^="/"]');
                                const author = authorEl
                                    ? authorEl.getAttribute('href').replace('/', '').toLowerCase()
                                    : '';
                                if (mainAuthor && author && author !== mainAuthor) break;
                                const textEl = article.querySelector('[data-testid="tweetText"]');
                                if (textEl) {
                                    const t = textEl.innerText.trim();
                                    if (t) parts.push(t);
                                }
                            }
                            return parts.join(' ');
                        }
                    """)
                    if detail and len(detail) > len(text):
                        full_text = detail
                except Exception:
                    pass

                # 回到用户主页
                try:
                    page.go_back(wait_until="commit", timeout=120000)
                    _time.sleep(1)
                except Exception:
                    page.goto(f"https://x.com/{username}",
                              wait_until="commit", timeout=120000)
                    _time.sleep(2)

                date_str = item.get("date", "")
                try:
                    posted_dt = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")).replace(tzinfo=None) if date_str else datetime.utcnow()
                except Exception:
                    posted_dt = datetime.utcnow()

                tweets.append({
                    "platform_id": hashlib.md5(post_url.encode()).hexdigest()[:12],
                    "content":     full_text[:500],
                    "posted_at":   posted_dt,
                    "linked_url":  post_url,
                })

        except Exception as e:
            print(f"[scraper] Twitter browser error for @{username}: {e}")
        finally:
            browser.close()

    return tweets[:max_tweets]


async def _fetch_twitter(username: str, max_results: int = 50) -> list[dict]:
    """Twitter/X 公开入口：Playwright + Cookie 浏览器抓取"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_twitter_sync, username, max_results)


def _parse_count(text: str) -> int:
    """把 '2.3M' / '1,234' / '12.5K' 这类粉丝数文本解析为整数。失败返回 0。"""
    import re as _re
    if not text:
        return 0
    t = text.strip().replace(",", "").upper()
    m = _re.search(r"([\d.]+)\s*([KMB]?)", t)
    if not m:
        return 0
    try:
        num = float(m.group(1))
    except ValueError:
        return 0
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(m.group(2), 1)
    return int(num * mult)


def _scrape_twitter_profile_sync(username: str) -> dict:
    """打开 X 用户主页，提取显示名与粉丝数。任何失败都返回 followers=0（不抛异常）。"""
    import time as _time
    from playwright.sync_api import sync_playwright

    info = {"display_name": "", "followers": 0}
    with sync_playwright() as p:
        browser, context = _make_twitter_context(p)
        page = context.new_page()
        try:
            page.goto(f"https://x.com/{username}",
                      wait_until="domcontentloaded", timeout=120000)
            if "login" in page.url or "onboarding" in page.url:
                print(f"[scraper] Twitter profile: not logged in for @{username}")
                return info
            try:
                page.wait_for_selector('[data-testid="UserName"]', timeout=15000)
            except Exception:
                pass
            _time.sleep(1)
            data = page.evaluate("""
                () => {
                    const out = {display_name: '', followers: ''};
                    const nameEl = document.querySelector('[data-testid="UserName"]');
                    if (nameEl) {
                        const span = nameEl.querySelector('span');
                        out.display_name = span ? span.innerText.trim() : '';
                    }
                    const link = document.querySelector(
                        'a[href$="/verified_followers"], a[href$="/followers"]');
                    if (link) {
                        // X 把完整数字放在内层 span 的 title 属性里；否则退回可见文本
                        const numSpan = link.querySelector('span[title]');
                        out.followers = numSpan
                            ? numSpan.getAttribute('title')
                            : (link.innerText || '');
                    }
                    return out;
                }
            """)
            if data:
                info["display_name"] = (data.get("display_name") or "").strip()
                info["followers"] = _parse_count(data.get("followers", ""))
        except Exception as e:
            print(f"[scraper] Twitter profile error for @{username}: {e}")
        finally:
            browser.close()
    return info


async def _get_twitter_info(handle: str) -> dict:
    """Twitter/X 账号档案（显示名 + 粉丝数）。"""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _scrape_twitter_profile_sync, handle)
    return {
        "handle": handle,
        "display_name": data.get("display_name") or handle.capitalize(),
        "followers": data.get("followers", 0),
    }


async def _get_youtube_info(handle: str) -> dict:
    """YouTube 频道档案（显示名 + 订阅数）。channel_id 存于 FEED_MAP['feed']。

    复用 yt-dlp：频道 extract_info 顶层含 channel_follower_count（订阅数）。
    任何失败都回退到 FEED_MAP 里的显示名 + followers=0（不抛异常）。
    """
    entry = FEED_MAP.get(handle, {})
    channel_id = entry.get("feed", "")
    display = entry.get("display", handle)
    followers = 0
    try:
        import yt_dlp  # type: ignore
        channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 1}
        loop = asyncio.get_event_loop()
        def _info():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(channel_url, download=False)
        info = await loop.run_in_executor(None, _info)
        followers = info.get("channel_follower_count") or 0
        display = info.get("channel") or info.get("uploader") or display
    except ImportError:
        print("[scraper] yt-dlp not installed; YouTube followers unavailable")
    except Exception as e:
        print(f"[scraper] YouTube info error for {handle}: {e}")
    return {"handle": handle, "display_name": display, "followers": followers}

# ── 公开入口 ───────────────────────────────────────────────────────────────────
async def fetch_profile_info(handle: str) -> dict:
    handle = handle.lower().strip()
    if handle in FEED_MAP:
        entry = FEED_MAP[handle]
        # YouTube 频道有订阅数，单独抓取；RSS 无粉丝概念，保持 0。
        if entry.get("type") == "youtube":
            return await _get_youtube_info(handle)
        return {"handle": handle, "display_name": entry["display"], "followers": 0}
    # 微博：weibo/{uid}
    if _is_weibo(handle):
        return await _get_weibo_info(handle)
    # Reddit subreddit 或 user
    if _is_reddit(handle):
        return await _get_reddit_info(handle)
    # Bluesky 账号：实时查询显示名
    if _is_bluesky(handle):
        bsky_handle = handle if "." in handle else f"{handle}.bsky.social"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{BLUESKY_API}/app.bsky.actor.getProfile",
                    params={"actor": bsky_handle},
                    timeout=_TIMEOUT,
                )
                if r.status_code == 200:
                    profile = r.json()
                    return {
                        "handle": handle,
                        "display_name": profile.get("displayName") or bsky_handle,
                        "followers": profile.get("followersCount", 0),
                    }
        except Exception:
            pass
    # 其余一律按 Twitter/X 处理（与 detect_platform 的兜底一致），抓取粉丝数
    return await _get_twitter_info(handle)

async def _fetch_substack_fulltext(handle: str, max_posts: int = 20) -> list[dict]:
    """
    Substack 全文抓取：对 RSS 里每篇文章，直接抓取 HTML 页面提取正文。
    绕过 RSS 内容截断问题。只对免费文章有效。
    """
    # 先拿 RSS 获取文章列表和 URL
    feed_url = FEED_MAP[handle]["feed"] if handle in FEED_MAP else f"https://{handle}.substack.com/feed"
    rss_posts = await _fetch_rss(feed_url)
    if not rss_posts:
        return []

    enriched = []
    async with httpx.AsyncClient() as client:
        for post in rss_posts[:max_posts]:
            url = post.get("linked_url")
            if not url:
                enriched.append(post)
                continue
            try:
                r = await client.get(url, headers=HEADERS, timeout=_TIMEOUT, follow_redirects=True)
                if r.status_code != 200:
                    enriched.append(post)
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                # Substack 正文在 .body.markup 或 article 标签里
                body = (soup.select_one(".body.markup") or
                        soup.select_one("article .available-content") or
                        soup.select_one("article"))
                if body:
                    # 移除订阅提示、按钮等噪声元素
                    for noise in body.select(".subscription-widget, .button-wrapper, .paywall"):
                        noise.decompose()
                    full_text = body.get_text(" ", strip=True)[:800]
                    if len(full_text) > len(post["content"]):
                        post = {**post, "content": f"{post['content'].split('.')[0]}. {full_text}"}
            except Exception:
                pass
            enriched.append(post)
    return enriched


async def fetch_recent_posts(handle: str, max_pages: int = 3) -> list[dict]:
    handle = handle.lower().strip()

    # ── 微博：weibo/{uid} ────────────────────────────────────────────────────
    if _is_weibo(handle):
        uid = handle.split("/")[1]
        return await _fetch_weibo(uid, max_posts=50)

    # ── Reddit subreddit 或 user ───────────────────────────────────────────────
    if _is_reddit(handle):
        if handle.startswith("r/"):
            return await _fetch_reddit_subreddit(handle[2:], max_posts=50)
        elif handle.startswith("u/"):
            return await _fetch_reddit_user(handle[2:], max_posts=50)

    # ── Bluesky 账号 ──────────────────────────────────────────────────────────
    if _is_bluesky(handle) and handle not in FEED_MAP:
        return await _fetch_bluesky(handle, max_posts=50)

    # ── FEED_MAP 已知账号 ──────────────────────────────────────────────────────
    if handle in FEED_MAP:
        entry = FEED_MAP[handle]
        if entry["type"] == "youtube":
            posts = await _fetch_youtube(entry["feed"], max_videos=20)
            if posts:
                return posts
            yt_rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={entry['feed']}"
            return (await _fetch_rss(yt_rss))[:20]
        elif entry["type"] == "bluesky":
            return await _fetch_bluesky(entry["feed"], max_posts=50)
        else:
            if "substack.com" in entry["feed"] or handle in ("astralcodexten", "lenny"):
                posts = await _fetch_substack_fulltext(handle, max_posts=20)
            else:
                posts = await _fetch_rss(entry["feed"])
            return posts[:30]

    # ── 未知账号：依次尝试 Twitter → Bluesky → Substack ───────────────────────
    # Twitter: 用 Playwright + Cookie（需 .env 配置 TWITTER_AUTH_TOKEN 和 TWITTER_CT0）
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "")
    if auth_token:
        posts = await _fetch_twitter(handle, max_results=50)
        if posts:
            return posts
    # 所有带点号的 handle 都先尝试 Bluesky
    if _is_bluesky(handle):
        posts = await _fetch_bluesky(handle, max_posts=50)
        if posts:
            return posts
    # Substack fallback
    posts = await _fetch_substack_fulltext(handle, max_posts=20)
    if posts:
        return posts
    return (await _fetch_rss(f"https://{handle}.substack.com/feed"))[:30]

async def fetch_url_publish_date(url: str) -> Optional[datetime]:
    if not url:
        return None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=HEADERS, timeout=_TIMEOUT, follow_redirects=True)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "lxml")
            for prop in ("article:published_time", "og:published_time", "datePublished", "pubdate"):
                el = (soup.find("meta", attrs={"property": prop}) or
                      soup.find("meta", attrs={"name": prop}) or
                      soup.find("time", attrs={"datetime": True}))
                if el:
                    val = el.get("content") or el.get("datetime", "")
                    dt = _parse_date(val)
                    if dt:
                        return dt
    except Exception:
        pass
    return None

# ── Bluesky 账号集合（用于路由判断）─────────────────────────────────────────
# handle 格式：不带 @ 和 .bsky.social，例如 "atproto" 对应 atproto.bsky.social
BLUESKY_HANDLES: set[str] = {
    # AI / Tech
    "atproto", "pfrazee", "jay", "why", "dholms",
    "karenx", "emilywithrows", "aaronbeveridge",
    "mosseri", "caseynewton", "nilay",
    # Tech media on Bluesky
    "verge", "techcrunch", "theverge",
    # 科技创业
    "paulg", "sama", "jack",
}

# 自定义域名 Bluesky 账号（不以 .bsky.social 结尾，需要单独列出）
BLUESKY_CUSTOM_DOMAINS: set[str] = {
    "pfrazee.com",
    "jay.bsky.team",
    "nytimes.com",
    "theguardian.com",
    "washingtonpost.com",
    "bbc.com",
    "npr.org",
    "reuters.com",
    "ft.com",
    "bloomberg.com",
    "theathletic.com",
}

def _is_bluesky(handle: str) -> bool:
    """判断是否是 Bluesky 账号（含自定义域名）"""
    return (
        handle in BLUESKY_HANDLES or
        handle.endswith(".bsky.social") or
        handle.endswith(".bsky.team") or
        handle in BLUESKY_CUSTOM_DOMAINS or
        # 包含点号且不是常见 RSS 路径格式的，尝试当 Bluesky 处理
        ("." in handle and not handle.startswith("http") and
         not any(handle.endswith(ext) for ext in [".xml", ".rss", ".atom", ".json"]))
    )

# 加入 FEED_MAP（type="bluesky"，feed 字段是完整 handle 含域名）
FEED_MAP.update({
    # Bluesky 原生创作者
    "pfrazee":      {"feed": "pfrazee.com",           "display": "Paul Frazee",      "type": "bluesky"},
    "jay-bsky":     {"feed": "jay.bsky.team",         "display": "Jay Graber",       "type": "bluesky"},
    "caseynewton":  {"feed": "caseynewton.bsky.social","display": "Casey Newton",    "type": "bluesky"},
    "nilaypatel":   {"feed": "nilay.bsky.social",     "display": "Nilay Patel",      "type": "bluesky"},
    "karenx":       {"feed": "karenx.bsky.social",    "display": "Karen X Cheng",    "type": "bluesky"},
    "atproto":      {"feed": "atproto.bsky.social",   "display": "AT Protocol",      "type": "bluesky"},
    "mosseri":      {"feed": "mosseri.bsky.social",   "display": "Adam Mosseri",     "type": "bluesky"},
})

FEED_MAP.update({
    "sethgodin":         {"feed": "https://seths.blog/feed/atom",                         "display": "Seth Godin",          "type": "rss"},
    "farnamstreet":      {"feed": "https://fs.blog/feed/",                                 "display": "Farnam Street",       "type": "rss"},
    "marginalian":       {"feed": "https://www.themarginalian.org/feed/",                  "display": "The Marginalian",     "type": "rss"},
    "waitbutwhy":        {"feed": "https://waitbutwhy.com/feed",                           "display": "Wait But Why",        "type": "rss"},
    "scotthyoung":       {"feed": "https://www.scotthyoung.com/blog/feed/",                "display": "Scott H Young",       "type": "rss"},
    "ryanholiday":       {"feed": "https://ryanholiday.net/feed/",                         "display": "Ryan Holiday",        "type": "rss"},
    "lilianweng":        {"feed": "https://lilianweng.github.io/index.xml",                "display": "Lilian Weng",         "type": "rss"},
    "jalammar":          {"feed": "https://jalammar.github.io/feed.xml",                   "display": "Jay Alammar",         "type": "rss"},
    "colah":             {"feed": "https://colah.github.io/rss.xml",                       "display": "Chris Olah",          "type": "rss"},
    "distill":           {"feed": "https://distill.pub/rss.xml",                           "display": "Distill",             "type": "rss"},
    "arxiv-ai":          {"feed": "https://rss.arxiv.org/rss/cs.AI",                       "display": "ArXiv AI",            "type": "rss"},
    "googleresearch":    {"feed": "https://research.google/blog/rss/",                     "display": "Google Research",     "type": "rss"},
    "nvidia-blog":       {"feed": "https://developer.nvidia.com/blog/feed/",               "display": "NVIDIA Blog",         "type": "rss"},
    "wired":             {"feed": "https://www.wired.com/feed/rss",                        "display": "WIRED",               "type": "rss"},
    "theguardian-tech":  {"feed": "https://www.theguardian.com/technology/rss",            "display": "The Guardian Tech",   "type": "rss"},
    "bbc-tech":          {"feed": "https://feeds.bbci.co.uk/news/technology/rss.xml",      "display": "BBC Technology",      "type": "rss"},
    "nyt-tech":          {"feed": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "display": "NYT Technology","type": "rss"},
    "siliconangle":      {"feed": "https://siliconangle.com/feed",                         "display": "SiliconANGLE",        "type": "rss"},
    "gizmodo":           {"feed": "https://gizmodo.com/feed/rss",                          "display": "Gizmodo",             "type": "rss"},
    "engadget":          {"feed": "https://www.engadget.com/rss.xml",                      "display": "Engadget",            "type": "rss"},
    "pcmag":             {"feed": "https://www.pcmag.com/feeds/rss/latest",                "display": "PCMag",               "type": "rss"},
    "wsj-markets":       {"feed": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",         "display": "WSJ Markets",         "type": "rss"},
    "ft-tech":           {"feed": "https://www.ft.com/technology?format=rss",              "display": "FT Technology",       "type": "rss"},
    "bloomberg-tech":    {"feed": "https://feeds.bloomberg.com/technology/news.rss",       "display": "Bloomberg Tech",      "type": "rss"},
    "goodfinancialcents":{"feed": "https://www.goodfinancialcents.com/feed",               "display": "Good Financial Cents","type": "rss"},
    "millenialmoney":    {"feed": "https://millennialmoney.com/feed/",                     "display": "Millennial Money",    "type": "rss"},
    "getrichslowly":     {"feed": "https://www.getrichslowly.org/feed/",                   "display": "Get Rich Slowly",     "type": "rss"},
    "bankingdive":       {"feed": "https://www.bankingdive.com/feeds/news/",               "display": "Banking Dive",        "type": "rss"},
    "cointelegraph":     {"feed": "https://cointelegraph.com/rss",                         "display": "CoinTelegraph",       "type": "rss"},
    "decrypt":           {"feed": "https://decrypt.co/feed",                               "display": "Decrypt",             "type": "rss"},
    "sciencedaily":      {"feed": "https://www.sciencedaily.com/rss/top/health.xml",       "display": "Science Daily",       "type": "rss"},
    "statnews":          {"feed": "https://www.statnews.com/feed/",                        "display": "STAT News",           "type": "rss"},
    "3blue1brown":       {"feed": "UCYO_jab_esuFRV4b17AJtAg",  "display": "3Blue1Brown",  "type": "youtube"},
    "kurzgesagt":        {"feed": "UCsXVk37bltHxD1rDPwtNM8Q",  "display": "Kurzgesagt",   "type": "youtube"},
    "veritasium":        {"feed": "UCHnyfMqiRRG1u-2MsSQLbXA",  "display": "Veritasium",   "type": "youtube"},
    "andrewhuang":       {"feed": "UCddiUEpeqJcYeBxX1IVBKvQ",  "display": "Andrew Huang", "type": "youtube"},
    "coldusion":         {"feed": "UC4QZ_LsYcvcq7qOsOhpAX4A",  "display": "ColdFusion",   "type": "youtube"},
    "nandoogaming":      {"feed": "UCo8bcnLyZH8tBIH9V1mLgqQ",  "display": "Nando Gaming",     "type": "youtube"},
    # ── Batch2 新增 YouTube 频道 ──────────────────────────────────────────
    "cgpgrey":           {"feed": "UC2C_jShtL725hvbm1arSV9w",  "display": "CGP Grey",          "type": "youtube"},
    "grahamstephan":     {"feed": "UCV6KDgJskWaEckne5aPA0aQ",  "display": "Graham Stephan",    "type": "youtube"},
    "nandomovies":       {"feed": "UCo8bcnLyZH8tBIH9V1mLgqQ",  "display": "Nando v Movies",   "type": "youtube"},
    "linustechtips":     {"feed": "UCXuqSBlHAE6Xw-yeJA0Tunw",  "display": "Linus Tech Tips",  "type": "youtube"},
    "markrober":         {"feed": "UC7cs8q-gJRlGwj4A8OmCmXg",  "display": "Mark Rober",        "type": "youtube"},
    "teded":             {"feed": "UCY1kMZp36IQSyNx_9h4mpCg",  "display": "TED-Ed",            "type": "youtube"},
    "mkbhd":             {"feed": "UCBcRF18a7Qf58cCRy5xuWwQ",  "display": "MKBHD",             "type": "youtube"},
    "youngtturks":       {"feed": "UC1yBKRuGpC1tSM73A0ZjYjQ",  "display": "The Young Turks",  "type": "youtube"},
    "vicenews":          {"feed": "UCaXkIU1QidjPwiAYu6GcHjg",  "display": "VICE News",         "type": "youtube"},
    "polymatter":        {"feed": "UC5fdssPqmmGhkhsJi4VcckA",  "display": "Polymatter",        "type": "youtube"},
    "karpathy":          {"feed": "UCnUYZLuoy1rq1aVMwx4aTzw",  "display": "Andrej Karpathy",  "type": "youtube"},
    "twominutepapers":   {"feed": "UCZHmQk67mSJgfCCTn7xBfew",  "display": "Two Minute Papers", "type": "youtube"},
    "andreijikh":        {"feed": "UCGy7SkBjcIAgTiwkXEtPnYg",  "display": "Andrei Jikh",       "type": "youtube"},
    "cnn":               {"feed": "UCupvZG-5ko_eiXAupbDfxWw",  "display": "CNN",               "type": "youtube"},
    "andreijikh2":       {"feed": "UCGy7SkBjcIAgTiwkXEtPnYg",  "display": "Andrei Jikh",       "type": "youtube"},
    # Batch2 中之前已测试通过的
    "sentdex":           {"feed": "UCbmNph6atAoGfqLoCL_duAg",  "display": "Sentdex",           "type": "youtube"},
    "freecodecamp":      {"feed": "UC8butISFwT-Wl7EV0hUK0BQ",  "display": "freeCodeCamp",      "type": "youtube"},
    "computerphile":     {"feed": "UCVls1GmFKf6WlTraIb_IaJg",  "display": "Computerphile",     "type": "youtube"},
    "numberphile":       {"feed": "UCoxcjq-8xIDTYp3uz647V5A",  "display": "Numberphile",       "type": "youtube"},
    "crashcourse":       {"feed": "UC9-y-6csu5WGm29I7JiwpnA",  "display": "Crash Course",      "type": "youtube"},
    "marktilbury":       {"feed": "UCsXVk37bltHxD1rDPwtNM8Q",  "display": "Mark Tilbury",      "type": "youtube"},
    "minoritymindset":   {"feed": "UCzWQYUVCpZqtN93H8RR44Qw",  "display": "Minority Mindset",  "type": "youtube"},
    "meetkevin":         {"feed": "UC3Wn3dABlgESm8Bzn8Vamgg",  "display": "Meet Kevin",        "type": "youtube"},
    "abcnews":           {"feed": "UCIALMKvObZNtJ6AmdCLP7Lg",  "display": "ABC News",          "type": "youtube"},
})

# ── Bluesky API（完全免费，无需申请）─────────────────────────────────────────
BLUESKY_API = "https://public.api.bsky.app/xrpc"

async def _resolve_bluesky_did(handle: str, client: httpx.AsyncClient) -> Optional[str]:
    """把 @handle 解析成 Bluesky DID（用户唯一标识）"""
    try:
        r = await client.get(
            f"{BLUESKY_API}/com.atproto.identity.resolveHandle",
            params={"handle": handle},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            return r.json().get("did")
    except Exception as e:
        print(f"[scraper] Bluesky resolve DID error for {handle}: {e}")
    return None

async def _fetch_bluesky(handle: str, max_posts: int = 50) -> list[dict]:
    """
    用 Bluesky 公开 API 抓取用户帖子（skeets）。
    不需要任何 API key，完全免费。
    handle 格式：handle.bsky.social 或 custom domain
    """
    # 清理 handle，去掉 @ 前缀
    handle = handle.lstrip("@").lower().strip()
    # 如果没有域名后缀，自动加上 bsky.social
    if "." not in handle:
        handle = f"{handle}.bsky.social"

    async with httpx.AsyncClient() as client:
        # 解析 DID
        did = await _resolve_bluesky_did(handle, client)
        if not did:
            print(f"[scraper] Bluesky: could not resolve DID for {handle}")
            return []

        # 拉取帖子列表
        posts = []
        cursor = None
        fetched = 0

        while fetched < max_posts:
            params = {
                "actor": did,
                "limit": min(100, max_posts - fetched),
                "filter": "posts_no_replies",  # 只要原创帖，不要回复
            }
            if cursor:
                params["cursor"] = cursor

            try:
                r = await client.get(
                    f"{BLUESKY_API}/app.bsky.feed.getAuthorFeed",
                    params=params,
                    timeout=_TIMEOUT,
                )
                if r.status_code != 200:
                    print(f"[scraper] Bluesky feed error {r.status_code}: {r.text[:200]}")
                    break
                data = r.json()
            except Exception as e:
                print(f"[scraper] Bluesky fetch error: {e}")
                break

            feed = data.get("feed", [])
            if not feed:
                break

            for item in feed:
                post = item.get("post", {})
                record = post.get("record", {})

                # 只处理原创帖（跳过转发）
                if item.get("reason"):
                    continue
                # 跳过回复
                if record.get("reply"):
                    continue

                text = record.get("text", "").strip()
                if not text:
                    continue

                # 处理嵌入内容（图片描述、引用帖子等）
                embed = record.get("embed", {})
                embed_text = ""
                if embed:
                    # 引用帖子
                    if embed.get("$type") == "app.bsky.embed.record":
                        quoted = embed.get("record", {}).get("value", {})
                        if quoted.get("text"):
                            embed_text = f' [引用: {quoted["text"][:100]}]'
                    # 外链卡片
                    elif embed.get("$type") == "app.bsky.embed.external":
                        ext = embed.get("external", {})
                        if ext.get("title"):
                            embed_text = f' [链接: {ext["title"][:100]}]'

                content = text + embed_text

                # 解析时间
                created_at = record.get("createdAt", "")
                posted_dt = _parse_date(created_at) or datetime.utcnow()

                # 构造帖子 URL
                uri = post.get("uri", "")
                rkey = uri.split("/")[-1] if uri else ""
                post_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else None

                platform_id = post.get("cid", hashlib.md5(content[:100].encode()).hexdigest()[:12])

                posts.append({
                    "platform_id": platform_id[:12],
                    "content":     content[:500],
                    "posted_at":   posted_dt,
                    "linked_url":  post_url,
                })
                fetched += 1
                if fetched >= max_posts:
                    break

            cursor = data.get("cursor")
            if not cursor:
                break

    return posts


# ── Weibo Playwright 抓取（移动端 API，无需登录）──────────────────────────────
# handle 格式：weibo/{uid}，例如 weibo/2803301701

def _is_weibo(handle: str) -> bool:
    """判断是否是微博账号"""
    return handle.lower().startswith("weibo/")


def _clean_weibo_text(raw: str) -> str:
    """清理微博 HTML 正文"""
    import re as _re
    raw = raw.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    raw = raw.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    raw = _re.sub(r'<[^>]+>', '', raw)
    raw = _re.sub(r'\s+', ' ', raw).strip()
    return raw


def _scrape_weibo_sync(uid: str, max_posts: int = 50) -> list[dict]:
    """
    用 Playwright 抓取微博用户帖子。
    通过移动端 API（m.weibo.cn/api/container/getIndex）获取数据，无需登录。
    uid: 微博用户数字 ID，例如 "2803301701"
    """
    import time as _time
    import json as _json
    from email.utils import parsedate_to_datetime
    from datetime import datetime as _dt
    from playwright.sync_api import sync_playwright

    weibo_sub  = os.getenv("WEIBO_SUB", "").strip()
    weibo_subp = os.getenv("WEIBO_SUBP", "").strip()
    containerid = f"107603{uid}"

    def _parse_weibo_date(s: str):
        # 微博 created_at 形如 "Thu Aug 27 13:21:27 +0800 2026"（asctime+tz）
        try:
            return _dt.strptime(s, "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=None)
        except Exception:
            pass
        try:
            return parsedate_to_datetime(s).replace(tzinfo=None)
        except Exception:
            return datetime.utcnow()

    posts = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=CHROMIUM_LEAN_ARGS,
        )
        try:
            # ── 首选：桌面 weibo.com 已登录路径（可翻页取到 max_posts 条）──
            # 需要 .env 里的 WEIBO_SUB/WEIBO_SUBP（桌面 weibo.com 的 Cookie，非 m.weibo.cn）。
            if weibo_sub:
                context = browser.new_context(user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ))
                ck = [{"name": "SUB", "value": weibo_sub, "domain": ".weibo.com", "path": "/"}]
                if weibo_subp:
                    ck.append({"name": "SUBP", "value": weibo_subp, "domain": ".weibo.com", "path": "/"})
                context.add_cookies(ck)
                page = context.new_page()
                page.goto(f"https://weibo.com/u/{uid}", wait_until="domcontentloaded", timeout=40000)
                _time.sleep(5)
                if "login" in page.url or "passport" in page.url:
                    print(f"[scraper] Weibo: desktop cookies rejected (redirected to login) for uid={uid}")
                else:
                    # 从 Cookie 取 XSRF-TOKEN，mymblog 接口需要 X-XSRF-TOKEN 头
                    xsrf = next((c["value"] for c in context.cookies() if c["name"] == "XSRF-TOKEN"), "")

                    def _ajax(page_num: int) -> str:
                        return page.evaluate(
                            """async (args) => {
                                const [api, xsrf] = args;
                                try {
                                    const r = await fetch(api, {headers: {
                                        'X-Requested-With': 'XMLHttpRequest',
                                        'X-XSRF-TOKEN': xsrf,
                                        'Accept': 'application/json'},
                                        credentials: 'include'});
                                    return await r.text();
                                } catch (e) { return ''; }
                            }""",
                            [f"/ajax/statuses/mymblog?uid={uid}&page={page_num}&feature=0", xsrf])

                    for page_num in range(1, 20):
                        raw = _ajax(page_num)
                        _time.sleep(1.5)
                        try:
                            data = _json.loads(raw)
                        except Exception:
                            print(f"[scraper] Weibo: desktop page {page_num} not JSON for uid={uid}, stopping")
                            break
                        if data.get("ok") != 1:
                            break

                        lst = data.get("data", {}).get("list", [])
                        new_count = 0
                        for it in lst:
                            mid = it.get("id") or it.get("mblogid")
                            if not mid or mid in seen:
                                continue
                            seen.add(mid)
                            # text_raw 是纯文本；缺失时退回 HTML 版的 text 并清洗
                            text = (it.get("text_raw") or _clean_weibo_text(it.get("text", "")) or "").strip()
                            if not text or len(text) < 3:
                                continue
                            posts.append({
                                "platform_id": str(mid),
                                "content":     text[:500],
                                "posted_at":   _parse_weibo_date(it.get("created_at", "")),
                                "likes":       it.get("attitudes_count", 0),
                                "comments":    it.get("comments_count", 0),
                                "reposts":     it.get("reposts_count", 0),
                            })
                            new_count += 1
                            if len(posts) >= max_posts:
                                break
                        if new_count == 0 or len(posts) >= max_posts:
                            break
                context.close()

            # ── 回退：移动端访客路径（未配置 Cookie，或桌面路径没抓到）→ 只能取首页约 10 条 ──
            if not posts:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
                    ),
                    viewport={"width": 390, "height": 844},
                )
                page = context.new_page()
                # 用真实资料页建立访客 Session（走完 visitor.passport 握手拿 Cookie），
                # 而不是导航到裸 API URL——后者第二次请求会被 wbBotDetector 反爬拦成 HTML 页。
                page.goto(f"https://m.weibo.cn/u/{uid}", wait_until="networkidle", timeout=40000)
                _time.sleep(3)
                if "passport" in page.url or "visitor" in page.url:
                    _time.sleep(2)
                    page.goto(f"https://m.weibo.cn/u/{uid}", wait_until="networkidle", timeout=40000)
                    _time.sleep(3)

                def _api(page_num: int) -> str:
                    api = (f"/api/container/getIndex?uid={uid}&type=uid&value={uid}"
                           f"&containerid={containerid}&page={page_num}")
                    return page.evaluate(
                        """async (api) => {
                            try {
                                const r = await fetch(api, {
                                    headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
                                    credentials: 'include',
                                });
                                return await r.text();
                            } catch (e) { return ''; }
                        }""", api)

                for page_num in range(1, 6):
                    raw = _api(page_num)
                    _time.sleep(2.0)
                    try:
                        data = _json.loads(raw)
                    except Exception:
                        print(f"[scraper] Weibo: page {page_num} not JSON for uid={uid}, stopping")
                        break
                    ok = data.get("ok")
                    if ok != 1:
                        if page_num > 1:
                            print(f"[scraper] Weibo: pagination blocked at page {page_num} (ok={ok}) for uid={uid}; "
                                  f"guest session is limited to the first page — set desktop WEIBO_SUB/WEIBO_SUBP for more")
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
                        text = _clean_weibo_text(mblog.get("text", ""))
                        if not text or len(text) < 3:
                            continue
                        posts.append({
                            "platform_id": mid,
                            "content":     text[:500],
                            "posted_at":   _parse_weibo_date(mblog.get("created_at", "")),
                            "likes":       mblog.get("attitudes_count", 0),
                            "comments":    mblog.get("comments_count", 0),
                            "reposts":     mblog.get("reposts_count", 0),
                        })
                        new_count += 1
                        if len(posts) >= max_posts:
                            break
                    if new_count == 0 or len(posts) >= max_posts:
                        break

        except Exception as e:
            print(f"[scraper] Weibo error for uid={uid}: {e}")
        finally:
            browser.close()

    return posts[:max_posts]


async def _fetch_weibo(uid: str, max_posts: int = 50) -> list[dict]:
    """微博公开入口：Playwright 移动端 API 抓取"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_weibo_sync, uid, max_posts)


def _parse_cn_count(val) -> int:
    """解析微博粉丝数：可能是整数，也可能是带中文单位的字符串（如 '1.58亿'、'12.3万'）。"""
    if isinstance(val, (int, float)):
        return int(val)
    if not val:
        return 0
    s = str(val).strip().replace(",", "")
    try:
        if s.endswith("亿"):
            return int(float(s[:-1]) * 100_000_000)
        if s.endswith("万"):
            return int(float(s[:-1]) * 10_000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _scrape_weibo_info_sync(uid: str) -> dict:
    """通过 m.weibo.cn 移动端 API 获取微博用户昵称与粉丝数。失败返回 followers=0。"""
    import time as _time
    import json as _json
    from playwright.sync_api import sync_playwright

    info = {"display_name": "", "followers": 0}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=CHROMIUM_LEAN_ARGS,
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
            viewport={"width": 390, "height": 844},
        )
        page = context.new_page()
        try:
            # 先访问首页初始化 Session（获取必要 Cookie）
            page.goto("https://m.weibo.cn", timeout=20000)
            _time.sleep(3)
            page.goto(
                f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}",
                timeout=15000,
            )
            _time.sleep(2)
            content = page.content()
            b = content.find("{")
            e = content.rfind("}") + 1
            if b >= 0:
                data = _json.loads(content[b:e])
                user = data.get("data", {}).get("userInfo", {})
                info["display_name"] = user.get("screen_name", "") or ""
                info["followers"] = _parse_cn_count(user.get("followers_count", 0))
        except Exception as ex:
            print(f"[scraper] Weibo info error for {uid}: {ex}")
        finally:
            browser.close()
    return info


async def _get_weibo_info(handle: str) -> dict:
    """获取微博账号基本信息（昵称 + 粉丝数，UID 为标识）。"""
    uid = handle.split("/")[1] if "/" in handle else handle
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _scrape_weibo_info_sync, uid)
    return {
        "handle":       handle,
        "display_name": data.get("display_name") or f"微博用户 {uid}",
        "followers":    data.get("followers", 0),
    }


# ── Reddit API（完全免费，无需 API key）────────────────────────────────────────
REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DistortionResearch/1.0; academic)",
    "Accept": "application/json",
}
REDDIT_API = "https://www.reddit.com"

def _is_reddit(handle: str) -> bool:
    """判断是否是 Reddit 来源（r/subreddit 或 u/username）"""
    h = handle.lstrip("@").lower()
    return h.startswith("r/") or h.startswith("u/")

async def _fetch_reddit_subreddit_json(subreddit: str, max_posts: int = 50) -> list[dict]:
    """
    抓取 Subreddit 热门帖子（httpx JSON API，作为 Playwright 的兜底）。
    subreddit: 不带 r/ 前缀，例如 "wallstreetbets"
    """
    posts = []
    after = None
    fetched = 0

    async with httpx.AsyncClient() as client:
        while fetched < max_posts:
            params = {"limit": min(100, max_posts - fetched), "t": "month"}
            if after:
                params["after"] = after
            try:
                r = await client.get(
                    f"{REDDIT_API}/r/{subreddit}/top.json",
                    headers=REDDIT_HEADERS,
                    params=params,
                    timeout=_TIMEOUT,
                    follow_redirects=True,
                )
                if r.status_code != 200:
                    print(f"[scraper] Reddit subreddit {subreddit} error {r.status_code}")
                    break
                data = r.json()
            except Exception as e:
                print(f"[scraper] Reddit fetch error: {e}")
                break

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                post = child.get("data", {})
                title = post.get("title", "").strip()
                selftext = post.get("selftext", "").strip()
                # 合并标题和正文前300字
                content = f"{title}. {selftext[:300]}" if selftext and selftext != "[removed]" else title
                if not content.strip():
                    continue

                created = post.get("created_utc")
                posted_dt = datetime.utcfromtimestamp(created) if created else datetime.utcnow()
                post_id = post.get("id", "")
                permalink = post.get("permalink", "")
                url = f"https://www.reddit.com{permalink}" if permalink else None

                posts.append({
                    "platform_id": post_id or hashlib.md5(content[:100].encode()).hexdigest()[:12],
                    "content": content[:500],
                    "posted_at": posted_dt,
                    "linked_url": url,
                })
                fetched += 1
                if fetched >= max_posts:
                    break

            after = data.get("data", {}).get("after")
            if not after:
                break

    return posts


async def _fetch_reddit_user_json(username: str, max_posts: int = 50) -> list[dict]:
    """
    抓取 Reddit 用户的发帖历史（httpx JSON API，作为 Playwright 的兜底）。
    username: 不带 u/ 前缀，例如 "spez"
    """
    posts = []
    after = None
    fetched = 0

    async with httpx.AsyncClient() as client:
        while fetched < max_posts:
            params = {"limit": min(100, max_posts - fetched), "sort": "new"}
            if after:
                params["after"] = after
            try:
                r = await client.get(
                    f"{REDDIT_API}/user/{username}/submitted.json",
                    headers=REDDIT_HEADERS,
                    params=params,
                    timeout=_TIMEOUT,
                    follow_redirects=True,
                )
                if r.status_code == 404:
                    print(f"[scraper] Reddit user {username} not found")
                    break
                if r.status_code != 200:
                    print(f"[scraper] Reddit user {username} error {r.status_code}")
                    break
                data = r.json()
            except Exception as e:
                print(f"[scraper] Reddit user fetch error: {e}")
                break

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                post = child.get("data", {})
                title = post.get("title", "").strip()
                selftext = post.get("selftext", "").strip()
                content = f"{title}. {selftext[:300]}" if selftext and selftext != "[removed]" else title
                if not content.strip():
                    continue

                created = post.get("created_utc")
                posted_dt = datetime.utcfromtimestamp(created) if created else datetime.utcnow()
                post_id = post.get("id", "")
                permalink = post.get("permalink", "")
                url = f"https://www.reddit.com{permalink}" if permalink else None

                posts.append({
                    "platform_id": post_id or hashlib.md5(content[:100].encode()).hexdigest()[:12],
                    "content": content[:500],
                    "posted_at": posted_dt,
                    "linked_url": url,
                })
                fetched += 1
                if fetched >= max_posts:
                    break

            after = data.get("data", {}).get("after")
            if not after:
                break

    return posts


async def _get_reddit_info(handle: str) -> dict:
    """获取 Reddit subreddit 或 user 的基本信息"""
    h = handle.lstrip("@").lower()
    async with httpx.AsyncClient() as client:
        try:
            if h.startswith("r/"):
                sub = h[2:]
                r = await client.get(f"{REDDIT_API}/r/{sub}/about.json",
                                     headers=REDDIT_HEADERS, timeout=_TIMEOUT)
                if r.status_code == 200:
                    d = r.json().get("data", {})
                    return {
                        "handle": handle,
                        "display_name": d.get("display_name_prefixed", handle),
                        "followers": d.get("subscribers", 0),
                    }
            elif h.startswith("u/"):
                user = h[2:]
                r = await client.get(f"{REDDIT_API}/user/{user}/about.json",
                                     headers=REDDIT_HEADERS, timeout=_TIMEOUT)
                if r.status_code == 200:
                    d = r.json().get("data", {})
                    return {
                        "handle": handle,
                        "display_name": d.get("name", user),
                        "followers": d.get("total_karma", 0),
                    }
        except Exception:
            pass
    return {"handle": handle, "display_name": handle, "followers": 0}


# ── Reddit Playwright 抓取（绕过 403）────────────────────────────────────────
MAX_BODY_CHARS    = 800
MAX_COMMENTS      = 3
MAX_COMMENT_CHARS = 300

def _scrape_subreddit_sync(subreddit: str, max_posts: int = 50) -> list[dict]:
    """用 Playwright 浏览器抓取 Subreddit 热门帖子，绕过 403"""
    import time, hashlib as _hash
    from playwright.sync_api import sync_playwright

    url = f"https://www.reddit.com/r/{subreddit}/top/?t=month"
    posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[*CHROMIUM_LEAN_ARGS, "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        try:
            # networkidle 让 Reddit 的 JS anti-bot 挑战（?js_challenge=1&token=...）跑完并跳转，
            # domcontentloaded 会在挑战页就返回，随后的 evaluate 撞上跳转 → "Execution context
            # was destroyed" / document.body 为 null → "Cannot read null.scrollHeight"。
            page.goto(url, wait_until="networkidle", timeout=45000)
            # 关闭 cookie 弹窗
            for btn in ["Accept all", "Accept", "Reject non-essential"]:
                try:
                    page.get_by_role("button", name=btn, exact=False).first.click(timeout=2000)
                    time.sleep(1)
                    break
                except Exception:
                    continue

            # 等真正的帖子元素出现（挑战解决后内容才注入），而不是死等固定秒数
            try:
                page.wait_for_selector("shreddit-post", timeout=20000)
            except Exception as e:
                print(f"[scraper] Reddit: shreddit-post not found for r/{subreddit}: {e}")

            # 滚动加载更多帖子（多次滚动确保加载足够内容）
            for scroll_i in range(8):
                # null-guard：挑战/空白页时 document.body 可能为 null
                try:
                    page.evaluate("() => { if (document.body) window.scrollTo(0, document.body.scrollHeight); }")
                except Exception:
                    break
                time.sleep(2.5)
                # 检查帖子数量是否已足够
                count = page.evaluate("""
                    () => document.querySelectorAll('shreddit-post').length
                """)
                if count >= max_posts:
                    break

            raw = page.evaluate(f"""
                (maxPosts) => {{
                    const posts = [];
                    const seen = new Set();

                    // shreddit 新格式
                    for (const el of document.querySelectorAll('shreddit-post')) {{
                        const title = el.getAttribute('post-title') || '';
                        const permalink = el.getAttribute('permalink') || '';
                        if (!title || !permalink) continue;
                        const url = permalink.startsWith('/') ? 'https://www.reddit.com' + permalink : permalink;
                        if (seen.has(url)) continue;
                        seen.add(url);
                        posts.push({{
                            title,
                            url,
                            subreddit: el.getAttribute('subreddit-prefixed-name') || 'r/{subreddit}',
                            score: parseInt(el.getAttribute('score') || '0') || 0,
                            author: el.getAttribute('author') || '',
                            date: el.getAttribute('created-timestamp') || '',
                        }});
                        if (posts.length >= maxPosts) break;
                    }}

                    // 旧格式 fallback
                    if (posts.length === 0) {{
                        for (const link of document.querySelectorAll('a[data-click-id="body"][href*="/comments/"]')) {{
                            const href = link.getAttribute('href') || '';
                            const url = href.startsWith('/') ? 'https://www.reddit.com' + href : href;
                            if (seen.has(url)) continue;
                            seen.add(url);
                            const title = link.innerText.trim();
                            if (!title) continue;
                            posts.push({{ title, url, subreddit: 'r/{subreddit}', score: 0, author: '', date: '' }});
                            if (posts.length >= maxPosts) break;
                        }}
                    }}
                    return posts;
                }}
            """, max_posts)

            for item in (raw or []):
                title = item.get("title", "").strip()
                if not title:
                    continue
                post_url = item.get("url", "")
                pid = _hash.md5(title.encode()).hexdigest()[:12]
                date_str = item.get("date", "")
                try:
                    posted_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None) if date_str else datetime.utcnow()
                except Exception:
                    posted_dt = datetime.utcnow()

                # 抓取帖子正文（访问详情页，读取 selftext）
                selftext = ""
                if post_url:
                    try:
                        page.goto(post_url + ".json", timeout=8000)
                        time.sleep(1)
                        body = page.evaluate("() => document.body.innerText")
                        import json as _json
                        data = _json.loads(body)
                        selftext = data[0]["data"]["children"][0]["data"].get("selftext", "") or ""
                        selftext = selftext.strip()
                        if selftext in ("[removed]", "[deleted]"):
                            selftext = ""
                    except Exception:
                        selftext = ""

                content = f"{title}. {selftext[:300]}" if selftext else title
                posts.append({
                    "platform_id": pid,
                    "content": content[:500],
                    "posted_at": posted_dt,
                    "linked_url": post_url or None,
                })
        except Exception as e:
            print(f"[scraper] Reddit browser error for r/{subreddit}: {e}")
        finally:
            browser.close()

    return posts[:max_posts]


def _scrape_reddit_user_sync(username: str, max_posts: int = 50) -> list[dict]:
    """用 Playwright 浏览器抓取 Reddit 用户帖子"""
    import time, hashlib as _hash
    from playwright.sync_api import sync_playwright

    url = f"https://www.reddit.com/user/{username}/submitted/?sort=new"
    posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=CHROMIUM_LEAN_ARGS,
        )
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        try:
            # networkidle 让 Reddit 的 JS anti-bot 挑战（?js_challenge=1&token=...）跑完并跳转，
            # 否则 evaluate 撞上跳转 → "Execution context destroyed" / document.body 为 null。
            page.goto(url, wait_until="networkidle", timeout=45000)
            try:
                page.wait_for_selector("shreddit-post", timeout=20000)
            except Exception as e:
                print(f"[scraper] Reddit: shreddit-post not found for u/{username}: {e}")
            for scroll_i in range(8):
                # null-guard：挑战/空白页时 document.body 可能为 null
                try:
                    page.evaluate("() => { if (document.body) window.scrollTo(0, document.body.scrollHeight); }")
                except Exception:
                    break
                time.sleep(2.5)
                count = page.evaluate("""
                    () => document.querySelectorAll('shreddit-post').length
                """)
                if count >= max_posts:
                    break

            raw = page.evaluate(f"""
                (maxPosts) => {{
                    const posts = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('shreddit-post')) {{
                        const title = el.getAttribute('post-title') || '';
                        const permalink = el.getAttribute('permalink') || '';
                        if (!title || !permalink) continue;
                        const url = permalink.startsWith('/') ? 'https://www.reddit.com' + permalink : permalink;
                        if (seen.has(url)) continue;
                        seen.add(url);
                        posts.push({{
                            title,
                            url,
                            subreddit: el.getAttribute('subreddit-prefixed-name') || '',
                            score: parseInt(el.getAttribute('score') || '0') || 0,
                            author: el.getAttribute('author') || '',
                            date: el.getAttribute('created-timestamp') || '',
                        }});
                        if (posts.length >= maxPosts) break;
                    }}
                    if (posts.length === 0) {{
                        for (const link of document.querySelectorAll('a[data-click-id="body"][href*="/comments/"]')) {{
                            const href = link.getAttribute('href') || '';
                            const url = href.startsWith('/') ? 'https://www.reddit.com' + href : href;
                            if (seen.has(url)) continue;
                            seen.add(url);
                            const title = link.innerText.trim();
                            if (!title) continue;
                            posts.push({{ title, url, subreddit: '', score: 0, author: '', date: '' }});
                            if (posts.length >= maxPosts) break;
                        }}
                    }}
                    return posts;
                }}
            """, max_posts)

            for item in (raw or []):
                title = item.get("title", "").strip()
                if not title:
                    continue
                post_url = item.get("url", "")
                pid = _hash.md5(title.encode()).hexdigest()[:12]
                date_str = item.get("date", "")
                try:
                    posted_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None) if date_str else datetime.utcnow()
                except Exception:
                    posted_dt = datetime.utcnow()

                # 抓取帖子正文
                selftext = ""
                if post_url:
                    try:
                        page.goto(post_url + ".json", timeout=8000)
                        time.sleep(1)
                        body = page.evaluate("() => document.body.innerText")
                        import json as _json
                        data = _json.loads(body)
                        selftext = data[0]["data"]["children"][0]["data"].get("selftext", "") or ""
                        selftext = selftext.strip()
                        if selftext in ("[removed]", "[deleted]"):
                            selftext = ""
                    except Exception:
                        selftext = ""

                content = f"{title}. {selftext[:300]}" if selftext else title
                posts.append({
                    "platform_id": pid,
                    "content": content[:500],
                    "posted_at": posted_dt,
                    "linked_url": post_url or None,
                })
        except Exception as e:
            print(f"[scraper] Reddit browser user error for u/{username}: {e}")
        finally:
            browser.close()

    return posts[:max_posts]


async def _fetch_reddit_subreddit(subreddit: str, max_posts: int = 50) -> list[dict]:
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, _scrape_subreddit_sync, subreddit, max_posts)
    # Playwright 抓到 0 帖（挑战未过 / 结构变动）→ 自动兜底到 JSON API
    if not posts:
        print(f"[scraper] Reddit: Playwright returned 0 posts for r/{subreddit}, falling back to JSON API")
        try:
            posts = await _fetch_reddit_subreddit_json(subreddit, max_posts)
        except Exception as e:
            print(f"[scraper] Reddit JSON fallback error for r/{subreddit}: {e}")
    return posts


async def _fetch_reddit_user(username: str, max_posts: int = 50) -> list[dict]:
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, _scrape_reddit_user_sync, username, max_posts)
    # Playwright 抓到 0 帖（挑战未过 / 结构变动）→ 自动兜底到 JSON API
    if not posts:
        print(f"[scraper] Reddit: Playwright returned 0 posts for u/{username}, falling back to JSON API")
        try:
            posts = await _fetch_reddit_user_json(username, max_posts)
        except Exception as e:
            print(f"[scraper] Reddit JSON fallback error for u/{username}: {e}")
    return posts
