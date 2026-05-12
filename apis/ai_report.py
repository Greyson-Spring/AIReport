import io
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.article import Article
from .base import success_response, error_response
from docx import Document
from docx.shared import Pt, Inches, RGBColor  # 设置全局段落间距
from docx.enum.text import WD_ALIGN_PARAGRAPH
from core.models.ai_report_history import AIReportHistory
from core.models.feed import Feed  
from core.models.folder import Folder, FolderFeed
import markdown
from bs4 import BeautifulSoup
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re

router = APIRouter(prefix="/ai", tags=["AI功能"])


class AIReportRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    prompt: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    mp_id: Optional[str] = None
    keyword: Optional[str] = None  # 关键字搜索（匹配标题和描述）
    source: Optional[str] = "all"      # all, favorite, folder，mp
    folder_id: Optional[int] = None    # 文件夹ID
    folder_name: Optional[str] = None  # 文件夹名称

DEFAULT_REPORT_PROMPT = (
    "你是一个专业的行业分析师。请根据以下多篇文章的摘要信息，"
    "生成一份结构化的分析报告。报告应包含以下部分：\n"
    "1. 概述：总结本期主要内容方向\n"
    "2. 热点分析：提炼关键话题和趋势\n"
    "3. 详细分析：对每个主要话题进行深入分析\n"
    "4. 总结与展望：给出总结性观点和未来趋势预测\n\n"
    "请使用清晰的标题和段落结构，语言专业简洁。\n\n"
)


async def _call_llm(api_url: str, api_key: str, model: str,
                    system_msg: str, user_msg: str) -> str:
    url = api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.7,
        "max_tokens": 8192
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=2000.0) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        raise Exception(f"API调用失败({resp.status_code}): {resp.text[:300]}")

    result = resp.json()
    content = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    return content.strip()
