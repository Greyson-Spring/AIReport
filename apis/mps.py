from logging import info
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks
from core.auth import get_current_user_or_ak
from core.db import DB
from core.wx import search_Biz
from driver.wx import Wx
from .base import success_response, error_response
from datetime import datetime
from core.config import cfg
from core.res import save_avatar_locally
from core.models.feed import FEATURED_MP_ID, FEATURED_MP_NAME, FEATURED_MP_INTRO
from core.models.user_feed import UserFeed
from core.models.base import DATA_STATUS
from core.cache import clear_cache_pattern
import io
import os
from jobs.article import UpdateArticle
from driver.wxarticle import WXArticleFetcher
import threading
from uuid import uuid4
router = APIRouter(prefix=f"/mps", tags=["公众号管理"])


def build_featured_mp_item():
    now = datetime.now().isoformat()
    return {
        "id": FEATURED_MP_ID,
        "mp_name": FEATURED_MP_NAME,
        "mp_cover": "/static/logo.svg",
        "mp_intro": FEATURED_MP_INTRO,
        "status": 1,
        "created_at": now,
        "is_system": True
    }


_featured_article_tasks = {}
_featured_article_tasks_lock = threading.Lock()


def _set_featured_article_task(task_id: str, data: dict):
    with _featured_article_tasks_lock:
        _featured_article_tasks[task_id] = data


def _ensure_featured_feed(session):
    from core.models.feed import Feed
    featured_feed = session.query(Feed).filter(Feed.id == FEATURED_MP_ID).first()
    if featured_feed:
        return featured_feed
    now = datetime.now()
    featured_feed = Feed(
        id=FEATURED_MP_ID,
        mp_name=FEATURED_MP_NAME,
        mp_cover="logo.svg",
        mp_intro=FEATURED_MP_INTRO,
        status=1,
        sync_time=0,
        update_time=0,
        created_at=now,
        updated_at=now,
        faker_id=FEATURED_MP_ID
    )
    session.add(featured_feed)
    return featured_feed


