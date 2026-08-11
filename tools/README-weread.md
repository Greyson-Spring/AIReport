# 微信读书采集（weread_mp）使用说明

## 架构原理

```
WeRSS (Docker容器, weread_mp模式)
   ↓ POST http://host.docker.internal:9000/fetch {book_id}
宿主机代理 (tools/host_weread_agent.py, 端口9000)
   ↓ CDP WebSocket
宿主机Edge (--remote-debugging-port=9222, 已登录微信读书, 开着阅读器页)
   ↓ 页面内fetch (浏览器自动计算x-wrpa动态签名)
微信读书 → 文章列表 → 数据库
```

**为什么需要这样？** 微信读书 `/web/mp/articles` 接口需要浏览器动态签名(x-wrpa-0)，后端直接请求会被拒绝(-2041)。只有真实浏览器在阅读器页上下文里发请求才能通过。所以借用一个"登录着的真实Edge"来完成请求。

## 启动步骤

### 1. 启动宿主机服务（每次开机后执行一次）
双击 `tools/start_weread_host.bat`，会启动两个窗口：
- **weread-edge**：Edge（调试口9222，独立配置）打开河海大学阅读器页
- **weread-agent**：宿主机代理（端口9000）

> 首次使用：在 weread-edge 窗口里扫码登录微信读书（只需一次，配置会保存）。

### 2. 确认 WeRSS 容器已配置
`.env` 里（本机保留，未提交到git）：
```
GATHER_MODEL=weread_mp
WEREAD_COOKIE="wr_vid=...; wr_skey=..."   # 微信读书登录Cookie
```
容器用 `docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss` 重建即可。

### 3. 触发抓取
- 网页上点公众号"更新"，或等定时任务。
- 日志看到 `微信读书公众号采集模式: xxx` + `成功N条` 即为成功。

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 日志报 `host_agent_error` | 宿主机代理没启动 | 运行 `start_weread_host.bat` |
| 代理报 `NO_READER_PAGE` | Edge里没有打开阅读器页 | 在 weread-edge 窗口打开阅读器页 |
| 代理报 `CDP_RECV_FAIL`/超时 | 阅读器页卡住 | 在 weread-edge 里按 F5 刷新阅读器页 |
| 某公众号抓不到 | 该号不在你的微信读书书架 | 在微信读书里订阅/收藏它 |
| `gather.model` 不是 weread_mp | 环境变量没生效 | 确认 `.env` 用 `GATHER_MODEL`(无点) |

## 限制与注意

1. **只覆盖微信读书里有的公众号**：需要先在微信读书关注该公众号（`weread.qq.com` 搜公众号 → 加入书架）。
2. **Edge 和代理必须常驻**：这两个窗口关闭则无法抓取。可考虑把 bat 加入开机启动（Win+R → `shell:startup` 放入快捷方式）。
3. **阅读器页偶尔卡住**：刷新即可恢复（代理已加30秒超时保护）。
4. **Cookie 可能过期**：微信读书登录失效后，在 weread-edge 里重新扫码。
5. **频率控制**：微信读书有限频，别设置过短抓取间隔。

## 文件清单

- `tools/host_weread_agent.py` — 宿主机代理（把CDP抓取包成HTTP接口）
- `tools/start_weread_host.bat` — 一键启动 Edge + 代理
- `core/wx/model/weread.py` — 微信读书基类（来自上游）
- `core/wx/model/weread_mp.py` — 公众号采集（已改造：文章列表走宿主机代理）
- `apis/weread.py` — 微信读书管理接口
- `web_ui/...` — 微信读书管理页面
