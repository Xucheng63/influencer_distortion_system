#!/usr/bin/env python3
"""
test_reddit_users.py — 先用 Playwright 测试30个用户是否有帖子，再运行正式实验

运行：python test_reddit_users.py
"""
import time, asyncio
from playwright.sync_api import sync_playwright

CANDIDATE_USERS = [
    # 已知高活跃 — 内容创作者/科普类
    "u/Gallowboob",
    "u/mvea",
    "u/madazzahatter",
    "u/Shitty_Watercolour",
    "u/AWildSketchAppeared",
    "u/IAmA_Nurse_AMA",
    "u/Fluffee",
    "u/GovSchwarzenegger",
    "u/iamthatis",
    "u/Zelda_IRL",
    # 新闻/政治类
    "u/PoliticalHumor",
    "u/SchuminWeb",
    "u/brokentoaster_",
    "u/FoxNewsAutobot",
    "u/HuffPostAutobot",
    "u/AP_NewsAutobot",
    "u/johncena_actual",
    "u/Ambrosiana",
    "u/Journeymannn",
    "u/Gauntlet_of_Might",
    # 科技/AI 类
    "u/Ketamine4Depression",
    "u/Portarossa",
    "u/TalesFromTheFrontDesk",
    "u/BootlegHoops",
    "u/OctaviaBlake_",
    "u/Sumelar",
    "u/HardFacts_Liam",
    "u/vaultteam6",
    "u/Lets_talk_about_this_",
    "u/georgewbush_ebooks",
]

def check_user(username: str) -> tuple[int, str]:
    """用 Playwright 检查用户是否有帖子，返回 (帖子数, 状态说明)"""
    name = username.lstrip("u/")
    url = f"https://www.reddit.com/user/{name}/submitted/?sort=new"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            result = page.evaluate("""
                () => {
                    // 检查是否被封禁或不存在
                    const body = document.body.innerText || '';
                    if (body.includes('page not found') || body.includes('banned') ||
                        body.includes('suspended') || body.includes('404')) {
                        return {count: -1, reason: 'not found/banned'};
                    }
                    // 计算帖子数
                    const posts = document.querySelectorAll('shreddit-post');
                    const links = document.querySelectorAll('a[data-click-id="body"][href*="/comments/"]');
                    const count = Math.max(posts.length, links.length);
                    return {count, reason: 'ok'};
                }
            """)
            count = result.get("count", 0)
            reason = result.get("reason", "")
            return count, reason
        except Exception as e:
            return 0, str(e)[:40]
        finally:
            browser.close()

def main():
    print("\n" + "="*65)
    print("Reddit 用户预检测 — 验证30个候选用户是否有帖子")
    print("="*65)

    good = []
    bad = []

    for i, user in enumerate(CANDIDATE_USERS, 1):
        print(f"  [{i:2d}/30] {user:<35}", end="", flush=True)
        count, reason = check_user(user)
        if count > 0:
            print(f"✓ {count} 帖子")
            good.append((user, count))
        elif count == -1:
            print(f"✗ {reason}")
            bad.append((user, reason))
        else:
            print(f"~ 0 帖子 ({reason})")
            bad.append((user, "0 posts"))

    print(f"\n{'='*65}")
    print(f"✓ 有帖子: {len(good)} 个")
    for u, c in sorted(good, key=lambda x: -x[1]):
        print(f"   {u:<35} {c} 帖子")
    print(f"\n✗ 无帖子/不存在: {len(bad)} 个")
    for u, r in bad:
        print(f"   {u:<35} {r}")
    print("="*65 + "\n")

if __name__ == "__main__":
    main()
