# AIReport 配置系统（三层环境变量 + config.yaml）

> 面向零基础读者，用大白话 + 本项目真实文件，讲清：
> 环境变量是什么、三层配置入口、`${}` 是什么、config.py 与 cfg 怎么工作、为什么这样设计。
> 全文按"为什么 → 是什么 → 怎么流转 → 怎么改"层层递进。

---

## 一、为什么要有"配置系统"？（先懂动机）

一个程序有大量"可调的东西"：数据库地址、要不要抓正文、Cookie、密钥、间隔时间……
如果全部写死在代码里，会遇到：
1. **改一处要改代码、要重新发布**；
2. **密码/密钥跟着代码泄露**；
3. **不同环境（本地/测试/服务器）要用不同值，得维护多份代码**。

所以业界通用做法（12-Factor 第 3 条"配置存于环境"）：
> **代码里不写配置值，只写"我要某个配置"；真正的值由"运行环境"在启动时提供。**

本项目把这套实现成**三层 + 一个总配置对象**。下面逐层讲。

---

## 二、环境变量是什么？（先懂基础概念）

- **环境变量 = 进程启动时拿到的"键值对参数"**（形如 `DB=xxx`、`GATHER.CONTENT=True`）。
- 它**只在进程运行时存在**，进程随时能读，但值在进程启动那一刻固定。
- 不是 Windows/Linux 系统专属——**任何程序进程都有**，Docker 容器启动时可以把值注入进去。
- Python 读环境变量用：`os.getenv("名字")` 或 `os.environ.get("名字")`。

> 误区澄清：文件夹里的 `.env` **不是**环境变量，它只是一个"源头文本文件"。真正的环境变量在**运行中的进程内存里**。工具在启动进程时读 `.env`，把内容注入成进程环境变量（这一步叫"**注入**"）。

---

## 三、三层配置入口（全景）

| 层 | 动作 | 在哪写 | 放什么 | 会不会进 git |
|---|---|---|---|---|
| **第 1 层** compose yaml `environment:` | 注入（set） | `compose/docker-compose.local.yaml` | 固定连接地址（DB/REDIS_URL） | 会（随 yaml） |
| **第 2 层** `.env` + `env_file:` | 注入（set） | 服务器 `~/AIReport/.env` | 可变/敏感（GATHER.CONTENT、WEREAD_COOKIE） | **不会**（gitignore） |
| **第 3 层** `config.yaml` + `config.py` | 取 + 整理（get） | 容器内 `/app/config.yaml` | 声明"要用哪些配置 + 默认值" | example 进 git |

- 前两层是"**放**"，第三层是"**取 + 整理**"。
- `environment:` 和 `env_file:` 区别只在"值从哪来"：yaml 里写死 vs 从文件读；同名时 `environment:` 优先。

### 第 1 层示例（compose yaml）
```yaml
we-mp-rss:
  env_file:
    - ../.env
  environment:
    DB: mysql+pymysql://rss_user:pass123456@db-mp-local/we_mp_rss
    REDIS_URL: redis://redis:6379/0
    PROXY_HTTP_URL: http://singbox:7890
```

### 第 2 层示例（.env，明文但被 git 排除）
```
GATHER_MODEL=weread_mp
GATHER.CONTENT=True
WEREAD_COOKIE=xxx...
```
> `.env` 是业界通用约定（dotenv），名字可换（compose 用 `env_file:` 指定任意路径）。它**不加密**，安全靠：① 不进 git ② 服务器权限。

---

## 四、第三层到底在干啥？（最核心）

### 4.1 两个文件的分工

- **`config.example.yaml`** = 模板/清单，进 git，给所有人看有哪些配置和默认值。
- **`config.yaml`** = 实际生效的那份，**不在 git**；本项目由 Dockerfile 构建时复制生成：
  ```dockerfile
  COPY config.example.yaml /app/config.yaml
  ```
  所以容器里 `/app/config.yaml` 就是 example 的一份拷贝（**保留 `${}` 占位符**）。

### 4.2 config.yaml 长什么样
```yaml
gather:
  content: ${GATHER.CONTENT:-True}     # "gather.content 这个值: 从环境变量GATHER.CONTENT取, 没有就默认True"
  model: ${GATHER_MODEL:-web}
weread:
  cookie: "${WEREAD_COOKIE:-}"
```
这里的 `${变量:-默认值}` **不是 YAML 语法**，也不是 Python 语法——它只是 config.yaml 里的**普通字符串**，是**本项目自定义的占位符写法**。