def _run_add_featured_article_task(task_id: str, url: str, user_id: str | None = None):
    session = DB.get_session()
    fetcher = None
    try:
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": url,
            "status": "running",
            "message": "任务执行中"
        })
        from core.models.article import Article
        from core.models.user_favorite import UserFavorite
        target_url = str(url or "").strip()
        if not target_url:
            raise ValueError("请输入文章链接")
        fetcher = WXArticleFetcher()
        info = fetcher.get_article_content(target_url)
        if not info or info.get("fetch_error"):
            raise ValueError(info.get("fetch_error") or "文章抓取失败，请检查链接或登录状态")
        if info.get("content") == "DELETED":
            raise ValueError("该文章暂不可访问或已删除")

        _ensure_featured_feed(session)

        # 按 URL 查重（不限 mp_id）：如果文章已存在于任何公众号下，直接复用，不重复创建
        existing_by_url = session.query(Article).filter(
            Article.url == target_url
        ).first()

        now = datetime.now()

        if existing_by_url:
            # 文章已存在（可能属于某个已订阅的公众号），复用记录
            article = existing_by_url
            article_id = existing_by_url.id
            created = False
            # 更新文章内容（保持最新），但不修改 mp_id（保留在原公众号下）
            article.title = info.get("title") or target_url
            article.description = info.get("description") or fetcher.get_description(info.get("content") or "")
            article.content = info.get("content") or ""
            article.publish_time = info.get("publish_time") or article.publish_time
            article.url = target_url
            article.pic_url = info.get("topic_image") or info.get("pic_url") or ""
            article.status = DATA_STATUS.ACTIVE
            article.updated_at = int(now.timestamp())
            article.updated_at_millis = int(now.timestamp() * 1000)
        else:
            # 全新文章：创建到精选文章公众号下
            raw_article_id = info.get("id") or fetcher.extract_id_from_url(target_url)
            if not raw_article_id:
                raise ValueError("无法解析文章ID，请确认链接格式")
            article_id = f"{FEATURED_MP_ID}-{raw_article_id}".replace("MP_WXS_", "")
            article = session.query(Article).filter(Article.id == article_id).first()
            if article:
                created = False
                # 已有 FEATURED_MP_ID 记录，更新内容
                article.title = info.get("title") or target_url
                article.description = info.get("description") or fetcher.get_description(info.get("content") or "")
                article.content = info.get("content") or ""
                article.publish_time = info.get("publish_time") or article.publish_time
                article.url = target_url
                article.pic_url = info.get("topic_image") or info.get("pic_url") or ""
                article.status = DATA_STATUS.ACTIVE
                article.updated_at = int(now.timestamp())
                article.updated_at_millis = int(now.timestamp() * 1000)
            else:
                publish_time = info.get("publish_time")
                if not isinstance(publish_time, int):
                    try:
                        publish_time = int(publish_time)
                    except Exception:
                        publish_time = int(now.timestamp())
                article = Article(
                    id=article_id,
                    mp_id=FEATURED_MP_ID,
                    title=info.get("title") or target_url,
                    description=info.get("description") or fetcher.get_description(info.get("content") or ""),
                    content=info.get("content") or "",
                    publish_time=publish_time,
                    url=target_url,
                    pic_url=info.get("topic_image") or info.get("pic_url") or "",
                    status=DATA_STATUS.ACTIVE,
                    created_at=now,
                    updated_at=int(now.timestamp()),
                    updated_at_millis=int(now.timestamp() * 1000),
                    is_read=0,
                )
                session.add(article)
                created = True

        # 为添加该文章的用户创建收藏记录（按用户隔离）
        if user_id:
            existing_fav = session.query(UserFavorite).filter(
                UserFavorite.user_id == user_id,
                UserFavorite.article_id == article_id
            ).first()
            if not existing_fav:
                session.add(UserFavorite(
                    user_id=user_id,
                    article_id=article_id,
                    created_at=now
                ))

        session.commit()
        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": target_url,
            "status": "success",
            "message": "精选文章添加成功" if created else "精选文章更新成功",
            "id": article_id,
            "mp_id": FEATURED_MP_ID,
            "mp_name": FEATURED_MP_NAME,
            "title": article.title,
            "created": created
        })
    except Exception as e:
        session.rollback()
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": url,
            "status": "failed",
            "message": str(e)
        })
    finally:
        if fetcher is not None:
            try:
                fetcher.Close()
            except Exception:
                pass
        session.close()


def _get_user_id(current_user: dict) -> str:
    """从 current_user 中提取 user_id"""
    user_id = current_user.get("username")
    if not user_id:
        original_user = current_user.get("original_user")
        if original_user:
            user_id = original_user.username
    return user_id


@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str = "",
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        result = search_Biz(kw, limit=limit, offset=offset)
        data = {
            'list': result.get('list') if result is not None else [],
            'page': {
                'limit': limit,
                'offset': offset
            },
            'total': result.get('total') if result is not None else 0
        }
        return success_response(data)
    except Exception as e:
        print(f"搜索公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="搜索公众号失败,请重新扫码授权！",
            )
        )


