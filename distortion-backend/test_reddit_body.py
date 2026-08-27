#!/usr/bin/env python3
"""
test_reddit_body.py — 测试带正文抓取的 Reddit scraper
选 r/wallstreetbets 验证 title + selftext 是否都能抓到

运行：python test_reddit_body.py
"""
import time, json, hashlib
from playwright.sync_api import sync_playwright
from datetime import datetime

TEST_SUBREDDIT = "wallstreetbets"

def test():
    print(f"\n{'='*60}")
    print(f"测试带正文抓取 — r/{TEST_SUBREDDIT}")
    print("="*60)

    posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        try:
            # Step 1: 抓帖子列表（只抓5个测试）
            print(f"\nStep 1: 抓取帖子列表...")
            url = f"https://www.reddit.com/r/{TEST_SUBREDDIT}/top/?t=month"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)

            raw = page.evaluate("""
                () => {
                    const posts = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('shreddit-post')) {
                        const title = el.getAttribute('post-title') || '';
                        const permalink = el.getAttribute('permalink') || '';
                        if (!title || !permalink) continue;
                        const url = permalink.startsWith('/') ?
                            'https://www.reddit.com' + permalink : permalink;
                        if (seen.has(url)) continue;
                        seen.add(url);
                        posts.push({ title, url,
                            date: el.getAttribute('created-timestamp') || '' });
                        if (posts.length >= 5) break;
                    }
                    return posts;
                }
            """)
            print(f"  抓到 {len(raw or [])} 个帖子标题")

            # Step 2: 逐个访问 .json 抓正文
            print(f"\nStep 2: 抓取每个帖子的正文...")
            for i, item in enumerate(raw or [], 1):
                title = item.get("title", "").strip()
                post_url = item.get("url", "")
                selftext = ""

                if post_url:
                    try:
                        page.goto(post_url + ".json", timeout=8000)
                        time.sleep(1)
                        body = page.evaluate("() => document.body.innerText")
                        data = json.loads(body)
                        selftext = data[0]["data"]["children"][0]["data"].get("selftext", "") or ""
                        selftext = selftext.strip()
                        if selftext in ("[removed]", "[deleted]"):
                            selftext = ""
                    except Exception as e:
                        selftext = ""
                        print(f"  [{i}] 正文抓取失败: {e}")

                content = f"{title}. {selftext[:300]}" if selftext else title

                print(f"\n  [{i}] 标题: {title[:60]}")
                print(f"       正文: {selftext[:80] if selftext else '（无正文，链接帖）'}")
                print(f"       合并内容长度: {len(content)} 字符")

                posts.append({
                    "platform_id": hashlib.md5(title.encode()).hexdigest()[:12],
                    "content": content[:500],
                    "selftext_len": len(selftext),
                    "has_body": bool(selftext),
                })

        except Exception as e:
            print(f"✗ 错误: {e}")
        finally:
            browser.close()

    # 统计
    print(f"\n{'='*60}")
    print(f"结果统计:")
    print(f"  总帖子: {len(posts)}")
    print(f"  有正文: {sum(1 for p in posts if p['has_body'])} 个")
    print(f"  仅标题: {sum(1 for p in posts if not p['has_body'])} 个（链接帖，正常现象）")
    avg_len = sum(len(p['content']) for p in posts) / len(posts) if posts else 0
    print(f"  平均内容长度: {round(avg_len)} 字符（之前纯标题约50字符）")
    print("="*60 + "\n")

if __name__ == "__main__":
    test()
