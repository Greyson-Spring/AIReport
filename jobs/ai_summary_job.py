"""AI摘要定时任务执行模块

遍历所选公众号的所有文章，对 description 为空或未生成摘要的文章调用 LLM 生成摘要。
"""
import json
import httpx
from datetime import datetime
from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.models.ai_summary_task import AISummaryTask
from core.models.config_management import ConfigManagement
from core.task import TaskScheduler
from core.print import print_info, print_success, print_error

ai_summary_scheduler = TaskScheduler()

# ---------- LLM 调用（与 apis/ai_summary.py 逻辑一致）----------

SINGLE_ARTICLE_PROMPT = (
    "请对以下文章内容进行摘要总结，用2-3句话提取关键信息和要点。"
    "摘要中请包含公众号名称、文章标题、文章链接和发布日期。\n\n"
)


def _get_llm_config():
    """从数据库读取大模型配置"""
    session = DB.get_session()
    try:
        keys = ["llm_api_url", "llm_api_key", "llm_model"]
        configs = session.query(ConfigManagement).filter(
            ConfigManagement.config_key.in_(keys)
        ).all()
        cfg = {c.config_key: c.config_value for c in configs}
        return {
            "api_url": cfg.get("llm_api_url", ""),
            "api_key": cfg.get("llm_api_key", ""),
            "model": cfg.get("llm_model", "gpt-3.5-turbo"),
        }
    finally:
        session.close()


def _call_llm_sync(api_url: str, api_key: str, model: str,
                    system_msg: str, user_msg: str) -> str:
    """同步方式调用 LLM（在后台线程中使用）"""
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

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        raise Exception(f"API调用失败({resp.status_code}): {resp.text[:300]}")

    result = resp.json()
    content = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    return content.strip()


# ---------- 任务执行 ----------

def _is_summary_generated(article) -> bool:
    """通过 ai_summarized 标记字段判断文章是否已生成过AI摘要"""
    return getattr(article, 'ai_summarized', 0) == 1


def run_ai_summary_task(task_id: str):
    """执行单个 AI 摘要任务"""
    session = DB.get_session()
    try:
        task = session.query(AISummaryTask).filter(AISummaryTask.id == task_id).first()
        if not task:
            print_error(f"AI摘要任务 [{task_id}] 不存在")
            return

        llm_cfg = _get_llm_config()
        if not llm_cfg["api_url"] or not llm_cfg["api_key"]:
            print_error("AI摘要任务执行失败：大模型未配置，请先在「大模型配置」页面设置")
            return

        # 解析公众号列表
        mp_ids = []
        try:
            mps = json.loads(task.mps_id)
            mp_ids = [item["id"] if isinstance(item, dict) else item for item in mps]
        except (json.JSONDecodeError, KeyError):
            pass

        # 查询公众号名称映射
        if mp_ids:
            feeds = session.query(Feed).filter(Feed.id.in_(mp_ids)).all()
        else:
            feeds = session.query(Feed).filter(Feed.status == 1).all()
            mp_ids = [f.id for f in feeds]

        mp_name_map = {f.id: f.mp_name for f in feeds}

        # 查询需要处理的文章（排除已生成AI摘要的）
        query = session.query(Article).filter(
            Article.mp_id.in_(mp_ids),
            Article.status == 1,
            (Article.ai_summarized == 0) | (Article.ai_summarized == None)
        )
        articles = query.order_by(Article.publish_time.desc()).all()

        prompt = task.prompt or SINGLE_ARTICLE_PROMPT
        system_msg = "你是一个专业的内容分析助手，擅长总结和提炼文章要点。"
        model = llm_cfg["model"]

        total = len(articles)
        generated = 0
        skipped = 0
        failed = 0

        print_info(f"AI摘要任务 [{task.name}] 开始执行，共 {total} 篇文章")

        for idx, art in enumerate(articles):
            text = art.content or art.description or ""
            if not text.strip():
                skipped += 1
                continue

            try:
                mp_name = mp_name_map.get(art.mp_id, '未知公众号')
                pub_date = datetime.fromtimestamp(art.publish_time).strftime('%Y-%m-%d') if art.publish_time else '未知'
                link = art.url or ''
                meta = f"公众号：{mp_name}\n标题：{art.title}\n链接：{link}\n发布日期：{pub_date}"
                user_msg = f"{prompt}\n\n{meta}\n正文：{text}"

                summary = _call_llm_sync(
                    llm_cfg["api_url"], llm_cfg["api_key"], model,
                    system_msg, user_msg
                )
                if summary:
                    art.description = summary
                    art.ai_summarized = 1
                    session.commit()
                    generated += 1
                else:
                    failed += 1
            except Exception as e:
                session.rollback()
                failed += 1
                print_error(f"AI摘要生成失败 [{art.title}]: {e}")

            if (idx + 1) % 10 == 0:
                print_info(f"AI摘要进度 [{task.name}]: {idx + 1}/{total} (生成:{generated} 跳过:{skipped} 失败:{failed})")

        print_success(f"AI摘要任务 [{task.name}] 完成: 总计{total}篇, 生成{generated}篇, 跳过{skipped}篇, 失败{failed}篇")

    except Exception as e:
        print_error(f"AI摘要任务执行异常: {e}")
    finally:
        session.close()


# ---------- 调度器管理 ----------

def reload_ai_summary_jobs():
    """重载所有 AI 摘要定时任务"""
    ai_summary_scheduler.clear_all_jobs()
    start_ai_summary_jobs()


def start_ai_summary_jobs():
    """启动所有启用的 AI 摘要定时任务"""
    session = DB.get_session()
    try:
        tasks = session.query(AISummaryTask).filter(AISummaryTask.status == 1).all()
        if not tasks:
            print_info("没有启用的AI摘要定时任务")
            return

        for task in tasks:
            if not task.cron_exp:
                print_error(f"AI摘要任务 [{task.id}] 没有设置cron表达式")
                continue
            job_id = ai_summary_scheduler.add_cron_job(
                run_ai_summary_task,
                cron_expr=task.cron_exp,
                kwargs={"task_id": task.id},
                job_id=f"ai_summary_{task.id}",
                tag="AI摘要定时"
            )
            print_info(f"已添加AI摘要定时任务: {task.name} ({job_id})")

        ai_summary_scheduler.start()
        print_success(f"AI摘要调度器已启动，共 {len(tasks)} 个任务")
    except Exception as e:
        print_error(f"启动AI摘要调度器失败: {e}")
    finally:
        session.close()
