# apis/folder.py

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import and_
from pydantic import BaseModel
from typing import List, Optional

from core.db import DB
from core.auth import get_current_user  # 改成从 core.auth 导入
from core.models.folder import Folder, FolderFeed
from core.models.feed import Feed


router = APIRouter(prefix="/folder", tags=["文件夹管理"])


class CreateFolderRequest(BaseModel):
    name: str


class AddFeedToFolderRequest(BaseModel):
    feed_ids: List[str]   # 支持批量添加


@router.post("/create", summary="创建文件夹")
async def create_folder(
    req: CreateFolderRequest,
    current_user: dict = Depends(get_current_user)  # 👈 改成 dict 类型，因为 get_current_user 返回的是字典
):
    """
    创建一个新文件夹
    
    current_user 结构示例：
    {
        "username": "admin",
        "role": "admin",
        "original_user": <User对象>
    }
    """
    session = DB.get_session()
    try:
        # 获取用户ID（从 original_user 对象取 id）
        user_id = current_user.get("original_user").id
        
        folder = Folder(
            user_id=user_id,  # 用真实的用户ID，比如 "0" 或 "admin"
            name=req.name
        )
        
        session.add(folder)
        session.commit()
        session.refresh(folder)
        
        return {
            "code": 0, # 成功码
            "message": "文件夹创建成功", # 成功消息
            "data": folder.to_dict() # 返回新创建的文件夹信息
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")
    finally:
        session.close()


@router.get("/list", summary="获取我的文件夹列表")
async def get_my_folders(
    current_user: dict = Depends(get_current_user)
):
    """获取当前用户的所有文件夹"""
    session = DB.get_session()
    try:
        user_id = current_user.get("original_user").id
        
        folders = session.query(Folder)\
            .filter(Folder.user_id == user_id)\
            .order_by(Folder.created_at.desc())\
            .all()
        
        return {
            "code": 0,
            "data": [f.to_dict() for f in folders]
        }
        
    finally:
        session.close()

@router.put("/{folder_id}", summary="更新文件夹名称")
async def update_folder(
    folder_id: int,
    name: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """更新文件夹名称"""
    session = DB.get_session()
    try:
        user_id = current_user.get("original_user").id
        
        # 查找文件夹
        folder = session.query(Folder).filter(
            Folder.id == folder_id,
            Folder.user_id == user_id
        ).first()
        
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        # 检查新名称是否与同用户下的其他文件夹重复
        existing = session.query(Folder).filter(
            Folder.user_id == user_id,
            Folder.name == name,
            Folder.id != folder_id
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="文件夹名称已存在")
        
        # 更新名称
        folder.name = name
        session.commit()
        session.refresh(folder)
        
        return {
            "code": 0,
            "message": "更新成功",
            "data": folder.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
    finally:
        session.close()

@router.delete("/{folder_id}", summary="删除文件夹（同时删除文件夹内的所有公众号）")
async def delete_folder(
    folder_id: int,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        user_id = current_user.get("original_user").id
        
        # 1. 检查文件夹是否存在且属于当前用户
        folder = session.query(Folder).filter(
            Folder.id == folder_id,
            Folder.user_id == user_id
        ).first()
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        # 2. 获取该文件夹内所有公众号的 feed_id
        feed_ids = session.query(FolderFeed.feed_id).filter(
            FolderFeed.folder_id == folder_id
        ).all()
        feed_ids = [f[0] for f in feed_ids]  # 转换为普通列表
        
        # 3. 删除这些公众号（如果有的话）
        if feed_ids:
            session.query(Feed).filter(Feed.id.in_(feed_ids)).delete(synchronize_session=False)
        
        # 4. 删除文件夹与公众号的关联记录
        session.query(FolderFeed).filter(FolderFeed.folder_id == folder_id).delete()
        
        # 5. 删除文件夹本身
        session.delete(folder)
        
        session.commit()
        return {
            "code": 0,
            "message": f"已删除文件夹及其中的 {len(feed_ids)} 个公众号"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    finally:
        session.close()

# @router.delete("/{folder_id}", summary="删除文件夹")
# async def delete_folder(
#     folder_id: int,
#     current_user: dict = Depends(get_current_user)
# ):
#     """删除文件夹"""
#     session = DB.get_session()
#     try:
#         user_id = current_user.get("original_user").id
        
#         folder = session.query(Folder).filter(
#             Folder.id == folder_id,
#             Folder.user_id == user_id
#         ).first()
        
#         if not folder:
#             raise HTTPException(status_code=404, detail="文件夹不存在")
        
#         # 删除关联的公众号
#         session.query(FolderFeed).filter(
#             FolderFeed.folder_id == folder_id
#         ).delete()
        
#         session.delete(folder)
#         session.commit()
        
#         return {
#             "code": 0,
#             "message": "删除成功"
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         session.rollback()
#         raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
#     finally:
#         session.close()



# 在添加新关联之前，先查找这个公众号是否已有旧关联
# 如果有，先删除旧关联
# 再添加新关联

@router.post("/{folder_id}/feeds", summary="添加公众号到文件夹（自动移动）")
async def add_feeds_to_folder(
    folder_id: int,
    req: AddFeedToFolderRequest,
    current_user: dict = Depends(get_current_user)
):
    """添加公众号到文件夹（如果公众号已在其他文件夹，自动移动）"""
    session = DB.get_session()
    try:
        user_id = current_user.get("original_user").id
        
        # 验证目标文件夹存在且属于当前用户
        target_folder = session.query(Folder).filter(
            Folder.id == folder_id,
            Folder.user_id == user_id
        ).first()
        
        if not target_folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        added = 0
        moved = 0
        
        for feed_id in req.feed_ids:
            # 1. 查找这个公众号当前所在的文件夹
            old_relation = session.query(FolderFeed).filter(
                FolderFeed.feed_id == feed_id
            ).first()
            
            # 2. 如果已经在其他文件夹，先删除旧关联
            if old_relation:
                if old_relation.folder_id == folder_id:
                    # 已经在目标文件夹，跳过
                    continue
                session.delete(old_relation)
                moved += 1
            
            # 3. 添加新关联
            new_relation = FolderFeed(
                folder_id=folder_id,
                feed_id=feed_id
            )
            session.add(new_relation)
            added += 1
        
        session.commit()
        
        message = f"成功添加 {added} 个公众号"
        if moved > 0:
            message += f"（其中 {moved} 个从其他文件夹移动过来）"
        
        return {
            "code": 0,
            "message": message,
            "data": {
                "added": added,
                "moved": moved
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
    finally:
        session.close()



@router.get("/{folder_id}/feeds", summary="获取文件夹里的公众号列表")
async def get_feeds_in_folder(
    folder_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取文件夹里的公众号列表（简化版，不含分页）"""
    session = DB.get_session()
    try:
        user_id = current_user.get("original_user").id
        
        # 1. 验证文件夹存在且属于当前用户
        folder = session.query(Folder).filter(
            Folder.id == folder_id,
            Folder.user_id == user_id
        ).first()
        
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        # 2. 查询关联的公众号
        # 注意：Feed 表的字段名是 mp_name 和 mp_cover，不是 name 和 avatar
        results = session.query(FolderFeed, Feed).join(
            Feed, FolderFeed.feed_id == Feed.id
        ).filter(
            FolderFeed.folder_id == folder_id
        ).all()
        
        # 3. 构建返回数据
        feeds = []
        for relation, feed in results:
            feeds.append({
                "id": feed.id,
                "name": feed.mp_name,           # 字段名是 mp_name
                "avatar": feed.mp_cover or "",  # 字段名是 mp_cover
                "description": feed.mp_intro or "",
                "status": feed.status 
            })
        
        return {
            "code": 0,
            "data": {
                "feeds": feeds
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取文件夹内公众号失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")
    finally:
        session.close()


@router.delete("/{folder_id}/feeds/{feed_id}", summary="从文件夹移除公众号")
async def remove_feed_from_folder(
    folder_id: int,
    feed_id: str,
    current_user: dict = Depends(get_current_user)
):
    """从文件夹中移除单个公众号"""
    session = DB.get_session()
    try:
        user_id = current_user.get("original_user").id
        
        # 验证文件夹存在且属于当前用户
        folder = session.query(Folder).filter(
            Folder.id == folder_id,
            Folder.user_id == user_id
        ).first()
        
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        
        # 删除关联
        result = session.query(FolderFeed).filter(
            FolderFeed.folder_id == folder_id,
            FolderFeed.feed_id == feed_id
        ).delete()
        
        session.commit()
        
        if result == 0:
            raise HTTPException(status_code=404, detail="公众号不在该文件夹中")
        
        return {
            "code": 0,
            "message": "移除成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"移除失败: {str(e)}")
    finally:
        session.close()
        