def _build_word_document(markdown_text: str, title: str, date_range: str) -> io.BytesIO:
    """
    将 Markdown 格式的报告转换为 Word 文档
    支持超链接、加粗、斜体、标题、列表等所有格式
    
    参数：
        markdown_text: Markdown 格式的报告内容（已包含一级标题）
        title: 文档主标题（从数据库 title 字段传入）
        date_range: 报告周期（如 "2026-05-01 ~ 2026-05-31"）
    
    返回：
        BytesIO 对象，可直接用于下载
    """
    
    # ========== 辅助函数1：设置中文字体 ==========
    def set_chinese_font(run, font_name='微软雅黑', font_size=None):
        """
        为 Run 对象设置中文字体
        必须同时设置 font.name 和 eastAsia 属性，否则中文会显示为 MS Gothic
        """
        run.font.name = font_name
        if font_size:
            run.font.size = Pt(font_size)
        
        # 关键：设置中文字体属性（解决中文显示为 MS Gothic 的问题）
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn('w:eastAsia'), font_name)
        rFonts.set(qn('w:ascii'), font_name)
        rFonts.set(qn('w:hAnsi'), font_name)
    
    # ========== 辅助函数2：设置标题字体 ==========
    def set_heading_font(heading, font_name='微软雅黑', font_size=None):
        """为标题设置字体"""
        if heading.runs:
            set_chinese_font(heading.runs[0], font_name, font_size)
    
    # ========== 辅助函数3：添加超链接（带样式） ==========
    def add_hyperlink(paragraph, url, text):
        """
        在段落中添加可点击的超链接，手动设置蓝色 + 下划线
        """
        
        # 获取文档部件，添加外部链接关系
        part = paragraph.part
        r_id = part.relate_to(
            url,
            'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',
            is_external=True
        )
        
        # 创建超链接 XML 元素
        hyperlink = OxmlElement('w:hyperlink')
        hyperlink.set(qn('r:id'), r_id)
        
        # 创建 run 元素
        run = OxmlElement('w:r')
        
        # ========== 手动设置字体属性 ==========
        rPr = OxmlElement('w:rPr')
        
        # 1. 设置颜色为蓝色（#0000FF）
        color = OxmlElement('w:color')
        color.set(qn('w:val'), '0000FF')
        rPr.append(color)
        
        # 2. 设置下划线（single = 单下划线）
        underline = OxmlElement('w:u')
        underline.set(qn('w:val'), 'single')
        rPr.append(underline)
        
        # 3. 设置字体为微软雅黑
        rFonts = OxmlElement('w:rFonts')
        rFonts.set(qn('w:ascii'), '微软雅黑')
        rFonts.set(qn('w:eastAsia'), '微软雅黑')
        rFonts.set(qn('w:hAnsi'), '微软雅黑')
        rPr.append(rFonts)
        
        # 将样式应用到 run
        run.append(rPr)
        
        # 添加文本
        run_text = OxmlElement('w:t')
        run_text.text = text
        run.append(run_text)
        
        # 组装
        hyperlink.append(run)
        paragraph._p.append(hyperlink)
    
    # ========== 辅助函数4：规范化 Markdown 链接 ==========
    def normalize_markdown_links(text):
        """规范化 Markdown 链接格式，修复常见的格式错误"""
        # 修复 [标题] (url) -> [标题](url)（去掉空格）
        text = re.sub(r'\[([^\]]+)\]\s*\(([^)]+)\)', r'[\1](\2)', text)
        # 修复没有方括号的链接（纯 URL 转成链接格式）
        text = re.sub(r'(?<![\[(])(https?://[^\s\)\]]+)', r'[\1](\1)', text)
        return text
    
    # ========== 第一步：去掉 markdown_text 中的一级标题 ==========
    lines = markdown_text.split('\n')
    content_without_title = []
    skip_title = False
    
    for i, line in enumerate(lines):
        if i == 0 and line.strip().startswith('# '):
            skip_title = True
            continue
        if skip_title and not line.strip():
            skip_title = False
            continue
        content_without_title.append(line)
    
    cleaned_markdown = '\n'.join(content_without_title).strip()
    if not cleaned_markdown:
        cleaned_markdown = markdown_text
    
    # ========== 第二步：规范化链接格式 ==========
    cleaned_markdown = normalize_markdown_links(cleaned_markdown)
    
    # ========== 第三步：调试日志 ==========
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    found_links = re.findall(link_pattern, cleaned_markdown)
    print(f" 检测到 {len(found_links)} 个 Markdown 链接")
    
    # ========== 第四步：创建 Word 文档 ==========
    doc = Document()
    
    # ========== 第五步：修改标题样式为黑色 ==========
    for level in range(1, 5):
        try:
            heading_style = doc.styles[f'Heading {level}']
            heading_style.font.color.rgb = RGBColor(0, 0, 0)  # 黑色
            heading_style.font.name = '微软雅黑'
            heading_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
            
            if level == 1:
                heading_style.font.size = Pt(18)
            elif level == 2:
                heading_style.font.size = Pt(16)
            elif level == 3:
                heading_style.font.size = Pt(14)
        except KeyError:
            pass
    
    # ========== 第六步：设置全局段落间距为0 ==========
    normal_style = doc.styles['Normal']
    normal_style.font.color.rgb = RGBColor(0, 0, 0)
    normal_style.font.name = '微软雅黑'
    normal_style.font.size = Pt(11)
    normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    normal_style.paragraph_format.space_after = Pt(0)
    normal_style.paragraph_format.space_before = Pt(0)
    
    # ========== 第七步：添加文档主标题 ==========
    main_title = doc.add_heading(title, level=1)
    main_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_heading_font(main_title, '微软雅黑', 22)
    
    # ========== 第八步：添加日期范围和生成时间 ==========
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_para.add_run(f"报告周期：{date_range}")
    set_chinese_font(date_run, '微软雅黑', 10)
    date_run.font.color.rgb = RGBColor(128, 128, 128)
    
    time_para = doc.add_paragraph()
    time_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    time_run = time_para.add_run(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    set_chinese_font(time_run, '微软雅黑', 10)
    time_run.font.color.rgb = RGBColor(128, 128, 128)
    
    # ========== 第九步：Markdown 转 HTML ==========
    html_content = markdown.markdown(cleaned_markdown, extensions=['extra', 'nl2br'])
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # ========== 第十步：递归处理行内元素 ==========
    def process_inline(paragraph, elem):
        """处理行内元素（文本、链接、加粗、斜体）"""
        if elem.name is None:
            if elem.string and elem.string.strip():
                run = paragraph.add_run(elem.string)
                set_chinese_font(run, '微软雅黑', 11)
            return
        
        # 处理超链接
        if elem.name == 'a':
            url = elem.get('href', '')
            text = elem.get_text(strip=True)
            if url and text:
                add_hyperlink(paragraph, url, text)
            return
        
        # 处理加粗
        if elem.name in ('strong', 'b'):
            for child in elem.children:
                process_inline(paragraph, child)
            if paragraph.runs:
                paragraph.runs[-1].bold = True
            return
        
        # 处理斜体
        if elem.name in ('em', 'i'):
            for child in elem.children:
                process_inline(paragraph, child)
            if paragraph.runs:
                paragraph.runs[-1].italic = True
            return
        
        # 其他标签，递归处理子元素
        for child in elem.children:
            process_inline(paragraph, child)
    
    # ========== 第十一步：递归处理块级元素 ==========
    def process_element(elem):
        """处理块级元素"""
        if elem.name is None:
            return
        
        if elem.name == 'h1':
            heading = doc.add_heading(elem.get_text(strip=True), level=2)
            set_heading_font(heading, '微软雅黑', 18)
        elif elem.name == 'h2':
            heading = doc.add_heading(elem.get_text(strip=True), level=2)
            set_heading_font(heading, '微软雅黑', 16)
        elif elem.name == 'h3':
            heading = doc.add_heading(elem.get_text(strip=True), level=3)
            set_heading_font(heading, '微软雅黑', 14)
        elif elem.name == 'h4':
            heading = doc.add_heading(elem.get_text(strip=True), level=4)
            set_heading_font(heading, '微软雅黑', 12)
        elif elem.name == 'p':
            # 检查段落是否有实际内容，空段落跳过
            text = elem.get_text(strip=True)
            if not text:
                return
            p = doc.add_paragraph()
            for child in elem.children:
                process_inline(p, child)
        elif elem.name == 'ul':
            for li in elem.find_all('li', recursive=False):
                p = doc.add_paragraph(style='List Bullet')
                for child in li.children:
                    process_inline(p, child)
        elif elem.name == 'ol':
            for li in elem.find_all('li', recursive=False):
                p = doc.add_paragraph(style='List Number')
                for child in li.children:
                    process_inline(p, child)
        elif elem.name == 'hr':
            p = doc.add_paragraph()
            p.add_run('_' * 50)
        else:
            for child in elem.children:
                process_element(child)
    
    # ========== 第十二步：执行解析 ==========
    for elem in soup.children:
        if elem.name is not None:
            process_element(elem)
    
    # ========== 第十三步：保存并返回 ==========
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

# ========= 生成报告并返回 Word 文件 ==========
'''
@router.post("/report", summary="AI报告生成")
async def ai_report(
    req: AIReportRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """生成报告并直接返回 Word 文件（用于下载）"""
    if not req.api_url or not req.api_key:
        return error_response(400, "请配置大模型API地址和密钥")

    try:
        start_dt = datetime.strptime(req.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(req.end_date, "%Y-%m-%d")
    except ValueError:
        return error_response(400, "日期格式错误，请使用 YYYY-MM-DD")

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) + 86399

    session = DB.get_session()
    try:
        # ========== 第一步：根据数据来源筛选公众号 ==========
        feed_ids = []  # 要查询的公众号ID列表
        
        # 精选文章：全站范围，不限制公众号，只通过 is_favorite 筛选
        if req.source == "favorite":
            pass
        elif req.source == "folder":
            if not req.folder_id:
                return error_response(400, "请提供文件夹ID")
            folder_feeds = session.query(FolderFeed).filter(
                FolderFeed.folder_id == req.folder_id
            ).all()
            feed_ids = [ff.feed_id for ff in folder_feeds]
            if not feed_ids:
                return error_response(404, f"该文件夹下没有公众号")
        else:  # source == "all"
            if req.mp_id:
                feed_ids = [req.mp_id]

        # ========== 第二步：构建文章查询 ==========
        query = session.query(Article).filter(
            Article.publish_time >= start_ts,
            Article.publish_time <= end_ts,
            Article.status == 1
        )
        
        if feed_ids:
            query = query.filter(Article.mp_id.in_(feed_ids))
        
        if req.source == "favorite":
            query = query.filter(Article.is_favorite == 1)
        
        if req.keyword:
            kw = f"%{req.keyword}%"
            query = query.filter(
                (Article.title.like(kw)) | (Article.description.like(kw))
            )

        articles = query.order_by(Article.publish_time.desc()).all()

        if not articles:
            return error_response(404, f"在 {req.start_date} ~ {req.end_date} 期间未找到文章")

        # ========== 第三步：构建文章摘要并调用AI ==========
        # 获取所有涉及的公众号ID,article中没有mp_name，需要查询feed表获取公众号名称映射
        mp_ids = list(set(art.mp_id for art in articles if art.mp_id))
        mp_name_map = {}
        if mp_ids:
            feeds = session.query(Feed).filter(Feed.id.in_(mp_ids)).all()
            mp_name_map = {f.id: f.mp_name for f in feeds}
        # 构建文章摘要列表，格式化日期和链接，并添加公众号名称
        article_summaries = []
        for art in articles:
            desc = art.description or ""
            if not desc.strip():
                desc = art.title

            # 格式化发布日期
            pub_date = datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'
            # 处理 URL（如果为空，用空字符串代替）
            article_url = art.url or ""
            # 获取公众号名称（需要从之前查询的 mp_name_map 中获取）
            # 注意：需要先查询 mp_name_map，下面的代码会补充
            mp_name = mp_name_map.get(art.mp_id, '未知公众号')
            article_summaries.append(
                f"【{art.title}】\n"
                f"公众号：{mp_name}\n"
                f"发布日期：{pub_date}\n"
                f"链接：{article_url}\n"
                f"摘要：{desc}"
            )
            # article_summaries.append(
            #     f"【{art.title}】\n发布时间：{datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'}\n摘要：{desc}"
            # )

        articles_text = "\n\n---\n\n".join(article_summaries)
        prompt = req.prompt or DEFAULT_REPORT_PROMPT
        user_message = f"{prompt}\n\n以下是 {req.start_date} 至 {req.end_date} 期间共 {len(articles)} 篇文章的摘要：\n\n{articles_text}"

        model = req.model or "gpt-3.5-turbo"
        # ========== 第四步：调用 AI，要求返回带标题的格式 ==========
        system_msg = (
            "你是一个专业的行业分析师和报告撰写专家，擅长从多篇文章中提炼趋势和洞察，生成结构化的分析报告。\n\n"
            "【输出格式要求】\n"
            "第一行必须以 'TITLE: ' 开头，后接10-15字的概括性标题，概括本期核心主题\n"
            "标题后必须空一行\n"
            "开始报告正文，使用 Markdown 格式组织\n\n"
            "【参考来源要求】\n"
            "在报告正文结束后，请添加「参考来源」章节，列出所有在报告中引用的文章。\n"
            "每条参考来源的格式如下（使用 Markdown 链接格式）：\n"
            "[序号] 文章标题(文章链接)，公众号名称，YYYY-MM-DD\n"
            "参考资料部分把链接放在标题的背后做成超链接形式，点击标题就可以跳转到原文。\n"
            "【输出禁令】\n"
            "- 正文中禁止使用一级标题（#）\n"
            "- 严禁只提供碎片化的短句，每个分析点需具备一定的论述深度；\n"
            "- 严禁输出“好的”、“这是为你生成的报告”等任何开场白或结束语。"
        )
        report_content = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not report_content:
            return error_response(500, "大模型未返回有效内容")
        # ========== 第五步：解析 AI 返回的标题和内容 ==========
        ai_title = None
        ai_content = report_content
        # 检查是否包含 TITLE: 标记
        if report_content.startswith('TITLE:'):
            lines = report_content.split('\n', 1)
            title_line = lines[0].strip()
            ai_title = title_line.replace('TITLE:', '').strip()
            if len(lines) > 1:
                ai_content = lines[1].strip()
                if ai_content.startswith('\n'):
                    ai_content = ai_content[1:]
            else:
                ai_content = report_content
        else:
            ai_content = report_content

        # ========== 第六步：确定来源类型 ==========
        if req.source == 'favorite':
            real_source = 'favorite'
        elif req.source == 'folder':
            real_source = 'folder'
            # ⭐ 新增：根据 folder_id 获取文件夹名称
            # folder_name_from_db = None
            # if req.folder_id:
            #     folder = session.query(Folder).filter(Folder.id == req.folder_id).first()
            #     folder_name_from_db = folder.name if folder else None
        elif req.mp_id:
            real_source = 'mp'
        else:
            real_source = 'all'
        
        # 获取公众号名称
        mp_display_name = None
        if req.mp_id:
            mp = session.query(Feed).filter(Feed.id == req.mp_id).first()
            mp_display_name = mp.mp_name if mp else req.mp_id
        # ========== 第七步：生成默认标题（如果 AI 没返回） ==========
        if not ai_title:
            if real_source == 'favorite':
                ai_title = f"精选文章 {req.start_date} 至 {req.end_date}"
            elif real_source == 'mp' and mp_display_name:
                ai_title = f"{mp_display_name} {req.start_date} 至 {req.end_date}"
            elif real_source == 'folder':
                ai_title = f"文件夹报告 {req.start_date} 至 {req.end_date}"
            else:
                ai_title = f"全部公众号 {req.start_date} 至 {req.end_date}"
        # ⭐ 构建完整 Markdown
        full_markdown = f"# {ai_title}\n{ai_content}"
        # ========== 第八步：保存到数据库 ==========
        user_id = "unknown"
        if current_user:
            if current_user.get("original_user"):
                user_id = current_user.get("original_user").id
            elif current_user.get("username"):
                user_id = current_user.get("username")
        
        history = AIReportHistory(
            user_id=user_id,
            title=ai_title,
            source=real_source,
            mp_id=req.mp_id,
            mp_name=mp_display_name,
            folder_id=req.folder_id if real_source == 'folder' else None, # 条件赋值语句
            folder_name=req.folder_name if real_source == 'folder' else None,  # 使用从数据库查到的文件夹名称
            start_date=req.start_date,
            end_date=req.end_date,
            keyword=req.keyword,
            prompt=req.prompt,
            model=req.model,
            report_content=full_markdown  # 存完整的markdown
        )
        session.add(history)
        session.commit()
        print(f"✅ 报告已保存，ID={history.id}, 标题={ai_title}")
        # ========== 第九步：构建 Word 文档并返回 ==========
        date_range = f"{req.start_date} ~ {req.end_date}"
        title = f"公众号文章分析报告"
        doc_buffer = _build_word_document(report_content, title, date_range)

        filename = f"AI_Report_{req.start_date}_{req.end_date}.docx"

        return StreamingResponse(
            doc_buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    except httpx.TimeoutException:
        return error_response(504, "大模型API调用超时，请检查网络或API地址")
    except httpx.ConnectError:
        return error_response(502, "无法连接到大模型API，请检查API地址")
    except Exception as e:
        return error_response(500, f"AI报告生成失败: {str(e)}")
    finally:
        session.close()
        
'''

@router.post("/report/preview", summary="AI报告预览")
async def ai_report_preview(
    req: AIReportRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """预览报告内容（返回文本），不生成Word文件"""
    if not req.api_url or not req.api_key:
        return error_response(400, "请配置大模型API地址和密钥")

    try:
        start_dt = datetime.strptime(req.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(req.end_date, "%Y-%m-%d")
    except ValueError:
        return error_response(400, "日期格式错误，请使用 YYYY-MM-DD")

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) + 86399

    session = DB.get_session()
    try:
        # ========== 第一步：根据数据来源筛选公众号 ==========
        feed_ids = []  # 要查询的公众号ID列表
        
        if req.source == "favorite":
            # 精选文章：全站范围，不限制公众号，只通过 is_favorite 筛选
            # feed_ids 保持为空，表示不限制公众号
            pass
            
        elif req.source == "folder":
            # 文件夹：获取该文件夹下的所有公众号ID
            if not req.folder_id:
                return error_response(400, "请提供文件夹ID")
            folder_feeds = session.query(FolderFeed).filter(
                FolderFeed.folder_id == req.folder_id
            ).all()
            feed_ids = [ff.feed_id for ff in folder_feeds]
            if not feed_ids:
                return error_response(404, f"该文件夹下没有公众号")
                
        else:  # source == "all"
            # 全部：如果指定了 mp_id，只查该公众号；否则查全部
            if req.mp_id:
                feed_ids = [req.mp_id]
            # 如果 feed_ids 为空，表示查全部公众号

        # ========== 第二步：构建文章查询 ==========
        query = session.query(Article).filter(
            Article.publish_time >= start_ts,
            Article.publish_time <= end_ts,
            Article.status == 1
        )
        
        # 根据 feed_ids 筛选（如果为空，表示不限制公众号）
        if feed_ids:
            query = query.filter(Article.mp_id.in_(feed_ids))
        
        # 精选文章筛选（只有 source="favorite" 时才应用）
        if req.source == "favorite":
            query = query.filter(Article.is_favorite == 1)
        
        # 关键词搜索
        if req.keyword:
            kw = f"%{req.keyword}%"
            query = query.filter(
                (Article.title.like(kw)) | (Article.description.like(kw))
            )

        articles = query.order_by(Article.publish_time.desc()).all()

        if not articles:
            return error_response(404, f"在 {req.start_date} ~ {req.end_date} 期间未找到文章")

        # ========== 第三步：构建文章摘要 ==========
        # 获取所有涉及的公众号ID,article中没有mp_name，需要查询feed表获取公众号名称映射
        mp_ids = list(set(art.mp_id for art in articles if art.mp_id))
        mp_name_map = {}
        if mp_ids:
            feeds = session.query(Feed).filter(Feed.id.in_(mp_ids)).all()
            mp_name_map = {f.id: f.mp_name for f in feeds}  
        # 构建文章摘要列表，格式化日期和链接，并添加公众号名称
        article_summaries = []
        for art in articles:
            desc = art.description or ""
            if not desc.strip():
                desc = art.title
            pub_date = datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'
            article_url = art.url or ""
            mp_name = mp_name_map.get(art.mp_id, '未知公众号')

            article_summaries.append(
                f"【{art.title}】\n"
                f"公众号：{mp_name}\n"
                f"发布日期：{pub_date}\n"
                f"链接：{article_url}\n"
                f"摘要：{desc}"
            )
            # article_summaries.append(
            #     f"【{art.title}】\n发布时间：{datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'}\n摘要：{desc}"
            # )

        articles_text = "\n\n---\n\n".join(article_summaries)
        prompt = req.prompt or DEFAULT_REPORT_PROMPT
        user_message = f"{prompt}\n\n以下是 {req.start_date} 至 {req.end_date} 期间共 {len(articles)} 篇文章的摘要：\n\n{articles_text}"

        model = req.model or "gpt-3.5-turbo"
        # 第四步：调用大模型，要求返回带标题的报告内容，标题必须以 "TITLE: " 开头
        system_msg = (
            "你是一个专业的行业分析师和报告撰写专家，擅长从多篇文章中提炼趋势和洞察，生成结构化的分析报告。\n\n"
            "【输出格式要求】\n"
            "第一行必须以 'TITLE: ' 开头，后接10-15字的概括性标题，概括本期核心主题\n"
            "标题后必须空一行\n"
            "正文使用 Markdown 格式\n\n"
            "【参考来源要求】\n"
            "在报告正文结束后，请添加「参考来源」章节，列出所有在报告中引用的文章。\n"
            "每条来源必须使用标准的 Markdown 链接格式，且链接不能省略：\n"
            "[序号] 文章标题(文章链接)，公众号名称，YYYY-MM-DD\n"
            "【格式示例】\n"
            "`[1] [安谋科技八周年庆典](https://mp.weixin.qq.com/s/xxx)，安谋科技，2026-05-01`\n\n"
            "【特别注意】\n"
            "- 链接 href 属性必须是文章的真实 URL\n"
            "- 不允许输出任何不带链接的纯文本引用\n"
            "- 不要省略方括号和圆括号之间的空格或换行"
            "【输出禁令】\n"
            "- 正文中禁止使用一级标题（#）\n"
            "- 严禁只提供碎片化的短句，每个分析点需具备一定的论述深度；\n"
            "- 严禁输出“好的”、“这是为你生成的报告”等任何开场白或结束语。"
        )

        report_content = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not report_content:
            return error_response(500, "大模型未返回有效内容")
        
        # ========== 第五步：解析 AI 返回的标题和内容 ==========
        ai_title = None
        ai_content = report_content
        
        # 检查 AI 返回的内容是否包含 TITLE: 标记
        if report_content.startswith('TITLE:'):
            # 按换行分割，第一行是 TITLE: xxx
            lines = report_content.split('\n', 1)
            title_line = lines[0].strip()
            # 提取标题内容（去掉 "TITLE:" 前缀）
            ai_title = title_line.replace('TITLE:', '').strip()
            
            # 剩余部分是正文
            if len(lines) > 1:
                ai_content = lines[1].strip()
                # 如果正文开头有换行，去掉它
                if ai_content.startswith('\n'):
                    ai_content = ai_content[1:]
            else:
                ai_content = report_content
        else:
            # 如果 AI 没有按格式返回，整个内容当作正文
            ai_content = report_content
        # ========== 第六步：确定来源类型（用于保存） ==========
        # 判断真正来源
        if req.source == 'favorite':
            real_source = 'favorite'
        elif req.source == 'folder':
            real_source = 'folder'
        elif req.mp_id:
            # 有 mp_id 且不是上面情况 = 单个公众号
            real_source = 'mp'
        else:
            real_source = 'all'
        # 获取公众号名称（如果有），用于保存和生成默认标题
        mp_display_name = None
        if req.mp_id:
            mp = session.query(Feed).filter(Feed.id == req.mp_id).first()
            mp_display_name = mp.mp_name if mp else req.mp_id
        # ========== 第七步：如果没有解析到标题，生成默认标题 ==========
        if not ai_title:
            if real_source == 'favorite':
                ai_title = f"精选文章 {req.start_date} 至 {req.end_date}"
            elif real_source == 'mp' and mp_display_name:
                ai_title = f"{mp_display_name} {req.start_date} 至 {req.end_date}"
            elif real_source == 'folder':
                ai_title = f"文件夹报告 {req.start_date} 至 {req.end_date}"
            else:
                ai_title = f"全部公众号 {req.start_date} 至 {req.end_date}"
        # ========== ⭐⭐⭐ 关键修改：构建完整的 Markdown 内容 ⭐⭐⭐ ==========
        # 格式：一级标题（文章总标题）+ 空行 + 正文
        # 这样前端直接转换 MD 到 HTML 就能正确显示，不需要任何拼接
        full_markdown = f"# {ai_title}\n\n{ai_content}"
        # ========== 第八步：获取用户ID ==========
        user_id = "unknown"
        if current_user:
            if current_user.get("original_user"):
                user_id = current_user.get("original_user").id
            elif current_user.get("username"):
                user_id = current_user.get("username")

        # ========== 第九步：保存到数据库 ==========
        history = AIReportHistory(
            user_id=user_id,
            title=ai_title,  # 使用AI生成的标题
            source=real_source,
            mp_id=req.mp_id,
            mp_name=mp_display_name,  
            # folder_id=req.folder_id,
            folder_id=req.folder_id if real_source == 'folder' else None,
            folder_name=req.folder_name if real_source == 'folder' else None,  # ⭐ 使用从数据库查到的文件夹名称
            start_date=req.start_date,
            end_date=req.end_date,
            keyword=req.keyword,
            prompt=req.prompt,
            model=req.model,
            report_content=full_markdown  # 保存原始Markdown(标题+正文)
        )
        session.add(history)
        session.commit()
        print(f"报告已保存，ID={history.id}, 标题={ai_title}")  # 控制台输出，方便查看

        # ========== 第十步：返回给前端 ==========
        return success_response({
            "report": full_markdown,  # 返回完整的Markdown内容，前端直接展示
            "title": ai_title,     # 返回标题
            "article_count": len(articles),
            "date_range": f"{req.start_date} ~ {req.end_date}",
            "model": model,
            "history_id": history.id  # 返回历史记录ID，方便前端后续操作
        })

    except httpx.TimeoutException:
        return error_response(504, "大模型API调用超时，请检查网络或API地址")
    except httpx.ConnectError:
        return error_response(502, "无法连接到大模型API，请检查API地址")
    except Exception as e:
        return error_response(500, f"AI报告生成失败: {str(e)}")
    finally:
        session.close()

@router.get("/history/list", summary="获取历史报告列表")
async def get_history_list(
    current_user: dict = Depends(get_current_user_or_ak)
):
    """获取当前用户的所有历史报告列表"""
        # from core.models.ai_report_history import AIReportHistory
    
    session = DB.get_session()
    try:
        # 获取用户ID
        user_id = "unknown"
        if current_user:
            if current_user.get("original_user"):
                user_id = current_user.get("original_user").id
            elif current_user.get("username"):
                user_id = current_user.get("username")
        
        # 查询该用户的所有历史记录，按创建时间倒序（最新的在前）
        history_list = session.query(AIReportHistory).filter(
            AIReportHistory.user_id == user_id
        ).order_by(AIReportHistory.created_at.desc()).all()
        
        return success_response({
            "list": [h.to_dict() for h in history_list],
            "total": len(history_list)
        })
    except Exception as e:
        return error_response(500, f"获取历史记录失败: {str(e)}")
    finally:
        session.close()


@router.get("/history/export/{history_id}", summary="导出历史报告为Word")
async def export_history_report(
    history_id: int,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    导出历史保存的报告为 Word 文档
    
    流程：
    1. 根据 history_id 查询数据库中的报告记录
    2. 验证用户是否有权限访问（只能导出自己的报告）
    3. 将保存的 report_content（Markdown格式）转换为 Word 文档
    4. 返回 Word 文件供下载
    """
    session = DB.get_session()
    try:
        # 1. 获取用户ID
        user_id = "unknown"
        if current_user:
            if current_user.get("original_user"):
                user_id = current_user.get("original_user").id
            elif current_user.get("username"):
                user_id = current_user.get("username")
        
        # 2. 查询历史记录
        history = session.query(AIReportHistory).filter(
            AIReportHistory.id == history_id
        ).first()
        
        # 3. 验证记录存在
        if not history:
            return error_response(404, f"历史记录不存在，ID={history_id}")
        
        # 4. 验证用户权限（只能导出自己的报告）
        if history.user_id != user_id:
            return error_response(403, "无权访问此报告")
        
        # 5. 构建 Word 文档标题
        title = history.title
        if history.source == 'mp' and history.mp_name:
            title = f"{history.mp_name} 公众号文章分析报告"
        elif history.source == 'favorite':
            title = f"精选文章分析报告"
        elif history.source == 'folder' and history.folder_name:
            title = f"{history.folder_name} 文件夹文章分析报告"
        else:
            title = f"公众号文章分析报告"
        
        # 6. 构建日期范围字符串
        date_range = f"{history.start_date} ~ {history.end_date}"
        
        # 7. 将保存的 Markdown 内容转换为 Word 文档
        doc_buffer = _build_word_document(
            # history.report_content,  # 使用保存的内容，不重新调用AI
            # title,
            # date_range
            markdown_text=history.report_content,  # Markdown 内容
            title=history.title,                   # 使用数据库中的标题
            date_range=date_range                  # 日期范围
        )
        
        # 8. 生成文件名
        filename = f"AI_Report_{history.id}_{history.start_date}_{history.end_date}.docx"
        
        # 9. 返回 Word 文件
        return StreamingResponse(
            doc_buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
        
    except Exception as e:
        return error_response(500, f"导出历史报告失败: {str(e)}")
    finally:
        session.close()

@router.delete("/history/{history_id}", summary="删除历史报告")
async def delete_history_report(
    history_id: int,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    删除历史报告记录
    
    原理：
    1. 根据 history_id 查询数据库记录
    2. 验证当前用户是否有权限（只能删除自己的）
    3. 执行删除操作
    """
    session = DB.get_session()
    try:
        # 获取用户ID
        user_id = "unknown"
        if current_user:
            if current_user.get("original_user"):
                user_id = current_user.get("original_user").id
            elif current_user.get("username"):
                user_id = current_user.get("username")
        
        # 查询历史记录
        history = session.query(AIReportHistory).filter(
            AIReportHistory.id == history_id
        ).first()
        
        # 验证记录存在
        if not history:
            return error_response(404, f"历史记录不存在，ID={history_id}")
        
        # 验证用户权限
        if history.user_id != user_id:
            return error_response(403, "无权删除此报告")
        
        # 执行删除
        session.delete(history)
        session.commit()
        
        print(f"🗑️ 历史报告已删除，ID={history_id}, 标题={history.title}")
        
        return success_response({
            "message": "删除成功",
            "deleted_id": history_id
        })
        
    except Exception as e:
        session.rollback()
        return error_response(500, f"删除失败: {str(e)}")
    finally:
        session.close()