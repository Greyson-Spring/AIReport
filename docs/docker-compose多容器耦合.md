# docker compose 与多容器耦合（we-mp-rss 是怎么和 mysql/redis 连起来的）

> 面向零基础读者。目标：搞懂 compose 是啥、镜像从哪来、三个"名字"的区别、
> 以及 we-mp-rss 是怎么和数据库、缓存、代理容器"耦合"运行的。

---

## 一、compose 是干什么的（先懂定位）

`docker run` 一次只能启动**一个**容器，参数还得手动写一堆。真实项目往往要**多个容器协作**：
本项目就有 4 个服务：

| 服务 | 干嘛 |
|---|---|
| `mysql`（容器 `db-mp-local`） | 数据库，存文章/公众号等 |
| `redis`（容器 `we-mp-rss-redis-local`） | 缓存 / 临时状态 |
| `singbox`（容器 `we-mp-rss-singbox-local`） | 网络代理（抓取走它） |
| `we-mp-rss`（容器 `we-mp-rss-local`） | 主程序（网站/定时任务） |

**compose yaml 就是"这一整套怎么跑的编排文件"**：`docker compose up` 读它，自动把多个容器启动好、连进同一网络、传好环境变量。

---

## 二、镜像从哪来？（compose 怎么知道拉什么）

yaml 里每个服务要么 `image:`（用现成镜像），要么 `build:`（本地造）：
```yaml
mysql:
  image: docker.1ms.run/mysql:8.3.0    # 仓库地址/镜像名:标签 → 本地没有就去拉
redis:
  image: docker.1ms.run/redis:7-alpine
we-mp-rss:
  build:                                 # 本地按 Dockerfile 现造
    context: ..
    dockerfile: Dockerfile
  image: we-mp-rss:local
```
- **`image:` 的字段本身就是"去哪个仓库拉"的地址**（docker.1ms.run=镜像仓库，mysql=镜像名，8.3.0=版本标签）。
- we-mp-rss 写的是 `build:` → 不拉，本地按 Dockerfile + 项目代码构建。

---

## 三、三个"名字"别搞混

| 名字 | 是啥 | 例子 |
|---|---|---|
| **服务名** | yaml `services:` 下的 key，compose 用它管 | `we-mp-rss`、`mysql` |
| **镜像名** | `image:` 字段，模板的名字 | `we-mp-rss:local`、`docker.1ms.run/mysql:8.3.0` |
| **容器名** | 运行实例的名字（`container_name:`） | `we-mp-rss-local`、`db-mp-local` |

要点：
- **一个镜像能开多个容器，但容器名必须唯一**（同名冲突；不指定则随机起名）。镜像名（模板）可被很多容器共用，不矛盾。
- 记法：**compose 系列命令用"服务名"**；`docker ps / docker stop / docker logs` 用"**容器名**"。

---

## 四、we-mp-rss 是怎么和别的容器"耦合"的？（核心）

耦合靠**三个机制**一起工作：

### 机制①：同一个 compose 内部网络（底层基础）
同一 yaml 里的服务会自动加入**同一个内部网络**，彼此能用"服务名/容器名"当主机名互相访问。
（相当于给这些容器建了一栋"内部大楼"，各住一个房间，凭门牌号互相找。）

### 机制②：环境变量把"对方地址"传给程序
yaml 给 we-mp-rss 传了环境变量，告诉它数据库/缓存在哪：
```yaml
we-mp-rss:
  environment:
    DB: mysql+pymysql://rss_user:pass123456@db-mp-local/we_mp_rss  # 数据库在 db-mp-local
    REDIS_URL: redis://redis:6379/0                                 # redis 在 redis
    PROXY_HTTP_URL: http://singbox:7890                             # 代理在 singbox
```
程序代码读这些环境变量 → 拼连接串 → 连过去。

