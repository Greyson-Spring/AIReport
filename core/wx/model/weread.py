"""
微信读书(Weread)通道采集器

通过微信读书 Web API 采集指定用户的：
- 书架上的书籍列表
- 每本书的划线/笔记（高亮标注）
- 阅读进度和统计信息

API 端点（需要已登录的 Cookie）:
- 书架:  https://i.weread.qq.com/shelf/sync?userVid={vid}&synckey=0
- 书籍详情: https://i.weread.qq.com/book/info?bookId={bookId}
- 笔记/划线: https://i.weread.qq.com/book/bookmarklist?bookId={bookId}
- 章节列表: https://i.weread.qq.com/book/chapterInfos?bookIds={bookId}&synckeys=0
- 评论: https://i.weread.qq.com/web/review/list?bookId={bookId}&listType=11
- 阅读统计: https://i.weread.qq.com/web/book/readstat?bookId={bookId}

认证方式:
- 需要从浏览器获取 weread.qq.com 的 Cookie
- 关键 Cookie: wr_vid, wr_skey, wr_gid, wr_fp, wr_name
- Cookie 存储在 data/wx.lic 下独立的 weread 区段
"""

import json
import time
import random
from typing import Dict, List, Optional
from core.wx.base import WxGather
from core.print import print_error, print_info, print_warning, print_success
from core.log import logger


# ---- 微信读书 API 配置 ----
WEREAD_BASE = "https://i.weread.qq.com"


