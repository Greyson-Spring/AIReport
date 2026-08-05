"""
用户文章隐藏关联表
记录每个用户主动隐藏/删除的文章（即用户在自己的视图中删除了某篇文章）。
文章本身是共享资源，不会从数据库真正删除，只是对隐藏的用户不可见。
"""
from sqlalchemy import Column, Integer, String, DateTime
from core.models.base import Base
import datetime


class UserHiddenArticle(Base):
    """
    用户隐藏记录：user_id + article_id 构成唯一隐藏关系。
    有记录表示该用户不希望看到这篇文章，查询时会被过滤掉。
    全局删除（文章状态置为 DELETED）仍然会作用于所有用户。
    """
    __tablename__ = 'user_hidden_articles'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(String(100), nullable=False, index=True, comment='用户ID')
    article_id = Column(String(255), nullable=False, index=True, comment='文章ID，关联 articles.id')
    hidden_at = Column(DateTime, default=datetime.datetime.now, comment='隐藏时间')
