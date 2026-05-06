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
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from core.models.folder import FolderFeed  # 新增
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
    source: Optional[str] = "all"      # 新增：all, favorite, folder
    folder_id: Optional[int] = None    # 新增：文件夹ID

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


def _build_word_document(report_text: str, title: str, date_range: str) -> io.BytesIO:
    """将AI生成的报告文本构建为Word文档"""
    doc = Document()

    # 设置默认字体
    style = doc.styles['Normal']
    font = style.font
    font.name = '微软雅黑'
    font.size = Pt(11)

    # 标题
    heading = doc.add_heading(title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 日期范围
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_para.add_run(f"报告周期：{date_range}")
    date_run.font.size = Pt(10)
    date_run.font.color.rgb = RGBColor(128, 128, 128)

    # 生成时间
    time_para = doc.add_paragraph()
    time_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    time_run = time_para.add_run(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    time_run.font.size = Pt(10)
    time_run.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()  # 空行

    # 解析报告内容，按行处理
    lines = report_text.split('\n')
    for line in lines:
        stripped = line.strip()
        if not stripped:
            doc.add_paragraph()
            continue

        # 处理标题行
        if stripped.startswith('# '):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith('## '):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith('### '):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith('#### '):
            doc.add_heading(stripped[5:], level=4)
        elif stripped.startswith('- ') or stripped.startswith('* '):
            doc.add_paragraph(stripped[2:], style='List Bullet')
        elif stripped[0].isdigit() and '. ' in stripped[:5]:
            idx = stripped.index('. ')
            doc.add_paragraph(stripped[idx + 2:], style='List Number')
        else:
            doc.add_paragraph(stripped)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


""" @router.post("/report", summary="AI报告生成")
async def ai_report(
    req: AIReportRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    if not req.api_url or not req.api_key:
        return error_response(400, "请配置大模型API地址和密钥")

    try:
        start_dt = datetime.strptime(req.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(req.end_date, "%Y-%m-%d")
    except ValueError:
        return error_response(400, "日期格式错误，请使用 YYYY-MM-DD")

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) + 86399  # 包含当天最后一秒

    session = DB.get_session()
    try:
        query = session.query(Article).filter(
            Article.publish_time >= start_ts,
            Article.publish_time <= end_ts,
            Article.status == 1
        )
        if req.mp_id:
            query = query.filter(Article.mp_id == req.mp_id)
        if req.keyword:
            kw = f"%{req.keyword}%"
            query = query.filter(
                (Article.title.like(kw)) | (Article.description.like(kw))
            )

        articles = query.order_by(Article.publish_time.desc()).all()

        if not articles:
            return error_response(404, f"在 {req.start_date} ~ {req.end_date} 期间未找到文章")

        # 构建文章摘要列表
        article_summaries = []
        for art in articles:
            desc = art.description or ""
            if not desc.strip():
                desc = art.title
            article_summaries.append(
                f"【{art.title}】\n发布时间：{datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'}\n摘要：{desc}"
            )

        articles_text = "\n\n---\n\n".join(article_summaries)
        prompt = req.prompt or DEFAULT_REPORT_PROMPT
        user_message = f"{prompt}\n\n以下是 {req.start_date} 至 {req.end_date} 期间共 {len(articles)} 篇文章的摘要：\n\n{articles_text}"

        model = req.model or "gpt-3.5-turbo"
        system_msg = "你是一个专业的行业分析师和报告撰写专家，擅长从多篇文章中提炼趋势和洞察，生成结构化的分析报告。请使用 Markdown 格式来组织标题和列表。"

        report_content = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not report_content:
            return error_response(500, "大模型未返回有效内容")

        # 构建Word文档
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
        session.close() """
@router.post("/report", summary="AI报告生成")
async def ai_report(
    req: AIReportRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
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
        article_summaries = []
        for art in articles:
            desc = art.description or ""
            if not desc.strip():
                desc = art.title
            article_summaries.append(
                f"【{art.title}】\n发布时间：{datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'}\n摘要：{desc}"
            )

        articles_text = "\n\n---\n\n".join(article_summaries)
        prompt = req.prompt or DEFAULT_REPORT_PROMPT
        user_message = f"{prompt}\n\n以下是 {req.start_date} 至 {req.end_date} 期间共 {len(articles)} 篇文章的摘要：\n\n{articles_text}"

        model = req.model or "gpt-3.5-turbo"
        system_msg = "你是一个专业的行业分析师和报告撰写专家，擅长从多篇文章中提炼趋势和洞察，生成结构化的分析报告。请使用 Markdown 格式来组织标题和列表。"

        report_content = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not report_content:
            return error_response(500, "大模型未返回有效内容")

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
        article_summaries = []
        for art in articles:
            desc = art.description or ""
            if not desc.strip():
                desc = art.title
            article_summaries.append(
                f"【{art.title}】\n发布时间：{datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'}\n摘要：{desc}"
            )

        articles_text = "\n\n---\n\n".join(article_summaries)
        prompt = req.prompt or DEFAULT_REPORT_PROMPT
        user_message = f"{prompt}\n\n以下是 {req.start_date} 至 {req.end_date} 期间共 {len(articles)} 篇文章的摘要：\n\n{articles_text}"

        model = req.model or "gpt-3.5-turbo"
        system_msg = "你是一个专业的行业分析师和报告撰写专家，擅长从多篇文章中提炼趋势和洞察，生成结构化的分析报告。请使用 Markdown 格式来组织标题和列表。"

        report_content = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not report_content:
            return error_response(500, "大模型未返回有效内容")

        return success_response({
            "report": report_content,
            "article_count": len(articles),
            "date_range": f"{req.start_date} ~ {req.end_date}",
            "model": model
        })

    except httpx.TimeoutException:
        return error_response(504, "大模型API调用超时，请检查网络或API地址")
    except httpx.ConnectError:
        return error_response(502, "无法连接到大模型API，请检查API地址")
    except Exception as e:
        return error_response(500, f"AI报告生成失败: {str(e)}")
    finally:
        session.close()
""" @router.post("/report/preview", summary="AI报告预览")
async def ai_report_preview(
    req: AIReportRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    # 预览报告内容（返回文本），不生成Word文件
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
        query = session.query(Article).filter(
            Article.publish_time >= start_ts,
            Article.publish_time <= end_ts,
            Article.status == 1
        )
        if req.mp_id:
            query = query.filter(Article.mp_id == req.mp_id)
        if req.keyword:
            kw = f"%{req.keyword}%"
            query = query.filter(
                (Article.title.like(kw)) | (Article.description.like(kw))
            )

        articles = query.order_by(Article.publish_time.desc()).all()

        if not articles:
            return error_response(404, f"在 {req.start_date} ~ {req.end_date} 期间未找到文章")

        article_summaries = []
        for art in articles:
            desc = art.description or ""
            if not desc.strip():
                desc = art.title
            article_summaries.append(
                f"【{art.title}】\n发布时间：{datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'}\n摘要：{desc}"
            )

        articles_text = "\n\n---\n\n".join(article_summaries)
        prompt = req.prompt or DEFAULT_REPORT_PROMPT
        user_message = f"{prompt}\n\n以下是 {req.start_date} 至 {req.end_date} 期间共 {len(articles)} 篇文章的摘要：\n\n{articles_text}"

        model = req.model or "gpt-3.5-turbo"
        system_msg = "你是一个专业的行业分析师和报告撰写专家，擅长从多篇文章中提炼趋势和洞察，生成结构化的分析报告。请使用 Markdown 格式来组织标题和列表。"

        report_content = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not report_content:
            return error_response(500, "大模型未返回有效内容")

        return success_response({
            "report": report_content,
            "article_count": len(articles),
            "date_range": f"{req.start_date} ~ {req.end_date}",
            "model": model
        })

    except httpx.TimeoutException:
        return error_response(504, "大模型API调用超时，请检查网络或API地址")
    except httpx.ConnectError:
        return error_response(502, "无法连接到大模型API，请检查API地址")
    except Exception as e:
        return error_response(500, f"AI报告生成失败: {str(e)}")
    finally:
        session.close()
 """