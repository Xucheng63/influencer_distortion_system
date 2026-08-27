"""
app/services/scheduler.py  —  每日定时刷新 watchlist 账号

用 APScheduler 的 AsyncIOScheduler，在 FastAPI 事件循环上每天 06:00 UTC
逐个重新分析固定 watchlist，保持数据新鲜。
"""
from __future__ import annotations
import os
import traceback

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import AsyncSessionLocal
from app.services import pipeline

# 本项目未配置 logging，自定义 logger 的 INFO 不会进 stdout；沿用 scraper 的
# print() 约定，保证定时任务的日志能出现在 Render 日志里（flush 确保及时刷新）。
def _log(msg: str) -> None:
    print(f"[scheduler] {msg}", flush=True)

# 每日刷新的固定 watchlist（与前端默认 watchlist 保持一致）
WATCHLIST_HANDLES = [
    "pfrazee.com",
    "simonwillison",
    "lexfridman",
    "r/MachineLearning",
    "weibo/2803301701",
]

# 触发时间：每天 06:00 UTC
REFRESH_HOUR = 6
REFRESH_MINUTE = 0

_scheduler: AsyncIOScheduler | None = None


async def refresh_watchlist() -> None:
    """
    逐个重新分析 watchlist 账号。
    - 串行执行：一次只跑一个，避免同时启动多个 Chromium。
    - 复用 analyze 端点的并发信号量：与用户触发的分析共用同一把锁，
      保证定时任务不会和在线请求并发抓取而把实例打爆。
    - 单个账号失败不影响其余账号。
    """
    # 延迟导入，避免 services 层在模块加载期反向依赖 api 层（防循环导入）。
    from app.api.routes import _analyze_semaphore

    _log(f"daily watchlist refresh start ({len(WATCHLIST_HANDLES)} accounts)")
    ok = 0
    for handle in WATCHLIST_HANDLES:
        try:
            async with _analyze_semaphore:
                async with AsyncSessionLocal() as session:
                    result = await pipeline.run(handle, session)
            ok += 1
            _log(f"refreshed {handle} — {result.get('new_posts_crawled')} new posts")
        except Exception:
            _log(f"failed to refresh {handle}:\n{traceback.format_exc()}")
    _log(f"daily watchlist refresh done ({ok}/{len(WATCHLIST_HANDLES)} ok)")


def start_scheduler() -> AsyncIOScheduler | None:
    """在应用启动时调用（lifespan 内）。可用 ENABLE_SCHEDULER=0 关闭。"""
    global _scheduler
    if os.getenv("ENABLE_SCHEDULER", "1").strip().lower() in ("0", "false", "no", ""):
        _log("disabled via ENABLE_SCHEDULER")
        return None
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        refresh_watchlist,
        trigger=CronTrigger(hour=REFRESH_HOUR, minute=REFRESH_MINUTE, timezone="UTC"),
        id="daily_watchlist_refresh",
        replace_existing=True,
        coalesce=True,          # 错过多次只补跑一次
        max_instances=1,        # 不允许上一轮没跑完又启动下一轮
        misfire_grace_time=3600,
    )
    _scheduler.start()
    _log(f"started — daily watchlist refresh at {REFRESH_HOUR:02d}:{REFRESH_MINUTE:02d} UTC")
    return _scheduler


def shutdown_scheduler() -> None:
    """在应用关闭时调用（lifespan 内）。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _log("stopped")
    _scheduler = None
