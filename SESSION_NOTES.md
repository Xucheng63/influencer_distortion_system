# Distortion Detection — Session Notes

_Full-stack debugging + scraper-hardening session. Date: 2026-08-27._

Backend = FastAPI (`distortion-backend/`), Frontend = single-page `influencer-distortion-tool/index.html`.

> ⚠️ **DO NOT COMMIT TO GIT.** All changes this session are **local working-tree only** — do not `git add`, `git commit`, or `git push`. (The repo also currently has no commits; everything is untracked.)

---

## 0. TL;DR — what happened this session

1. **Fixed the `"no low surrogate in string"` 400 errors** — lone UTF-16 surrogates in scraped text made OpenAI reject the classifier request. Added a sanitizer.
2. **Fixed the Reddit scraper** (both subreddit and user) — it was dying on Reddit's JS anti-bot challenge. Now waits for the challenge, null-guards the DOM, and falls back to the JSON API.
3. **Improved the Twitter/X scraper** — respects the real max (was hardcoded 50), collects up to 50, scrolls more.
4. **Fixed the Weibo 10-post cap** — mobile guest API is limited to page 1; switched to the authenticated desktop `weibo.com` API (with cookies) → 50 posts. Falls back to 10-post guest mode if no cookie.
5. **Verified all 6 platforms pass** end-to-end (scrape → rules → GPT verify → aggregate → profile).

---

## 1. Files modified this session (all LOCAL, uncommitted)

### `distortion-backend/app/services/classifier.py`
- **Added `strip_lone_surrogates(text)`** — removes unpaired UTF-16 surrogate code points (U+D800–U+DFFF) via `text.encode("utf-8","ignore").decode("utf-8")`. Valid emoji (single code points) are preserved.
- **Called it at the top of `classify()`** so no lone surrogate ever reaches OpenAI.
- **Added `logger = logging.getLogger("distortion.classifier")`** and **WARNING logging** in both LLM `except` blocks (`verify_with_gpt`, `classify_llm_fresh`) so outbound OpenAI failures are visible in the uvicorn log instead of only surviving in `classification_method`.

### `distortion-backend/app/services/pipeline.py`
- **Sanitize scraped content at ingestion**: `raw["content"] = classifier.strip_lone_surrogates(raw["content"])` before classify/store — protects the DB and the `ensure_ascii=False` export path too.

### `distortion-backend/app/services/scraper.py`
- **Reddit subreddit** (`_scrape_subreddit_sync`): `wait_until="networkidle"` + `timeout=45000` (was `domcontentloaded`+`sleep`), added `wait_for_selector("shreddit-post")`, and **null-guarded** the scroll (`if (document.body) …`). Fixes the JS-challenge crashes (`Execution context was destroyed` / `Cannot read null.scrollHeight`).
- **Reddit user** (`_scrape_reddit_user_sync`): same networkidle + wait_for_selector + null-guard treatment.
- **Reddit JSON fallback**: renamed the shadowed httpx functions to `_fetch_reddit_subreddit_json` / `_fetch_reddit_user_json`, and wired them as automatic fallbacks in the async wrappers — if Playwright returns 0 posts, retry via the JSON API.
- **Twitter/X** (`_scrape_twitter_sync`): `[:50]` hardcode → **`[:max_tweets]`**; scroll iterations **12 → 20**. In `fetch_recent_posts`, Twitter dispatch **`max_results=30` → `50`**.
- **Weibo** (`_scrape_weibo_sync`): **rewritten**. Primary path = authenticated **desktop `weibo.com/ajax/statuses/mymblog`** (uses `WEIBO_SUB`/`WEIBO_SUBP`, desktop UA, `XSRF-TOKEN` header, paginates to `max_posts`). Fallback = mobile `m.weibo.cn` guest **in-page XHR** (replaces the old fragile `find("{")/rfind("}")` extraction; ~10 posts). Shared `_parse_weibo_date` handles the `"Thu Aug 27 13:21:27 +0800 2026"` format.

### `distortion-backend/.env`
- Added **`WEIBO_SUB`** and **`WEIBO_SUBP`** (desktop weibo.com session cookies — these are **session cookies and will expire**; on expiry the scraper logs a login-redirect and auto-falls back to 10-post guest mode).

> Everything else (models, routes, aggregator, frontend) is unchanged from the prior session.

---

## 2. Root causes & fixes (detail)

### Bug 1 — `"no low surrogate in string"` 400s
Scraped text (esp. YouTube captions, truncated emoji) can contain a **lone UTF-16 surrogate**. The OpenAI SDK serializes it as an unpaired `\udXXX`; OpenAI's server rejects the body with HTTP 400 `no low surrogate in string` (on this machine's SDK it surfaces as a client-side `UnicodeEncodeError: surrogates not allowed`). The classifier's broad `except` swallowed it → analyze returned **200** while classification silently degraded (that's why the 400 was never in the uvicorn log — it's an **outbound** error to OpenAI). Fix: strip lone surrogates before the OpenAI call and at ingestion; log failures at WARNING.

### Bug 2 — Reddit scraper returned 0 posts
Reddit serves the headless browser a **JS anti-bot challenge** (`...&js_challenge=1&token=...`). With `domcontentloaded`, the code ran `evaluate()` on the challenge page mid-navigation (`Execution context was destroyed`) or against a null `document.body` (`Cannot read null.scrollHeight`). Fix: `networkidle` + `wait_for_selector` lets the challenge resolve; null-guard + JSON fallback for safety. (The `www.reddit.com` JSON API 403s from this host, so Playwright is primary; fallback is best-effort.)

### Bug 3 — Twitter/X capped / rate-limited
`[:50]` ignored the `max_tweets` param; dispatch only asked for 30. Now `[:max_tweets]`, `max_results=50`, 20 scrolls. **Note:** actual yield is X-side limited — rate-limiting / virtual-scroll / a stale cookie cap real results below 50 (realDonaldTrump's timeline is stale — newest tweet 2026-07-28).

### Bug 4 — Weibo only returned 10 posts
The mobile `m.weibo.cn` guest API only serves **page 1** (~10 posts); page 2 returns `ok=-100` / a `wbBotDetector` HTML challenge — verified even Weibo's own mobile frontend can't paginate as a guest (platform restriction, not a code bug). Desktop cookies don't work on the mobile domain. Fix: use the **desktop `weibo.com/ajax/statuses/mymblog`** endpoint with desktop cookies → 20 posts/page, paginates freely (tested to 100). Now returns 50.

---

## 3. Current system state

- **Backend:** running on **:8002** (PID **49537** at time of writing — will change on restart), `/health` → `{"status":"ok"}`.
- **Env:** `ischool` conda env (`/usr/local/Caskroom/miniconda/base/envs/ischool/bin/...`).
- **DB in use:** `distortion-backend/data/distortion.db` (server cwd = `distortion-backend/`, `DATABASE_URL=sqlite+aiosqlite:///./data/distortion.db`).
- **Uvicorn log:** `/private/tmp/uvicorn_distortion.log` (stdout+stderr redirected here).
- **Frontend:** `influencer-distortion-tool/index.html` → `http://localhost:8002/api`.
- **`.env`:** has `OPENAI_API_KEY`, `TWITTER_AUTH_TOKEN`/`TWITTER_CT0`, `WEIBO_SUB`/`WEIBO_SUBP`, `CORS_ORIGINS=...,null` (file:// enabled). **All secrets are plaintext — rotate/vault if this leaves the machine.**

### Current post counts in the DB (per tested account)
| Handle | Platform | Posts |
|---|---|---|
| simonwillison | RSS | 33 |
| cgpgrey | YouTube | 20 |
| pfrazee.com | Bluesky | 50 |
| r/machinelearning | Reddit | 50 |
| weibo/2803301701 | Weibo | 50 |
| elonmusk | Twitter/X | 29 |
| realdonaldtrump | Twitter/X | 26 |

---

## 4. Platform test results (final, this session)

All return HTTP **200** with valid profiles and **zero error methods**. GPT `gpt-4o-mini` verification confirmed running (Weibo/2803301701 skips GPT only because no posts had rule hits — by design, not an error).

| Platform | Account | HTTP | Posts | Distortion Index | SI / AM / NC / LL / TD | GPT posts |
|---|---|---|---|---|---|---|
| RSS | simonwillison | 200 | 33 | 2 | .061 / 0 / 0 / 0 / 0 | 2 |
| YouTube | cgpgrey | 200 | 20 | 1 | 0 / 0 / 0 / 0 / .1 | 2 |
| Bluesky | pfrazee.com | 200 | 50 | 0 | 0 / 0 / .02 / 0 / 0 | 3 |
| Reddit | r/MachineLearning | 200 | 50 | 0 | 0 / 0 / 0 / 0 / 0 | 1 |
| Weibo | weibo/2803301701 | 200 | 50 | 0 | 0 / 0 / 0 / 0 / 0 | 0 (no rule hits) |
| Twitter/X | elonmusk | 200 | 29 | 1 | .034 / 0 / 0 / 0 / 0 | 1 |
| Twitter/X | realDonaldTrump | 200 | 26 (24 in window) | 20 | .42 / .083 / 0 / .33 / 0 | 11 |

**Notes:**
- **Weibo** = 50 via the authenticated desktop path (was 10 as guest).
- **Twitter/X** yields are X-side limited (rate-limiting + stale cookie). realDonaldTrump's newest tweet is 2026-07-28; scroll bump 12→20 raised it from ~20 to 26.
- Cached accounts may show `new_posts_crawled: 0` on re-analyze (dedup by `platform_id`) — clear the account's posts to force a fresh scrape.

---

## 5. How to restart everything

### Backend (port 8002)
```bash
cd /Users/yuxucheng/Desktop/ischool/distortion-full-project/distortion-backend
# stop any existing server on :8002
kill $(lsof -nP -iTCP:8002 | awk '/LISTEN/{print $2}') 2>/dev/null
# start (logs to /private/tmp/uvicorn_distortion.log)
nohup /usr/local/Caskroom/miniconda/base/envs/ischool/bin/uvicorn \
  app.main:app --port 8002 --app-dir . >> /private/tmp/uvicorn_distortion.log 2>&1 &
# verify
curl -s http://localhost:8002/health      # → {"status":"ok"}
```
> No `--reload` — **restart after any code/.env edit** for changes to load.

### Frontend
```bash
open /Users/yuxucheng/Desktop/ischool/distortion-full-project/influencer-distortion-tool/index.html
# (works via file:// because CORS_ORIGINS includes null; already points at :8002)
```

### Analyze an account (CLI)
```bash
# URL-encode slashes in handles, e.g. r%2FMachineLearning, weibo%2F2803301701
curl -X POST http://localhost:8002/api/analyze/<handle>
```

### Force a fresh scrape (clear one account's cache)
```bash
/usr/local/Caskroom/miniconda/base/envs/ischool/bin/python - <<'PY'
import sqlite3
c=sqlite3.connect("/Users/yuxucheng/Desktop/ischool/distortion-full-project/distortion-backend/data/distortion.db")
aid=c.execute("select id from account where handle=?",("<handle>",)).fetchone()[0]
c.execute("delete from post where account_id=?",(aid,)); c.commit(); c.close()
PY
```

### Tail the log
```bash
tail -f /private/tmp/uvicorn_distortion.log
# useful greps: "surrogate", "Reddit browser error", "Weibo:", "pagination blocked"
```

---

## 6. Known issues & gotchas

- **DO NOT COMMIT** — keep all changes local (user directive).
- **Weibo cookies expire** — `WEIBO_SUB`/`WEIBO_SUBP` are desktop `weibo.com` session cookies. On expiry the scraper logs `desktop cookies rejected (redirected to login)` and falls back to 10-post guest mode. Refresh from a logged-in `weibo.com` browser (DevTools → Application → Cookies) when that happens.
- **Twitter/X rate-limiting** — repeated scrapes → 0 posts (fails silently, ~20s). Profile/display name still resolves. Wait a few minutes and retry; don't hammer. Yields below 50 are expected when throttled.
- **Reddit JSON fallback** — `www.reddit.com/*.json` 403s from this host, so the fallback is best-effort; Playwright (now fixed) is the reliable path.
- **Relative DB path** — launching uvicorn from `distortion-backend/` uses `distortion-backend/data/distortion.db`; launching from the project root uses `./data/distortion.db`. **Two different DBs** — this session uses the `distortion-backend/` one. Be consistent.
- **Analysis window = 365 days** (`WINDOW_DAYS=365`). Posts older than that display via `/posts` but don't count toward the profile (`total_analyzed`).
- **Empty profile on scrape failure** — scrapers return `[]` on failure and the endpoint still returns **200** with an empty profile. Scrape failures now log (Weibo/Reddit); classifier failures log at WARNING.

---

## 7. Test accounts that work (per platform)

| Platform | Handle | Notes |
|---|---|---|
| RSS | `simonwillison` | FEED_MAP RSS. |
| YouTube | `cgpgrey`, `lexfridman` | Channel RSS + transcripts. cgpgrey = emoji-heavy captions (was the surrogate-bug trigger). |
| Bluesky | `pfrazee.com` | Custom-domain Bluesky via AT Protocol. |
| Reddit | `r/MachineLearning` | Playwright `top/?t=month` (now handles JS challenge). `u/<user>` also fixed. |
| Weibo | `weibo/2803301701` | 人民日报. `weibo/{uid}`. 50 posts via desktop auth. |
| Twitter/X | `elonmusk`, `realDonaldTrump` | Playwright + cookies. Rate-limit sensitive. |

---

## 8. Suggested follow-ups (not done)
- Refresh Weibo cookies when they expire; consider adding them to a secret store.
- Consider making `WINDOW_DAYS` and per-platform post caps env-configurable.
- Rotate the plaintext credentials in `.env`.
- Reddit subreddit uses `top/?t=month` (not newest-first) — switch to `/new/` + date sort if recency matters.
- The `experiment_weibo_batch*.py` scripts use the old 10-post guest method (superseded by the desktop-auth scraper).
