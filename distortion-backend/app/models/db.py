from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    handle: str = Field(index=True, unique=True)
    display_name: str = ""
    platform: str = "twitter"
    domain: str = ""
    followers: int = 0
    tracked_since: datetime = Field(default_factory=datetime.utcnow)
    last_crawled: Optional[datetime] = None


class Post(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    platform_id: str = Field(index=True)
    content: str
    posted_at: datetime
    crawled_at: datetime = Field(default_factory=datetime.utcnow)
    deleted: bool = False
    deleted_detected_at: Optional[datetime] = None
    linked_url: Optional[str] = None
    linked_published_at: Optional[datetime] = None
    distortion_types: str = ""
    confidence: float = 0.0
    classification_method: str = ""
    annotation_label: Optional[str] = None
    trigger_signals: str = ""


class DistortionProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    window_days: int = 90
    significance_inflation_rate: float = 0.0
    anxiety_manufacturing_rate: float = 0.0
    novelty_claim_rate: float = 0.0
    loaded_language_rate: float = 0.0   # ← 新增 LL 维度字段
    temporal_distortion_rate: float = 0.0
    consistency_score: float = 0.0      # 独立置信度指标，不参与 DI 公式
    distortion_index: int = 0
    deletion_rate: float = 0.0
    deleted_count: int = 0
    total_posts_analyzed: int = 0


class BehaviorLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_handle: str
    response: str
    logged_at: datetime = Field(default_factory=datetime.utcnow)