class MpsWeread(WxGather):
    """
    微信读书采集器

    将以用户为中心采集：
    1. 书架上的所有书籍
    2. 每本书的笔记/划线（高亮标注）
    3. 阅读进度信息

    每本书映射为 Feed（订阅源），每条笔记/划线映射为 Article（文章）。
    """

    def __init__(self, is_add: bool = False):
        super().__init__(is_add=is_add)
        self._weread_cookies: str = ""
        self._weread_ticket: str = ""
        self._weread_vid: str = ""
        self._weread_name: str = ""

    def _load_weread_auth(self):
        """加载微信读书的 Cookie"""
        from core.config import Config, cfg as app_cfg
        import os

        lic_path = "./data/wx.lic"
        os.makedirs(os.path.dirname(lic_path), exist_ok=True)
        if not os.path.exists(lic_path):
            with open(lic_path, "w") as f:
                f.write("{}")

        weread_cfg = Config(lic_path)
        weread_data = weread_cfg.get("weread_data", {})
        if isinstance(weread_data, str):
            try:
                weread_data = json.loads(weread_data)
            except Exception:
                weread_data = {}

        self._weread_cookies = app_cfg.get("weread.cookie", "") or weread_data.get("cookie", "")
        self._weread_ticket = app_cfg.get("weread.ticket", "") or weread_data.get("ticket", "")
        self._weread_vid = app_cfg.get("weread.vid", "") or weread_data.get("vid", "")
        self._weread_name = weread_data.get("name", "")

    def _weread_get(self, url: str, params: dict = None) -> Optional[dict]:
        """带微信读书 Cookie 的 GET 请求"""
        import requests

        headers = {
            "Cookie": self._weread_cookies,
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://weread.qq.com/",
        }

        try:
            proxies = self._get_proxies()
            resp = requests.get(
                url, params=params, headers=headers, proxies=proxies, timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401 or resp.status_code == 403:
                print_warning(f"Weread API 认证失败: {resp.status_code}")
                return None
            else:
                print_warning(f"Weread API 返回 {resp.status_code}: {url}")
                return None
        except requests.exceptions.Timeout:
            print_warning(f"Weread API 超时: {url}")
            return None
        except Exception as e:
            print_warning(f"Weread API 异常: {e}")
            return None

    def _get_shelf_books(self) -> List[Dict]:
        """获取书架上的所有书籍"""
        if not self._weread_vid:
            print_error("微信读书 vid 未设置，请先在管理页保存 Cookie")
            return []

        url = f"{WEREAD_BASE}/shelf/sync"
        params = {
            "userVid": self._weread_vid,
            "synckey": 0,
            "lectureSynckey": 0,
        }

        data = self._weread_get(url, params)
        if not data:
            return []

        books = []
        # 书架数据格式: {"books": [...], "synckey": xxx}
        raw_books = data.get("books", [])
        for item in raw_books:
            book_id = str(item.get("bookId", ""))
            if not book_id:
                continue
            books.append({
                "book_id": book_id,
                "title": item.get("title", ""),
                "author": item.get("author", ""),
                "cover": item.get("cover", ""),
                "intro": item.get("intro", ""),
                "category": item.get("category", ""),
                "progress": item.get("progress", 0),
                "chapterUid": item.get("chapterUid", 0),
                "update_time": item.get("updateTime", 0),
                "readingTime": item.get("readingTime", 0),
                "finishedDate": item.get("finishedDate", 0),
                "format": item.get("format", ""),
            })
        return books

    def _get_book_bookmarks(self, book_id: str) -> List[Dict]:
        """获取一本书的划线/笔记"""
        url = f"{WEREAD_BASE}/book/bookmarklist"
        params = {"bookId": book_id}

        data = self._weread_get(url, params)
        if not data:
            return []

        # 笔记数据格式: {"updated": [...], "synckey": xxx}
        bookmarks = data.get("updated", [])
        result = []
        for bm in bookmarks:
            result.append({
                "bookmark_id": bm.get("bookmarkId", ""),
                "chapter_uid": bm.get("chapterUid", 0),
                "chapter_name": bm.get("chapterName", ""),
                "content": bm.get("markText", ""),
                "note": bm.get("content", ""),  # 用户自己的笔记
                "style": bm.get("style", 0),     # 划线样式
                "type": bm.get("type", 0),       # 类型(0=划线,1=其他)
                "create_time": bm.get("createTime", 0),
                "update_time": bm.get("updateTime", 0),
                "range": bm.get("range", ""),
                "color_style": bm.get("colorStyle", 0),
                "book_version": bm.get("bookVersion", 0),
            })
        return result

    def _get_book_info(self, book_id: str) -> Optional[Dict]:
        """获取书籍详情"""
        url = f"{WEREAD_BASE}/book/info"
        params = {"bookId": book_id}

        data = self._weread_get(url, params)
        if not data:
            return None

        return {
            "book_id": str(data.get("bookId", book_id)),
            "title": data.get("title", ""),
            "author": data.get("author", ""),
            "cover": data.get("cover", ""),
            "intro": data.get("intro", ""),
            "category": data.get("category", ""),
            "publisher": data.get("publisher", ""),
            "translator": data.get("translator", ""),
            "isbn": data.get("isbn", ""),
            "totalWords": data.get("totalWords", 0),
            "price": data.get("price", 0),
            "originalPrice": data.get("originalPrice", 0),
            "publishTime": data.get("publishTime", ""),
            "rating": data.get("newRating", 0),
            "ratingCount": data.get("newRatingCount", 0),
            "reviewCount": data.get("newReviewCount", 0),
            "type": data.get("type", 0),
        }

    def _get_chapter_info(self, book_id: str) -> List[Dict]:
        """获取书籍章节列表"""
        url = f"{WEREAD_BASE}/book/chapterInfos"
        params = {"bookIds": book_id, "synckeys": 0}

        data = self._weread_get(url, params)
        if not data or not data.get("data"):
            return []

        chapters = []
        for chapter_data in data["data"]:
            if not chapter_data:
                continue
            updated = chapter_data.get("updated", [])
            for ch in updated:
                chapters.append({
                    "chapter_uid": ch.get("chapterUid", 0),
                    "chapter_idx": ch.get("chapterIdx", 0),
                    "title": ch.get("title", ""),
                    "word_count": ch.get("wordCount", 0),
                    "update_time": ch.get("updateTime", 0),
                    "pay_status": ch.get("payStatus", 0),
                })
        return chapters

    def _extract_vid_from_cookie(self, cookie_str: str) -> str:
        """从 Cookie 字符串中提取 wr_vid"""
        if not cookie_str:
            return ""
        for item in cookie_str.split(";"):
            item = item.strip()
            if item.startswith("wr_vid="):
                return item.replace("wr_vid=", "").strip()
        return ""

    def content_extract(self, url: str) -> str:
        """微信读书暂不需要外部链接内容提取"""
        return ""

    def get_Articles(
        self,
        faker_id: str = None,
        Mps_id: str = None,
        Mps_title="",
        CallBack=None,
        start_page: int = 0,
        MaxPage: int = 1,
        interval=10,
        Gather_Content=False,
        Item_Over_CallBack=None,
        Over_CallBack=None,
    ):
        """
        微信读书主入口：采集笔记/划线

        工作流程:
        1. 加载微信读书 Cookie
        2. 通过 faker_id (即 bookId) 直接采集该书的划线/笔记
        3. 如果 faker_id 为空，则遍历所有书架书籍
        4. 每条划线/笔记作为一条 Article 输出
        """
        super().Start(mp_id=Mps_id)
        if self.Gather_Content:
            Gather_Content = True

        # 加载微信读书的认证信息
        self._load_weread_auth()

        if not self._weread_cookies:
            super().Error("微信读书 Cookie 未配置，请在管理页设置", code="Invalid Session")
            return

        # 自动提取 vid
        if not self._weread_vid:
            self._weread_vid = self._extract_vid_from_cookie(self._weread_cookies)

        if not self._weread_vid:
            super().Error("无法从 Cookie 中提取 wr_vid，请检查 Cookie 是否完整")
            return

        print_info(f"微信读书采集模式，用户: {self._weread_name or '未知'}")
        print_info(f"源标识: {Mps_title} (bookId={faker_id})\n")

        all_bookmarks = []

        if faker_id and faker_id.strip():
            # 指定了 bookId，直接采集该书的笔记
            print_info(f"采集书籍 {Mps_title} 的笔记/划线...")
            bookmarks = self._get_book_bookmarks(faker_id)
            for bm in bookmarks:
                bm["book_id"] = faker_id
                bm["book_title"] = Mps_title
            all_bookmarks = bookmarks
            print_info(f"获取到 {len(all_bookmarks)} 条笔记/划线")
        else:
            # 未指定 bookId，遍历书架采集所有书的笔记
            print_info("获取书架书籍列表...")
            books = self._get_shelf_books()
            print_info(f"书架上共 {len(books)} 本书")

            if not books:
                print_warning("书架上没有书籍或获取失败")
                super().Over(CallBack=Over_CallBack)
                return

            for idx, book in enumerate(books):
                book_id = book["book_id"]
                book_title = book["title"]

                print_info(f"[{idx+1}/{len(books)}] 采集《{book_title}》的笔记...")
                time.sleep(random.randint(1, interval))

                try:
                    bookmarks = self._get_book_bookmarks(book_id)
                    for bm in bookmarks:
                        bm["book_id"] = book_id
                        bm["book_title"] = book_title
                    all_bookmarks.extend(bookmarks)
                    print_info(f"  《{book_title}》: {len(bookmarks)} 条笔记")
                except Exception as e:
                    print_error(f"  《{book_title}》采集失败: {e}")

                print_info(f"已采集 {len(all_bookmarks)} 条笔记")

            print_success(f"全部笔记采集完成，共 {len(all_bookmarks)} 条")

        # 将笔记输出为标准 Article 格式
        for bm in all_bookmarks:
            # 构造文章数据 - 划线内容作为 title，笔记作为 content
            mark_text = bm.get("content", "") or bm.get("markText", "")
            note = bm.get("note", "")
            book_title = bm.get("book_title", Mps_title)
            chapter_name = bm.get("chapter_name", "")

            # 标题: 书中原文摘录（截断显示）
            title = mark_text[:200] if mark_text else f"《{book_title}》笔记"
            if chapter_name:
                title = f"[{chapter_name}] {title}"

            # 正文: 包含完整划线内容和笔记
            content_parts = [f"「{mark_text}」"] if mark_text else []
            if note:
                content_parts.append(f"\n\n>>> 我的笔记:\n{note}")
            content = "\n".join(content_parts)

            item = {
                "aid": bm.get("bookmark_id", "") or str(int(time.time() * 1000)),
                "title": title,
                "link": f"https://weread.qq.com/web/reader/{bm.get('book_id', '')}",
                "cover": "",
                "digest": mark_text[:500] if mark_text else "",
                "content": content,
                "create_time": bm.get("create_time", 0),
                "update_time": bm.get("update_time", 0),
                "item_show_type": 0,
                "copyright_stat": 1,
                # 扩展信息
                "book_id": bm.get("book_id", ""),
                "book_title": book_title,
                "chapter_name": chapter_name,
                "note_text": note,
                "style": bm.get("style", 0),
            }

            item["id"] = item["aid"]
            item["mp_id"] = Mps_id

            if CallBack is not None:
                super().FillBack(
                    CallBack=CallBack,
                    data=item,
                    Ext_Data={"mp_title": Mps_title, "mp_id": Mps_id},
                )

        super().Over(CallBack=Over_CallBack)

    # ---- 辅助方法 ----

    def test_auth(self) -> dict:
        """
        测试微信读书认证是否有效
        返回: {"ok": bool, "name": str, "vid": str, "book_count": int, "error": str}
        """
        self.get_token()  # 加载基础配置
        self._load_weread_auth()

        if not self._weread_cookies:
            return {"ok": False, "name": "", "vid": "", "book_count": 0, "error": "Cookie 未配置"}

        if not self._weread_vid:
            self._weread_vid = self._extract_vid_from_cookie(self._weread_cookies)

        if not self._weread_vid:
            return {"ok": False, "name": "", "vid": "", "book_count": 0, "error": "Cookie 中未找到 wr_vid"}

        books = self._get_shelf_books()
        if books is None:
            return {"ok": False, "name": "", "vid": self._weread_vid, "book_count": 0, "error": "API 请求失败，Cookie 可能已过期"}

        # 尝试获取用户名
        name = self._weread_name
        if not name and books:
            # 从第一本书尝试获取更多信息
            pass

        return {
            "ok": True,
            "name": name,
            "vid": self._weread_vid,
            "book_count": len(books),
            "error": "",
        }