@router.get("", summary="获取公众号列表（当前用户的订阅）")
async def get_mps(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    status: int = Query(None, description="状态筛选: 1=启用, 0=停用, 不传=全部"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    查询当前用户订阅的公众号列表。
    通过 user_feeds 关联表获取，不同用户看到的是各自的订阅状态。
    """
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        user_id = _get_user_id(current_user)
        if not user_id:
            return success_response({"list": [build_featured_mp_item()], "page": {"limit": limit, "offset": offset, "total": 1}, "total": 1})

        # 通过 UserFeed 关联查询当前用户的订阅
        query = session.query(
            Feed.id,
            Feed.mp_name,
            Feed.mp_cover,
            Feed.mp_intro,
            Feed.created_at,
            UserFeed.status.label("user_status"),
            UserFeed.created_at.label("subscribed_at")
        ).join(
            UserFeed, Feed.id == UserFeed.feed_id
        ).filter(
            UserFeed.user_id == user_id,
            Feed.id != FEATURED_MP_ID
        )

        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
        if status is not None:
            query = query.filter(UserFeed.status == status)

        total = query.count()
        rows = query.order_by(UserFeed.created_at.desc()).limit(limit).offset(offset).all()

        mps_list = [{
            "id": row.id,
            "mp_name": row.mp_name,
            "mp_cover": row.mp_cover,
            "mp_intro": row.mp_intro,
            "status": row.user_status,  # 返回用户级别的状态
            "created_at": row.created_at.isoformat()
        } for row in rows]

        # 只在筛选全部且无搜索关键词时添加精选文章（精选是全局系统项，无需订阅）
        if offset == 0 and status is None and not kw:
            mps_list.insert(0, build_featured_mp_item())

        return success_response({
            "list": mps_list,
            "page": {
                "limit": limit,
                "offset": offset,
                "total": total + 1  # +1 精选文章
            },
            "total": total + 1
        })
    except Exception as e:
        print(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号列表失败"
            )
        )


@router.post("/featured/article", summary="添加精选文章")
async def add_featured_article(
    url: str = Body(..., embed=True, min_length=1),
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        target_url = str(url or "").strip()
        if not target_url:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40001,
                    message="请输入文章链接"
                )
            )
        if "mp.weixin.qq.com/s/" not in target_url:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40002,
                    message="请输入有效的公众号文章链接"
                )
            )

        task_id = str(uuid4())
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": target_url,
            "status": "pending",
            "message": "任务已创建"
        })

        # 获取当前用户 ID，传递给后台任务用于创建 UserFavorite 记录
        user_id = _get_user_id(current_user)

        threading.Thread(
            target=_run_add_featured_article_task,
            args=(task_id, target_url, user_id),
            daemon=True
        ).start()

        return success_response({
            "task_id": task_id,
            "url": target_url,
            "status": "pending"
        }, message="已开始添加/抓取，请稍后刷新查看结果")
    except HTTPException:
        raise
    except Exception as e:
        print(f"添加精选文章任务启动失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="添加精选文章失败"
            )
        )


@router.get("/featured/article/tasks/{task_id}", summary="查询精选文章添加任务状态")
async def get_featured_article_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    with _featured_article_tasks_lock:
        task = _featured_article_tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(
                code=40404,
                message="任务不存在"
            )
        )
    return success_response(task)


@router.get("/update/{mp_id}", summary="更新公众号文章")
async def update_mps(
    mp_id: str,
    start_page: int = 0,
    end_page: int = 1,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            return error_response(
                code=40401,
                message="请选择一个公众号"
            )
        import time
        sync_interval = cfg.get("sync_interval", 60)
        if mp.update_time is None:
            mp.update_time = int(time.time()) - sync_interval
        time_span = int(time.time()) - int(mp.update_time)
        if time_span < sync_interval:
            return error_response(
                code=40402,
                message="请不要频繁更新操作",
                data={"time_span": time_span}
            )
        result = []

        def UpArt(mp):
            from core.wx import WxGather
            wx = WxGather().Model()
            wx.get_Articles(mp.faker_id, Mps_id=mp.id, Mps_title=mp.mp_name, CallBack=UpdateArticle, start_page=start_page, MaxPage=end_page)
            result = wx.articles
        import threading
        threading.Thread(target=UpArt, args=(mp,)).start()
        return success_response({
            "time_span": time_span,
            "list": result,
            "total": len(result),
            "mps": mp
        })
    except Exception as e:
        print(f"更新公众号文章: {str(e)}", e)
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=f"更新公众号文章{str(e)}"
            )
        )


@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp(
    mp_id: str,
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(mp)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号详情失败"
            )
        )


@router.post("/by_article", summary="通过文章链接获取公众号详情")
async def get_mp_by_article(
    url: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        info = await WXArticleFetcher().async_get_article_content(url)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(info)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="请输入正确的公众号文章链接"
            )
        )


@router.post("", summary="添加公众号（订阅）")
async def add_mp(
    mp_name: str = Body(..., min_length=1, max_length=255),
    mp_cover: str = Body(None, max_length=255),
    mp_id: str = Body(None, max_length=255),
    avatar: str = Body(None, max_length=500),
    mp_intro: str = Body(None, max_length=255),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    订阅一个公众号：
    1. 如果该公众号（faker_id）在 feeds 表中不存在，则创建（全局唯一）
    2. 在 user_feeds 中创建/恢复当前用户的订阅关系
    3. 仅当 feeds 首次创建时才触发文章抓取（避免重复抓取）
    """
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        import time
        now = datetime.now()

        import base64
        mpx_id = base64.b64decode(mp_id).decode("utf-8")
        local_avatar_path = f"{save_avatar_locally(avatar)}"

        user_id = _get_user_id(current_user)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(code=40101, message="无法识别用户身份")
            )

        # 1. 全局查重：通过 faker_id 判断公众号是否已存在（不限用户）
        existing_feed = session.query(Feed).filter(Feed.faker_id == mp_id).first()

        is_new_feed = False
        if existing_feed:
            # 更新公众号信息
            existing_feed.mp_name = mp_name
            existing_feed.mp_cover = local_avatar_path
            existing_feed.mp_intro = mp_intro
            existing_feed.updated_at = now
            feed = existing_feed
        else:
            # 创建全局公众号记录（共享资源）
            feed = Feed(
                id=f"MP_WXS_{mpx_id}",
                mp_name=mp_name,
                mp_cover=local_avatar_path,
                mp_intro=mp_intro,
                status=1,
                created_at=now,
                updated_at=now,
                faker_id=mp_id,
                update_time=0,
                sync_time=0,
            )
            session.add(feed)
            is_new_feed = True

        # 2. 创建/恢复当前用户的订阅关系
        user_feed = session.query(UserFeed).filter(
            UserFeed.user_id == user_id,
            UserFeed.feed_id == feed.id
        ).first()

        if user_feed:
            # 已存在订阅关系：如果之前是停用状态则重新启用
            if user_feed.status == 0:
                user_feed.status = 1
                user_feed.disabled_at = None
                user_feed.updated_at = now
        else:
            # 新建订阅关系
            user_feed = UserFeed(
                user_id=user_id,
                feed_id=feed.id,
                status=1,
                created_at=now,
                updated_at=now,
            )
            session.add(user_feed)

        session.commit()

        # 3. 仅当公众号是首次被创建时才触发文章抓取
        if is_new_feed:
            from core.queue import TaskQueue
            from core.wx import WxGather
            Max_page = int(cfg.get("max_page", "2"))
            TaskQueue.add_task(
                WxGather().Model().get_Articles,
                faker_id=feed.faker_id,
                Mps_id=feed.id,
                CallBack=UpdateArticle,
                MaxPage=Max_page,
                Mps_title=mp_name,
                task_name=mp_name
            )

        return success_response({
            "id": feed.id,
            "mp_name": feed.mp_name,
            "mp_cover": feed.mp_cover,
            "mp_intro": feed.mp_intro,
            "status": user_feed.status if user_feed else 1,
            "faker_id": mp_id,
            "created_at": feed.created_at.isoformat()
        })
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"添加公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="添加公众号失败"
            )
        )


