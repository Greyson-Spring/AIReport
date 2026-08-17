import threading
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status as fast_status, Query
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.base import DATA_STATUS
from core.models.article import Article,ArticleBase
from sqlalchemy import and_, or_, desc
from .base import success_response, error_response
from core.config import cfg
from apis.base import format_search_kw
from core.print import print_warning, print_info, print_error, print_success
from core.cache import clear_cache_pattern
from tools.fix import fix_article
from core.article_content import sync_article_content
from driver.wxarticle import WXArticleFetcher
router = APIRouter(prefix=f"/articles", tags=["文章管理"])

_refresh_tasks = {}
_refresh_tasks_lock = threading.Lock()


def _set_refresh_task(task_id: str, data: dict):
    with _refresh_tasks_lock:
        _refresh_tasks[task_id] = data


def _get_active_refresh_task(article_id: str):
    with _refresh_tasks_lock:
        for task in _refresh_tasks.values():
            if task.get("article_id") != article_id:
                continue
            if task.get("status") in {"pending", "running"}:
                return dict(task)
    return None


def _run_refresh_article_task(task_id: str, article_id: str):
    session = DB.get_session()
    fetcher = None
    try:
        _set_refresh_task(task_id, {
            "task_id": task_id,
            "article_id": article_id,
            "status": "running",
            "message": "任务执行中"
        })

        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            _set_refresh_task(task_id, {
                "task_id": task_id,
                "article_id": article_id,
                "status": "failed",
                "message": "文章不存在"
            })
            return

        target_url = (article.url or "").strip()
        if not target_url:
            _set_refresh_task(task_id, {
                "task_id": task_id,
                "article_id": article_id,
                "status": "failed",
                "message": "文章缺少可抓取链接"
            })
            return

        fetcher = WXArticleFetcher()
        fetched = fetcher.get_article_content(target_url)
        fetched_content = fetched.get("content")

        if fetched_content != "DELETED" and not fetched_content:
            fetch_error = fetched.get("fetch_error") or "文章内容抓取为空"
            _set_refresh_task(task_id, {
                "task_id": task_id,
                "article_id": article_id,
                "status": "failed",
                "message": f"文章刷新失败: {fetch_error}"
            })
            return

        article.title = fetched.get("title") or article.title
        article.url = target_url
        article.publish_time = fetched.get("publish_time") or article.publish_time
        article.content = fetched_content if fetched_content is not None else article.content
        if fetched_content == "DELETED":
            article.description = fetched.get("description") or article.description
        else:
            article.description = fetched.get("description") or fetcher.get_description(article.content or "")
        article.pic_url = fetched.get("topic_image") or fetched.get("pic_url") or article.pic_url
        article.status = DATA_STATUS.DELETED if fetched_content == "DELETED" else DATA_STATUS.ACTIVE

        now_seconds = int(time.time())
        now_millis = int(time.time() * 1000)
        article.updated_at = now_seconds
        article.updated_at_millis = now_millis
        session.commit()

        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")

        _set_refresh_task(task_id, {
            "task_id": task_id,
            "article_id": article_id,
            "status": "success",
            "message": "文章刷新成功",
            "updated_at": now_seconds
        })
    except Exception as e:
        session.rollback()
        _set_refresh_task(task_id, {
            "task_id": task_id,
            "article_id": article_id,
            "status": "failed",
            "message": f"文章刷新失败: {str(e)}"
        })
    finally:
        if fetcher is not None:
            try:
                fetcher.Close()
            except Exception:
                pass
        session.close()


    
@router.delete("/clean", summary="清理无效文章(MP_ID不存在于Feeds表中的文章)")
async def clean_orphan_articles(
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.models.article import Article
        
        # 找出Articles表中mp_id不在Feeds表中的记录
        subquery = session.query(Feed.id).subquery()
        deleted_count = session.query(Article)\
            .filter(~Article.mp_id.in_(subquery))\
            .delete(synchronize_session=False)
        
        session.commit()
        
        # 清除相关缓存
        clear_cache_pattern("articles_list")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")
        
        return success_response({
            "message": "清理无效文章成功",
            "deleted_count": deleted_count
        })
    except Exception as e:
        session.rollback()
        print(f"清理无效文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="清理无效文章失败"
            )
        )

@router.put("/{article_id}/read", summary="改变文章阅读状态")
async def toggle_article_read_status(
    article_id: str,
    is_read: bool = Query(..., description="阅读状态: true为已读, false为未读"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.user_read_article import UserReadArticle

        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        # 获取当前用户ID
        user_id = current_user.get("username")
        if not user_id:
            ou = current_user.get("original_user")
            if ou:
                user_id = ou.username
        if not user_id:
            raise HTTPException(
                status_code=fast_status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="无法识别用户身份")
            )

        if is_read:
            # 标记已读：添加 UserReadArticle 记录
            existing = session.query(UserReadArticle).filter(
                UserReadArticle.user_id == user_id,
                UserReadArticle.article_id == article_id
            ).first()
            if not existing:
                session.add(UserReadArticle(user_id=user_id, article_id=article_id))
        else:
            # 标记未读：删除 UserReadArticle 记录
            session.query(UserReadArticle).filter(
                UserReadArticle.user_id == user_id,
                UserReadArticle.article_id == article_id
            ).delete()

        session.commit()

        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("tag_detail")

        return success_response({
            "message": f"文章已标记为{'已读' if is_read else '未读'}",
            "is_read": is_read
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"更新文章阅读状态失败: {str(e)}"
            )
        )


@router.put("/{article_id}/favorite", summary="改变文章收藏状态")
async def toggle_article_favorite_status(
    article_id: str,
    is_favorite: bool = Query(..., description="收藏状态: true为收藏, false为取消收藏"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.user_favorite import UserFavorite

        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        # 获取当前用户的唯一标识（与 UserFeed 使用同一字段：username）
        user_id = current_user.get("username")
        if not user_id:
            ou = current_user.get("original_user")
            if ou:
                user_id = ou.username
        if not user_id:
            raise HTTPException(
                status_code=fast_status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="无法识别用户身份")
            )

        if is_favorite:
            # 收藏：添加 UserFavorite 记录（每人每篇文章只能收藏一次）
            existing = session.query(UserFavorite).filter(
                UserFavorite.user_id == user_id,
                UserFavorite.article_id == article_id
            ).first()
            if not existing:
                session.add(UserFavorite(user_id=user_id, article_id=article_id))
        else:
            # 取消收藏：删除当前用户的收藏记录
            session.query(UserFavorite).filter(
                UserFavorite.user_id == user_id,
                UserFavorite.article_id == article_id
            ).delete()

        session.commit()

        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("tag_detail")

        return success_response({
            "message": "文章已收藏" if is_favorite else "已取消收藏",
            "is_favorite": is_favorite
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"更新文章收藏状态失败: {str(e)}"
            )
        )

@router.delete("/clean_duplicate_articles", summary="清理重复文章")
async def clean_duplicate(
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        from tools.clean import clean_duplicate_articles
        (msg, deleted_count) =clean_duplicate_articles()
        return success_response({
            "message": msg,
            "deleted_count": deleted_count
        })
    except Exception as e:
        print(f"清理重复文章: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="清理重复文章"
            )
        )


@router.api_route("", summary="获取文章列表",methods= ["GET", "POST"], operation_id="get_articles_list")
async def get_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    status: str = Query(None),
    search: str = Query(None),
    mp_id: str = Query(None),
    folder_id: int = Query(None),
    only_favorite: bool = Query(False),
    has_content:bool=Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from sqlalchemy import case, func, or_, and_, false

        # 构建查询条件 - 使用 ArticleBase 并通过 case 表达式判断是否有正文
        # 避免加载大量 content 数据
        query = session.query(
            ArticleBase,
            case(
                ((Article.content.isnot(None)) & (Article.content != ''), 1),
                else_=0
            ).label('has_content')
        )
        if status:
            query = query.filter(ArticleBase.status == status)
        else:
            query = query.filter(ArticleBase.status != DATA_STATUS.DELETED)

        # 过滤掉当前用户已隐藏的文章（按用户隔离的"删除"功能）
        uid_hidden = current_user.get("username")
        if not uid_hidden:
            ou = current_user.get("original_user")
            if ou:
                uid_hidden = ou.username
        if uid_hidden:
            from core.models.user_hidden_article import UserHiddenArticle
            hidden_subq = session.query(UserHiddenArticle.article_id).filter(
                UserHiddenArticle.user_id == uid_hidden
            ).subquery()
            query = query.filter(ArticleBase.id.notin_(hidden_subq))

        # 按文件夹筛选: 一次查询文件夹内所有公众号的文章(替代前端逐个公众号请求)
        if folder_id:
            from core.models.folder import FolderFeed
            folder_feed_ids = [
                ff.feed_id for ff in session.query(FolderFeed).filter(
                    FolderFeed.folder_id == folder_id
                ).all()
            ]
            if folder_feed_ids:
                query = query.filter(ArticleBase.mp_id.in_(folder_feed_ids))
            else:
                # 文件夹里没有公众号, 返回空
                query = query.filter(false())
        # 用户文章隔离：未指定 mp_id/folder_id 时，只显示当前用户订阅的公众号文章
        # 但当 only_favorite=True 时跳过订阅过滤，因为 UserFavorite JOIN
        # 已经保证只返回用户收藏的文章（包括精选文章，它不在 UserFeed 中）
        elif not mp_id and not only_favorite:
            from core.models.user_feed import UserFeed
            user_id = current_user.get("username")
            if not user_id:
                original_user = current_user.get("original_user")
                if original_user:
                    user_id = original_user.username
            if user_id:
                subscriptions = session.query(UserFeed).filter(
                    UserFeed.user_id == user_id
                ).all()
                if subscriptions:
                    feed_filters = []
                    for sub in subscriptions:
                        if sub.status == 1:
                            # 启用状态：显示该公众号全部文章
                            feed_filters.append(ArticleBase.mp_id == sub.feed_id)
                        elif sub.status == 0 and sub.disabled_at is not None:
                            # 停用状态：只显示停用时间之前已发布的文章
                            disabled_ts = int(sub.disabled_at.timestamp())
                            feed_filters.append(
                                and_(
                                    ArticleBase.mp_id == sub.feed_id,
                                    ArticleBase.publish_time.isnot(None),
                                    ArticleBase.publish_time <= disabled_ts
                                )
                            )
                    if feed_filters:
                        query = query.filter(or_(*feed_filters))
                    else:
                        # 没有可访问的订阅，返回空
                        query = query.filter(false())
                else:
                    # 没有任何订阅
                    query = query.filter(false())

        if mp_id:
            query = query.filter(ArticleBase.mp_id == mp_id)

            # 精选文章按用户隔离：只显示当前用户有收藏记录的文章
            from core.models.feed import FEATURED_MP_ID as _FID
            if mp_id == _FID:
                from core.models.user_favorite import UserFavorite
                uid = current_user.get("username")
                if not uid:
                    ou = current_user.get("original_user")
                    if ou:
                        uid = ou.username
                if uid:
                    query = query.join(UserFavorite, and_(
                        UserFavorite.article_id == ArticleBase.id,
                        UserFavorite.user_id == uid
                    ))
                else:
                    query = query.filter(false())
            else:
                # 普通公众号：尊重用户的停用状态
                user_id = current_user.get("username")
                if not user_id:
                    ou = current_user.get("original_user")
                    if ou:
                        user_id = ou.username
                if user_id:
                    from core.models.user_feed import UserFeed
                    uf = session.query(UserFeed).filter(
                        UserFeed.user_id == user_id,
                        UserFeed.feed_id == mp_id
                    ).first()
                    if uf and uf.status == 0 and uf.disabled_at is not None:
                        disabled_ts = int(uf.disabled_at.timestamp())
                        query = query.filter(
                            ArticleBase.publish_time.isnot(None),
                            ArticleBase.publish_time <= disabled_ts
                        )
        if only_favorite:
            # 使用 UserFavorite 表实现按用户筛选收藏（不同用户收藏独立）
            from core.models.user_favorite import UserFavorite
            from core.models.feed import FEATURED_MP_ID as _FID
            # 精选文章已在上面的 mp_id 分支中做了 UserFavorite 隔离，跳过以避免重复 JOIN
            if mp_id == _FID:
                pass
            else:
                uid = current_user.get("username")
                if not uid:
                    ou = current_user.get("original_user")
                    if ou:
                        uid = ou.username
                if uid:
                    query = query.join(UserFavorite, and_(
                        UserFavorite.article_id == ArticleBase.id,
                        UserFavorite.user_id == uid
                    ))
                else:
                    query = query.filter(false())
        if search:
            query = query.filter(
               format_search_kw(search)
            )
        
        # 获取总数
        total = query.count()
        query= query.order_by(ArticleBase.publish_time.desc()).offset(offset).limit(limit)
        # query= query.order_by(Article.id.desc()).offset(offset).limit(limit)
        # 分页查询（按发布时间降序）
        results = query.all()
        
        # 打印生成的 SQL 语句（包含分页参数）
        print_warning(query.statement.compile(compile_kwargs={"literal_binds": True}))
                       
        # 查询公众号名称
        from core.models.feed import Feed
        mp_names = {}
        for result in results:
            article = result[0]  # ArticleBase 对象
            if article.mp_id and article.mp_id not in mp_names:
                feed = session.query(Feed).filter(Feed.id == article.mp_id).first()
                mp_names[article.mp_id] = feed.mp_name if feed else "未知公众号"
        
        # 批量查询当前用户的收藏状态（使用 UserFavorite，实现按用户隔离）
        from core.models.user_favorite import UserFavorite
        favorited_article_ids = set()
        uid = current_user.get("username")
        if not uid:
            ou = current_user.get("original_user")
            if ou:
                uid = ou.username
        if uid and results:
            article_ids = [result[0].id for result in results]
            fav_records = session.query(UserFavorite).filter(
                UserFavorite.user_id == uid,
                UserFavorite.article_id.in_(article_ids)
            ).all()
            favorited_article_ids = {r.article_id for r in fav_records}

        # 批量查询当前用户的阅读状态（按用户隔离）
        from core.models.user_read_article import UserReadArticle
        read_article_ids = set()
        if uid and results:
            read_records = session.query(UserReadArticle).filter(
                UserReadArticle.user_id == uid,
                UserReadArticle.article_id.in_(article_ids)
            ).all()
            read_article_ids = {r.article_id for r in read_records}

        # 合并公众号名称到文章列表
        article_list = []
        for result in results:
            article = result[0]  # ArticleBase 对象
            has_content_val = result[1]  # has_content 计算值
            article_dict = article.__dict__.copy()
            article_dict["mp_name"] = mp_names.get(article.mp_id, "未知公众号")
            article_dict["is_favorite"] = 1 if article.id in favorited_article_ids else 0
            article_dict["is_read"] = 1 if article.id in read_article_ids else 0
            article_dict["has_content"] = has_content_val
            article_list.append(article_dict)
        
        from .base import success_response
        return success_response({
            "list": article_list,
            "total": total
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取文章列表失败: {str(e)}"
            )
        )

@router.post("/{article_id}/refresh", summary="刷新单篇文章")
async def refresh_article(
    article_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        article_exists = session.query(Article.id).filter(Article.id == article_id).first()
        if not article_exists:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        active_task = _get_active_refresh_task(article_id)
        if active_task:
            return success_response(active_task, message="该文章已有刷新任务在执行")

        task_id = str(uuid4())
        task = {
            "task_id": task_id,
            "article_id": article_id,
            "status": "pending",
            "message": "任务已创建"
        }
        _set_refresh_task(task_id, task)

        threading.Thread(
            target=_run_refresh_article_task,
            args=(task_id, article_id),
            daemon=True
        ).start()

        return success_response(task, message="已开始刷新，请稍后查看")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"文章刷新失败: {str(e)}"
            )
        )
    finally:
        session.close()


@router.get("/refresh/tasks/{task_id}", summary="查询文章刷新任务状态")
async def get_refresh_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    with _refresh_tasks_lock:
        task = _refresh_tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(
                code=40404,
                message="刷新任务不存在"
            )
        )
    return success_response(task)


@router.get("/{article_id}", summary="获取文章详情")
def get_article_detail(
    article_id: str,
    content: bool = Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        article = session.query(Article).filter(Article.id==article_id).filter(Article.status != DATA_STATUS.DELETED).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        if content:
            updated, _ = sync_article_content(
                session=session,
                article=article,
                preferred_mode=cfg.get("gather.content_mode", "web"),
            )
            if updated:
                clear_cache_pattern("articles_list")
                clear_cache_pattern("article_detail")
                clear_cache_pattern("home_page")
                clear_cache_pattern("tag_detail")
        result = fix_article(article)
        # 如果已登录，从关联表查询当前用户的收藏和阅读状态（按用户隔离）
        if current_user:
            user_id = current_user.get("username")
            if not user_id:
                ou = current_user.get("original_user")
                if ou:
                    user_id = ou.username
            if user_id:
                from core.models.user_favorite import UserFavorite
                fav = session.query(UserFavorite).filter(
                    UserFavorite.user_id == user_id,
                    UserFavorite.article_id == article_id
                ).first()
                result["is_favorite"] = 1 if fav else 0

                from core.models.user_read_article import UserReadArticle
                read = session.query(UserReadArticle).filter(
                    UserReadArticle.user_id == user_id,
                    UserReadArticle.article_id == article_id
                ).first()
                result["is_read"] = 1 if read else 0
        return success_response(result)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取文章详情失败: {str(e)}"
            )
        )   

@router.delete("/{article_id}", summary="删除文章（仅对当前用户隐藏）")
async def delete_article(
    article_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.user_hidden_article import UserHiddenArticle

        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        # 获取当前用户ID
        user_id = current_user.get("username")
        if not user_id:
            ou = current_user.get("original_user")
            if ou:
                user_id = ou.username
        if not user_id:
            raise HTTPException(
                status_code=fast_status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="无法识别用户身份")
            )

        # 按用户隐藏文章（不修改全局 article.status），其他用户仍可见
        existing = session.query(UserHiddenArticle).filter(
            UserHiddenArticle.user_id == user_id,
            UserHiddenArticle.article_id == article_id
        ).first()
        if not existing:
            session.add(UserHiddenArticle(
                user_id=user_id,
                article_id=article_id
            ))

        session.commit()
        return success_response(None, message="文章已隐藏")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"隐藏文章失败: {str(e)}"
            )
        )

@router.get("/{article_id}/next", summary="获取下一篇文章")
def get_next_article(
    article_id: str,
    content: bool = Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        current_article = session.query(Article).filter(Article.id == article_id).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )

        # 获取当前用户ID（用于后续的用户隔离过滤）
        user_id = current_user.get("username")
        if not user_id:
            ou = current_user.get("original_user")
            if ou:
                user_id = ou.username

        # 排除当前用户已隐藏的文章
        if user_id:
            from core.models.user_hidden_article import UserHiddenArticle
            hidden_subq = session.query(UserHiddenArticle.article_id).filter(
                UserHiddenArticle.user_id == user_id
            ).subquery()

        # 查询发布时间更晚的第一篇文章
        query = session.query(Article)\
            .filter(Article.publish_time > current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.mp_id == current_article.mp_id)
        if user_id:
            query = query.filter(Article.id.notin_(hidden_subq))
        next_article = query.order_by(Article.publish_time.asc()).first()

        if not next_article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40402,
                    message="没有下一篇文章"
                )
            )
        if content:
            updated, _ = sync_article_content(
                session=session,
                article=next_article,
                preferred_mode=cfg.get("gather.content_mode", "web"),
            )
            if updated:
                clear_cache_pattern("articles_list")
                clear_cache_pattern("article_detail")
                clear_cache_pattern("home_page")
                clear_cache_pattern("tag_detail")
        result = fix_article(next_article)
        # 覆盖为当前用户的阅读状态（按用户隔离）
        if user_id:
            from core.models.user_read_article import UserReadArticle
            read = session.query(UserReadArticle).filter(
                UserReadArticle.user_id == user_id,
                UserReadArticle.article_id == next_article.id
            ).first()
            result["is_read"] = 1 if read else 0
        return success_response(result)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取下一篇文章失败: {str(e)}"
            )
        )

