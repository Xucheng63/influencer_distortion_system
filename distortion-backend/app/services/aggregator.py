"""
app/services/aggregator.py  —  90天滑动窗口聚合，计算五维度 + consistency score

五维度（v2）：
  significance_inflation  (inflate)
  anxiety_manufacturing   (anxiety)
  novelty_claim           (novelty)
  loaded_language         (loaded_language) ← 新增
  temporal_distortion     (temporal)

CS（一致性分数）单独计算并写入数据库，不再参与 DI 公式。
"""
from __future__ import annotations
import json, statistics
from datetime import datetime, timedelta
from collections import defaultdict

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.db import Post, DistortionProfile, Account
from app.services.classifier import compute_distortion_index

WINDOW_DAYS = 365


async def aggregate_profile(account_id: int, session: AsyncSession) -> DistortionProfile:
    """
    计算账号的最新 DistortionProfile 并写入数据库。
    """
    cutoff = datetime.utcnow() - timedelta(days=WINDOW_DAYS)

    # 取窗口内所有帖子
    stmt = select(Post).where(
        Post.account_id == account_id,
        Post.posted_at >= cutoff,
    )
    result = await session.exec(stmt)
    posts = result.all()

    total = len(posts)
    if total == 0:
        return await _save_empty(account_id, session)

    # ── 五维度比率 ──────────────────────────────────────────────────
    counters = defaultdict(int)
    deleted_count = 0
    temporal_mismatch_count = 0

    for p in posts:
        types = json.loads(p.distortion_types) if p.distortion_types else []
        for t in types:
            counters[t] += 1
        if p.deleted:
            deleted_count += 1
        # 时间失真：链接原始发布日早于帖子发布 30 天以上
        if p.linked_published_at and p.posted_at:
            delta = (p.posted_at - p.linked_published_at).days
            if delta > 30:
                temporal_mismatch_count += 1

    inflation_rate       = counters["inflate"] / total
    anxiety_rate         = counters["anxiety"] / total
    novelty_rate         = counters["novelty"] / total
    loaded_language_rate = counters["loaded_language"] / total   # ← 新增
    # 时间失真率取规则检测 + 链接日期比对中较大者
    temporal_rate        = max(counters["temporal"] / total,
                               temporal_mismatch_count / total)
    deletion_rate        = deleted_count / total

    # ── Consistency score（独立置信度指标，不参与 DI 公式） ─────────
    # 将帖子按周分桶，计算每周失真率，取标准差倒数归一化
    # CS < 0.30 时该账号标注低置信度，不参与跨平台比较
    weekly: dict[int, list[bool]] = defaultdict(list)
    for p in posts:
        week = (datetime.utcnow() - p.posted_at).days // 7
        types = json.loads(p.distortion_types) if p.distortion_types else []
        weekly[week].append(bool(types))

    week_rates = [sum(v) / len(v) for v in weekly.values() if v]
    if len(week_rates) >= 2:
        std = statistics.stdev(week_rates)
        # std=0 → 完全一致 → score=1.0；std=0.5 → score≈0
        consistency = max(0.0, 1.0 - std * 2)
    elif len(week_rates) == 1:
        consistency = 0.5   # 数据不足，中立值
    else:
        consistency = 0.0

    profile_data = {
        "significance_inflation_rate": round(inflation_rate, 4),
        "anxiety_manufacturing_rate":  round(anxiety_rate, 4),
        "novelty_claim_rate":          round(novelty_rate, 4),
        "loaded_language_rate":        round(loaded_language_rate, 4),   # ← 新增
        "temporal_distortion_rate":    round(temporal_rate, 4),
        "consistency_score":           round(consistency, 4),   # 保留字段，作为独立置信度指标
    }

    distortion_index = compute_distortion_index(profile_data)

    profile = DistortionProfile(
        account_id=account_id,
        window_days=WINDOW_DAYS,
        total_posts_analyzed=total,
        deleted_count=deleted_count,
        deletion_rate=round(deletion_rate, 4),
        distortion_index=distortion_index,
        **profile_data,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def _save_empty(account_id: int, session: AsyncSession) -> DistortionProfile:
    p = DistortionProfile(account_id=account_id)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p
