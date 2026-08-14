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
    req = urllib.request.Request(AGENT_BASE + path)
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))


def _agent_post(path, data=None):
    body = json.dumps(data or {}).encode('utf-8')
    req = urllib.request.Request(AGENT_BASE + path, data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))


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
    """启动一个新Chrome账号, 自动点"登录"让二维码显示, 返回端口"""
    import urllib.parse
    try:
        result = _agent_post("/spawn", {})
        if result.get('err'):
            return error_response(code=50002, message=f"启动Chrome失败: {result['err']}")
        port = result.get('port')
        if port:
            import time
            # 1. 导航到微信读书首页(刷新拿新二维码)
            try:
                _agent_get(f"/navigate?port={port}&url={urllib.parse.quote('https://weread.qq.com/')}")
            except Exception:
                pass
            # 2. 点"登录"让二维码显示(重试2轮)
            for _round in range(2):
                for text in ['登录', '扫码登录', '微信登录']:
                    try:
                        _agent_get(f"/click?port={port}&text={urllib.parse.quote(text)}")
                    except Exception:
                        pass
                time.sleep(4)
        return success_response(data=result, message="账号已启动, 请尽快扫码登录")
    except Exception as e:
        return error_response(code=50001, message=f"添加失败(确认代理已启动): {e}")


@router.post("/refresh", summary="刷新某账号的登录二维码")
async def account_refresh(port: int = Body(...), current_user: dict = Depends(get_current_user_or_ak)):
    """重新导航+点登录, 生成新二维码(过期时用)"""
    import urllib.parse
    try:
        _agent_get(f"/navigate?port={port}&url={urllib.parse.quote('https://weread.qq.com/')}")
        for text in ['登录', '扫码登录', '微信登录']:
            try:
                _agent_get(f"/click?port={port}&text={urllib.parse.quote(text)}")
            except Exception:
                pass
        return success_response(data={"port": port}, message="二维码已刷新, 请尽快扫码")
    except Exception as e:
        return error_response(code=50001, message=f"刷新失败: {e}")


@router.post("/remove", summary="移除账号")
async def account_remove(port: int = Body(...), current_user: dict = Depends(get_current_user_or_ak)):
    """停掉指定端口对应的Chrome账号"""
    try:
        result = _agent_post("/remove", {"port": port})
        return success_response(data=result, message="账号已移除")
    except Exception as e:
        return error_response(code=50001, message=f"移除失败: {e}")
