# Docker 命令笔记（小白实战版）

> 面向零基础读者，用本项目（AIReport / we-mp-rss）的真实命令讲解。
> 目标：看完能看懂常用 Docker 命令、能上手部署与排查。

---

## 一、核心概念（先懂原理）

### 1.1 三个名词

| 名词 | 是什么 | 类比 |
|---|---|---|
| **镜像 (image)** | 打包好的**只读模板**（系统+程序+代码+配置） | 软件的"安装盘" |
| **容器 (container)** | 镜像**运行起来的实例**，有自己独立的文件系统 | 装好盘、正在运行的那台机器 |
| **宿主 (host)** | 运行 Docker 的服务器 | 房间本身 |

- **一个镜像能启动多个容器**，但**容器名必须唯一**（同名会冲突；不指定则 Docker 随机起名）。
  > 类比：一个 Word 安装包能开很多个窗口，但每个窗口得有不同的名字来区分。**镜像名（模板）只有一个，容器名（每个实例）各不相同**——不矛盾。
- 容器内部 = 一台独立的小电脑（完整文件系统），所以里面有各种目录。
- 命令里的 `we-mp-rss-local` 是**容器名**（不是镜像名）。

### 1.2 镜像名与标签（tag）

镜像完整名字 = `仓库名:标签`。标签通常是**版本或用途**：

```
mysql:8.3.0                        # 标签=8.3.0（版本）
we-mp-rss:local                    # 标签=local（本地构建）
ghcr.io/rachelos/base-full:latest  # 标签=latest（最新）
```

- `docker images` 能看到两列：REPOSITORY（仓库名）和 TAG（标签）。
- **`docker run` / compose 尽量写全 `名:标签`**；省略标签默认找 `:latest`，容易找错。

### 1.3 Dockerfile 和 compose yaml 各管什么

| 文件 | 管什么 | 类比 |
|---|---|---|
| **Dockerfile** | **一个镜像怎么造**（放哪些项目代码、装什么依赖） | 做菜的"菜谱" |
| **compose yaml** | **整个项目怎么跑**（mysql/redis/we-mp-rss 协作、端口、环境变量、数据目录） | 整桌菜的"菜单+安排" |

- 造镜像**不只靠 Dockerfile**：Dockerfile 里有 `COPY . /app`，所以还需要**项目代码**。
- `docker compose up` = 读 yaml → 自动 build（如需要）+ 启动所有容器 + 配好网络/存储。

### 1.4 容器里的文件系统（各目录干啥）

容器内部 = 一台小电脑，目录约定类比 Windows：

| 目录 | 放什么 | 类比 Windows |
|---|---|---|
| `/` | 根目录（一切起点） | `C:\` |
| `/usr`、`/bin` | 系统程序和库 | `C:\Program Files` |
| `/etc` | 配置文件 | 配置目录 |
| `/var` | 运行数据、日志 | `C:\ProgramData` |
| `/tmp` | **临时文件**（重启会清） | 临时目录 |
| `/home` | 用户文件 | `C:\Users` |
| `/app` | **本项目自己的代码**（部署位置） | 你的项目目录 |

### 1.5 前台 vs 后台

- **前台**：程序占着你的终端，关终端程序通常跟着死。
- **后台**：程序脱离终端，由系统常驻管家托管，关终端照跑。三种常见方式：
  - `nohup 命令 &`：放后台 + 忽略关终端信号；
  - **Docker 容器**：由 Docker daemon（开机常驻系统服务）托管，本来就不在任何终端里 → 关 SSH 网站照常运行；
  - `docker exec -d`：在容器里后台执行命令。
- 长期服务（网站/数据库/采集代理）都是系统托管的后台进程，终端只是"启动入口/遥控器"。

---

## 二、查看命令（随时掌握状态）

```bash
docker images                              # 本机有哪些镜像(仓库名:标签)
docker ps                                  # 正在运行的容器
docker ps -a                               # 全部容器(含已停止)
docker logs 容器名 --tail 30                # 某容器日志末尾30行
docker logs -f 容器名                       # 实时跟随日志
```

---

## 三、传文件

### 3.1 `scp`：你的电脑 ⇄ 服务器

```bash
# Windows → 服务器
scp "C:\xx\xx\文件.py" appadmin@10.188.26.61:~/AIReport/lh/
```

**为什么路径要加双引号**：防止路径被 shell "拆开"。路径里有**空格**（如 `project deploy`）或 `* ? ( ) $` 等特殊字符时，不加引号会被当成多个参数 → 报错。加双引号 = "这一整串是一个路径"。**都加上更保险**。

### 3.2 `docker cp`：服务器(宿主机) ⇄ 容器

```bash
# 宿主机 → 容器
docker cp ~/AIReport/lh/a.py we-mp-rss-local:/app/lh/a.py

