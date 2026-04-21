from .base import Base, Column, Integer, String, DateTime, Text
from datetime import datetime


class AISummaryTask(Base):
    from_attributes = True
    __tablename__ = 'ai_summary_tasks'

    id = Column(String(255), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=True)
    mps_id = Column(Text, nullable=False)  # JSON array of subscription IDs
    cron_exp = Column(String(100), nullable=False)
    status = Column(Integer, default=1)  # 1=启用 0=禁用
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
