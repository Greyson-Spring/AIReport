#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键补抓指定公众号所有空正文文章(优先走账号池Chrome通道)

用法:
    docker exec -it we-mp-rss-local python tools/backfill_content.py "百度文心"
    docker exec -it we-mp-rss-local python tools/backfill_content.py MP_WXS_xxx
    docker exec -it we-mp-rss-local python tools/backfill_content.py "百度文心" 50   # 只补最近50篇
"""
import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_
from core.db import DB
from core.models.article import Article
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.article_content import sync_article_content
from core.print import print_success, print_error, print_info


def find_mp(session, keyword):
    if str(keyword).startswith("MP_WXS_"):
        feeds = session.query(Feed).filter(Feed.id == keyword).all()
    else:
        feeds = session.query(Feed).filter(Feed.mp_name.like(f"%{keyword}%")).all()
    if not feeds:
        print_error(f"未找到公众号: {keyword}")
        sys.exit(1)
    if len(feeds) > 1:
        print_info("匹配到多个公众号, 默认使用第一个:")
        for f in feeds:
            print_info(f"  {f.id}  {f.mp_name}")
    return feeds[0]


def main():
    if len(sys.argv) < 2:
        print('用法: python tools/backfill_content.py "公众号名称或ID" [数量]')
        sys.exit(1)
    keyword = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    session = DB.get_session()
    mp = find_mp(session, keyword)

    query = session.query(Article).filter(
        Article.mp_id == mp.id,
        or_(Article.content.is_(None), Article.content == ""),
        Article.status != DATA_STATUS.DELETED,
    ).order_by(Article.publish_time.desc())
    total = query.count()
    if limit and limit > 0:
        query = query.limit(limit)
    articles = query.all()

    print_info(f"公众号 [{mp.mp_name}] ({mp.id}) 共 {total} 篇空正文文章, 本次补 {len(articles)} 篇...")
    ok = fail = 0
    for i, art in enumerate(articles, 1):
        try:
            updated, mode = sync_article_content(session=session, article=art)
            if updated:
                ok += 1
                print_success(f"[{i}/{len(articles)}] 已补: {str(art.title)[:30]} (mode={mode})")
            else:
                fail += 1
                print_error(f"[{i}/{len(articles)}] 失败: {str(art.title)[:30]} (mode={mode})")
        except Exception as e:
            fail += 1
            print_error(f"[{i}/{len(articles)}] 异常: {e}")
        if i < len(articles):
            time.sleep(random.randint(3, 6))
    print("=" * 50)
    print_success(f"完成: 成功 {ok} 篇, 失败 {fail} 篇")
    session.close()


if __name__ == "__main__":
    main()
