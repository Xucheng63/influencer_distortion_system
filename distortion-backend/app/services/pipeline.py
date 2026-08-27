"""
app/services/pipeline.py  —  完整五步分析流水线
  Step 1: 内容采集 (scraper)
  Step 2: 关键词检测 (classifier - rules)
  Step 3: LLM 二次分类 (classifier - llm, 可选)
  Step 4: 时间交叉验证 (scraper.fetch_url_publish_date)
  Step 5: 档案聚合 (aggregator)
"""
from __future__ import annotations
import json
from datetime import datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.db import Account, Post, DistortionProfile
from app.services import scraper, classifier, aggregator


def detect_platform(handle: str) -> str:
    """根据 handle 路由规则推断真实平台展示名（供前端显示）。"""
    h = handle.lstrip("@").lower()
    if scraper._is_weibo(h):
        return "Weibo"
    if scraper._is_reddit(h):
        return "Reddit"
    if h in scraper.FEED_MAP:
        return {"youtube": "YouTube", "bluesky": "Bluesky", "rss": "RSS"}.get(
            scraper.FEED_MAP[h].get("type"), "RSS"
        )
    if scraper._is_bluesky(h):
        return "Bluesky"
    return "Twitter/X"


async def run(handle: str, session: AsyncSession) -> dict:
    """
    执行完整流水线，返回最终 profile dict 供 API 使用。
    handle: 不含 @
    """
    handle = handle.lstrip("@").lower()

    # ── 获取或创建账号记录 ────────────────────────────────────────
    stmt = select(Account).where(Account.handle == handle)
    result = await session.exec(stmt)
    account = result.first()

    if not account:
        info = await scraper.fetch_profile_info(handle)
        account = Account(
            handle=handle,
            display_name=info.get("display_name", handle),
            followers=info.get("followers", 0),
            platform=detect_platform(handle),
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
    else:
        # 回填/纠正已有账号的平台字段（历史数据默认都是 "twitter"）
        account.platform = detect_platform(handle)
        # 回填粉丝数：历史账号常存为 0，重新分析时尝试补齐
        if not account.followers:
            info = await scraper.fetch_profile_info(handle)
            if info.get("followers"):
                account.followers = info["followers"]
            if info.get("display_name"):
                account.display_name = info["display_name"]

    # ── Step 1: 抓取帖子 ──────────────────────────────────────────
    raw_posts = await scraper.fetch_recent_posts(handle, max_pages=3)

    # 已入库的 platform_id 集合（避免重复）
    existing_stmt = select(Post.platform_id).where(Post.account_id == account.id)
    existing_result = await session.exec(existing_stmt)
    existing_ids = set(existing_result.all())

    new_posts: list[Post] = []
    for raw in raw_posts:
        if raw["platform_id"] in existing_ids:
            continue

        # 清除孤立代理码点（截断的 emoji 半个高位代理），否则入库/导出(ensure_ascii=False)
        # 及发往 OpenAI 的请求都会因未配对代理而报错
        raw["content"] = classifier.strip_lone_surrogates(raw["content"])

        # ── Step 2 & 3: 分类 ──────────────────────────────────────
        cls = await classifier.classify(raw["content"])

        # ── Step 4: 时间交叉验证 ──────────────────────────────────
        linked_pub_date = None
        if raw.get("linked_url"):
            linked_pub_date = await scraper.fetch_url_publish_date(raw["linked_url"])

        post = Post(
            account_id=account.id,
            platform_id=raw["platform_id"],
            content=raw["content"],
            posted_at=raw["posted_at"],
            linked_url=raw.get("linked_url"),
            linked_published_at=linked_pub_date,
            distortion_types=json.dumps(cls["types"]),
            confidence=cls["confidence"],
            classification_method=cls["method"],
            trigger_signals=json.dumps(cls.get("signals", [])),
        )
        session.add(post)
        new_posts.append(post)

    # 检测已存在帖子是否被删（再次抓取时消失 → 标记删除）
    if existing_ids:
        current_ids = {p["platform_id"] for p in raw_posts}
        deleted_ids = existing_ids - current_ids
        if deleted_ids:
            del_stmt = select(Post).where(
                Post.account_id == account.id,
                Post.platform_id.in_(list(deleted_ids)),
                Post.deleted == False,
            )
            del_result = await session.exec(del_stmt)
            for p in del_result.all():
                p.deleted = True
                p.deleted_detected_at = datetime.utcnow()

    account.last_crawled = datetime.utcnow()
    await session.commit()

    # ── Step 5: 聚合档案 ──────────────────────────────────────────
    profile = await aggregator.aggregate_profile(account.id, session)

    # ── 组装 API 响应 ──────────────────────────────────────────────
    return _build_response(account, profile, new_posts)


def _build_response(account: Account, profile: DistortionProfile, new_posts: list[Post]) -> dict:
    return {
        "account": {
            "handle": account.handle,
            "display_name": account.display_name,
            "platform": account.platform,
            "followers": account.followers,
            "last_crawled": account.last_crawled.isoformat() if account.last_crawled else None,
        },
        "profile": {
            "distortion_index": profile.distortion_index,
            "significance_inflation_rate": profile.significance_inflation_rate,
            "anxiety_manufacturing_rate": profile.anxiety_manufacturing_rate,
            "novelty_claim_rate": profile.novelty_claim_rate,
            "loaded_language_rate": profile.loaded_language_rate,   # ← LL 维度
            "temporal_distortion_rate": profile.temporal_distortion_rate,
            "consistency_score": profile.consistency_score,         # 独立置信度指标
            "deletion_rate": profile.deletion_rate,
            "deleted_count": profile.deleted_count,
            "total_posts_analyzed": profile.total_posts_analyzed,
            "window_days": profile.window_days,
            "computed_at": profile.computed_at.isoformat(),
        },
        "new_posts_crawled": len(new_posts),
    }
