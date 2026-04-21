import httpx
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import or_
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from .base import success_response, error_response

router = APIRouter(prefix="/ai", tags=["AI功能"])


class AIQARequest(BaseModel):
    question: str
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    mp_id: Optional[str] = None


def _extract_keywords(question: str) -> List[str]:
    """从问题中提取搜索关键词（改进版：生成多种变体提高召回率）"""
    import re
    # 去掉常见停用词和标点
    stop_words = {
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
        '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
        '没有', '看', '好', '自己', '这', '他', '她', '吗', '什么', '哪些',
        '什么样', '怎么', '如何', '为什么', '请', '帮', '告诉', '关于',
        '最近', '最新', '有没有', '有关', '相关', '哪个', '可以', '能',
    }
    # 按标点和空格分割
    tokens = re.split(r'[\s,，。！？!?、；;：:""''""()\[\]{}]+', question)
    keywords = []
    seen = set()
    for t in tokens:
        t = t.strip()
        if len(t) >= 2 and t not in stop_words:
            low = t.lower()
            if low not in seen:
                keywords.append(t)
                seen.add(low)
            # 生成变体：去掉连字符 (RISC-V -> RISCV)，加连字符 (riscv -> risc-v 不一定准确但
            # 通过去符号匹配可以覆盖)
            stripped = re.sub(r'[-_\s]', '', t)
            if stripped.lower() not in seen and len(stripped) >= 2:
                keywords.append(stripped)
                seen.add(stripped.lower())
    return keywords[:15]


async def _call_llm(api_url: str, api_key: str, model: str,
                    messages: list) -> str:
    url = api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
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


@router.post("/qa", summary="AI问答")
async def ai_qa(
    req: AIQARequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """基于文章数据库的AI问答"""
    if not req.api_url or not req.api_key:
        return error_response(400, "请配置大模型API地址和密钥")

    if not req.question or not req.question.strip():
        return error_response(400, "请输入问题")

    # 从问题中提取关键词
    keywords = _extract_keywords(req.question)

    session = DB.get_session()
    try:
        def _base_query():
            q = session.query(Article, Feed.mp_name.label('mp_name')).outerjoin(
                Feed, Article.mp_id == Feed.id
            ).filter(Article.status == 1)
            if req.mp_id:
                q = q.filter(Article.mp_id == req.mp_id)
            return q

        results = []

        # 第一轮：用关键词做 LIKE 搜索（title + description）
        if keywords:
            conditions = []
            for kw in keywords:
                like_kw = f"%{kw}%"
                conditions.append(Article.title.ilike(like_kw))
                conditions.append(Article.description.ilike(like_kw))
            results = _base_query().filter(or_(*conditions)) \
                .order_by(Article.publish_time.desc()).limit(30).all()

        # 第二轮：如果第一轮没结果，用原始问题整体做模糊搜索
        if not results and req.question.strip():
            import re
            raw = req.question.strip()
            # 把问题里的特殊字符去掉，每2+字符段做 LIKE
            segments = re.split(r'[\s,，。！？!?、；;：:""''""()\[\]{}\-_]+', raw)
            segments = [s for s in segments if len(s) >= 2]
            if segments:
                conditions = []
                for seg in segments[:10]:
                    like_seg = f"%{seg}%"
                    conditions.append(Article.title.ilike(like_seg))
                    conditions.append(Article.description.ilike(like_seg))
                results = _base_query().filter(or_(*conditions)) \
                    .order_by(Article.publish_time.desc()).limit(30).all()

        # 第三轮：仍无结果，回退到最近的文章作为上下文
        if not results:
            results = _base_query().order_by(Article.publish_time.desc()).limit(20).all()

        if not results:
            return success_response({
                "answer": "抱歉，数据库中没有找到与您问题相关的文章信息。请尝试更换关键词或选择其他公众号。",
                "sources": [],
                "article_count": 0
            })

        # 构建文章上下文
        sources = []
        article_texts = []
        for i, (art, mp_name) in enumerate(results, 1):
            desc = art.description or ""
            if not desc.strip():
                desc = art.title
            pub_date = ""
            if art.publish_time:
                pub_date = datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d')

            article_texts.append(
                f"[{i}] 公众号：{mp_name or '未知'}\n"
                f"标题：{art.title}\n"
                f"发布日期：{pub_date}\n"
                f"摘要：{desc[:500]}"
            )
            sources.append({
                "index": i,
                "title": art.title,
                "mp_name": mp_name or "未知",
                "url": art.url or "",
                "publish_date": pub_date
            })

        context_text = "\n\n---\n\n".join(article_texts)

        model = req.model or "gpt-3.5-turbo"
        system_msg = (
            "你是一个基于公众号文章数据库的智能问答助手。用户会向你提问，你需要根据提供的文章信息来回答问题。\n"
            "回答要求：\n"
            "1. 严格基于提供的文章内容回答，不要编造信息\n"
            "2. 在回答中引用来源，使用 [序号] 格式标注出处，例如 [1]、[2]\n"
            "3. 如果文章内容不足以回答问题，请如实说明\n"
            "4. 回答要清晰、有条理，使用 Markdown 格式\n"
            "5. 在回答末尾列出引用的文章来源清单"
        )
        user_msg = (
            f"我的问题是：{req.question}\n\n"
            f"以下是数据库中检索到的 {len(results)} 篇相关文章信息：\n\n"
            f"{context_text}"
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]

        answer = await _call_llm(req.api_url, req.api_key, model, messages)

        if not answer:
            return error_response(500, "大模型未返回有效内容")

        return success_response({
            "answer": answer,
            "sources": sources,
            "article_count": len(results),
            "model": model
        })

    except Exception as e:
        return error_response(500, f"AI问答失败: {str(e)}")
    finally:
        session.close()
