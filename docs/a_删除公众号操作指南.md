# 删除公众号操作指南（服务器上自己删）

> 在服务器上用 Python 安全删除公众号（连文章和所有关联数据一起删）。
> 以后你要删号，照这份指南做就行，不用找别人帮忙。

---

## 一、原理：为什么容器在跑，就能用 Python 删除？

**关键：we-mp-rss 容器里跑着一个完整的 Python 应用，它连着数据库。**

```
we-mp-rss 容器（在运行）
  ├── Python 环境 (/app/env_x86_64/bin/python3)
  │     里面有这个项目所有代码(模型、数据库连接)
  ├── 数据库连接配置 (环境变量里存着 MySQL 的地址密码)
  └── 连接 → MySQL 数据库 (db-mp-local 容器)
```

**`docker exec we-mp-rss-local /app/env_x86_64/bin/python3 /app/xxx.py`** 的意思是：
> "钻进正在运行的容器里，用容器自己的 Python 跑一段代码。"

因为容器里**已经有**数据库连接的配置和项目模型代码，所以这段代码能**用和网站一样的"正规方式"操作数据库**（通过 ORM 模型），比直接手改数据库安全得多。

---

## 二、通用步骤（以后自己删号）

### 第 1 步：在服务器 home 目录建脚本

```
cat > ~/delete_feeds.py << 'PYEOF'
[脚本内容, 见第三节]
PYEOF
```

### 第 2 步：拷进容器并运行

```
docker cp ~/delete_feeds.py we-mp-rss-local:/app/delete_feeds.py
docker exec we-mp-rss-local /app/env_x86_64/bin/python3 /app/delete_feeds.py
```
- /app/env_x86_64/是python的虚拟环境。*虚拟环境 = 一个"独立的 Python + 它自己的依赖箱"*。每个项目可以装各自版本的包，互不干扰，也不污染系统的 Python。
- 容器里*系统的 python3 是"裸的"*，没装 SQLAlchemy 等项目依赖；项目的依赖（数据库、ORM 等）都装在 /app/env_x86_64 里。
- 所以跑项目代码（import core.db 需要 SQLAlchemy）必须用虚拟环境里的 python，否则报 No module named 'sqlalchemy'。
① 我凭什么知道 env_x86_64 是虚拟环境？
几个证据：
- Dockerfile 设了 PLANT_PATH=/app/env，并 RUN /app/install.sh（install 里会 python -m venv 建虚拟环境 + pip 装依赖）；
- start.sh 里 source /app/env_x86_64/bin/activate（激活虚拟环境 = venv 的标准操作）；
- 文件夹结构 bin/python3 + lib = 虚拟环境的标志；
- 而且容器裸 python3 没依赖，只有 venv 里有。
② 虚拟环境 = 独立的解释器 + 依赖库？
对，基本就是这样。它是一个独立的文件夹，里面有自己的 python 可执行文件 + 自己的一份已安装依赖库（site-packages）。目的：隔离——每个项目装自己的版本，互不干扰，不污染系统 Python。
③ 这个 python 和依赖是 Docker 根据 Dockerfile 下载的吗？
对。镜像从 base-full（里面带着系统 Python）开始，然后 Dockerfile 里 RUN install.sh 创建 /app/env_x86_64 虚拟环境并从镜像源 pip install requirements.txt。所以依赖是在"构建镜像"这一步装进 venv 的。
④ 容器运行完全参考这个虚拟环境？
主程序是：容器启动执行 start.sh → source .../activate 激活 venv → 用 venv 的 python 跑 main.py。所以网站/定时任务用的都是 venv 的 python + 它装的库。
（容器里其它系统工具/系统服务还是用系统 python，但和项目无关。）
⑤ 系统 python3 是啥？
就是 Ubuntu 系统自带的 Python（一般在 /usr/bin/python3），装系统时就带着，只有标准库、没有项目装的第三方包。所以直接 python3 跑项目代码会 No module named 'sqlalchemy'——这就是为什么必须用 venv 里的 python。
### 第 3 步：验证
- python3 -c "代码" = 把双引号里的字符串当作代码执行（不用写文件）。适合一次性小命令。
```
python3 -c "
import urllib.request, json
login = urllib.request.Request('http://localhost:8001/api/v1/wx/auth/login', data=b'username=admin&password=admin@123', headers={'Content-Type':'application/x-www-form-urlencoded'})
token = json.loads(urllib.request.urlopen(login, timeout=30).read())['data']['access_token']
req = urllib.request.Request('http://localhost:8001/api/v1/wx/mps?limit=1000', headers={'Authorization':'Bearer '+token})
mps = json.loads(urllib.request.urlopen(req, timeout=30).read())['data']['list']
print('剩余公众号:', len(mps))
for m in mps: print(' -', m.get('mp_name'))
"
```
① 验证用的 python3 是系统的吗？
是服务器（宿主 Ubuntu）的系统 python3，不是容器里的。因为它这段脚本只用标准库（urllib/json）发 HTTP 请求，不 import 项目代码，所以任何 python3 都行——包括宿主机系统那个。
② 为啥叫 python3？
Linux 约定：Python 3 的命令叫 python3（很多新版 Ubuntu 连 python 都不定义，避免和 Python 2 混淆）。
③ -c 是执行？
对，python3 -c "代码" = 把双引号里的字符串当作代码执行（不用写文件）。适合一次性小命令。
④ 这段验证是调用后端接口拿公众号信息吗？
对，两个 HTTP 调用：
1. 登录：POST /api/v1/wx/auth/login，传 username=admin&password=admin@123（表单格式）→ 后端验证 → 返回一个 token；
2. 拿列表：GET /api/v1/wx/mps，请求头里带 Authorization: Bearer <token> → 后端确认是你 → 返回公众号列表。
⑤ token 是啥？怎么"解析"的？
- *token = 登录成功后后端发给你的"门禁卡/通行证"*。之后每次请求带上它，后端就知道"这是登录过的 admin"，不用每回都输密码。
- 登录响应的 JSON 长这样：
{"code":0, "data": {"access_token": "eyJhbGciOi...", "user": {...}}}
- 代码 json.loads(...)['data']['access_token'] 就是：把返回的 JSON 解析成 Python 字典 → 取 data 里的 access_token 字符串 → 存进 token 变量。这就是"解析 token"。
- 然后拼进请求头：headers={'Authorization':'Bearer '+token}。
一句话：登录拿"卡"(token) → 之后每次请求出示这张卡，脚本里用 json.loads(...)['data']['access_token'] 把卡从登录响应里取出来。
---

