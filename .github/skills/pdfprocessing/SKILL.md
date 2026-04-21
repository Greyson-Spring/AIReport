---
# YAML 前置元数据：定义技能的元信息
name: pdf
description: 处理PDF文件，包括提取文本、表格和元数据。
license: Apache-2.0
version: 1.0.0
author: Your Name
tags:
  - document
  - pdf
---

# Markdown 指令体：定义技能的具体行为

## 核心能力
当用户询问关于PDF文件的内容时，你可以使用此技能。

## 工作流程
1.  **识别文件**：首先，确认用户需要处理的PDF文件路径。
2.  **执行脚本**：使用 `python scripts/extract_pdf.py` 脚本来提取文本内容。
3.  **分析结果**：根据脚本输出，回答用户的问题，例如总结文本、列出表格等。

## 可用脚本
- `scripts/extract_pdf.py`：使用 `PyPDF2` 库提取PDF中的文本和表格。
- `scripts/parse_metadata.py`：提取PDF的元数据（作者、创建时间等）。

## 示例
用户问：“帮我总结一下 `report.pdf` 的内容。”
你的操作：
1.  调用 `python scripts/extract_pdf.py report.pdf` 获取文本。
2.  基于提取的文本，生成一份简洁的总结。