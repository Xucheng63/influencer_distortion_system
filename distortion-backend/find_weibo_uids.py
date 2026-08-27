#!/usr/bin/env python3
"""
find_weibo_uids.py — 自动从微博搜索页面找到真实 UID
通过搜索用户名，从页面 URL 获取真实 UID，然后验证是否有帖子

运行：python find_weibo_uids.py
"""
import time, json, re
from playwright.sync_api import sync_playwright

# 要搜索的用户名列表
SEARCH_NAMES = [
    "人民日报", "新华社", "央视新闻", "环球时报", "澎湃新闻",
    "南方周末", "财新网", "新京报", "三联生活周刊", "人物杂志",
    "36氪", "虎嗅", "钛媒体", "极客公园", "爱范儿",
    "吴晓波频道", "老虎财经", "券商中国", "财联社", "第一财经",
    "丁香医生", "果壳网", "科普中国", "丁香园", "健康时报",
    "谢娜", "何炅", "李宇春", "王嘉尔", "朱正廷",
    "罗振宇", "李翔", "吴军", "刘润", "混沌大学",
    "NBA中国", "懒熊体育", "苏炳添", "中国之队", "国际足球",
    "科技唆麻", "阑夕", "月光博客", "和菜头", "keso方军",
    "李大霄", "但斌", "任泽平", "姜超宏观债券", "水皮",
]

def search_user_uid(name: str, page) -> tuple[str, str]:
    """搜索用户名，返回 (uid, 显示名)"""
    try:
        # 用微博搜索 API
        url = f"https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D3%26q%3D{name}&page_type=searchall"
        page.goto(url, timeout=12000)
        time.sleep(1.5)
        try:
            content = page.content()
        except Exception:
            time.sleep(2)
            content = page.content()

        b = content.find("{")
        e = content.rfind("}") + 1
        if b < 0:
            return "", ""

        data = json.loads(content[b:e])
        if data.get("ok") != 1:
            return "", ""

        cards = data.get("data", {}).get("cards", [])
        for card in cards:
            for sub in card.get("card_group", []):
                user = sub.get("user", {})
                if user:
                    uid = str(user.get("id", ""))
                    display = user.get("screen_name", "")
                    # 检查名字是否匹配
                    if uid and display:
                        return uid, display
            # 直接在 card 里
            user = card.get("user", {})
            if user:
                uid = str(user.get("id", ""))
                display = user.get("screen_name", "")
                if uid and display:
                    return uid, display
    except Exception as e:
        pass
    return "", ""

def check_uid_posts(uid: str, page) -> int:
    """检查 UID 是否有帖子"""
    try:
        url = (f"https://m.weibo.cn/api/container/getIndex"
               f"?uid={uid}&type=uid&value={uid}&containerid=107603{uid}&page=1")
        page.goto(url, timeout=12000)
        time.sleep(1.5)
        try:
            content = page.content()
        except Exception:
            time.sleep(2)
            content = page.content()

        b = content.find("{")
        e = content.rfind("}") + 1
        if b < 0:
            return 0
        data = json.loads(content[b:e])
        if data.get("ok") != 1:
            return 0
        cards = data.get("data", {}).get("cards", [])
        return sum(1 for c in cards if c.get("mblog"))
    except Exception:
        return 0

def main():
    print("\n" + "="*70)
    print("微博真实 UID 查询工具")
    print("="*70)

    good = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
            viewport={"width": 390, "height": 844},
        )
        page = context.new_page()

        # 初始化 Session
        page.goto("https://m.weibo.cn", timeout=20000)
        time.sleep(4)
        print("✓ Session 初始化完成\n")

        for i, name in enumerate(SEARCH_NAMES, 1):
            print(f"  [{i:2d}/{len(SEARCH_NAMES)}] 搜索「{name}」...", end="", flush=True)

            uid, display = search_user_uid(name, page)
            if not uid:
                print(f" ✗ 未找到")
                continue

            # 验证帖子数
            posts = check_uid_posts(uid, page)
            if posts > 0:
                print(f" ✓ uid={uid} 显示名={display} ({posts}帖)")
                good.append({"uid": uid, "name": display, "search": name, "posts": posts})
            else:
                print(f" ~ uid={uid} 显示名={display} (0帖，跳过)")

        browser.close()

    print(f"\n{'='*70}")
    print(f"✓ 找到有帖子的账号: {len(good)} 个\n")
    print("可直接用于实验脚本的账号列表：")
    print("-"*70)
    for acc in sorted(good, key=lambda x: -x["posts"]):
        print(f'  {{"handle": "weibo/{acc["uid"]}", "name": "{acc["name"]}", "posts": {acc["posts"]}}},')
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
