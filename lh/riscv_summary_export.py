#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立工具: 直接从数据库取 RISC-V 相关文章, 按 lh/ 提示词生成摘要并导出

功能:
  1. 按时间段查询文章, 只保留 RISC-V 相关(标题/正文/简介含 risc-?v)
  2. 用 lh/ai_analysis_prompt.txt(原样不改) 逐篇生成摘要
  3. 导出每篇摘要到 CSV/JSON
  4. 用 lh/ai_analysis_prompt_summary.txt(原样不改) 把全部单篇摘要汇总成月度报告
     → 导出 .md, 并尽量转成 .docx(复用项目 _build_word_document)

用法(在服务器容器里跑, 容器env里有DB连接串):
    docker cp lh/riscv_summary_export.py we-mp-rss-local:/app/lh/
    docker exec -it we-mp-rss-local sh -c 'PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" lh/riscv_summary_export.py 2026-08-01 2026-08-31'

LLM配置读取顺序: 环境变量 AI_API_URL/AI_API_KEY/AI_MODEL, 其次项目config_management表(llm_api_url/llm_api_key/llm_model)
"""
import os
import sys
import json
import csv
import re
import datetime as _dt
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import DB
from core.models.article import Article
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.print import print_success, print_error, print_info, print_warning

LH_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_SINGLE_FILE = os.path.join(LH_DIR, "ai_analysis_prompt.txt")
PROMPT_REPORT_FILE = os.path.join(LH_DIR, "ai_analysis_prompt_summary.txt")

RISCV_RE = re.compile(r"risc-?v", re.IGNORECASE)


def load_prompt(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def load_llm_config(session):
    cfg = {}
    if os.environ.get("AI_API_KEY"):
        cfg["api_url"] = os.environ.get("AI_API_URL", "")
        cfg["api_key"] = os.environ.get("AI_API_KEY", "")
        cfg["model"] = os.environ.get("AI_MODEL", "deepseek-v4-flash")
        return cfg
    from core.models.config_management import ConfigManagement
    keys = ["llm_api_url", "llm_api_key", "llm_model"]
    rows = session.query(ConfigManagement).filter(ConfigManagement.config_key.in_(keys)).all()
    m = {r.config_key: r.config_value for r in rows}
    return {
        "api_url": (m.get("llm_api_url") or "").strip(),
        "api_key": (m.get("llm_api_key") or "").strip(),
        "model": (m.get("llm_model") or "deepseek-v4-flash").strip(),
    }


def call_llm(cfg, system_msg, user_msg, timeout=300, max_tokens=8000):
    import httpx
    url = cfg["api_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"API调用失败({resp.status_code}): {resp.text[:200]}")
    result = resp.json()
    return (result.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()


def build_report_docx(markdown_text, title, out_path):
    """尽量复用项目 _build_word_document 生成docx, 失败则只保留md"""
    try:
        from apis.ai_report import _build_word_document
        buf = _build_word_document(markdown_text, title, "")
        with open(out_path, "wb") as f:
            f.write(buf.getvalue())
        return True
    except Exception as e:
        print_warning(f"生成docx失败(仅保留md): {e}")
        return False


def main():
    if len(sys.argv) < 3:
        print("用法: python lh/riscv_summary_export.py 2026-08-01 2026-08-31 [每篇间隔秒]")
        sys.exit(1)
    start_date, end_date = sys.argv[1], sys.argv[2]
    sleep_sec = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    out_prefix = f"riscv_summary_{start_date}_{end_date}"
    prompt_single = load_prompt(PROMPT_SINGLE_FILE)
    prompt_report = load_prompt(PROMPT_REPORT_FILE)
    print_info(f"提示词已加载(单篇 {len(prompt_single)}字 / 报告 {len(prompt_report)}字), 未作任何改动")

    session = DB.get_session()
    cfg = load_llm_config(session)
    if not cfg["api_url"] or not cfg["api_key"]:
        print_error("未找到LLM配置, 请设置环境变量AI_API_URL/AI_API_KEY, 或在'大模型配置'页面填写")
        sys.exit(1)
    print_info(f"LLM: {cfg['model']} @ {cfg['api_url']}")

    start_ts = int(_dt.datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(_dt.datetime.strptime(end_date, "%Y-%m-%d").timestamp() + 86400)

    articles = session.query(Article).filter(
        Article.publish_time >= start_ts,
        Article.publish_time < end_ts,
        Article.status != DATA_STATUS.DELETED,
    ).order_by(Article.publish_time.desc()).all()

    mp_ids = list(set(a.mp_id for a in articles if a.mp_id))
    mp_name_map = {}
    if mp_ids:
        feeds = session.query(Feed).filter(Feed.id.in_(mp_ids)).all()
        mp_name_map = {f.id: f.mp_name for f in feeds}

    # 只保留 RISC-V 相关
    hits = []
    for a in articles:
        text = " ".join([a.title or "", a.content or "", a.description or ""])
        if RISCV_RE.search(text):
            hits.append(a)
    print_info(f"时间段内共 {len(articles)} 篇, 其中 RISC-V 相关 {len(hits)} 篇")

    # ---- 1. 逐篇生成摘要(断点续跑: 已生成的自动跳过) ----
    csv_path = f"{out_prefix}.csv"
    json_path = f"{out_prefix}.json"

    done_keys = set()
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                k = (row.get("链接") or "").strip() or (row.get("标题") or "").strip()
                if k:
                    done_keys.add(k)
    if not os.path.exists(csv_path):
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(["公众号", "标题", "链接", "发布日期", "摘要"])

    def _key(a):
        return (a.url or "").strip() or (a.title or "").strip()

    todo = [a for a in hits if _key(a) not in done_keys and (a.content or "").strip()]
    print_info(f"共 {len(hits)} 篇 RISC-V 文章, 已有 {len(hits)-len(todo)} 篇, 本次待生成 {len(todo)} 篇")

    ok = fail = 0
    for i, a in enumerate(todo, 1):
        pub = _dt.datetime.fromtimestamp(a.publish_time).strftime('%Y-%m-%d') if a.publish_time else ''
        meta = f"公众号：{mp_name_map.get(a.mp_id, '未知公众号')}\n标题：{a.title}\n链接：{a.url or ''}\n发布日期：{pub}"
        try:
            summary = call_llm(cfg, "你是一个专业的内容分析助手。", f"{prompt_single}\n\n{meta}\n正文：{(a.content or '')[:8000]}")
            if summary:
                with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
                    csv.writer(f).writerow([mp_name_map.get(a.mp_id, ''), a.title, a.url or '', pub, summary])
                ok += 1
                print_success(f"[{i}/{len(todo)}] 已生成: {str(a.title)[:30]}")
            else:
                fail += 1
                print_error(f"[{i}/{len(todo)}] 空返回: {str(a.title)[:30]}")
        except Exception as e:
            fail += 1
            print_error(f"[{i}/{len(todo)}] 失败: {str(a.title)[:30]} ({str(e)[:80]})")
        if i < len(todo):
            time.sleep(sleep_sec)

    print_success(f"本次新增: 成功 {ok} 篇, 失败 {fail} 篇")

    # ---- 全量重导 JSON(从CSV读) ----
    all_rows = []
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            all_rows = list(csv.DictReader(f))
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print_success(f"CSV累计 {len(all_rows)} 篇, 已导出: {csv_path} / {json_path}")

    # ---- 2. 用全部摘要汇总月度报告 ----
    if all_rows:
        blocks = []
        for s in all_rows:
            blocks.append(
                f"【{s['标题']}】\n公众号：{s['公众号']}\n链接：{s['链接']}\n发布日期：{s['发布日期']}\n单篇摘要：{s['摘要']}"
            )
        combined = "\n\n---\n\n".join(blocks)
        print_info("开始生成月度报告(基于全部单篇摘要)...")
        try:
            report = call_llm(cfg, "你是一个半导体行业资深分析师。", f"{prompt_report}\n\n以下是{RISCV_RE.pattern}相关文章的单篇分析摘要：\n\n{combined}", max_tokens=12000)
            md_path = f"{out_prefix}_report.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# RISC-V 月度监测报告\n\n{report}")
            print_success(f"月度报告已导出: {md_path}")
            build_report_docx(report, "RISC-V 月度监测报告", f"{out_prefix}_report.docx")
        except Exception as e:
            print_error(f"月度报告生成失败: {str(e)[:120]}")

    session.close()


if __name__ == "__main__":
    main()
