# AIReport（WeRSS）— 公众号智能采集与总结系统

<div align="center">
<img src="static/logo.svg" alt="AIReport Logo" width="20%">
</div>

> 一个部署在公司内网服务器上的**微信公众号文章采集与 LLM 总结系统**：
> 通过微信读书 + 宿主机 Chrome 账号池自动抓取公众号文章，接入大模型生成单篇摘要与月度报告，Web 展示并可导出。

---

## 功能特性

- **公众号文章自动采集**：基于微信读书网页端，通过已登录 Chrome 账号池抓取文章列表与正文
- **定时任务**：按 cron 定时更新所有订阅公众号
- **LLM 摘要 / AI 报告**：按提示词为单篇文章生成摘要、为整月生成汇总报告
- **RSS 订阅**：为订阅内容生成 RSS 源
- **消息任务 + WebHook**：定时任务可推送公众号更新到自定义通知渠道（钉钉 / 飞书 / 企业微信 / 自定义）
- **HTML 内容过滤规则**：全局 / 公众号专属，自动清理广告等无用元素
- **多用户与权限**：用户订阅隔离、Access Key (AK) 认证、文件夹分组
- **账号池管理**：多微信读书账号（每账号一个 Chrome 端口），按公众号哈希分摊、防限流
- **多主题 / 响应式**：PC 与移动端分页适配
- **导出**：md / docx / pdf / json 等格式

---

## 系统架构（一句话）

```
定时任务 → 后端(FastAPI, 容器) → 宿主机代理(:9000, 不在容器) → 已登录微信读书的 Chrome 账号池
  → 在阅读器页执行 fetch 拿文章 JSON → 回传后端 → 存 MySQL → 页面展示 / LLM 摘要 / AI 报告
```

- **为什么绕不开"代理 + Chrome"**：微信读书文章接口需要浏览器环境的动态签名，纯 HTTP 会被拒；所以借用一个已扫码登录微信读书的 Chrome，在阅读器页里发请求。
- 详见 [docs/部署流程记录.md](docs/部署流程记录.md) 与 [tools/README-weread.md](tools/README-weread.md)。

---

## 快速开始（服务器部署）

**前置**：服务器已装 Docker 与 Compose；`~/AIReport/.env` 已配置（数据库凭据、GATHER_MODEL=weread_mp 等）。

```bash
# 1. 启动容器(首次 10~30 分钟)
cd ~/AIReport
docker compose -f compose/docker-compose.local.yaml up -d --build
docker compose -f compose/docker-compose.local.yaml ps

# 2. 启动宿主机抓取代理栈(Xvfb + Chrome 账号 + 代理 :9000)
sudo apt install -y xvfb
pgrep -f "Xvfb :99" || (Xvfb :99 -screen 0 1280x900x24 &)
pkill -9 -f host_weread_agent.py; sleep 2
cd ~/AIReport/tools && nohup python3 host_weread_agent.py > ~/weread-agent.log 2>&1 &
curl -s http://localhost:9000/status

# 3. 浏览器访问，登录后到"账号池"页添加账号并扫码，用 /navigate 打开阅读器页
```

浏览器访问 `http://<服务器IP>:8001`，登录 `admin / admin@123`（**建议尽快改密**）。

> 完整部署、日常运维、备份、常见问题见 [docs/部署流程记录.md](docs/部署流程记录.md)。

---

## 常用命令速查

```bash
cd ~/AIReport

# 容器
docker compose -f compose/docker-compose.local.yaml ps                  # 状态
docker compose -f compose/docker-compose.local.yaml logs -f we-mp-rss  # 实时日志(用服务名)
docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss   # 改代码后重建

# 宿主机代理(改代理代码后必须重启)
pkill -9 -f host_weread_agent.py; sleep 2
cd ~/AIReport/tools && nohup python3 host_weread_agent.py > ~/weread-agent.log 2>&1 &
curl -s http://localhost:9000/status

# 容器内跑一次性脚本(补正文/批量摘要; 依赖在虚拟环境, 必须用它的python)
docker cp 脚本 we-mp-rss-local:/app/tools/xxx.py
docker exec -it we-mp-rss-local sh -c 'PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" tools/xxx.py'
```

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/部署流程记录.md](docs/部署流程记录.md) | 项目框架 + 完整部署（容器/宿主机代理/账号池）+ 日常运维 + 备份 |
| [tools/README-weread.md](tools/README-weread.md) | 微信读书采集原理：抓取链路、fetch/CDP/回调、采集器体系 |
| [lh/README.md](lh/README.md) | RISC-V 文章摘要与月度报告导出工具 |
| [docs/AIReport配置系统.md](docs/AIReport配置系统.md) | 三层环境变量 / config.yaml / 配置原理 |
| [docs/docker命令笔记.md](docs/docker命令笔记.md) | Docker / scp / compose 小白教程 |
| [docs/docker-compose多容器耦合.md](docs/docker-compose多容器耦合.md) | 容器之间怎么耦合运行 |
| [docs/问题和解决.md](docs/问题和解决.md) | 历史问题排查与解决（正文/图片/性能/认证等） |

---

## 技术栈

- 后端：Python 3.13 + FastAPI + SQLAlchemy（ORM）
- 前端：Vue 3 + Vite + Arco Design
- 数据库：MySQL（容器）
- 缓存：Redis（容器）
- 抓取：宿主机代理（CDP）+ Chrome 账号池 + Xvfb
- 部署：Docker Compose
- 大模型：OpenAI 兼容接口（可配 API URL / Key / Model）

## 目录结构（关键）

| 目录 | 职责 |
|---|---|
| `apis/` | 后端接口（文章/公众号/账号池/AI 摘要等） |
| `core/` | 核心逻辑：模型、数据库、配置、采集基类 |
| `jobs/` | 定时任务（抓取、补正文、AI 摘要） |
| `tools/` | 宿主机代理、补抓/批量摘要脚本、HTML 处理 |
| `driver/` | 微信/爬取相关驱动 |
| `views/` | 后端渲染的页面（文章详情等） |
| `web_ui/` | 前端源码（构建后进 `static/`） |
| `compose/` | Docker Compose 配置 |

---

## License

MIT
