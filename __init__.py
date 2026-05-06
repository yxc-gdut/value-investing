#!/usr/bin/env python3
"""
巴菲特 & 段永平 LLM Wiki 知识提取系统
=====================================

将原始资料（股东信 + 段永平问答录）通过 LLM 提取为结构化知识条目，
构建类似 Wiki 的知识库，供 Agent 模式问答使用。

三个阶段：
  1. extract.py  — 批量提取知识点（离线跑一次）
  2. build_index.py — 构建知识库索引
  3. agent.py — Agent 模式问答

使用方式：
  # 阶段1：提取知识点
  export GLM_API_KEY="your-key"
  python3 extract.py

  # 阶段2：构建索引
  python3 build_index.py

  # 阶段3：开始问答
  python3 agent.py
"""
