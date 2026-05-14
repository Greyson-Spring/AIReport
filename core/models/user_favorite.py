"""
用户文章收藏关联表
记录每个用户对文章的收藏关系。
文章本身是共享资源，每个用户可以独立收藏/取消收藏。
"""
from sqlalchemy import Column, Integer, String, DateTime
from core.models.base import Base
import datetime


class UserFavorite(Base):
    """
    用户收藏记录：user_id + article_id 构成唯一收藏关系。
    - 收藏：添加一条记录
    - 取消收藏：删除对应记录
    """
    __tablename__ = 'user_favorites'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(String(100), nullable=False, index=True, comment='用户ID')
    article_id = Column(String(255), nullable=False, index=True, comment='文章ID，关联 articles.id')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='收藏时间')
