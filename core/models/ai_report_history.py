"""
AI报告历史记录模型
用于保存用户每次生成的AI报告
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from core.models.base import Base
import datetime


class AIReportHistory(Base):
    """AI报告历史记录表"""
    __tablename__ = 'ai_report_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    
    # 数据来源相关
    source = Column(String(20), nullable=False, default='all')
    mp_id = Column(String(100), nullable=True)
    mp_name = Column(String(200), nullable=True)
    folder_id = Column(Integer, nullable=True)
    folder_name = Column(String(200), nullable=True)
    
    # 筛选条件
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=False)
    keyword = Column(String(200), nullable=True)
    prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    
    # 报告内容
    report_content = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=datetime.datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'source': self.source,
            'mp_id': self.mp_id,
            'mp_name': self.mp_name,
            'folder_id': self.folder_id,
            'folder_name': self.folder_name,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'keyword': self.keyword,
            'prompt': self.prompt,
            'model': self.model,
            'report_content': self.report_content,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }