import sys
sys.path.insert(0, '/app')
from core.db import DB
from core.models.feed import Feed
from core.models.article import Article
from core.models.user_feed import UserFeed
from core.models.user_read_article import UserReadArticle
from core.models.user_hidden_article import UserHiddenArticle
from core.models.user_favorite import UserFavorite
from core.models.ai_report_history import AIReportHistory
from core.models.filter_rule import FilterRule
from core.models.folder import Folder, FolderFeed

NAMES = ['月之暗面 Kimi']

session = DB.get_session()
try:
    for name in NAMES:
        feeds = session.query(Feed).filter(Feed.mp_name == name).all()
        if not feeds:
            print(f'未找到: {name}')
            continue
        for feed in feeds:
            fid = feed.id
            art_ids = [r[0] for r in session.query(Article.id).filter(Article.mp_id == fid).all()]
            if art_ids:
                session.query(UserReadArticle).filter(UserReadArticle.article_id.in_(art_ids)).delete(synchronize_session=False)
                session.query(UserHiddenArticle).filter(UserHiddenArticle.article_id.in_(art_ids)).delete(synchronize_session=False)
                session.query(UserFavorite).filter(UserFavorite.article_id.in_(art_ids)).delete(synchronize_session=False)
            session.query(Article).filter(Article.mp_id == fid).delete(synchronize_session=False)
            session.query(UserFeed).filter(UserFeed.feed_id == fid).delete(synchronize_session=False)
            session.query(FilterRule).filter(FilterRule.mp_id == fid).delete(synchronize_session=False)
            session.query(FolderFeed).filter(FolderFeed.feed_id == fid).delete(synchronize_session=False)
            session.query(AIReportHistory).filter(AIReportHistory.mp_id == fid).delete(synchronize_session=False)
            session.query(Feed).filter(Feed.id == fid).delete(synchronize_session=False)
            print(f'已删除: {name} ({fid}), 文章 {len(art_ids)} 篇')
    session.commit()
    print('=== 删除完成 ===')
except Exception as e:
    session.rollback()
    print(f'出错已回滚: {e}')
finally:
    session.close()
