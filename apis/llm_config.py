from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.config_management import ConfigManagement
from .base import success_response, error_response

router = APIRouter(prefix="/llm-config", tags=["大模型配置"])

LLM_CONFIG_KEYS = {
    "api_url": "llm_api_url",
    "api_key": "llm_api_key",
    "model": "llm_model",
}


class LLMConfigRequest(BaseModel):
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


@router.get("", summary="获取大模型配置")
def get_llm_config(
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        keys = list(LLM_CONFIG_KEYS.values())
        configs = session.query(ConfigManagement).filter(
            ConfigManagement.config_key.in_(keys)
        ).all()
        config_map = {c.config_key: c.config_value for c in configs}

        return success_response({
            "api_url": config_map.get("llm_api_url", ""),
            "api_key": config_map.get("llm_api_key", ""),
            "model": config_map.get("llm_model", "gpt-3.5-turbo"),
        })
    except Exception as e:
        return error_response(500, f"获取大模型配置失败: {str(e)}")
    finally:
        session.close()


@router.put("", summary="保存大模型配置")
def save_llm_config(
    req: LLMConfigRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        updates = {
            "llm_api_url": req.api_url or "",
            "llm_api_key": req.api_key or "",
            "llm_model": req.model or "gpt-3.5-turbo",
        }

        for key, value in updates.items():
            existing = session.query(ConfigManagement).filter(
                ConfigManagement.config_key == key
            ).first()
            if existing:
                existing.config_value = value
            else:
                session.add(ConfigManagement(
                    config_key=key,
                    config_value=value,
                    description=f"大模型配置 - {key}"
                ))

        session.commit()
        return success_response(message="大模型配置已保存")
    except Exception as e:
        session.rollback()
        return error_response(500, f"保存大模型配置失败: {str(e)}")
    finally:
        session.close()
