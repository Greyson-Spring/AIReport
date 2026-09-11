# lh/riscv_summary_export.py — RISC-V 文章摘要与月度报告导出工具

> 独立工具：**直接连数据库 → 筛出 RISC-V 相关文章 → 按提示词逐篇生成摘要 → 汇总生成月度报告 → 导出文件**。
> 不写回知枢数据库，提示词一字不改（原样读取本目录两个 prompt 文件）。

---

## 一、它能干什么

输入一个时间段（如 `2026-08-01` 到 `2026-08-31`），自动完成：

1. 从数据库取出该时间段所有文章；
2. 按"标题/正文/简介里含 `risc-?v`（不区分大小写）"筛出 RISC-V 相关；
3. 用 `ai_analysis_prompt.txt`（单篇摘要提示词）**逐篇调 LLM 生成摘要**；
4. 导出每篇摘要到 **CSV + JSON**；
5. 把全部单篇摘要汇总，用 `ai_analysis_prompt_summary.txt`（月度报告提示词）**生成整月 RISC-V 报告**，导出 `.md`，并尽量转 `.docx`。

## 二、涉及文件（本目录仅保留这 3 个）

| 文件 | 作用 |
|---|---|
| `riscv_summary_export.py` | 主脚本 |
| `ai_analysis_prompt.txt` | 单篇摘要提示词（原样使用） |
| `ai_analysis_prompt_summary.txt` | 月度报告提示词（原样使用） |

## 三、原理（流程）

```
数据库(MySQL)
  → 按 publish_time 时间段查文章
  → 正则筛 RISC-V 相关 (risc-?v)
  → 逐篇: 单篇提示词 + 公众号/标题/链接/日期/正文(截断) → LLM → 摘要
       (每篇间隔 N 秒防限流; 断点续跑: CSV里已有的自动跳过)
  → 写出 CSV/JSON
  → 汇总全部摘要 → 报告提示词 → LLM → 月度报告
  → 导出 .md + 尽量 .docx
```

- **LLM 配置读取顺序**：环境变量 `AI_API_URL` / `AI_API_KEY` / `AI_MODEL` → 其次项目"大模型配置"页（config_management 表 `llm_api_url/llm_api_key/llm_model`）。
- **断点续跑**：脚本会读已存在的 CSV，**已生成的自动跳过**；中途断掉重跑不会重复。
- **不写库**：所有输出都是文件，不影响项目数据。

## 四、使用方法（服务器容器里跑）

**① 上传/拷进容器**（脚本 + 两个提示词都要在容器里）：
```bash
docker cp ~/AIReport/lh/riscv_summary_export.py we-mp-rss-local:/app/lh/riscv_summary_export.py
docker cp ~/AIReport/lh/ai_analysis_prompt.txt we-mp-rss-local:/app/lh/ai_analysis_prompt.txt
docker cp ~/AIReport/lh/ai_analysis_prompt_summary.txt we-mp-rss-local:/app/lh/ai_analysis_prompt_summary.txt
```

**② 运行**（第 3 个参数 = 每篇间隔秒数，防限流，默认 3）：
```bash
docker exec -it we-mp-rss-local sh -c 'cd /app && PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" lh/riscv_summary_export.py 2026-08-01 2026-08-31 3'
```

**③ 后台跑 + 看进度**（文章多时建议）：
```bash
docker exec -d we-mp-rss-local sh -c 'cd /app && PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); "$PY" lh/riscv_summary_export.py 2026-08-01 2026-08-31 3 > /tmp/riscv_summary.log 2>&1'
docker exec we-mp-rss-local tail -20 /tmp/riscv_summary.log
```

**④ 拿导出文件**（文件在容器 `/app` 下）：
```bash
docker cp we-mp-rss-local:/app/riscv_summary_2026-08-01_2026-08-31.csv ./
docker cp we-mp-rss-local:/app/riscv_summary_2026-08-01_2026-08-31_report.md ./
docker cp we-mp-rss-local:/app/riscv_summary_2026-08-01_2026-08-31_report.docx ./
```
然后用 MobaXterm SFTP 下载到本地查看/编辑。

## 五、输出文件说明

| 文件 | 内容 |
|---|---|
| `riscv_summary_<起>_<止>.csv` | 每篇：公众号 / 标题 / 链接 / 发布日期 / 摘要 |
| `riscv_summary_<起>_<止>.json` | 同上，JSON 格式 |
| `riscv_summary_<起>_<止>_report.md` | 月度报告（Markdown） |
| `riscv_summary_<起>_<止>_report.docx` | 月度报告转 Word（尽量，失败仅保留 md） |

## 六、注意事项

1. **提示词不能改**：脚本原样读两个 prompt 文件，别动内容；
2. **LLM 配置**：若报"未找到LLM配置"，去"大模型配置"页填，或运行时用环境变量注入：
   ```bash
   docker exec -it we-mp-rss-local sh -c 'cd /app && PY=$(ls -d /app/env*/bin/python 2>/dev/null | head -1); AI_API_URL="..." AI_API_KEY="..." AI_MODEL="..." "$PY" lh/riscv_summary_export.py 2026-08-01 2026-08-31'
   ```
3. **正文为空的文章**会被跳过（没料）；可先用 `tools/backfill_content.py` 补正文再生成；
4. **断点续跑**：CSV 里已有的自动跳过，重跑只会补缺的；
5. **报告一次喂全部摘要**：若文章很多导致报告空/截断，可考虑分批或精简。
