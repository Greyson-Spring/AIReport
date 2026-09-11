# 微信读书公众号采集（weread_mp）原理与使用手册

> 本文档讲清楚"公众号文章是怎么从微信读书抓进数据库的"，以及如何部署、排查。
> 涉及文件：`jobs/mps.py`、`core/wx/base.py`、`core/wx/model/weread.py`、`core/wx/model/weread_mp.py`、
> `tools/host_weread_agent.py`、`tools/weread_qr_capture.py`、`jobs/article.py`、`apis/weread.py`。

---

## 一、为什么必须"宿主机代理 + 真实 Chrome"？

微信读书的 `/web/mp/articles`（公众号文章列表）接口需要**浏览器环境的动态签名**（x-wr-pa 系列）。
后端用纯 HTTP 直接请求会被拒（如 -2041 风控）。只有"真实登录的浏览器、在阅读器页上下文里发请求"才能通过。

所以方案是：**借用一个已扫码登录微信读书的 Chrome，在它的阅读器页里执行 `fetch`，把结果拿回来**。

## 二、整体架构（一图看懂）

```
容器 we-mp-rss-local (FastAPI :8001)
  └─ 定时任务 jobs/mps.py / 手动点"更新"
       └─ base.py Model() 按 GATHER_MODEL 选出采集器 = MpsWereadMP
            └─ weread_mp.py get_Articles()
                 ├─ 列表: POST http://host.docker.internal:9000/fetch  {book_id, offset}
                 └─ 正文: POST .../content                             {review_id}
                      │
宿主机代理 host_weread_agent.py (:9000)   ← 跑在服务器(宿主), 不在容器里
  └─ CDP(Chrome调试协议, WebSocket) 指挥账号池里的 Chrome
       └─ Chrome(端口9222/9223..., 已扫码登录微信读书, 开着阅读器页)
            └─ 阅读页里执行 fetch('/web/mp/articles?bookId=...', {credentials:'include'})
                 → 微信读书返回文章 JSON → 经 CDP 通道传回代理 → 回传给容器后端
                      │
后端解析 → 回调 jobs/article.py UpdateArticle回调 → DB.add_article → 存进 MySQL
```

## 三、完整抓取链路（逐步 + 涉及文件）

1. **触发**：定时任务或网页点"更新" → `jobs/mps.py` 的 `do_job` 调 `wx.get_Articles(...)`。
2. **选采集器**：`core/wx/base.py` 的 `WxGather.Model()` 按配置 `gather.model`（=`.env` 里 `GATHER_MODEL`）创建采集器。当前是 `weread_mp` → `core/wx/model/weread_mp.py` 的 `MpsWereadMP`。
3. **发请求给代理**：`weread_mp.py` 的 `_get_mp_articles_page(book_id)` 把 `{book_id, offset}` POST 给宿主机代理 `/fetch`。
4. **代理指挥 Chrome**：`tools/host_weread_agent.py` 的 `fetch_articles` 按公众号 bookId 哈希选一个账号端口 → `_do_fetch` 通过 CDP 连该 Chrome → 找到**阅读器页** → `Runtime.evaluate` 执行：
   ```js
   fetch('/web/mp/articles?bookId=MP_WXS_xxx&offset=0', {credentials:'include'}).then(r => r.text())
   ```
5. **结果回来**：Chrome 执行 fetch → 微信读书返回文章 JSON 文本 → 作为 JS 返回值经 **CDP WebSocket 通道**传回代理进程 → 代理再作为 HTTP 响应返回容器后端。**全程在内存传字符串，不落盘**。
6. **解析**：`weread_mp.py` 的 `parse_mp_articles` 把 JSON 的 `reviews` 解析成"文章字典"（标题/链接/时间/摘要）。
7. **正文**：若 `GATHER_CONTENT=True`，对每篇调 `_get_mp_content(review_id, url)`：优先走代理 `/content`（Chrome 会话）→ 回退 api 直连原文 → 回退 .env Cookie。
8. **存库**：每篇文章通过回调 `CallBack=UpdateArticle`（`jobs/article.py`）→ `DB.add_article(art)` 写入 MySQL。

## 四、三个关键概念

