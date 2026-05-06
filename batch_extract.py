#!/usr/bin/env python3
"""
batch_extract.py — 由 OpenClaw Agent 调用的批量提取辅助脚本
不直接调用 LLM API，而是生成批次任务文件供 Agent 处理。

用法：
  python3 batch_extract.py --list-batch N        # 列出第 N 批的 chunk 文件
  python3 batch_extract.py --next-batch           # 列出下一批待处理的 chunk
  python3 batch_extract.py --mark-done <filename> # 标记某个 chunk 已完成
  python3 batch_extract.py --save-knowledge <json_file>  # 保存知识点
  python3 batch_extract.py --progress             # 查看进度
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PROGRESS_FILE = CHUNKS_DIR / "progress.json"
BATCH_SIZE = 5  # 每批 5 个 chunks


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text("utf-8"))
    return {"total": 0, "completed": [], "extracted": 0, "failed": 0}


def save_progress(progress):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), "utf-8")


def sanitize_filename(name):
    name = name.lower().strip()
    name = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:60]


def list_batch(batch_num):
    """列出第 N 批的 chunk 文件。"""
    all_chunks = sorted(CHUNKS_DIR.glob("*.txt"))
    start = (batch_num - 1) * BATCH_SIZE
    end = start + BATCH_SIZE
    batch = all_chunks[start:end]
    for f in batch:
        print(f.name)
    return len(batch)


def next_batch():
    """列出下一批待处理的 chunk。"""
    progress = load_progress()
    all_chunks = sorted(CHUNKS_DIR.glob("*.txt"))
    pending = [f for f in all_chunks if f.name not in progress["completed"]]

    if not pending:
        print("ALL_DONE")
        return 0

    batch = pending[:BATCH_SIZE]
    for f in batch:
        content = f.read_text("utf-8")
        # 提取来源信息
        parts = f.stem.split("_", 2)
        source_type = parts[0] if parts else "unknown"
        year_or_name = parts[1] if len(parts) > 1 else "unknown"

        if source_type == "buffett":
            source = f"巴菲特 {year_or_name}年致股东信"
        else:
            source = f"段永平 {year_or_name}"

        print(f"FILE:{f.name}")
        print(f"SOURCE:{source}")
        print(f"CONTENT_START:{content[:200]}")
        print(f"---END_CHUNK---")

    return len(batch)


def mark_done(filename, success=True):
    """标记一个 chunk 已处理。"""
    progress = load_progress()
    if filename not in progress["completed"]:
        progress["completed"].append(filename)
        if success:
            progress["extracted"] += 1
        else:
            progress["failed"] += 1
    save_progress(progress)


def save_knowledge(json_data, chunk_filename):
    """保存知识点为 Markdown 文件。"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        data = json.loads(json_data) if isinstance(json_data, str) else json_data
    except json.JSONDecodeError:
        print(f"ERROR: Invalid JSON")
        return None

    topic = data.get("topic", "unknown")
    parts = chunk_filename.split("_", 2)
    prefix = f"{parts[0]}_{parts[1]}" if len(parts) > 1 else "unknown"
    chunk_idx = parts[2].replace(".txt", "") if len(parts) > 2 else "001"

    filename = f"{prefix}_{sanitize_filename(topic)}.md"
    filepath = KNOWLEDGE_DIR / filename

    counter = 1
    while filepath.exists():
        filename = f"{prefix}_{sanitize_filename(topic)}_{counter}.md"
        filepath = KNOWLEDGE_DIR / filename
        counter += 1

    related = ", ".join(data.get("related_topics", []))
    key_points = data.get("key_points", [])

    # 截断过长引用
    quotes = data.get("quotes", [])
    total = 0
    trimmed = []
    for q in quotes:
        if total + len(q) > 1500:
            break
        trimmed.append(q)
        total += len(q)

    md = f"""---
topic: {topic}
category: {data.get("category", "未分类")}
source: {data.get("source", "")}
related: {related}
---

# {topic}

## 摘要
{data.get("summary", "")}

## 核心观点
{chr(10).join(f"{i+1}. {p}" for i, p in enumerate(key_points))}

## 原文引用
{chr(10).join(f"> {q}" for q in trimmed)}

## 来源
{data.get("source", "")}

## 相关主题
{chr(10).join(f"- {t}" for t in data.get("related_topics", []))}
"""

    filepath.write_text(md, "utf-8")
    print(f"SAVED:{filepath.name}")
    return filepath.name


def show_progress():
    """显示进度。"""
    progress = load_progress()
    all_chunks = sorted(CHUNKS_DIR.glob("*.txt"))
    total = len(all_chunks)
    done = len(progress["completed"])
    remaining = total - done
    pct = (done / total * 100) if total > 0 else 0

    print(f"总 chunks: {total}")
    print(f"已完成: {done} ({pct:.1f}%)")
    print(f"剩余: {remaining}")
    print(f"提取成功: {progress['extracted']}")
    print(f"提取失败: {progress['failed']}")

    knowledge_count = len(list(KNOWLEDGE_DIR.glob("*.md"))) - (1 if (KNOWLEDGE_DIR / "index.md").exists() else 0)
    print(f"知识条目: {knowledge_count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-batch", type=int, help="列出第 N 批")
    parser.add_argument("--next-batch", action="store_true", help="列出下一批待处理")
    parser.add_argument("--mark-done", type=str, help="标记 chunk 已完成")
    parser.add_argument("--mark-failed", type=str, help="标记 chunk 失败")
    parser.add_argument("--save-knowledge", type=str, help="保存知识点 JSON")
    parser.add_argument("--chunk-file", type=str, help="关联的 chunk 文件名")
    parser.add_argument("--progress", action="store_true", help="显示进度")
    args = parser.parse_args()

    if args.list_batch:
        list_batch(args.list_batch)
    elif args.next_batch:
        next_batch()
    elif args.mark_done:
        mark_done(args.mark_done, success=True)
    elif args.mark_failed:
        mark_done(args.mark_failed, success=False)
    elif args.save_knowledge:
        chunk_file = args.chunk_file or "unknown"
        with open(args.save_knowledge, "r", encoding="utf-8") as f:
            save_knowledge(f.read(), chunk_file)
    elif args.progress:
        show_progress()


if __name__ == "__main__":
    main()