# 容器 → 宿主机
docker cp we-mp-rss-local:/app/riscv_summary.csv ./
```

- **冒号 `:`** = 把"谁"和"里面哪个路径"分开：`docker cp 谁:里面哪 拷到哪`。
- 和 `cp` 的区别：`cp` 在同一台机器内复制；`docker cp` 跨"容器边界"。
- 拷成功会提示：`Successfully copied 84.5kB to /home/appadmin/./` → 表示已拷到你执行命令时的当前目录。

### 3.3 常见疑问：`./` vs `~/`

- `~` = **家目录**（`/home/appadmin`），固定。
- `.` = **当前目录**（shell 此刻停在哪，用 `pwd` 查看）。
- `docker cp 容器:/file ./` = 拷到"**当前所在目录**"。在 `~` 执行就等于 `~/`，在 `~/AIReport` 执行就是 `~/AIReport`。
- `.` 在 Windows（cmd/PowerShell）同样是"当前目录"。

---

## 四、进容器里执行命令（docker exec）

```bash
docker exec 容器名 要执行的命令
docker exec we-mp-rss-local mkdir -p /app/lh                 # 容器里创建文件夹
docker exec we-mp-rss-local tail -30 /tmp/riscv_summary.log  # 看容器里文件末尾30行
```

- `mkdir` = 建文件夹；**`-p`** = 上级目录不存在就一起建（避免报错）。
- `/app` 是**容器自己里面**的目录，不是服务器的 `/app`。
- `tail -N` = 看文件**结尾** N 行（`head -N` = 开头 N 行；`tail -f` = 实时跟随；`cat` = 整个打出来）。日志越写越长、最新在末尾 → 最常用 `tail`。
- `-d`（detach）= **后台运行**，不占终端、关 SSH 不中断 → 配合 `> 日志文件` 把输出写进文件，随时 tail 查看。

> 本项目"进容器跑脚本"的标准写法（要用虚拟环境里的 python，里面才有依赖）：
> ```bash
> docker exec -it we-mp-rss-local sh -c 'PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" tools/xxx.py'
> ```

---

## 五、构建与运行

### 5.1 `docker build`：按 Dockerfile 造镜像

```bash
# 在含 Dockerfile 的目录执行; . = 当前目录(含Dockerfile和代码)
docker build -t 我的应用:1.0 .
#           ^-t 给镜像起名(仓库名:标签)
```

### 5.2 `docker run`：用镜像启动单个容器

```bash
docker run -d -p 8001:8001 --name 我的容器名 我的应用:1.0
#         ^-d 后台  ^-p 主机端口:容器端口  ^----name 容器名
```

> run 用于"单独/临时"起某个镜像；真实服务要手动写一堆 `-p/-e/-v` 很啰嗦 → 这就是用 compose 的原因。

### 5.3 停止 / 删除

```bash
docker stop 容器名        # 停容器
docker rm 容器名          # 删容器(先停止)
docker rmi 镜像名:标签     # 删镜像
```

### 5.4 镜像存在哪？怎么迁移？

- 镜像**不是单个文件、没有后缀**，由 Docker daemon 分层管理，存在本机 **`/var/lib/docker/`**。
- 两台机器之间传镜像（**仅当目标机没有源码时**）：
  ```bash
  # 本机: 打包成 tar
  docker save -o 我的应用.tar 我的应用:1.0
  scp 我的应用.tar appadmin@服务器:~/
  # 服务器: 解包进 Docker 镜像库(/var/lib/docker), 之后 docker images 就能看到
  docker load -i 我的应用.tar
  ```
- **本项目不需要 save/load**：你 scp **代码**到服务器，然后 `docker compose ... up -d --build`（在服务器本地造镜像）。

---

## 六、compose：本项目日常主力

```bash
cd ~/AIReport   # compose 文件在 compose/ 下, 相对路径都基于它

