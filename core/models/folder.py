# core/models/folder.py
"""
文件夹功能的数据模型
定义了两个表：
1. folders     - 文件夹表（存储用户创建的文件夹）
2. folder_feeds - 文件夹-公众号关联表（存储哪些公众号被放进了哪个文件夹）
"""

from sqlalchemy import Column, String, Integer, DateTime, Index
from core.models.base import Base
import datetime


class Folder(Base):
    """
    文件夹表
    作用：存储用户创建的文件夹基本信息
    类比：就像你在电脑里创建的"技术文章"文件夹
    """
    __tablename__ = 'folders'  # 数据库中的表名

    # 字段定义
    id = Column(Integer, primary_key=True, autoincrement=True)
    """主键ID，自动增长，唯一标识一个文件夹"""
    
    user_id = Column(String(100), nullable=False, index=True)
    """用户ID，用来区分是哪个用户创建的文件夹，加上索引(index)提高查询速度"""
    
    name = Column(String(200), nullable=False)
    """文件夹名称，比如"技术公众号"、"生活百科" """
    
    created_at = Column(DateTime, default=datetime.datetime.now)
    """创建时间，默认是当前时间"""
    
    def to_dict(self):
        """
        将模型对象转换成字典
        作用：方便返回JSON给前端
        """
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class FolderFeed(Base):
    """
    文件夹-公众号关联表
    作用：记录哪个公众号被放进了哪个文件夹
    类比：就像"技术文章"文件夹里有哪些文章
    """
    __tablename__ = 'folder_feeds'  # 数据库中的表名

    id = Column(Integer, primary_key=True, autoincrement=True)
    """主键ID，自动增长"""
    
    folder_id = Column(Integer, nullable=False, index=True)
    """文件夹ID，关联到folders表的id，加上索引提高查询速度"""
    
    feed_id = Column(String(255), nullable=False, index=True)
    """公众号ID，关联到feeds表的id（已有的公众号表）"""
    
    added_at = Column(DateTime, default=datetime.datetime.now)
    """添加到文件夹的时间"""
    
    def to_dict(self):
        """转换成字典，用于API返回"""
        return {
            'id': self.id,
            'folder_id': self.folder_id,
            'feed_id': self.feed_id,
            'added_at': self.added_at.strftime('%Y-%m-%d %H:%M:%S') if self.added_at else None
        }