@router.delete("/{mp_id}", summary="取消订阅（删除当前用户的订阅关系）")
async def delete_mp(
    mp_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    取消订阅：只删除 user_feeds 中的订阅关系，不影响 feeds 全局表。
    其他用户仍可正常使用该公众号。
    """
    session = DB.get_session()
    try:
        user_id = _get_user_id(current_user)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(code=40101, message="无法识别用户身份")
            )

        # 删除当前用户的订阅关系（而非删除 feeds 本身）
        user_feed = session.query(UserFeed).filter(
            UserFeed.user_id == user_id,
            UserFeed.feed_id == mp_id
        ).first()
        if not user_feed:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="订阅关系不存在"
                )
            )

        session.delete(user_feed)
        session.commit()
        return success_response({
            "message": "取消订阅成功",
            "id": mp_id
        })
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"取消订阅错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="取消订阅失败"
            )
        )


@router.put("/{mp_id}", summary="更新订阅状态（启用/停用）")
async def update_mp_status(
    mp_id: str,
    mp_name: str = Body(None),
    mp_cover: str = Body(None),
    mp_intro: str = Body(None),
    status: int = Body(None),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    更新当前用户对某公众号的订阅状态。
    启用：user_feeds.status = 1, disabled_at = None
    停用：user_feeds.status = 0, disabled_at = NOW（用于文章过滤）
    """
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        user_id = _get_user_id(current_user)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(code=40101, message="无法识别用户身份")
            )

        user_feed = session.query(UserFeed).filter(
            UserFeed.user_id == user_id,
            UserFeed.feed_id == mp_id
        ).first()
        if not user_feed:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="订阅关系不存在"
                )
            )

        now = datetime.now()

        # 更新公众号全局信息（共享，所有用户可见）
        if mp_name is not None or mp_cover is not None or mp_intro is not None:
            feed = session.query(Feed).filter(Feed.id == mp_id).first()
            if feed:
                if mp_name is not None:
                    feed.mp_name = mp_name
                if mp_cover is not None:
                    feed.mp_cover = mp_cover
                if mp_intro is not None:
                    feed.mp_intro = mp_intro
                feed.updated_at = now

        # 更新用户级别订阅状态
        if status is not None:
            user_feed.status = status
            if status == 0:
                # 停用时记录停用时间，用于文章历史截断
                user_feed.disabled_at = now
            else:
                # 重新启用时清除停用时间
                user_feed.disabled_at = None
            user_feed.updated_at = now

        session.commit()

        return success_response({
            "message": "更新成功",
            "id": mp_id,
            "status": user_feed.status
        })
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"更新订阅状态错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="更新订阅状态失败"
            )
        )


