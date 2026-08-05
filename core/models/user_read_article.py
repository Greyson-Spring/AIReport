"""
用户文章阅读状态关联表
记录每个用户对文章的已读状态。
文章本身是共享资源，每个用户可以独立标记已读/未读。
"""
from sqlalchemy import Column, Integer, String, DateTime
from core.models.base import Base
import datetime


class UserReadArticle(Base):
    """
    用户阅读记录：user_id + article_id 构成唯一阅读关系。
    - 有记录 = 已读
    - 无记录 = 未读
    """
    __tablename__ = 'user_read_articles'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(String(100), nullable=False, index=True, comment='用户ID')
    article_id = Column(String(255), nullable=False, index=True, comment='文章ID，关联 articles.id')
    read_at = Column(DateTime, default=datetime.datetime.now, comment='阅读时间')
