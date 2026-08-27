#!/usr/bin/env python3
"""
test_reddit_batch2.py — 预检测30个新 Reddit 候选账号
用 Playwright 浏览器验证是否真实存在且有帖子

运行：python test_reddit_batch2.py
"""
import time
from playwright.sync_api import sync_playwright

# 30个候选账号（Subreddit + 用户，多类别覆盖）
CANDIDATES = [
    # Subreddit — 高失真预期
    ("r/aitechnology",       "subreddit", "ai_ml"),
    ("r/ChatGPT",            "subreddit", "ai_ml"),
    ("r/OpenAI",             "subreddit", "ai_ml"),
    ("r/StockMarket",        "subreddit", "finance"),
    ("r/investing_discussion","subreddit","finance"),
    ("r/CryptoCurrency",     "subreddit", "crypto"),
    ("r/Bitcoin",            "subreddit", "crypto"),
    ("r/economy",            "subreddit", "finance"),
    ("r/geopolitics",        "subreddit", "politics"),
    ("r/worldpolitics",      "subreddit", "politics"),
    # Subreddit — 低/中失真预期
    ("r/MachineLearning",    "subreddit", "ai_ml"),
    ("r/learnprogramming",   "subreddit", "tech"),
    ("r/cscareerquestions",  "subreddit", "tech"),
    ("r/AskHistorians",      "subreddit", "learning"),
    ("r/explainlikeimfive",  "subreddit", "learning"),
    ("r/space",              "subreddit", "science"),
    ("r/Physics",            "subreddit", "science"),
    ("r/medicine",           "subreddit", "health"),
    ("r/nutrition",          "subreddit", "health"),
    ("r/personalfinance",    "subreddit", "finance"),
    # Reddit 用户 — 知名活跃账号
    ("u/AutoModerator",      "user",      "tech"),
    ("u/GallowBoob",         "user",      "culture"),
    ("u/Poem_for_your_sprog","user",      "culture"),
    ("u/mvea",               "user",      "science"),
    ("u/Braveliltoaster2",   "user",      "culture"),
    ("u/spez",               "user",      "tech"),
    ("u/karmanaut",          "user",      "culture"),
    ("u/AWildSketchAppeared","user",      "culture"),
    ("u/IAmA_Moderator",     "user",      "tech"),
    ("u/lobbydancer",        "user",      "culture"),
]

def check_account(handle: str, kind: str, page) -> tuple[int, str]:
    """检查账号是否有帖子，返回 (帖子数, 状态)"""
    try:
        if kind == "subreddit":
            sub = handle[2:]
            url = f"https://www.reddit.com/r/{sub}/top/?t=month"
        else:
            user = handle[2:]
            url = f"https://www.reddit.com/user/{user}/submitted/?sort=new"

        page.goto(url, timeout=20000)
        time.sleep(4)

        result = page.evaluate("""
            () => {
                const body = document.body.innerText || '';
                if (body.includes('page not found') || body.includes('banned') ||
                    body.includes('suspended') || body.includes('private') ||
                    body.includes('404')) {
                    return {count: -1, reason: 'not found/banned/private'};
                }
                const posts = document.querySelectorAll('shreddit-post');
                const links = document.querySelectorAll('a[data-click-id="body"][href*="/comments/"]');
                const count = Math.max(posts.length, links.length);
                return {count, reason: 'ok'};
            }
        """)
        return result.get("count", 0), result.get("reason", "")
    except Exception as e:
        return 0, str(e)[:40]

def main():
    print("\n" + "="*65)
    print("Reddit 第二批账号预检测")
    print(f"候选账号: {len(CANDIDATES)} 个")
    print("="*65)

    good = []
    bad = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))

        for i, (handle, kind, category) in enumerate(CANDIDATES, 1):
            print(f"  [{i:2d}/30] {handle:<30}", end="", flush=True)
            count, reason = check_account(handle, kind, page)
            if count > 0:
                print(f"✓ {count} 帖子 [{category}]")
                good.append((handle, kind, category, count))
            elif count == -1:
                print(f"✗ {reason}")
                bad.append((handle, reason))
            else:
                print(f"~ 0 帖子 ({reason})")
                bad.append((handle, "0 posts"))

        browser.close()

    print(f"\n{'='*65}")
    print(f"✓ 有帖子: {len(good)} 个")
    for handle, kind, cat, count in sorted(good, key=lambda x: -x[3]):
        print(f"   {handle:<30} {kind:<12} {cat:<12} {count} 帖子")
    print(f"\n✗ 无帖子/不存在: {len(bad)} 个")
    for handle, reason in bad:
        print(f"   {handle:<30} {reason}")
    print("="*65 + "\n")

if __name__ == "__main__":
    main()