@router.get("/export/mps", summary="导出公众号列表")
async def export_mps(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    status: int = Query(None, description="状态筛选: 1=启用, 0=停用"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """导出当前用户的公众号列表（格式同 GET /mps，不含精选文章）"""
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        user_id = _get_user_id(current_user)
        if not user_id:
            return success_response({"list": [], "page": {"limit": limit, "offset": offset, "total": 0}, "total": 0})

        query = session.query(
            Feed.id,
            Feed.mp_name,
            Feed.mp_cover,
            Feed.mp_intro,
            Feed.faker_id,
            UserFeed.status.label("user_status"),
            UserFeed.created_at.label("subscribed_at")
        ).join(
            UserFeed, Feed.id == UserFeed.feed_id
        ).filter(
            UserFeed.user_id == user_id,
            Feed.id != FEATURED_MP_ID
        )

        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
        if status is not None:
            query = query.filter(UserFeed.status == status)

        total = query.count()
        rows = query.order_by(UserFeed.created_at.desc()).limit(limit).offset(offset).all()

        mps_list = [{
            "id": row.id,
            "mp_name": row.mp_name,
            "mp_cover": row.mp_cover,
            "mp_intro": row.mp_intro,
            "faker_id": row.faker_id,
            "status": row.user_status,
            "created_at": row.subscribed_at.isoformat() if row.subscribed_at else None
        } for row in rows]

        return success_response({
            "list": mps_list,
            "page": {"limit": limit, "offset": offset, "total": total},
            "total": total
        })
    except Exception as e:
        print(f"导出公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message="导出公众号列表失败")
        )
