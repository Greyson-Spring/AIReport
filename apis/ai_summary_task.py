import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel
from typing import Optional
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.ai_summary_task import AISummaryTask
from .base import success_response, error_response

router = APIRouter(prefix="/ai-summary-tasks", tags=["AI摘要任务"])


class AISummaryTaskCreate(BaseModel):
    name: str
    prompt: Optional[str] = None
    mps_id: str  # JSON string
    cron_exp: str
    status: int = 1


class AISummaryTaskUpdate(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None
    mps_id: Optional[str] = None
    cron_exp: Optional[str] = None
    status: Optional[int] = None


@router.get("", summary="获取AI摘要任务列表")
def list_tasks(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        total = session.query(AISummaryTask).count()
        tasks = session.query(AISummaryTask).order_by(
            AISummaryTask.created_at.desc()
        ).offset(offset).limit(limit).all()

        task_list = []
        for t in tasks:
            task_list.append({
                "id": t.id,
                "name": t.name,
                "prompt": t.prompt,
                "mps_id": t.mps_id,
                "cron_exp": t.cron_exp,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            })

        return success_response({
            "list": task_list,
            "total": total,
            "page": {"limit": limit, "offset": offset}
        })
    except Exception as e:
        return error_response(500, str(e))
    finally:
        session.close()


@router.get("/{task_id}", summary="获取AI摘要任务详情")
def get_task(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        task = session.query(AISummaryTask).filter(AISummaryTask.id == task_id).first()
        if not task:
            return error_response(404, "任务不存在")
        return success_response({
            "id": task.id,
            "name": task.name,
            "prompt": task.prompt,
            "mps_id": task.mps_id,
            "cron_exp": task.cron_exp,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        })
    except Exception as e:
        return error_response(500, str(e))
    finally:
        session.close()


@router.post("", summary="创建AI摘要任务")
def create_task(
    data: AISummaryTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        task = AISummaryTask(
            id=str(uuid.uuid4()),
            name=data.name,
            prompt=data.prompt,
            mps_id=data.mps_id,
            cron_exp=data.cron_exp,
            status=data.status,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(task)
        session.commit()
        return success_response({"id": task.id}, message="创建成功")
    except Exception as e:
        session.rollback()
        return error_response(500, str(e))
    finally:
        session.close()


@router.put("/{task_id}", summary="更新AI摘要任务")
def update_task(
    task_id: str,
    data: AISummaryTaskUpdate = Body(...),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        task = session.query(AISummaryTask).filter(AISummaryTask.id == task_id).first()
        if not task:
            return error_response(404, "任务不存在")

        if data.name is not None:
            task.name = data.name
        if data.prompt is not None:
            task.prompt = data.prompt
        if data.mps_id is not None:
            task.mps_id = data.mps_id
        if data.cron_exp is not None:
            task.cron_exp = data.cron_exp
        if data.status is not None:
            task.status = data.status
        task.updated_at = datetime.now()

        session.commit()
        return success_response(message="更新成功")
    except Exception as e:
        session.rollback()
        return error_response(500, str(e))
    finally:
        session.close()


@router.delete("/{task_id}", summary="删除AI摘要任务")
def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        task = session.query(AISummaryTask).filter(AISummaryTask.id == task_id).first()
        if not task:
            return error_response(404, "任务不存在")
        session.delete(task)
        session.commit()
        return success_response(message="删除成功")
    except Exception as e:
        session.rollback()
        return error_response(500, str(e))
    finally:
        session.close()


@router.put("/job/fresh", summary="应用AI摘要任务（重载调度器）")
def fresh_ai_summary_jobs(
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        from jobs.ai_summary_job import reload_ai_summary_jobs
        reload_ai_summary_jobs()
        return success_response(message="AI摘要任务已应用")
    except Exception as e:
        return error_response(500, f"应用失败: {str(e)}")


@router.get("/{task_id}/run", summary="手动执行AI摘要任务")
def run_task(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        task = session.query(AISummaryTask).filter(AISummaryTask.id == task_id).first()
        if not task:
            return error_response(404, "任务不存在")

        from jobs.ai_summary_job import run_ai_summary_task
        import threading
        t = threading.Thread(target=run_ai_summary_task, args=(task_id,))
        t.daemon = True
        t.start()

        return success_response(message=f"AI摘要任务「{task.name}」已开始执行，将在后台进行")
    except Exception as e:
        return error_response(500, str(e))
    finally:
        session.close()
