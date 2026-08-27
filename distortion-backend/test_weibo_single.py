#!/usr/bin/env python3
"""
test_weibo_single.py v4 — 用 page 参数翻页
"""
import time, json, re
from playwright.sync_api import sync_playwright

TEST_UID  = "2803301701"
TEST_NAME = "人民日报"

def clean_text(raw: str) -> str:
    raw = raw.replace('&lt;','<').replace('&gt;','>').replace('&amp;','&')
    raw = raw.replace('&quot;','"').replace('&#39;',"'").replace('&nbsp;',' ')
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw

def test_weibo():
    print("\n" + "="*60)
    print(f"微博抓取测试 v4 — @{TEST_NAME}")
    print("="*60)

    posts = []
    seen = set()
    containerid = f"107603{TEST_UID}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
            viewport={"width": 390, "height": 844},
        )
        page = context.new_page()
        try:
            # 初始化 Session
            page.goto("https://m.weibo.cn", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            print("\n✓ Session 初始化完成")

            # 用 page 参数翻页
            print(f"\n开始抓取（目标50条）...")
            for page_num in range(1, 8):
                url = (
                    f"https://m.weibo.cn/api/container/getIndex"
                    f"?uid={TEST_UID}&type=uid&value={TEST_UID}"
                    f"&containerid={containerid}&page={page_num}"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)

                content = page.content()
                b = content.find("{")
                e = content.rfind("}") + 1
                if b < 0:
                    break
                try:
                    data = json.loads(content[b:e])
                except Exception:
                    break

                if data.get("ok") != 1:
                    print(f"  页面{page_num}: 失败")
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
                    text = clean_text(mblog.get("text", ""))
                    if not text or len(text) < 3:
                        continue
                    posts.append({
                        "id": mid,
                        "content": text[:500],
                        "created_at": mblog.get("created_at", ""),
                        "likes": mblog.get("attitudes_count", 0),
                        "comments": mblog.get("comments_count", 0),
                        "reposts": mblog.get("reposts_count", 0),
                    })
                    new_count += 1

                print(f"  页面{page_num}: +{new_count}条 (共{len(posts)}条)")
                if len(posts) >= 50:
                    break
                if new_count == 0:
                    print("  没有新帖子，停止")
                    break

        except Exception as e:
            print(f"✗ 错误: {e}")
        finally:
            browser.close()

    print(f"\n结果：共 {len(posts)} 条帖子")
    print("\n前5条:")
    for i, p in enumerate(posts[:5], 1):
        print(f"  {i}. {p['content'][:80]}")
        print(f"     👍{p['likes']} 💬{p['comments']} 🔁{p['reposts']}")

    print("\n" + "="*60)
    print(f"{'✓ 可接入正式系统' if len(posts) >= 30 else '~ 帖子数偏少，但基本可用'} — {len(posts)} 条")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_weibo()