@router.get("/{article_id}/prev", summary="获取上一篇文章")
def get_prev_article(
    article_id: str,
    content: bool = Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        current_article = session.query(Article).filter(Article.id == article_id).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )

        # 获取当前用户ID
        user_id = current_user.get("username")
        if not user_id:
            ou = current_user.get("original_user")
            if ou:
                user_id = ou.username

        # 排除当前用户已隐藏的文章
        if user_id:
            from core.models.user_hidden_article import UserHiddenArticle
            hidden_subq = session.query(UserHiddenArticle.article_id).filter(
                UserHiddenArticle.user_id == user_id
            ).subquery()

        # 查询发布时间更早的第一篇文章
        query = session.query(Article)\
            .filter(Article.publish_time < current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.mp_id == current_article.mp_id)
        if user_id:
            query = query.filter(Article.id.notin_(hidden_subq))
        prev_article = query.order_by(Article.publish_time.desc()).first()

        if not prev_article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40403,
                    message="没有上一篇文章"
                )
            )
        if content:
            updated, _ = sync_article_content(
                session=session,
                article=prev_article,
                preferred_mode=cfg.get("gather.content_mode", "web"),
            )
            if updated:
                clear_cache_pattern("articles_list")
                clear_cache_pattern("article_detail")
                clear_cache_pattern("home_page")
                clear_cache_pattern("tag_detail")
        result = fix_article(prev_article)
        # 覆盖为当前用户的阅读状态
        if user_id:
            from core.models.user_read_article import UserReadArticle
            read = session.query(UserReadArticle).filter(
                UserReadArticle.user_id == user_id,
                UserReadArticle.article_id == prev_article.id
            ).first()
            result["is_read"] = 1 if read else 0
        return success_response(result)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取上一篇文章失败: {str(e)}"
            )
        )
