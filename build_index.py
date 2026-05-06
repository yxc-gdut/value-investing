#!/usr/bin/env python3
"""
build_index.py — 构建知识库索引
==============================

扫描 knowledge/ 目录下所有知识点文件，生成 knowledge/index.md。
Agent 问答时先读 index.md，了解有哪些知识可用。

使用：python3 build_index.py
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"


def parse_frontmatter(content: str) -> dict:
    """解析 Markdown 文件的 YAML frontmatter。"""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}
    meta = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, _, value = line.partition(':')
            meta[key.strip()] = value.strip()
    return meta


def main():
    if not KNOWLEDGE_DIR.exists():
        print(f"❌ 知识库目录不存在: {KNOWLEDGE_DIR}")
        print("   请先运行 python3 extract.py")
        sys.exit(1)

    # 扫描所有知识点文件
    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    md_files = [f for f in md_files if f.name != "index.md"]

    if not md_files:
        print("❌ 知识库目录下没有知识点文件")
        print("   请先运行 python3 extract.py")
        sys.exit(1)

    print(f"📄 扫描到 {len(md_files)} 个知识点文件\n")

    # 按分类聚合
    categories = defaultdict(list)
    all_topics = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)

        topic = meta.get("topic", "未命名")
        category = meta.get("category", "未分类")
        source = meta.get("source", "")
        related = meta.get("related", "")

        # 提取摘要（第一个 ## 摘要 下面的内容）
        summary = ""
        summary_match = re.search(r'## 摘要\s*\n(.*?)(?=\n## )', content, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()
        # 如果没有 ## 分隔，取第二段
        if not summary:
            parts = content.split('\n\n')
            if len(parts) > 2:
                summary = parts[2].strip()[:100]

        categories[category].append({
            "topic": topic,
            "filename": md_file.name,
            "source": source,
            "summary": summary[:120],  # index 中只保留短摘要
            "related": [r.strip() for r in related.split(',') if r.strip()]
        })
        all_topics.append(topic)

    # 生成 index.md
    lines = [
        "# 价值投资知识库索引",
        "",
        f"共 **{len(md_files)}** 个知识条目，涵盖 **{len(categories)}** 个分类。",
        "",
        "---",
        ""
    ]

    # 按分类输出
    category_order = [
        "投资原则", "估值方法", "商业分析", "市场与心理",
        "风险管理", "企业管理", "宏观经济", "人生哲学", "未分类"
    ]

    existing_cats = set(categories.keys())
    ordered_cats = [c for c in category_order if c in existing_cats]
    # 把不在预定义列表中的分类也加上
    for c in sorted(existing_cats):
        if c not in ordered_cats:
            ordered_cats.append(c)

    for cat in ordered_cats:
        items = categories[cat]
        lines.append(f"## {cat}")
        lines.append(f"共 {len(items)} 条{''}")
        lines.append("")

        for item in items:
            link = f"[{item['topic']}]({item['filename']})"
            lines.append(f"- {link} — {item['summary']}（{item['source']}）")

        lines.append("")

    # 统计信息
    lines.append("---")
    lines.append("")
    lines.append("## 统计")
    lines.append("")
    for cat in ordered_cats:
        lines.append(f"- {cat}: {len(categories[cat])} 条")
    lines.append(f"- **总计: {len(md_files)} 条**")
    lines.append("")

    # 写入
    INDEX_FILE.write_text('\n'.join(lines), encoding="utf-8")
    print(f"✅ 索引已生成: {INDEX_FILE}")
    print(f"   分类数: {len(ordered_cats)}")
    print(f"   总条目: {len(md_files)}")
    print()
    print("💡 下一步: python3 agent.py")


if __name__ == "__main__":
    main()
