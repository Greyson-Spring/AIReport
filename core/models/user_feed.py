"""
用户-公众号订阅关联表
记录每个用户对每个公众号的订阅关系和状态。
公众号本身是共享的（feeds表），每个用户可以独立订阅/停用。
"""
from sqlalchemy import Column, Integer, String, DateTime
from core.models.base import Base
import datetime


class UserFeed(Base):
    """
    用户订阅记录：user_id + feed_id 构成唯一订阅关系。
    - status=1 启用：用户可以看到该公众号的全部文章
    - status=0 停用：用户只能看到停用前已发布的文章（通过 disabled_at 截断）
    """
    __tablename__ = 'user_feeds'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(String(100), nullable=False, index=True, comment='用户ID')
    feed_id = Column(String(255), nullable=False, index=True, comment='公众号ID，关联 feeds.id')
    status = Column(Integer, default=1, index=True, comment='订阅状态: 1=启用, 0=停用')
    disabled_at = Column(DateTime, nullable=True, comment='停用时间，用于过滤停用后发布的文章')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='订阅创建时间')
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment='最后更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'feed_id': self.feed_id,
            'status': self.status,
            'disabled_at': self.disabled_at.isoformat() if self.disabled_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