### 4.3 `${}` 是怎么被处理的？（config.py 干的事）
`core/config.py` 定义了一个 `Config` 类：
- 启动时读 `config.yaml`；
- 用**正则**在字符串里找出 `${变量:-默认}` 这种模式，抓出"变量名"和"默认值"；
- 然后 `os.getenv("变量名", "默认值")` 替换。

**正则是什么**：一种"按模式找文本"的规则。config.py 用一条正则把 `${VAR}` / `${VAR:-默认}` 匹配出来再替换。类比 Word 的"查找替换"里用通配符。

### 4.4 cfg 是什么
config.py 末尾有一句 `cfg = Config()`——**创建全局唯一的一个配置对象实例**。全程序 `from core.config import cfg` 拿到的都是它，调用 `cfg.get("gather.content")` 取值：
```python
from core.config import cfg
if cfg.get("gather.content", True):   # 取 gather.content, 没有默认True
    # 去抓正文
```
`cfg.get()` 内部：按 `分组.项` 拆 key → 取到值 → 若含 `${}` 再替换一次 → 类型转换（True/数字）→ 返回。

---

## 五、完整数据流转（一张图讲清）

```
【值从哪来】
  .env (GATHER.CONTENT=True)          compose environment (DB=...)
        │  env_file: 读文件               │ 直接写死
        ▼                                ▼
  容器进程的环境变量 os.environ          (两条都注入成进程环境变量)

【声明 + 解析】
  config.example.yaml(带 ${} 和默认值)
        │ Dockerfile: COPY config.example.yaml /app/config.yaml
        ▼
  容器内 /app/config.yaml(仍是 ${} 占位符)
        │ 程序启动: config.py 读它, 正则找 ${...}, os.getenv 替换
        ▼
  cfg 对象 (cfg.get("gather.content") → True)

【使用】
  各程序: from core.config import cfg; cfg.get("分组.项")
```

要点：
- 环境变量在**进程启动时**注入、之后固定 → **改 .env / compose 必须重启容器**才生效；
- config.yaml 里的 `${}` **不会被打平写回文件**，每次 get 时内存里替换；
- 优先级：环境变量 > yaml 默认值。

---

## 六、怎么改配置（三种情况）

| 你想改 | 在哪改 | 怎么生效 |
|---|---|---|
| 有对应环境变量的开关（GATHER.CONTENT） | `.env` | 重建/重启容器（env_file 重新注入） |
| example 里写死的默认值 | `config.example.yaml` | 重新构建镜像（Dockerfile 重新 COPY） |
| 新增一个配置项 | `config.example.yaml` + 代码里 `cfg.get("新分组.新项", 默认)` | 重建镜像 |

> 带点号的坑：`config.yaml` 里 `${GATHER.CONTENT:-True}` 读的是**名字带点**的 `GATHER.CONTENT`（os.getenv 按原名字取），所以 `.env` 里必须写 `GATHER.CONTENT=True`，写 `GATHER_CONTENT`（无点）**不生效**。

---

## 七、验证命令

```bash
# 看容器里到底有哪些环境变量(应能看到 environment: 和 .env 注入的)
docker exec we-mp-rss-local env
docker exec we-mp-rss-local printenv DB

# 看容器里生效的配置yaml
docker exec we-mp-rss-local cat /app/config.yaml

# 看程序里 cfg.get 取到的值(在容器里跑python)
docker exec -it we-mp-rss-local sh -c 'PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" -c "import sys; sys.path.insert(0,\"/app\"); from core.config import cfg; print(\"gather.content=\", cfg.get(\"gather.content\"))"'
```

---

## 八、为什么这样设计？（设计思想）

对应 **12-Factor App 第 3 条"配置存于环境"**：
1. **配置与代码分离**：同一份代码，不同环境只改配置；
2. **敏感信息不进代码**：`.env` 被 git 排除；
3. **配置集中可读**：config.yaml 一份清单，默认值一目了然；
4. **运行时可覆盖**：环境变量优先于默认值；
5. 代码用统一 `cfg.get()` 取值，不散落一堆 `os.getenv`。

这是**主流成熟项目通用做法**：Node(dotenv)、Java Spring(application.yml + env)、Kubernetes(ConfigMap/Secret) 都遵循同样的"配置不进代码、运行时可被环境覆盖"思路。
