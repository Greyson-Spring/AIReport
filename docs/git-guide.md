# Git 基础操作指南

> 基于 AIReport 项目实际操作的问答整理

---

## Q1: 项目从 Gerrit 克隆下来，`.git` 是什么？`git init` 为什么报错？

- **Clone（克隆/拉取）**：从远程仓库下载完整代码 + 全部提交历史到本地，相当于复制了一份
- **`.git` 目录**：git 仓库的"大脑"，是一个隐藏文件夹，存储所有版本历史、分支、配置、远程地址等元数据
- 因为项目本身就是通过 clone 得到的，`.git` 已存在，所以 `git init` 会报错（不能在一个已有仓库里再初始化）

---

## Q2: 如何上传项目到 GitHub 私有仓库？

### 第一步：在 GitHub 上创建私有仓库

**方式A（推荐）：用命令行**
```powershell
gh repo create AIReport --private --source=. --remote=github --push
```

**方式B：网页上手动创建**
1. 打开 https://github.com/new
2. Repository name 填项目名
3. 选 **Private**
4. **不要勾选** "Add a README file"（因为已有代码）
5. 点 "Create repository"
6. 复制仓库地址，如 `https://github.com/你的用户名/AIReport.git`

### 第二步：添加 GitHub 作为新的远程仓库

```powershell
git remote add github https://github.com/你的用户名/AIReport.git
```

**原理：**
- `git remote add` = 添加一个新的远程仓库地址
- `github` = 给这个远程地址起的别名（可以叫任何名字）
- 原来 `origin` 指向 Gerrit，现在 `github` 指向 GitHub，两个远程互不影响
- 相当于一个本地仓库有了多个"邮寄地址"

### 第三步：推送到 GitHub

```powershell
git push -u github master
```

**原理：**
- `git push` = 把本地提交记录上传到远程仓库
- `-u` = `--set-upstream`，建立本地分支和远程分支的追踪关系，之后只需 `git push` 即可
- `github` = 推送到哪个远程仓库
- `master` = 推送哪个分支

### 第四步：验证

```powershell
git remote -v
```

应该看到两个远程地址：`origin`（Gerrit）和 `github`（GitHub）。

---

## Q3: 如何知道 push 到哪个远程仓库？

`git push` 的完整格式：

```
git push <远程别名> <分支名>
```

你在命令里明确指定了远程别名，所以不会搞混。

如果只写 `git push`，git 会推送到当前分支"追踪"的远程。用 `git branch -vv` 查看追踪关系：

```powershell
> git branch -vv
* master  b89b120 [origin/master] fix：...
```

方括号里 `origin/master` 表示当前 `master` 追踪的是 `origin` 的 `master`。

> 每一次 push 就是把 `.git` 里的 commit 对象（快照 + 元数据）传到远程，远程也存一份同样的 `.git`。

---

## Q4: `main` 和 `master` 都可以用吗？

**是的，本质上只是名字不同**，没有功能区别。

- `master` 是 git 的老传统
- `main` 是 GitHub 2020 年后的新默认

用哪个都行，项目能正常运行。

```powershell
git branch -M main          # 本地分支改名为 main
git push -u origin main     # 推送到远程的 main 分支
```

`-M` = move/rename，强制重命名当前分支。

---

## Q5: `git push` 和 `git push -u` 的区别？

| 命令 | 效果 |
|------|------|
| `git push origin master` | 推送，但不建立追踪关系 |
| `git push -u origin master` | 推送，**同时建立追踪关系** |

建立追踪后，以后只需 `git push` 即可，不用每次写 `origin master`。**建议首次推送时加 `-u`，之后省事。**

---

## Q6: 推送到 Gerrit 怎么操作？

把远程别名换成 `origin` 就行：

```powershell
git push origin master
```

因为 `origin` 指向的就是 Gerrit 地址。

---

## Q7: `git remote -v` 里的 `(fetch)` 和 `(push)` 是什么意思？

```
origin  http://xxx (fetch)
origin  http://xxx (push)
```

同一个地址出现两次：

- **fetch**：执行 `git pull` / `git fetch` 时，从这个地址拉取代码
- **push**：执行 `git push` 时，向这个地址推送代码

大部分情况下两个地址一样。可以不一样——比如只读别人的仓库但推送到自己的 fork。

---

## Q8: `.gitignore` 怎么创建？格式是怎样的？

**创建方式：**