## 三、删除脚本模板（通用版）

**把 `NAMES` 列表改成你想删的公众号名字**，然后按第二节操作。

```python
import sys
sys.path.insert(0, '/app')
from core.db import DB
from core.models.feed import Feed
from core.models.article import Article
from core.models.user_feed import UserFeed
from core.models.user_read_article import UserReadArticle
from core.models.user_hidden_article import UserHiddenArticle
from core.models.user_favorite import UserFavorite
from core.models.ai_report_history import AIReportHistory
from core.models.filter_rule import FilterRule
from core.models.folder import Folder, FolderFeed

# ★★★ 改成你要删的公众号名字（要和网站显示的一模一样）★★★
NAMES = [
    '要删的公众号A',
    '要删的公众号B',
]

session = DB.get_session()
try:
    for name in NAMES:
        feeds = session.query(Feed).filter(Feed.mp_name == name).all()
        if not feeds:
            print(f'未找到: {name}')   # 名字对不上(有空格/全半角等)会显示这个
            continue
        for feed in feeds:
            fid = feed.id
            # 1. 找这个号的所有文章ID
            art_ids = [r[0] for r in session.query(Article.id).filter(Article.mp_id == fid).all()]
            # 2. 删文章相关的"用户阅读/隐藏/收藏"记录
            if art_ids:
                session.query(UserReadArticle).filter(UserReadArticle.article_id.in_(art_ids)).delete(synchronize_session=False)
                session.query(UserHiddenArticle).filter(UserHiddenArticle.article_id.in_(art_ids)).delete(synchronize_session=False)
                session.query(UserFavorite).filter(UserFavorite.article_id.in_(art_ids)).delete(synchronize_session=False)
            # 3. 删文章
            session.query(Article).filter(Article.mp_id == fid).delete(synchronize_session=False)
            # 4. 删"用户订阅"关系
            session.query(UserFeed).filter(UserFeed.feed_id == fid).delete(synchronize_session=False)
            # 5. 删该号的过滤规则
            session.query(FilterRule).filter(FilterRule.mp_id == fid).delete(synchronize_session=False)
            # 6. 删文件夹关联
            session.query(FolderFeed).filter(FolderFeed.feed_id == fid).delete(synchronize_session=False)
            # 7. 删 AI 报告历史(若按mp_id)
            session.query(AIReportHistory).filter(AIReportHistory.mp_id == fid).delete(synchronize_session=False)
            # 8. 最后删公众号本身
            session.query(Feed).filter(Feed.id == fid).delete(synchronize_session=False)
            print(f'已删除: {name} ({fid}), 文章 {len(art_ids)} 篇')
    session.commit()
    print('=== 删除完成 ===')
except Exception as e:
    session.rollback()   # 出错就回滚, 不留下半删的数据
    print(f'出错已回滚: {e}')
finally:
    session.close()
```
### 注意：删除脚本里明确删除了这些表
表	是什么
user_favorites	✅ 收藏
user_read_articles	✅ 已读记录
user_hidden_articles	✅ 隐藏记录
articles	✅ 文章本身
user_feeds	✅ 订阅关系
filter_rules / folder_feeds / ai_report_history	✅ 过滤规则/文件夹/AI历史
feeds	✅ 公众号本身