### 4.1 `fetch()` 是啥
不是 Linux 命令，是**网页 JavaScript 里发网络请求的函数**。执行后返回一个 Promise，`.then(r => r.text())` 把响应读成文本。
`fetch('/web/mp/articles?bookId=...', {credentials:'include'}).then(r => r.text())`
- 浏览器执行它 → 微信读书服务器返回 JSON 文本 → JS 拿到这段文本。
- 关键：它不是"下载到服务器本地文件"，而是把结果作为 JS 的返回值"传回去"。 流程：
- 宿主机代理 _do_fetch():
   ① 通过 CDP 向 Chrome 阅读页发 Runtime.evaluate 指令
   ② Chrome 执行上面那段 JS → fetch 拿到 JSON 文本
   ③ JSON 文本作为"JS 执行结果" → 通过 CDP 的 WebSocket 通道 传回代理进程
   ④ 代理把文本作为 HTTP 响应 返回给容器后端
- 类比：你不是让浏览器"把文件存到硬盘"，而是让它在页面里"发起请求并拿到结果文本"，结果由代理伸手从浏览器里接过来（CDP 通道），再转手交给后端。全程只是内存里传递字符串，不落盘。

### 4.2 JSON 是怎么"回到后端"的（不落盘）
```
Chrome 阅读页执行 fetch → 拿到 JSON 文本
  → 文本作为 Runtime.evaluate 的"返回值"
  → 通过 CDP WebSocket 通道传回宿主机代理进程
  → 代理作为 HTTP 响应返回容器后端
```
关键：结果**不是下载到服务器某个文件**，而是"JS 返回值 → CDP 通道 → 代理内存 → 后端内存"一路传字符串。

### 4.3 回调函数（Callback）是啥
回调 = 你把一个**函数**作为参数传给调用方，调用方在合适时机"回头调用"它。
`weread_mp.py` 里 `CallBack=UpdateArticle`：采集器每解析出一篇文章，就调用一次 `UpdateArticle(art)`，由它把文章存进数据库。**调用方不知道你拿到文章想干嘛，通过回调让你决定**。回调与"钩子(hook)"是同一家族：满足条件/时机就调用你给的那个函数。
先回答你的理解：对，回调和钩子本质是同一家族——都是"满足条件/时机到了，就调用你给的那个函数"。微妙的区别只是：
- 回调：你把自己的函数作为参数传给调用方，调用方在完成时"回头调用"（如 CallBack=UpdateArticle）；
- 钩子：系统在流程里预留插口，你把自己的逻辑挂上去，事件发生时系统调它（如 webhook、生命周期钩子）。
很多场合两者可互换。你抓到"触发→调用"这个本质就对了。
## 五、采集器体系（GATHER_MODEL 是什么）

- `GATHER_MODEL` 是**环境变量**（写在 `.env`，程序启动读进配置 `gather.model`），决定**用哪个采集器**。
- `base.py` 的 `Model()` 按它分发：

| 值 | 采集器 | 原理 | 当前 |
|---|---|---|---|
| `weread_mp` | MpsWereadMP | 微信读书 + 宿主机代理 Chrome | ✅ 当前用的 |
| `web` | MpsWeb | Playwright 直接爬 mp.weixin.qq.com | 备选 |
| `app` | MpsAppMsg | 微信 App 消息接口 | 备选 |
| `api` | MpsApi | 微信公众平台 API | 备选 |

> 四种都继承 base.py 的 WxGather
> 默认值 `web`（config.example.yaml `${GATHER_MODEL:-web}`）。只有 `weread_mp` 走"宿主机代理 + Chrome"。
## 5.1 基类
1. 定义
- 基类 = 被别的类"继承"的类。class MpsWereadMP(MpsWeread) 表示 MpsWereadMP 自动拥有 MpsWeread 的所有能力，再自己加东西。
- 类比：MpsWeread = "微信读书通用工具箱"（会读 cookie、会发请求、会采书架笔记）；MpsWereadMP = "专抓公众号的那个采集器"——继承了工具箱，再加了"抓公众号文章"的逻辑。
2. 关系
|文件| 类 |	关系 | 在公众号抓取里|
|---|---|---|---|
|`core/wx/model/weread.py`|	MpsWeread|	基类|	被继承（提供读 cookie 等）|
|`core/wx/model/weread_mp.py`|	MpsWereadMP|	子类|	✅ 主力（抓公众号）|
|`apis/weread.py`|	— |	管理接口|旁路（配置 cookie/读书笔记用）|
3. 采集器的基类
core/wx/base.py = *所有采集器的"公共底座" + 选采集器的"工厂"*，干两件事：
① 工厂 Model()：按 gather.model 决定用哪个采集器。你在 Model() 里传入类型，它返回对应的采集器对象。
② 公共基类 WxGather：web/app/api/weread_mp 这四种采集器都继承它，共用它的通用能力：
- 文章列表去重（HasGathered/aids）；
- 加载 token/Cookie/User-Agent（get_token）；
- 代理（_get_proxies）；
- 把"文章字典"转成标准格式并触发回调存库（FillBack）；
- 开始/结束/出错/等待等流程控制（Start/Over/Error/Wait）。
所以 base.py = "地基"，四个采集器 = "盖的不同楼"。
## 六、登录与凭据