# 启动 yaml 里所有服务(镜像不存在会自动 build)
docker compose -f compose/docker-compose.local.yaml up -d

# 只启动/重建单个服务(改了代码后用它)
docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss

# 重启(不重建)
docker compose -f compose/docker-compose.local.yaml restart we-mp-rss

# 看状态 / 停 / 看日志
docker compose -f compose/docker-compose.local.yaml ps
docker compose -f compose/docker-compose.local.yaml stop
docker compose -f compose/docker-compose.local.yaml logs -f we-mp-rss-local
```

要点：
- `up -d` = 按 yaml **启动/更新**（有 build 配置且镜像不存在会先 build）；
- `up -d --build` = **强制重新构建再启动**（代码改了必须用它，否则跑旧代码）；
- `restart` = 只重启不重建；
- compose 能启动全部，也能 `up -d 服务名` **只启单个**。

### 代码改动 → 网站生效 的完整流程

```
① 你改代码(Windows) 
② scp 代码 → 服务器 ~/AIReport
③ docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss   ← 服务器按新代码造新镜像并重启
④ docker ps / docker logs 看状态
⑤ 浏览器访问 服务器IP:8001
```

---

## 七、命令速查总表

| 你想做的事 | 命令 |
|---|---|
| 看镜像 | `docker images` |
| 看运行中的容器 | `docker ps` |
| 看全部容器 | `docker ps -a` |
| 看容器日志(末尾30行) | `docker logs 容器名 --tail 30` |
| 实时看日志 | `docker logs -f 容器名` |
| 你的电脑→服务器传文件 | `scp "本地文件" 用户@IP:服务器路径` |
| 服务器→容器传文件 | `docker cp 服务器文件 容器名:/容器路径` |
| 容器→服务器拷出 | `docker cp 容器名:/容器路径 ./` |
| 进容器执行命令 | `docker exec 容器名 命令` |
| 容器里后台执行 | `docker exec -d 容器名 sh -c '... > /tmp/x.log 2>&1'` |
| 构建镜像 | `docker build -t 名:标签 .` |
| 启动单个容器 | `docker run -d -p 主机端口:容器端口 --name 名 镜像:标签` |
| 停容器 | `docker stop 容器名` |
| 删容器 | `docker rm 容器名` |
| 删镜像 | `docker rmi 镜像:标签` |
| 镜像打包成 tar | `docker save -o 名.tar 镜像:标签` |
| tar 导入镜像库 | `docker load -i 名.tar` |
| 按 yaml 启整套 | `cd ~/AIReport && docker compose -f compose/docker-compose.local.yaml up -d` |
| 重建+启动单服务 | `docker compose -f compose/docker-compose.local.yaml up -d --build we-mp-rss` |
| 看 compose 状态 | `docker compose -f compose/docker-compose.local.yaml ps` |
| 停整套 | `docker compose -f compose/docker-compose.local.yaml stop` |

---

## 八、本项目常见坑速记

- **改了代码要 `--build`**，否则容器跑旧代码；
- **代理(host_weread_agent.py)在宿主机跑、不走 Docker** → 改它要 pkill + 重启进程，不是重建容器；
- 容器内默认没有 `python`，只有 `python3`；依赖装在虚拟环境 `/app/env_*`，要用那个 python 跑脚本；
- 容器里文件是临时的（重建镜像会丢），一次性脚本常用 `docker cp` 塞进去；
- 编译产物/大文件别塞进镜像（`.dockerignore`）。
```
