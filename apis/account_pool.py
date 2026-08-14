"""账号池管理接口: 代理宿主机代理的账号增删查/状态"""
import json
import urllib.request
from fastapi import APIRouter, Depends, Body
from core.auth import get_current_user_or_ak
from core.config import cfg
from .base import success_response, error_response

router = APIRouter(prefix="/account-pool", tags=["账号池"])

# 宿主机代理地址(容器内通过 host.docker.internal 访问宿主机)
AGENT_BASE = cfg.get("weread.host_agent", "http://host.docker.internal:9000")
AGENT_BASE = AGENT_BASE.replace("/fetch", "")  # 去掉可能带上的 /fetch 后缀


def _agent_get(path):
    req = urllib.request.Request(AGENT_BASE + path, timeout=10)
    return json.loads(urllib.request.urlopen(req).read().decode('utf-8'))


def _agent_post(path, data=None):
    body = json.dumps(data or {}).encode('utf-8')
    req = urllib.request.Request(AGENT_BASE + path, data=body,
                                 headers={"Content-Type": "application/json"},
                                 timeout=20)
    return json.loads(urllib.request.urlopen(req).read().decode('utf-8'))


@router.get("/status", summary="账号池状态")
async def account_status(current_user: dict = Depends(get_current_user_or_ak)):
    """获取每个账号的状态(登录/错误码/Chrome是否存活)"""
    try:
        return success_response(data=_agent_get("/status"))
    except Exception as e:
        return error_response(code=50001, message=f"无法连接宿主机代理, 请确认代理已启动: {e}")


@router.get("/accounts", summary="账号列表")
async def account_list(current_user: dict = Depends(get_current_user_or_ak)):
    try:
        return success_response(data=_agent_get("/accounts"))
    except Exception as e:
        return error_response(code=50001, message=f"无法连接宿主机代理: {e}")


@router.get("/qr", summary="获取账号登录二维码图片(代理宿主机)")
async def account_qr(port: int = 9222, current_user: dict = Depends(get_current_user_or_ak)):
    """返回某账号Chrome当前画面(登录二维码), 经后端转发给浏览器"""
    from fastapi.responses import Response
    try:
        img = urllib.request.urlopen(f"{AGENT_BASE}/qr?port={port}", timeout=15).read()
        return Response(content=img, media_type="image/png")
    except Exception:
        return Response(content=b'', media_type="image/png")


@router.post("/add", summary="添加账号(启动新Chrome)")
async def account_add(current_user: dict = Depends(get_current_user_or_ak)):
    """启动一个新Chrome账号, 返回端口, 之后用 /qr?port= 看二维码扫码登录"""
    try:
        result = _agent_post("/spawn", {})
        if result.get('err'):
            return error_response(code=50002, message=f"启动Chrome失败: {result['err']}")
        return success_response(data=result, message="账号已启动, 请扫码登录")
    except Exception as e:
        return error_response(code=50001, message=f"添加失败(确认代理已启动): {e}")


@router.post("/remove", summary="移除账号")
async def account_remove(port: int = Body(...), current_user: dict = Depends(get_current_user_or_ak)):
    """停掉指定端口对应的Chrome账号"""
    try:
        result = _agent_post("/remove", {"port": port})
        return success_response(data=result, message="账号已移除")
    except Exception as e:
        return error_response(code=50001, message=f"移除失败: {e}")
