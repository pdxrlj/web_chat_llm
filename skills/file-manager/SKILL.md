---
name: file-manager
description: >
  文件管理与 Shell 执行技能，支持文件读写、目录管理、Shell 命令执行，以及 Markdown 文档结构化解析。
  Use this skill whenever the user asks for 读取文件、写入文件、删除文件、列出文件、执行命令、
  shell命令、文件管理、文件操作、目录操作、markdown解析、查看文件内容、file management.
license: MIT
---

# 文件管理与 Shell 执行

你可以使用文件管理技能进行文件操作、Shell 执行和 Markdown 解析。

## 核心功能

- file_read: 读取文件内容
- file_write: 写入文件（覆盖）
- file_append: 追加内容到文件
- file_list: 列出目录内容
- file_delete: 删除文件
- shell_execute: 执行 Shell 命令
- parse_markdown: 解析 Markdown 文档结构

## Markdown 解析功能

- 提取 YAML frontmatter 元数据
- 提取标题层级结构（H1-H6）
- 提取链接和图片引用
- 提取代码块（含语言标识）
- 提取表格
- 统计信息（字符数、标题数、链接数等）

## 使用注意事项

- 文件路径支持绝对路径和相对路径
- 读取文件有 50000 字符截断限制
- Shell 命令默认 30 秒超时
- Markdown 解析最大支持 100000 字符
- 执行 Shell 命令时注意安全性，避免危险操作