```powershell
# 方式一：直接用编辑器新建文件，命名为 .gitignore
# 方式二：终端创建
New-Item -Path .gitignore -ItemType File
```

**格式：每行一个匹配规则**

```gitignore
# 注释用 # 开头

# 忽略文件夹
node_modules/
__pycache__/

# 忽略特定文件类型
*.log
*.pyc

# 忽略特定文件
config.yaml
.env

# 感叹号表示例外（不忽略）
!important.log
```

> 技巧：去 [gitignore.io](https://www.toptal.com/developers/gitignore) 输入技术栈，自动生成一份。

**重要：** `.gitignore` 要在第一次 `git add` 之前就写好，否则已经跟踪的文件即使加入 `.gitignore` 也不会自动忽略（需要 `git rm --cached` 先移除跟踪）。

---

## Q9: `git clone` 和 `git pull` 的区别？

| | `git clone` | `git pull` |
|------|-------------|------------|
| **什么时候用** | 第一次，本地没有仓库 | 已有本地仓库，想同步远程更新 |
| **做了什么** | 下载整个仓库（代码+全部历史）到本地 | 拉取远程新 commit 并合并到本地 |
| **类比** | 去图书馆复印整本书 | 书已经在手里，去拿最新修订的几页 |

```powershell
git clone https://github.com/xxx/repo.git   # 第一回：整本下载
git pull                                     # 后续：拿更新
```

`git pull` = `git fetch`（拉取远程更新）+ `git merge`（合并到本地），两步合成一步。

---

## 完整流程总结

### 一、从头创建项目并上传

```powershell
# 1. 初始化 git 仓库（在项目根目录）
git init

# 2. 创建 .gitignore，排除不需要上传的文件

# 3. 添加远程仓库
git remote add origin https://github.com/用户名/仓库名.git

# 4. 暂存所有文件
git add .

# 5. 提交
git commit -m "feat: 初始化项目"

# 6. （可选）改分支名
git branch -M main

# 7. 推送并建立追踪
git push -u origin main
```

### 二、从远程仓库克隆

```powershell
git clone https://github.com/用户名/仓库名.git
# 克隆后自动绑定 origin，无需手动 git remote add
```

### 三、日常开发流程

```powershell
# 1. 拉取最新代码
git pull

# 2. （可选）创建新分支开发
git checkout -b feat/新功能

# 3. 写代码...

# 4. 查看改了哪些文件
git status

# 5. 查看具体改了什么
git diff

# 6. 暂存更改（可以只加特定文件）
git add .                      # 全部暂存
git add src/main.py            # 只暂存某个文件
git add src/                   # 暂存整个目录

# 7. 提交
git commit -m "feat: 添加新功能"

# 8. 推送到远程
git push                      # 已建立追踪，直接 push
```

---

## 常用命令速查

| 命令 | 作用 |
|------|------|
| `git status` | 查看当前状态：改了哪些、暂存了哪些 |
| `git diff` | 查看具体改动内容（未暂存的） |
| `git diff --staged` | 查看已暂存但未提交的改动 |
| `git log --oneline` | 查看提交历史（简洁版） |
| `git pull` | 从远程拉取并合并最新代码 |
| `git branch` | 查看本地分支 |
| `git branch -vv` | 查看分支追踪关系 |
| `git checkout -b 分支名` | 创建并切换到新分支 |
| `git merge 分支名` | 合并其他分支到当前分支 |
| `git remote -v` | 查看远程仓库地址 |
| `git remote add 别名 地址` | 添加远程仓库 |
| `git rm --cached 文件名` | 从 git 跟踪中移除，但保留本地文件 |

---

## 核心概念图

```
工作区（你的文件）
    ↓ git add
暂存区（.git 里等着被提交）
    ↓ git commit
本地仓库（.git 里已提交的快照）
    ↓ git push
远程仓库（GitHub / Gerrit）
```

---

## 关键概念速查

| 概念 | 解释 |
|------|------|
| **Clone（克隆/拉取）** | 从远程仓库下载完整代码+历史记录到本地 |
| **`.git` 目录** | git 仓库的核心，存储所有版本历史、分支、配置等元数据 |
| **Remote（远程）** | 远程仓库的地址别名，一个本地仓库可以有多个 remote |
| **Origin** | git clone 时自动创建的默认 remote 别名，指向克隆来源 |
| **追踪（Upstream）** | 本地分支与远程分支的绑定关系，建立后可直接 `git push` |