### 机制③：depends_on 保证启动顺序
```yaml
depends_on:
  mysql:
    condition: service_healthy   # we-mp-rss 等 mysql 健康了才启动
```
避免"程序起来了数据库还没好"。

**耦合 ≠ 数据共享**：容器之间通过**网络 + 名字 + 端口**通信，各自文件系统隔离。真正连起来的是"地址"。

---

## 五、we-mp-rss 的表是怎么建的？（没连上怎么建表？）

程序代码里（`core/db.py`）有 `B.metadata.create_all(self.engine)`：
```
we-mp-rss 启动
  → 读 DB 环境变量 → 连到 db-mp-local(mysql)
  → create_all: 检查表在不在, 不在就按模型定义自动建表
  → 迁移脚本补列/数据
  → 正常服务
```
所以**不是"没连就建表"**，是"先连上数据库 → 发现自己没表 → 自动建好 → 再干活"。

---

## 六、redis 怎么知道缓存什么？

**redis 自己不知道、也不会主动缓存**。它只是一个"**存键值对的储物柜**"。
是**你的程序主动决定**：代码里写"把这个结果/状态 set 进 redis，要用时 get 出来"
（本项目 `core/redis_client.py`、`core/cache.py` 干的就是这事）。

> 类比：储物柜不会主动帮你收东西，是"你"（程序）把要缓存的东西放进去、需要时取出来。
> 为什么放 redis：它是**独立于程序的内存数据库**，程序重启不丢、多个程序共享、读写快。

---

## 七、端口映射 vs 内部网络（外面和里面的区别）

```yaml
mysql:
  ports:
    - "3306:3306"     # 主机3306 → 容器3306(外面也能连)
we-mp-rss:
  ports:
    - "8001:8001"     # 浏览器访问 服务器IP:8001 → 容器8001
```
- **对外**：通过 `ports` 映射，外部访问"服务器IP:主机端口"；
- **对内**：容器之间走内部网络，用"服务名:容器端口"直连，不必暴露到外面。

---

## 八、compose 常用命令（配套速查）

```bash
cd ~/AIReport   # yaml 在 compose/ 下

# 启动 yaml 里所有服务(镜像不存在自动build)
docker compose -f compose/docker-compose.local.yaml up -d

# 只启动/重建单个服务(改了代码用它)
docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss

# 看该项目容器状态 / 停
docker compose -f compose/docker-compose.local.yaml ps
docker compose -f compose/docker-compose.local.yaml stop

# 看该项目日志(实时)
docker compose -f compose/docker-compose.local.yaml logs -f we-mp-rss
```

几个易错点：
- `docker compose -f 文件` 里的 `-f` = **file**（指定 yaml）；`logs -f` 里的 `-f` = **follow**（实时），两个 `-f` 意思不同。
- `docker compose ... logs 服务名` 要用**服务名**（`we-mp-rss`），不是容器名（`we-mp-rss-local`）——否则报"没有这个服务"。日志不用你配路径，Docker 自动收集容器 stdout/stderr。
- `docker ps` = 看**服务器上所有**容器；`docker compose -f yaml ps` = 只看**这个 yaml 项目**下的容器。
- 改了代码要 `--build`，否则跑旧镜像。

---

## 九、"改代码 → 网站生效"完整流程

```
① 你改代码(Windows)
② scp 代码 → 服务器 ~/AIReport
③ docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss
     (服务器按新代码构建新镜像 → 启动新容器 → 连上已有的 mysql/redis)
④ docker ps / docker logs 看状态
⑤ 浏览器访问 服务器IP:8001
```

---

## 十、一句话总结

compose 把几个容器**放进同一个内部网络**（能按名字互相找），用**环境变量**把"对方地址"传给 we-mp-rss，程序**自己负责连库、自动建表、主动用 redis 缓存**——数据库/缓存只提供服务，we-mp-rss 负责"使用"，全靠网络 + 名字 + 环境变量耦合，没有魔法。
