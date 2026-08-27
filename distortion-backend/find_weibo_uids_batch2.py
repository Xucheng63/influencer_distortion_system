#!/usr/bin/env python3
"""
find_weibo_uids_batch2.py — 自动搜索第二批微博用户真实 UID
搜索50个候选用户名，验证是否有帖子，输出可直接用的账号列表

运行：python find_weibo_uids_batch2.py
"""
import time, json
from playwright.sync_api import sync_playwright

# 50个候选搜索名（覆盖多类别）
SEARCH_NAMES = [
    # 财经/股票
    "华尔街见闻", "第一财经资讯", "证券时报", "上海证券报",
    "中国证券网", "新浪财经", "网易财经", "腾讯财经",
    "东方财富网", "同花顺财经",
    # 科技媒体
    "科技日报", "中关村在线", "电脑报", "IT之家",
    "快科技", "驱动之家", "雷科技", "数字尾巴",
    "品玩", "GeekPark极客公园",
    # 新闻媒体
    "新华网", "中国日报", "参考消息", "观察者网",
    "界面新闻", "财经杂志", "经济观察报", "21世纪经济报道",
    "第一财经日报", "南方都市报",
    # AI/科技大V
    "爱范儿ifanr", "少数派sspai", "机器之心", "量子位",
    "新智元", "雷锋网", "AI科技评论", "深度学习研究所",
    "智东西", "硅星人",
    # 生活/文化
    "丁香生活研究所", "果壳科学", "博物杂志",
    "中国国家地理", "星球研究所", "地球知识局",
    "九行Travel", "一条", "GQ中国", "时尚COSMO",
    # 体育
    "中国篮球NBA", "懒熊体育Plus", "直播吧",
    "虎扑体育", "足球报", "体育画报中国版",
    "中超联赛", "中国足球协会", "CCTV5", "中国男篮",
]

def search_and_check(name: str, page) -> tuple[str, str, int]:
    """搜索用户名，返回 (uid, 显示名, 帖子数)"""
    try:
        url = (f"https://m.weibo.cn/api/container/getIndex"
               f"?containerid=100103type%3D3%26q%3D{name}&page_type=searchall")
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
            return "", "", 0
        data = json.loads(content[b:e])
        if data.get("ok") != 1:
            return "", "", 0

        # 找第一个用户结果
        uid, display = "", ""
        for card in data.get("data", {}).get("cards", []):
            for sub in card.get("card_group", []):
                user = sub.get("user", {})
                if user and user.get("id"):
                    uid = str(user["id"])
                    display = user.get("screen_name", "")
                    break
            if uid:
                break
            user = card.get("user", {})
            if user and user.get("id"):
                uid = str(user["id"])
                display = user.get("screen_name", "")
                break

        if not uid:
            return "", "", 0

        # 验证帖子数
        api_url = (f"https://m.weibo.cn/api/container/getIndex"
                   f"?uid={uid}&type=uid&value={uid}&containerid=107603{uid}&page=1")
        page.goto(api_url, timeout=12000)
        time.sleep(1.5)
        try:
            content2 = page.content()
        except Exception:
            time.sleep(2)
            content2 = page.content()

        b2 = content2.find("{")
        e2 = content2.rfind("}") + 1
        if b2 < 0:
            return uid, display, 0
        data2 = json.loads(content2[b2:e2])
        if data2.get("ok") != 1:
            return uid, display, 0

        cards2 = data2.get("data", {}).get("cards", [])
        posts = sum(1 for c in cards2 if c.get("mblog"))
        return uid, display, posts

    except Exception as e:
        return "", "", 0

def main():
    print("\n" + "="*70)
    print("微博 UID 自动查询 — 第二批")
    print(f"候选账号: {len(SEARCH_NAMES)} 个")
    print("="*70)

    good = []
    bad = []

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
            uid, display, posts = search_and_check(name, page)

            if posts > 0:
                print(f" ✓ uid={uid} 显示={display} ({posts}帖)")
                good.append({"uid": uid, "display": display, "search": name, "posts": posts})
            elif uid:
                print(f" ~ uid={uid} 显示={display} (0帖，跳过)")
                bad.append((name, uid, "0帖"))
            else:
                print(f" ✗ 未找到")
                bad.append((name, "", "未找到"))

        browser.close()

    print(f"\n{'='*70}")
    print(f"✓ 找到有帖子的账号: {len(good)} 个\n")
    print("账号列表（直接用于实验脚本）：")
    print("-"*70)
    for acc in sorted(good, key=lambda x: -x["posts"]):
        print(f'  {{"handle": "weibo/{acc["uid"]}", "name": "{acc["display"]}", "posts": {acc["posts"]}}},')

    print(f"\n✗ 失败: {len(bad)} 个")
    for name, uid, reason in bad:
        print(f"  {name}: {reason}")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