- **主流程靠 Chrome 扫码登录**：代理在阅读页用 `credentials:'include'`，用的是**浏览器本身的登录态**（扫码登录的），不是 .env 的 Cookie。
- **`.env` 的 `WEREAD_COOKIE` 是旁路/兜底**：只在"代理失败 → api 失败"后的最后直连，以及"读书笔记采集"（`core/wx/model/weread.py` 的书架/划线）时才用。公众号抓取主流程基本用不到它。

## 七、部署与启动（服务器版）

1. **启动容器**：
   ```bash
   cd ~/AIReport
   docker compose -f compose/docker-compose.local.yaml up -d --build
   ```
2. **启动宿主机代理栈**（Xvfb + Chrome 账号 + 代理 :9000，**必须在容器之外单独起**）：
   ```bash
   sudo apt install -y xvfb
   pgrep -f "Xvfb :99" || (Xvfb :99 -screen 0 1280x900x24 &)
   pkill -9 -f host_weread_agent.py; sleep 2
   cd ~/AIReport/tools && nohup python3 host_weread_agent.py > ~/weread-agent.log 2>&1 &
   curl -s http://localhost:9000/status
   ```
   > 开机自启（可选）：把 Xvfb + 代理写进 `tools/server_run_agent.sh`，再启用 `tools/weread-host.service`。
3. **账号扫码登录**：网站"账号池"页添加账号 → 扫码 → 用代理把该 Chrome 导航到阅读器页：
   ```bash
   curl "http://localhost:9000/navigate?port=9222&url=https%3A%2F%2Fweread.qq.com%2Fweb%2Fmp%2Freader%2F1b742a6224d505f5758535f33303831363733383033e66"
   ```
4. **验证**：网页点"更新"某公众号，日志出现"微信读书公众号采集模式 xxx" + 成功 N 条。

## 八、常见问题速查

| 现象 | 原因 / 处理 |
|---|---|
| 代理报 `host_agent_error` | 宿主机代理没启动 → 按"七.2"启动 |
| 代理报 `NO_READER_PAGE` | 该账号 Chrome 没开阅读器页 → 用 /navigate 导航阅读页 |
| 队列"显示成功但没抓到新文章" | 早期代码把 `NO_READER_PAGE` 字符串错误当成功 → 已修：有 errCode 即报错 |
| 抓取报 -2014 / -2041 | 限流/风控 → 停手冷却，别猛打；多账号分摊 |
| 某公众号抓不到 | 该号需在微信读书里已关注/在书架 |
| 正文为空 | `GATHER.CONTENT=True` 是否生效（**带点号**）；或用 `tools/backfill_content.py` 补抓 |
| `GATHER_MODEL` 不生效 | .env 变量名/点号问题；用 `docker exec we-mp-rss-local env` 验证 |

## 九、文件清单与职责

| 文件 | 职责 | 在抓取链路里 |
|---|---|---|
| `jobs/mps.py` | 定时/手动触发采集 | 入口 |
| `core/wx/base.py` | `Model()` 工厂选采集器 + 公共基类 WxGather（去重/回调/代理等） | 分发 |
| `core/wx/model/weread.py` | 微信读书基类 MpsWeread（读 Cookie、书架/笔记采集） | 被继承 |
| `core/wx/model/weread_mp.py` | 公众号采集器 MpsWereadMP（列表/正文，走宿主机代理） | ✅ 主力 |
| `tools/host_weread_agent.py` | 宿主机代理：把 CDP 抓取封装成 HTTP 接口（/fetch、/content、/qr…） | ✅ 关键 |
| `tools/weread_qr_capture.py` | 用 Playwright 截账号二维码的辅助脚本 | 登录用 |
| `jobs/article.py` | `UpdateArticle` 回调：把文章写进 MySQL | 存库 |
| `apis/weread.py` | 微信读书管理接口（Cookie 配置/测试/读书笔记） | 旁路 |
