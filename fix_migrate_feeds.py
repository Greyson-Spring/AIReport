"""
数据库迁移：添加 user_feeds 表，迁移 feeds.user_id 数据

操作步骤：
1. 创建 user_feeds 表（如不存在）
2. 从 feeds 表迁移现有 user_id 数据到 user_feeds
3. 删除 feeds 表的 user_id 列
4. 清理重复的 feed 记录（同一个公众号被多个用户创建的多条记录合并为一条）

安全：幂等，可重复执行。
"""
import os
import sys
from datetime import datetime
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import cfg
from core.print import print_success, print_info, print_warning, print_error


def user_feeds_table_exists(engine: Engine) -> bool:
    """检查 user_feeds 表是否存在"""
    inspector = inspect(engine)
    return "user_feeds" in inspector.get_table_names()


def feeds_has_user_id(engine: Engine) -> bool:
    """检查 feeds 表是否有 user_id 列"""
    inspector = inspect(engine)
    try:
        columns = {col["name"] for col in inspector.get_columns("feeds")}
        return "user_id" in columns
    except Exception:
        return False


def create_user_feeds_table(engine: Engine) -> bool:
    """创建 user_feeds 表"""
    if user_feeds_table_exists(engine):
        print_info("user_feeds 表已存在，跳过创建")
        return False

    is_mysql = cfg.get("db", "").startswith("mysql")
    is_sqlite = cfg.get("db", "").startswith("sqlite")

    with engine.begin() as conn:
        if is_mysql:
            conn.execute(text("""
                CREATE TABLE user_feeds (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
                    user_id VARCHAR(100) NOT NULL COMMENT '用户ID',
                    feed_id VARCHAR(255) NOT NULL COMMENT '公众号ID',
                    status INT DEFAULT 1 COMMENT '订阅状态: 1=启用, 0=停用',
                    disabled_at DATETIME NULL COMMENT '停用时间',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    INDEX idx_user_feeds_user (user_id),
                    INDEX idx_user_feeds_feed (feed_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-公众号订阅关系'
            """))
        elif is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(100) NOT NULL,
                    feed_id VARCHAR(255) NOT NULL,
                    status INTEGER DEFAULT 1,
                    disabled_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_feeds_user ON user_feeds(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_feeds_feed ON user_feeds(feed_id)"))
        else:
            # PostgreSQL
            conn.execute(text("""
                CREATE TABLE user_feeds (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    feed_id VARCHAR(255) NOT NULL,
                    status INTEGER DEFAULT 1,
                    disabled_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_user_feeds_user ON user_feeds(user_id)"))
            conn.execute(text("CREATE INDEX idx_user_feeds_feed ON user_feeds(feed_id)"))

    print_success("user_feeds 表创建成功")
    return True


def user_favorites_table_exists(engine: Engine) -> bool:
    """检查 user_favorites 表是否存在"""
    inspector = inspect(engine)
    return "user_favorites" in inspector.get_table_names()


def create_user_favorites_table(engine: Engine) -> bool:
    """创建 user_favorites 表（用户文章收藏关联）"""
    if user_favorites_table_exists(engine):
        print_info("user_favorites 表已存在，跳过创建")
        return False

    is_mysql = cfg.get("db", "").startswith("mysql")
    is_sqlite = cfg.get("db", "").startswith("sqlite")

    with engine.begin() as conn:
        if is_mysql:
            conn.execute(text("""
                CREATE TABLE user_favorites (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
                    user_id VARCHAR(100) NOT NULL COMMENT '用户ID',
                    article_id VARCHAR(255) NOT NULL COMMENT '文章ID',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '收藏时间',
                    INDEX idx_user_fav_user (user_id),
                    INDEX idx_user_fav_article (article_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户文章收藏关联'
            """))
        elif is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(100) NOT NULL,
                    article_id VARCHAR(255) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_fav_user ON user_favorites(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_fav_article ON user_favorites(article_id)"))
        else:
            # PostgreSQL
            conn.execute(text("""
                CREATE TABLE user_favorites (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    article_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_user_fav_user ON user_favorites(user_id)"))
            conn.execute(text("CREATE INDEX idx_user_fav_article ON user_favorites(article_id)"))

    print_success("user_favorites 表创建成功")
    return True


def migrate_existing_favorites(engine: Engine) -> int:
    """
    迁移已有的收藏数据到 user_favorites 表。
    对于 articles 表中 is_favorite=1 的文章，为每个现有用户创建收藏记录。
    这样可以保持迁移前后的体验一致（之前是全局收藏，迁移后每个用户都能看到）。
    """
    if not user_favorites_table_exists(engine):
        print_info("user_favorites 表不存在，跳过收藏数据迁移")
        return 0

    # 先检查是否已有数据，避免重复迁移
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        existing_count = session.execute(
            text("SELECT COUNT(*) FROM user_favorites")
        ).scalar()
        if existing_count and existing_count > 0:
            print_info(f"user_favorites 表已有 {existing_count} 条记录，跳过迁移")
            return 0

        # 获取所有 is_favorite=1 的文章
        fav_articles = session.execute(
            text("SELECT id, created_at FROM articles WHERE is_favorite = 1 OR is_favorite = '1'")
        ).fetchall()
        if not fav_articles:
            print_info("没有需要迁移的收藏文章")
            return 0

        # 获取所有用户
        users = session.execute(
            text("SELECT DISTINCT user_id FROM user_feeds WHERE user_id IS NOT NULL AND user_id != ''")
        ).fetchall()
        all_users = [row[0] for row in users]

        if not all_users:
            print_info("没有用户数据，跳过收藏迁移")
            return 0

        migrated = 0
        now = datetime.now()
        for article_id, article_created_at in fav_articles:
            for uid in all_users:
                existing = session.execute(
                    text("SELECT id FROM user_favorites WHERE user_id = :uid AND article_id = :aid"),
                    {"uid": uid, "aid": article_id}
                ).fetchone()
                if not existing:
                    session.execute(
                        text("INSERT INTO user_favorites (user_id, article_id, created_at) VALUES (:uid, :aid, :ca)"),
                        {"uid": uid, "aid": article_id, "ca": article_created_at or now}
                    )
                    migrated += 1

        if migrated > 0:
            session.commit()
            print_success(f"已迁移 {migrated} 条收藏记录到 user_favorites 表（为 {len(all_users)} 个用户，{len(fav_articles)} 篇文章）")
        else:
            print_info("没有需要迁移的收藏记录")

        return migrated


def user_read_articles_table_exists(engine: Engine) -> bool:
    """检查 user_read_articles 表是否存在"""
    inspector = inspect(engine)
    return "user_read_articles" in inspector.get_table_names()


def user_hidden_articles_table_exists(engine: Engine) -> bool:
    """检查 user_hidden_articles 表是否存在"""
    inspector = inspect(engine)
    return "user_hidden_articles" in inspector.get_table_names()


def create_user_read_articles_table(engine: Engine) -> bool:
    """创建 user_read_articles 表（用户文章阅读状态）"""
    if user_read_articles_table_exists(engine):
        print_info("user_read_articles 表已存在，跳过创建")
        return False

    is_mysql = cfg.get("db", "").startswith("mysql")
    is_sqlite = cfg.get("db", "").startswith("sqlite")

    with engine.begin() as conn:
        if is_mysql:
            conn.execute(text("""
                CREATE TABLE user_read_articles (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
                    user_id VARCHAR(100) NOT NULL COMMENT '用户ID',
                    article_id VARCHAR(255) NOT NULL COMMENT '文章ID',
                    read_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '阅读时间',
                    INDEX idx_read_user (user_id),
                    INDEX idx_read_article (article_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户文章阅读状态'
            """))
        elif is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_read_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(100) NOT NULL,
                    article_id VARCHAR(255) NOT NULL,
                    read_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_read_user ON user_read_articles(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_read_article ON user_read_articles(article_id)"))
        else:
            conn.execute(text("""
                CREATE TABLE user_read_articles (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    article_id VARCHAR(255) NOT NULL,
                    read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_read_user ON user_read_articles(user_id)"))
            conn.execute(text("CREATE INDEX idx_read_article ON user_read_articles(article_id)"))

    print_success("user_read_articles 表创建成功")
    return True


def create_user_hidden_articles_table(engine: Engine) -> bool:
    """创建 user_hidden_articles 表（用户文章隐藏/按用户删除）"""
    if user_hidden_articles_table_exists(engine):
        print_info("user_hidden_articles 表已存在，跳过创建")
        return False

    is_mysql = cfg.get("db", "").startswith("mysql")
    is_sqlite = cfg.get("db", "").startswith("sqlite")

    with engine.begin() as conn:
        if is_mysql:
            conn.execute(text("""
                CREATE TABLE user_hidden_articles (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
                    user_id VARCHAR(100) NOT NULL COMMENT '用户ID',
                    article_id VARCHAR(255) NOT NULL COMMENT '文章ID',
                    hidden_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '隐藏时间',
                    INDEX idx_hidden_user (user_id),
                    INDEX idx_hidden_article (article_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户文章隐藏关联'
            """))
        elif is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_hidden_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(100) NOT NULL,
                    article_id VARCHAR(255) NOT NULL,
                    hidden_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_hidden_user ON user_hidden_articles(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_hidden_article ON user_hidden_articles(article_id)"))
        else:
            conn.execute(text("""
                CREATE TABLE user_hidden_articles (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    article_id VARCHAR(255) NOT NULL,
                    hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_hidden_user ON user_hidden_articles(user_id)"))
            conn.execute(text("CREATE INDEX idx_hidden_article ON user_hidden_articles(article_id)"))

    print_success("user_hidden_articles 表创建成功")
    return True


def migrate_feeds_user_id(engine: Engine) -> int:
    """
    迁移 feeds.user_id 数据到 user_feeds
    返回迁移记录数
    """
    if not feeds_has_user_id(engine):
        print_info("feeds 表没有 user_id 列或已迁移，跳过数据迁移")
        return 0

    from core.models.user_feed import UserFeed
    from sqlalchemy.orm import Session
    from sqlalchemy import text as sql_text

    migrated = 0
    with Session(engine) as session:
        # 查出所有有 user_id 的 feed 记录
        rows = session.execute(
            sql_text("SELECT id, user_id, created_at FROM feeds WHERE user_id IS NOT NULL AND user_id != ''")
        ).fetchall()

        for feed_id, user_id, created_at in rows:
            # 检查是否已存在
            existing = session.execute(
                sql_text(
                    "SELECT id FROM user_feeds WHERE user_id = :uid AND feed_id = :fid"
                ),
                {"uid": user_id, "fid": feed_id}
            ).fetchone()
            if existing:
                continue

            now = datetime.now()
            session.execute(
                sql_text(
                    "INSERT INTO user_feeds (user_id, feed_id, status, created_at, updated_at) "
                    "VALUES (:uid, :fid, 1, :ca, :ua)"
                ),
                {"uid": user_id, "fid": feed_id, "ca": created_at or now, "ua": now}
            )
            migrated += 1

        if migrated > 0:
            session.commit()

    if migrated > 0:
        print_success(f"已迁移 {migrated} 条订阅记录到 user_feeds 表")
    else:
        print_info("没有需要迁移的订阅记录")

    return migrated


def merge_duplicate_feeds(engine: Engine) -> int:
    """
    合并重复的 feed 记录：同一个 faker_id 出现多次时，保留第一条，将其余的文章指向保留的记录。
    返回删除的重复记录数。
    注：仅在有 user_id 列且可能产生重复时才有意义。
    """
    if not feeds_has_user_id(engine):
        return 0

    from sqlalchemy.orm import Session
    from sqlalchemy import text as sql_text

    cleaned = 0
    with Session(engine) as session:
        # 找出有重复 faker_id 且不为空的记录
        dup_faker_ids = session.execute(
            sql_text("""
                SELECT faker_id FROM feeds
                WHERE faker_id IS NOT NULL AND faker_id != ''
                GROUP BY faker_id
                HAVING COUNT(*) > 1
            """)
        ).fetchall()

        for (faker_id,) in dup_faker_ids:
            dups = session.execute(
                sql_text("SELECT id FROM feeds WHERE faker_id = :fid ORDER BY created_at ASC"),
                {"fid": faker_id}
            ).fetchall()

            if len(dups) < 2:
                continue

            keep_id = dups[0][0]
            remove_ids = [d[0] for d in dups[1:]]

            # 将重复 feed 的文章指向保留的 feed
            for rid in remove_ids:
                session.execute(
                    sql_text("UPDATE articles SET mp_id = :keep WHERE mp_id = :remove"),
                    {"keep": keep_id, "remove": rid}
                )
                session.execute(
                    sql_text("DELETE FROM user_feeds WHERE feed_id = :remove"),
                    {"remove": rid}
                )
                session.execute(
                    sql_text("DELETE FROM folder_feeds WHERE feed_id = :remove"),
                    {"remove": rid}
                )
                session.execute(
                    sql_text("DELETE FROM feeds WHERE id = :remove"),
                    {"remove": rid}
                )
                cleaned += 1

        if cleaned > 0:
            session.commit()

    if cleaned > 0:
        print_success(f"已合并 {cleaned} 条重复的 feed 记录")
    else:
        print_info("没有需要合并的重复记录")

    return cleaned


def drop_user_id_from_feeds(engine: Engine) -> bool:
    """删除 feeds 表的 user_id 列"""
    if not feeds_has_user_id(engine):
        print_info("feeds 表没有 user_id 列，跳过删除")
        return False

    is_sqlite = cfg.get("db", "").startswith("sqlite")
    is_mysql = cfg.get("db", "").startswith("mysql")

    with engine.begin() as conn:
        if is_sqlite:
            # SQLite 不支持 DROP COLUMN 直接操作，需要重建表
            # 但 SQLite 3.35.0+ 支持 DROP COLUMN
            try:
                conn.execute(text("ALTER TABLE feeds DROP COLUMN user_id"))
                print_success("feeds.user_id 列已删除")
                return True
            except Exception:
                print_warning("当前 SQLite 版本不支持 DROP COLUMN，尝试重建表...")
                _sqlite_rebuild_feeds_table(conn)
                return True
        elif is_mysql:
            conn.execute(text("ALTER TABLE feeds DROP COLUMN user_id"))
            print_success("feeds.user_id 列已删除")
            return True
        else:
            conn.execute(text("ALTER TABLE feeds DROP COLUMN user_id"))
            print_success("feeds.user_id 列已删除")
            return True

    return False


def _sqlite_rebuild_feeds_table(conn):
    """SQLite 重建 feeds 表（去掉 user_id 列）"""
    # 1. 获取旧表 schema
    result = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='feeds'"))
    row = result.fetchone()
    if not row:
        return
    old_sql = row[0]

    # 2. 创建不含 user_id 的新表
    conn.execute(text("""
        CREATE TABLE feeds_new (
            id VARCHAR(255) PRIMARY KEY,
            mp_name VARCHAR(255),
            mp_cover VARCHAR(255),
            mp_intro VARCHAR(255),
            status INTEGER,
            sync_time INTEGER,
            update_time INTEGER,
            created_at DATETIME,
            updated_at DATETIME,
            faker_id VARCHAR(255)
        )
    """))

    # 3. 复制数据
    conn.execute(text("""
        INSERT INTO feeds_new (id, mp_name, mp_cover, mp_intro, status, sync_time, update_time, created_at, updated_at, faker_id)
        SELECT id, mp_name, mp_cover, mp_intro, status, sync_time, update_time, created_at, updated_at, faker_id FROM feeds
    """))

    # 4. 删除旧表，重命名新表
    conn.execute(text("DROP TABLE feeds"))
    conn.execute(text("ALTER TABLE feeds_new RENAME TO feeds"))

    print_success("feeds 表已重建（去掉 user_id 列）")


def run_migration():
    """执行所有迁移步骤"""
    print_info("=" * 50)
    print_info("开始 user_feeds 数据迁移...")
    print_info("=" * 50)

    from core.db import DB
    engine = DB.get_engine()

    # Step 1: 创建 user_feeds 表
    create_user_feeds_table(engine)

    # Step 2: 迁移现有 user_id 数据
    migrate_feeds_user_id(engine)

    # Step 3: 合并重复 feeds
    merge_duplicate_feeds(engine)

    # Step 4: 删除 feeds.user_id 列
    drop_user_id_from_feeds(engine)

    print_success("=" * 50)
    print_success("user_feeds 迁移完成")
    print_success("=" * 50)

    # ===== 新增：user_favorites 表迁移 =====
    print_info("=" * 50)
    print_info("开始 user_favorites 数据迁移...")
    print_info("=" * 50)

    # Step 5: 创建 user_favorites 表
    create_user_favorites_table(engine)

    # Step 6: 迁移现有收藏数据
    migrate_existing_favorites(engine)

    print_success("=" * 50)
    print_success("user_favorites 迁移完成")
    print_success("=" * 50)

    # ===== 新增：user_read_articles 和 user_hidden_articles 表迁移 =====
    print_info("=" * 50)
    print_info("开始 user_read_articles / user_hidden_articles 迁移...")
    print_info("=" * 50)

    # Step 7: 创建 user_read_articles 表
    create_user_read_articles_table(engine)

    # Step 8: 创建 user_hidden_articles 表
    create_user_hidden_articles_table(engine)

    print_success("=" * 50)
    print_success("阅读/隐藏状态表迁移完成")
    print_success("=" * 50)


if __name__ == "__main__":
    run_migration()