所以收藏、阅读、隐藏状态都一起删干净了，不会留**孤儿数据**。

---

## 四、脚本每部分在干什么（解析）

| 部分 | 作用 |
|---|---|
| `sys.path.insert(0, '/app')` | 让 Python 能找到项目代码（在容器里 /app 下）|
| `from core.db import DB` | 拿到数据库连接（用网站同款配置）|
| `from core.models... import ...` | 导入各个"数据表模型"（Feed=公众号, Article=文章, 等）|
| `DB.get_session()` | 打开一个数据库会话（连接）|
| `session.query(...).filter(...)` | 按条件查询 |
| `.delete(synchronize_session=False)` | 删除匹配的记录 |
| `session.commit()` | 真正提交删除（不 commit 不会生效）|
| `session.rollback()` | 出错时回滚，撤销本次所有删除（安全保护）|

### 删除顺序为什么这样排？

**先删"孩子"，再删"爸爸"** —— 因为其他表都"引用"公众号和文章：
```
文章相关用户表(读/藏/收) → 文章 → 用户订阅 → 过滤规则/文件夹 → AI历史 → 公众号本身
```
顺序反了会报外键错误，或留下"孤儿数据"。

---

## 五、注意事项

1. **名字要对上**：`NAMES` 里的名字必须和网站显示的一模一样（有空格/全半角差异会"未找到"）。拿不准就先用第三节最后的验证命令列出所有号，复制名字。
2. **删除不可恢复**：删了公众号，它的文章和用户关联全没了。删之前想清楚。
3. **出错会回滚**：脚本有保护，任何一步出错会撤销全部删除，不会留半截。
4. **compose/data 目录没写权限**：所以脚本放 `~/`（home），用 `docker cp` 拷进容器。
5. **容器必须在运行**：`docker exec` 需要容器在跑。如果容器没起，先 `docker compose up -d`。

---

## 六、相关原理（想深入看）

- **ORM（对象关系映射）**：用 Python 对象操作数据库表，不用写 SQL。比如 `session.query(Feed)` 就是"查 feeds 表"。
- **为什么不用直接改 MySQL**：手写 SQL 容易漏删关联表、搞错表名，出错难恢复。用 ORM 模型是"正规操作"，有回滚保护。
