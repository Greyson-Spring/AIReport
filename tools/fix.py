import re
from core.models.article import Article

# 微信图床域名: 图片地址改走后端代理(/static/res/logo/...), 解决防盗链
_PROXY_IMG_RE = re.compile(
    r'(<img[^>]*?src=["\'])(https?://(?:mmbiz\.qpic\.cn|mmbiz\.qlogo\.cn|mmecoa\.qpic\.cn)/[^"\']*)',
    re.IGNORECASE,
)

def proxy_content_images(content: str) -> str:
    if not content:
        return content
    return _PROXY_IMG_RE.sub(r'\1/static/res/logo/\2', content)

def sanitize_utf8(content: str) -> str:
    """清理字符串中的非法UTF-8字符"""
    if not content:
        return ""
    try:
        if isinstance(content, str):
            return content.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        elif isinstance(content, bytes):
            return content.decode('utf-8', errors='ignore')
        return str(content)
    except Exception:
        return ""

def normalize_article_images(content: str) -> str:
    """微信懒加载图片处理: data-src 才是真实地址, 转成 src; 空src/占位图直接删掉"""
    if not content:
        return content
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        changed = False
        for img in soup.find_all('img'):
            data_src = (img.get('data-src') or '').strip()
            src = (img.get('src') or '').strip()
            if data_src:
                img['src'] = data_src
                changed = True
            elif not src or src.startswith('data:'):
                img.decompose()
                changed = True
            if 'data-src' in img.attrs:
                del img['data-src']
                changed = True
        return str(soup) if changed else content
    except Exception:
        return content

def fix_html(content: str):
    if not content:
        return ""
    content = sanitize_utf8(content)
    from core.content_format import format_content
    from tools.mdtools.md2html import convert_markdown_to_html
    from tools.htmltools import htmltools

    # 1. 先归一化图片(data-src→真实src, 删占位图), 避免markdown转换把图片弄丢
    content = normalize_article_images(content)
    # 2. 提前把微信图片改成代理地址(相对地址不会被markdown转坏)
    content = proxy_content_images(content)
    # 3. 清理无用元素(不再用 remove_attributes=[{'src': ''}], 那个会把所有图片删掉)
    content = htmltools.clean_html(content,
                         remove_selectors=["link", "head", "script"],
                         remove_ids=['content_bottom_interaction','activity-name','meta_content',"js_article_bottom_bar","js_pc_weapp_code","js_novel_card","js_pc_qr_code"]
                         )
    if not content:
        return ""
    content = format_content(content, content_format='markdown')
    if not content:
        return ""
    content = convert_markdown_to_html(content)
    # 4. 再兜底重写一次(转换后若又冒出直连微信图片地址)
    content = proxy_content_images(content)
    return content

def fix_article(article):
    art = article.to_dict()
    art['content'] = fix_html(art.get('content') or "")
    return art
