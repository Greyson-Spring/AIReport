import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from .base import success_response, error_response

router = APIRouter(prefix="/ai", tags=["AI功能"])


class AISummaryRequest(BaseModel):
    article_ids: List[str]
    prompt: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    save_to_db: bool = False


DEFAULT_PROMPT = (
    "请对以下文章内容进行摘要总结，提取关键信息，"
    "以简洁清晰的方式呈现要点。每篇文章的摘要中请包含公众号名称、文章标题、文章链接和发布日期。"
    "如果有多篇文章，请分别总结每篇文章，并在最后给出一个综合概述。\n\n"
)

SINGLE_ARTICLE_PROMPT = (
    "请对以下文章内容进行摘要总结，用2-3句话提取关键信息和要点。"
    "摘要中请包含公众号名称、文章标题、文章链接和发布日期。\n\n"
)


async def _call_llm(api_url: str, api_key: str, model: str,
                    system_msg: str, user_msg: str) -> str:
    """调用大模型API，返回生成的文本内容"""
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
        "max_tokens": 4096
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


@router.post("/summary", summary="AI文章摘要")
async def ai_summary(
    req: AISummaryRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    if not req.article_ids:
        return error_response(400, "请选择至少一篇文章")

    if not req.api_url or not req.api_key:
        return error_response(400, "请配置大模型API地址和密钥")

    # 获取文章内容
    session = DB.get_session()
    try:
        articles = session.query(Article).filter(
            Article.id.in_(req.article_ids)
        ).all()

        if not articles:
            return error_response(404, "未找到选中的文章")

        model = req.model or "gpt-3.5-turbo"
        system_msg = "你是一个专业的内容分析助手，擅长总结和提炼文章要点。"

        # 查询公众号名称映射
        mp_ids = list(set(art.mp_id for art in articles if art.mp_id))
        mp_name_map = {}
        if mp_ids:
            feeds = session.query(Feed).filter(Feed.id.in_(mp_ids)).all()
            mp_name_map = {f.id: f.mp_name for f in feeds}

        def _format_article_meta(art):
            mp_name = mp_name_map.get(art.mp_id, '未知公众号')
            pub_date = datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'
            link = art.url or ''
            return f"公众号：{mp_name}\n标题：{art.title}\n链接：{link}\n发布日期：{pub_date}"

        # 如果需要保存到数据库，逐篇生成摘要并写入 description
        if req.save_to_db:
            saved_count = 0
            failed_ids = []
            per_article_prompt = req.prompt or SINGLE_ARTICLE_PROMPT

            for art in articles:
                text = art.content or art.description or ""
                if not text.strip():
                    failed_ids.append(art.id)
                    continue
                try:
                    meta = _format_article_meta(art)
                    user_msg = f"{per_article_prompt}\n\n{meta}\n正文：{text}"
                    summary = await _call_llm(
                        req.api_url, req.api_key, model,
                        system_msg, user_msg
                    )
                    if summary:
                        art.description = summary
                        art.ai_summarized = 1
                        session.commit()
                        saved_count += 1
                    else:
                        failed_ids.append(art.id)
                except Exception:
                    session.rollback()
                    failed_ids.append(art.id)

            msg = f"已为 {saved_count} 篇文章生成并保存摘要"
            if failed_ids:
                msg += f"，{len(failed_ids)} 篇失败"

            return success_response({
                "summary": msg,
                "article_count": saved_count,
                "failed_ids": failed_ids,
                "model": model
            }, message=msg)

        # 不保存到数据库，整体生成摘要返回
        contents = []
        for art in articles:
            text = art.content or art.description or ""
            if not text.strip():
                continue
            meta = _format_article_meta(art)
            contents.append(f"{meta}\n正文：{text}")

        if not contents:
            return error_response(400, "选中的文章没有可用的正文内容")

        articles_text = "\n\n---\n\n".join(contents)
        prompt = req.prompt or DEFAULT_PROMPT
        user_message = f"{prompt}\n\n{articles_text}"

        summary = await _call_llm(
            req.api_url, req.api_key, model,
            system_msg, user_message
        )

        if not summary:
            return error_response(500, "大模型未返回有效内容")

        return success_response({
            "summary": summary,
            "article_count": len(contents),
            "model": model
        })

    except httpx.TimeoutException:
        return error_response(504, "大模型API调用超时，请检查网络或API地址")
    except httpx.ConnectError:
        return error_response(502, "无法连接到大模型API，请检查API地址")
    except Exception as e:
        return error_response(500, f"AI摘要生成失败: {str(e)}")
    finally:
        session.close()
