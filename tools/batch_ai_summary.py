#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量给指定时间段的所有公众号文章生成AI摘要, 写入 article.description 并标记 ai_summarized=1

用法(在容器里用虚拟环境的python运行):
    docker exec -it we-mp-rss-local sh -c 'PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" tools/batch_ai_summary.py 2026-08-01 2026-08-31'
可选第三参: 每篇间隔秒数(默认3), 防频率限制

前置: 先在"大模型配置"页面填好 llm_api_url / llm_api_key / llm_model
"""
import os
import sys
import time
import datetime as _dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import DB
from core.models.article import Article
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.models.config_management import ConfigManagement
from core.print import print_success, print_error, print_info, print_warning

DEFAULT_PROMPT = (
    "请对以下文章内容进行摘要总结，用2-3句话提取关键信息和要点。"
    "摘要中请包含公众号名称、文章标题和发布日期。\n\n"
)


def load_llm_config(session):
    keys = ["llm_api_url", "llm_api_key", "llm_model"]
    rows = session.query(ConfigManagement).filter(
        ConfigManagement.config_key.in_(keys)
    ).all()
    cfg = {r.config_key: r.config_value for r in rows}
    return {
        "api_url": (cfg.get("llm_api_url") or "").strip(),
        "api_key": (cfg.get("llm_api_key") or "").strip(),
        "model": (cfg.get("llm_model") or "gpt-3.5-turbo").strip(),
    }


def call_llm(api_url, api_key, model, system_msg, user_msg, timeout=180):
    import httpx
    url = api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"API调用失败({resp.status_code}): {resp.text[:200]}")
    result = resp.json()
    return (result.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()


def main():
    if len(sys.argv) < 3:
        print('用法: python tools/batch_ai_summary.py 2026-08-01 2026-08-31 [间隔秒]')
        sys.exit(1)
    start_date = sys.argv[1]
    end_date = sys.argv[2]
    sleep_sec = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    session = DB.get_session()
    cfg = load_llm_config(session)
    if not cfg["api_url"] or not cfg["api_key"]:
        print_error("未找到LLM配置(llm_api_url/llm_api_key), 请先在'大模型配置'页面填写")
        sys.exit(1)
    print_info(f"使用模型: {cfg['model']}  API: {cfg['api_url']}")

    start_ts = int(_dt.datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(_dt.datetime.strptime(end_date, "%Y-%m-%d").timestamp() + 86400)

    articles = session.query(Article).filter(
        Article.publish_time >= start_ts,
        Article.publish_time < end_ts,
        Article.content.isnot(None),
        Article.content != "",
        Article.status != DATA_STATUS.DELETED,
    ).order_by(Article.publish_time.desc()).all()

    print_info(f"时间段 {start_date}~{end_date} 共 {len(articles)} 篇文章需要生成摘要...")

    mp_ids = list(set(a.mp_id for a in articles if a.mp_id))
    mp_name_map = {}
    if mp_ids:
        feeds = session.query(Feed).filter(Feed.id.in_(mp_ids)).all()
        mp_name_map = {f.id: f.mp_name for f in feeds}

    system_msg = "你是一个专业的内容分析助手，擅长总结和提炼文章要点。"
    ok = fail = skip = 0
    for i, art in enumerate(articles, 1):
        if getattr(art, "ai_summarized", 0):
            skip += 1
            print_info(f"[{i}/{len(articles)}] 已摘要过, 跳过: {str(art.title)[:30]}")
            continue
        text = art.content or art.description or ""
        if not text.strip():
            skip += 1
            print_warning(f"[{i}/{len(articles)}] 无正文, 跳过: {str(art.title)[:30]}")
            continue
        pub = _dt.datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'
        meta = (
            f"公众号：{mp_name_map.get(art.mp_id, '未知公众号')}\n"
            f"标题：{art.title}\n"
            f"链接：{art.url or ''}\n"
            f"发布日期：{pub}"
        )
        try:
            summary = call_llm(
                cfg["api_url"], cfg["api_key"], cfg["model"],
                system_msg, f"{DEFAULT_PROMPT}\n\n{meta}\n正文：{text}",
            )
            if summary:
                art.description = summary
                art.ai_summarized = 1
                session.commit()
                ok += 1
                print_success(f"[{i}/{len(articles)}] 已生成: {str(art.title)[:30]}")
            else:
                fail += 1
                print_error(f"[{i}/{len(articles)}] 返回空: {str(art.title)[:30]}")
        except Exception as e:
            session.rollback()
            fail += 1
            print_error(f"[{i}/{len(articles)}] 失败: {str(art.title)[:30]} ({str(e)[:80]})")
        if i < len(articles):
            time.sleep(sleep_sec)

    print("=" * 50)
    print_success(f"完成: 成功 {ok} 篇, 失败 {fail} 篇, 跳过 {skip} 篇")
    session.close()


if __name__ == "__main__":
    main()
