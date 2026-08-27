"""
app/api/routes.py  —  REST API 端点
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from app.core.database import get_session
from app.models.db import Account, Post, DistortionProfile, BehaviorLog
from app.services import pipeline, aggregator, classifier

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ── 分析账号 ──────────────────────────────────────────────────────────────────

@router.post("/analyze/{handle:path}")
async def analyze_account(handle: str, session: SessionDep):
    """
    触发完整五步流水线分析。
    前端调用: POST /api/analyze/techguruglobal
    """
    try:
        result = await pipeline.run(handle, session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 账号 Profile ──────────────────────────────────────────────────────────────

@router.get("/profile/{handle:path}")
async def get_profile(handle: str, session: SessionDep):
    """
    返回已缓存的最新档案（不触发重新抓取）。
    """
    handle = handle.lstrip("@").lower()
    stmt = select(Account).where(Account.handle == handle)
    result = await session.exec(stmt)
    account = result.first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found. Run /analyze first.")

    profile_stmt = (
        select(DistortionProfile)
        .where(DistortionProfile.account_id == account.id)
        .order_by(DistortionProfile.computed_at.desc())
    )
    profile_result = await session.exec(profile_stmt)
    profile = profile_result.first()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile computed yet.")

    # 档案陈旧/脏数据检测，任一命中即重新计算。覆盖三种情况：
    #   1) 档案计算后又新增了帖子（窗口内计数变大）；
    #   2) 历史批量导入时保存了空档案（帖子已存在但 total=0）；
    #   3) 历史档案 distortion_index 与自身 rate 字段不自洽（脏数据，
    #      例如 DI=15 但五维 rate 全为 0）；
    #   4) 档案计算之后又重新抓取过帖子（crawled_at 晚于 computed_at）。
    cutoff = datetime.utcnow() - timedelta(days=aggregator.WINDOW_DAYS)
    count_stmt = (
        select(Post.id).where(Post.account_id == account.id, Post.posted_at >= cutoff)
    )
    current_in_window = len((await session.exec(count_stmt)).all())
    expected_di = classifier.compute_distortion_index({
        "significance_inflation_rate": profile.significance_inflation_rate,
        "anxiety_manufacturing_rate":  profile.anxiety_manufacturing_rate,
        "novelty_claim_rate":          profile.novelty_claim_rate,
        "loaded_language_rate":        profile.loaded_language_rate,
        "temporal_distortion_rate":    profile.temporal_distortion_rate,
    })
    recrawled_stmt = (
        select(Post.id)
        .where(Post.account_id == account.id, Post.crawled_at > profile.computed_at)
        .limit(1)
    )
    recrawled = (await session.exec(recrawled_stmt)).first() is not None
    if (current_in_window != profile.total_posts_analyzed
            or expected_di != profile.distortion_index
            or recrawled):
        profile = await aggregator.aggregate_profile(account.id, session)

    return {
        "account": {
            "handle": account.handle,
            "display_name": account.display_name,
            "followers": account.followers,
            "last_crawled": account.last_crawled.isoformat() if account.last_crawled else None,
        },
        "profile": {
            "distortion_index": profile.distortion_index,
            "significance_inflation_rate": profile.significance_inflation_rate,
            "anxiety_manufacturing_rate": profile.anxiety_manufacturing_rate,
            "novelty_claim_rate": profile.novelty_claim_rate,
            "loaded_language_rate": profile.loaded_language_rate,   # ← 新增
            "temporal_distortion_rate": profile.temporal_distortion_rate,
            "consistency_score": profile.consistency_score,         # 独立置信度指标
            "deletion_rate": profile.deletion_rate,
            "deleted_count": profile.deleted_count,
            "total_posts_analyzed": profile.total_posts_analyzed,
            "window_days": profile.window_days,
            "computed_at": profile.computed_at.isoformat(),
        },
    }


# ── 帖子列表 ──────────────────────────────────────────────────────────────────

@router.get("/posts/{handle:path}")
async def get_posts(
    handle: str,
    session: SessionDep,
    limit: int = 20,
    offset: int = 0,
    distortion_type: str | None = None,
    deleted_only: bool = False,
):
    """
    返回账号帖子，支持按失真类型 / 已删帖过滤。
    distortion_type: inflate | anxiety | novelty | loaded_language | temporal
    """
    handle = handle.lstrip("@").lower()
    stmt = select(Account).where(Account.handle == handle)
    acc_result = await session.exec(stmt)
    account = acc_result.first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    posts_stmt = (
        select(Post)
        .where(Post.account_id == account.id)
        .order_by(Post.posted_at.desc())
    )
    if deleted_only:
        posts_stmt = posts_stmt.where(Post.deleted == True)

    all_result = await session.exec(posts_stmt)
    posts = all_result.all()

    # 类型过滤（JSON 字段，在 Python 层过滤）
    if distortion_type:
        posts = [p for p in posts if distortion_type in (json.loads(p.distortion_types) if p.distortion_types else [])]

    total = len(posts)
    page = posts[offset: offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "posts": [
            {
                "id": p.id,
                "platform_id": p.platform_id,
                "content": p.content,
                "posted_at": p.posted_at.isoformat(),
                "deleted": p.deleted,
                "deleted_detected_at": p.deleted_detected_at.isoformat() if p.deleted_detected_at else None,
                "linked_url": p.linked_url,
                "linked_published_at": p.linked_published_at.isoformat() if p.linked_published_at else None,
                "temporal_gap_days": (
                    (p.posted_at - p.linked_published_at).days
                    if p.linked_published_at else None
                ),
                "distortion_types": json.loads(p.distortion_types) if p.distortion_types else [],
                "confidence": p.confidence,
                "classification_method": p.classification_method,
                "trigger_signals": json.loads(p.trigger_signals) if p.trigger_signals else [],
                "annotation_label": p.annotation_label,
            }
            for p in page
        ],
    }


# ── 语言模式分析 ───────────────────────────────────────────────────────────────

# 前端 5 个固定行 (pat-0..4) 对应的失真维度短语标签
_PATTERN_ROWS = [
    ("This changes everything",         "inflate"),
    ("Nobody is talking about this",    "novelty"),
    ("You'll be left behind",           "anxiety"),
    ("I discovered / built this first", "loaded_language"),
    ("Stale content reframed as breaking", "temporal"),
]


@router.get("/patterns/{handle:path}")
async def get_patterns(handle: str, session: SessionDep):
    """
    语言模式分解：五个失真维度的命中率 (供前端条形图) + 真实触发信号 Top-N 及计数。
    """
    handle = handle.lstrip("@").lower()
    account = (await session.exec(select(Account).where(Account.handle == handle))).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found. Run /analyze first.")

    posts = (await session.exec(select(Post).where(Post.account_id == account.id))).all()
    total = len(posts)

    type_counts: Counter = Counter()
    signal_counts: Counter = Counter()
    for p in posts:
        for t in (json.loads(p.distortion_types) if p.distortion_types else []):
            type_counts[t] += 1
        for s in (json.loads(p.trigger_signals) if p.trigger_signals else []):
            signal_counts[s] += 1

    def pct(t: str) -> int:
        return round(type_counts.get(t, 0) / total * 100) if total else 0

    patterns = [
        {"label": label, "type": t, "count": type_counts.get(t, 0), "pct": pct(t)}
        for label, t in _PATTERN_ROWS
    ]
    top_signals = [{"signal": s, "count": c} for s, c in signal_counts.most_common(10)]

    return {
        "handle": handle,
        "total": total,
        "patterns": patterns,
        "top_signals": top_signals,
    }


@router.get("/trend/{handle:path}")
async def get_trend(handle: str, session: SessionDep, weeks: int = 13):
    """
    过去 N 周（默认 13 周 ≈ 90 天）每周失真率趋势。
    返回 {labels, values}，values 为该周含失真类型的帖子占比 (0-100)。
    """
    handle = handle.lstrip("@").lower()
    account = (await session.exec(select(Account).where(Account.handle == handle))).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found. Run /analyze first.")

    posts = (await session.exec(select(Post).where(Post.account_id == account.id))).all()
    now = datetime.utcnow()

    bucket_total = [0] * weeks
    bucket_distorted = [0] * weeks
    for p in posts:
        if not p.posted_at:
            continue
        age_days = (now - p.posted_at).days
        if age_days < 0 or age_days >= weeks * 7:
            continue
        wk = weeks - 1 - (age_days // 7)   # 最新一周 -> 末尾
        if 0 <= wk < weeks:
            bucket_total[wk] += 1
            if (json.loads(p.distortion_types) if p.distortion_types else []):
                bucket_distorted[wk] += 1

    labels = [f"W{i + 1}" for i in range(weeks)]
    values = [
        round(bucket_distorted[i] / bucket_total[i] * 100) if bucket_total[i] else 0
        for i in range(weeks)
    ]
    return {
        "handle": handle,
        "labels": labels,
        "values": values,
        "post_counts": bucket_total,
    }


# ── Watchlist ─────────────────────────────────────────────────────────────────

@router.get("/watchlist")
async def get_watchlist(session: SessionDep):
    """返回所有被追踪账号及其最新档案摘要"""
    stmt = select(Account).order_by(Account.tracked_since.desc())
    result = await session.exec(stmt)
    accounts = result.all()

    rows = []
    for acc in accounts:
        profile_stmt = (
            select(DistortionProfile)
            .where(DistortionProfile.account_id == acc.id)
            .order_by(DistortionProfile.computed_at.desc())
        )
        pr = await session.exec(profile_stmt)
        profile = pr.first()

        risk = "pending"
        index = None
        consistency = None
        if profile:
            index = profile.distortion_index
            consistency = round(profile.consistency_score * 100)
            if index >= 75:
                risk = "high"
            elif index >= 45:
                risk = "moderate"
            else:
                risk = "low"

        rows.append({
            "handle": acc.handle,
            "display_name": acc.display_name,
            "domain": acc.domain,
            "followers": acc.followers,
            "distortion_index": index,
            "consistency_score": consistency,
            "risk": risk,
            "last_crawled": acc.last_crawled.isoformat() if acc.last_crawled else None,
        })
    return {"accounts": rows}


class AddAccountRequest(BaseModel):
    handle: str
    domain: str = ""


@router.post("/watchlist")
async def add_to_watchlist(body: AddAccountRequest, session: SessionDep):
    """添加账号到 watchlist（不触发立即分析）"""
    handle = body.handle.lstrip("@").lower()
    stmt = select(Account).where(Account.handle == handle)
    result = await session.exec(stmt)
    if result.first():
        raise HTTPException(status_code=409, detail="Account already exists.")

    account = Account(handle=handle, domain=body.domain)
    session.add(account)
    await session.commit()
    return {"handle": handle, "status": "added"}


# ── 人工标注 ──────────────────────────────────────────────────────────────────

class AnnotationRequest(BaseModel):
    types: list[str]


@router.post("/annotate/{post_id}")
async def annotate_post(post_id: int, body: AnnotationRequest, session: SessionDep):
    """人工标注覆盖 LLM 分类结果"""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")
    post.annotation_label = json.dumps(body.types)
    post.classification_method = "human"
    await session.commit()
    return {"post_id": post_id, "annotation": body.types}


@router.get("/annotation-queue/{handle:path}")
async def get_annotation_queue(handle: str, session: SessionDep, limit: int = 20):
    """返回置信度 < 0.70 且尚未人工标注的帖子"""
    handle = handle.lstrip("@").lower()
    stmt = select(Account).where(Account.handle == handle)
    acc_result = await session.exec(stmt)
    account = acc_result.first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    posts_stmt = (
        select(Post)
        .where(
            Post.account_id == account.id,
            Post.confidence < 0.70,
            Post.annotation_label == None,
        )
        .order_by(Post.posted_at.desc())
        .limit(limit)
    )
    result = await session.exec(posts_stmt)
    posts = result.all()

    return {
        "pending": len(posts),
        "posts": [
            {
                "id": p.id,
                "content": p.content,
                "posted_at": p.posted_at.isoformat(),
                "confidence": p.confidence,
                "suggested_types": json.loads(p.distortion_types) if p.distortion_types else [],
            }
            for p in posts
        ],
    }


# ── 行为影响追踪 ──────────────────────────────────────────────────────────────

class BehaviorRequest(BaseModel):
    handle: str
    response: str  # less | same | more | unfollow


@router.post("/behavior-log")
async def log_behavior(body: BehaviorRequest, session: SessionDep):
    """记录用户看到 distortion profile 后的行为意向（§5 研究用）"""
    allowed = {"less", "same", "more", "unfollow"}
    if body.response not in allowed:
        raise HTTPException(status_code=400, detail=f"response must be one of {allowed}")
    log = BehaviorLog(handle=body.handle.lstrip("@").lower(), response=body.response)
    session.add(log)
    await session.commit()
    return {"status": "logged"}


@router.get("/behavior-log/summary")
async def behavior_summary(session: SessionDep):
    """返回行为追踪聚合统计"""
    stmt = select(BehaviorLog)
    result = await session.exec(stmt)
    logs = result.all()
    counts: dict[str, int] = {}
    for log in logs:
        counts[log.response] = counts.get(log.response, 0) + 1
    return {"total": len(logs), "breakdown": counts}


# ── 数据导出 ──────────────────────────────────────────────────────────────────

@router.get("/export/{handle}/jsonl")
async def export_jsonl(handle: str, session: SessionDep):
    """导出标注语料（JSONL 格式，Research tab 用）"""
    from fastapi.responses import StreamingResponse
    handle = handle.lstrip("@").lower()
    stmt = select(Account).where(Account.handle == handle)
    acc_result = await session.exec(stmt)
    account = acc_result.first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    posts_stmt = select(Post).where(Post.account_id == account.id).order_by(Post.posted_at.desc())
    result = await session.exec(posts_stmt)
    posts = result.all()

    def generate():
        for p in posts:
            row = {
                "id": p.platform_id,
                "content": p.content,
                "posted_at": p.posted_at.isoformat(),
                "deleted": p.deleted,
                "distortion_types": json.loads(p.distortion_types) if p.distortion_types else [],
                "annotation": json.loads(p.annotation_label) if p.annotation_label else None,
                "confidence": p.confidence,
                "method": p.classification_method,
                "signals": json.loads(p.trigger_signals) if p.trigger_signals else [],
                "linked_url": p.linked_url,
                "linked_published_at": p.linked_published_at.isoformat() if p.linked_published_at else None,
            }
            yield json.dumps(row, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f"attachment; filename={handle}_corpus.jsonl"},
    )
