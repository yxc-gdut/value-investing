#!/usr/bin/env python3
"""
extract_via_openclaw.py — 通过 OpenClaw CLI 调用 LLM 提取知识点
===========================================================

使用 openclaw infer model run 来调用 LLM，避免自己处理 API 认证。

使用：python3 extract_via_openclaw.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "chunks"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PROGRESS_FILE = CHUNKS_DIR / "progress.json"

EXTRACT_PROMPT = """你是一位精通巴菲特和段永平价值投资哲学的专家研究员。请从以下文本片段中提取结构化知识点。

严格只输出 JSON，不要输出任何其他内容：
```json
{
  "topic": "主题名称（中文）",
  "category": "投资原则/估值方法/商业分析/市场与心理/风险管理/企业管理/宏观经济/人生哲学",
  "summary": "中文摘要（2-4句话）",
  "key_points": ["核心观点1", "核心观点2"],
  "quotes": ["原文引用1", "原文引用2"],
  "source": "来源信息",
  "related_topics": ["相关主题1", "相关主题2"]
}
```

以下是需要提取的文本：
"""


def sanitize_filename(name):
    name = name.lower().strip()
    name = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:60]


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text("utf-8"))
    return {"total": 0, "completed": [], "extracted": 0, "failed": 0}


def save_progress(progress):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), "utf-8")


def call_openclaw_model(prompt: str, model: str = "zai/glm-5-turbo") -> str:
    """通过 openclaw CLI 调用模型。"""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # 写 prompt 到临时文件，避免 shell 参数长度问题
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(prompt)
                prompt_file = f.name

            try:
                result = subprocess.run(
                    f'openclaw infer model run --gateway --model "{model}" --prompt "$(cat {prompt_file})"',
                    shell=True, capture_output=True, text=True, timeout=120
                )
            finally:
                os.unlink(prompt_file)

            output = result.stdout
            if not output:
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                    continue
                return ""

            # 移除 plugin 加载日志，只保留模型输出
            lines = output.split('\n')
            output_start = -1
            for i, line in enumerate(lines):
                if 'outputs:' in line:
                    output_start = i + 1
                    break

            if output_start >= 0:
                clean_output = '\n'.join(lines[output_start:]).strip()
            else:
                clean_output = '\n'.join(lines[-10:]).strip()

            # outputs: 0 或空内容，重试
            if not clean_output or clean_output == '0':
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                    continue
                return ""

            return clean_output

        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                time.sleep(3 * attempt)
                continue
            return ""
        except Exception as e:
            if attempt < max_retries:
                time.sleep(3 * attempt)
                continue
            return ""

    return ""


def parse_llm_response(text: str) -> dict | None:
    """解析 LLM 返回的 JSON。"""
    # 提取 ```json ... ``` 中的内容
    json_match = re.search(r'```json\s*\n(.*?)\n\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试找到第一个 { 和最后一个 }
    brace_start = text.find('{')
    brace_end = text.rfind('}')
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    return None


def save_knowledge(data: dict, chunk_filename: str) -> str | None:
    """保存知识点为 Markdown 文件。"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    topic = data.get("topic", "unknown")
    parts = chunk_filename.replace(".txt", "").split("_", 2)
    prefix = f"{parts[0]}_{parts[1]}" if len(parts) > 1 else "unknown"

    filename = f"{prefix}_{sanitize_filename(topic)}.md"
    filepath = KNOWLEDGE_DIR / filename

    counter = 1
    while filepath.exists():
        filename = f"{prefix}_{sanitize_filename(topic)}_{counter}.md"
        filepath = KNOWLEDGE_DIR / filename
        counter += 1

    related = ", ".join(data.get("related_topics", []))
    key_points = data.get("key_points", [])

    quotes = data.get("quotes", [])
    total = 0
    trimmed = []
    for q in quotes:
        if total + len(q) > 1500:
            break
        trimmed.append(q)
        total += len(q)

    source = data.get("source", "")
    # 从文件名提取来源
    if not source and parts[0] == "buffett":
        source = f"巴菲特 {parts[1]}年致股东信"
    elif not source and parts[0] == "duan":
        source = f"段永平"

    md = f"""---
topic: {topic}
category: {data.get("category", "未分类")}
source: {source}
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
{source}

## 相关主题
{chr(10).join(f"- {t}" for t in data.get("related_topics", []))}
"""

    filepath.write_text(md, "utf-8")
    return filepath.name


def main():
    print("=" * 60)
    print("📖 LLM Wiki 知识提取（通过 OpenClaw）")
    print("=" * 60)
    print()

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    # 加载 chunks
    all_chunks = sorted(CHUNKS_DIR.glob("*.txt"))
    if not all_chunks:
        print("❌ chunks 目录为空，请先运行切分脚本")
        sys.exit(1)

    progress = load_progress()
    pending = [f for f in all_chunks if f.name not in progress["completed"]]
    total = len(all_chunks)
    remaining = len(pending)

    print(f"📊 总 chunks: {total}")
    print(f"✅ 已完成: {total - remaining}")
    print(f"⏳ 剩余: {remaining}")
    print()

    if remaining == 0:
        print("🎉 所有 chunks 已处理完毕！")
        return

    start_time = time.time()
    ok_count = 0
    fail_count = 0

    for i, chunk_file in enumerate(pending, 1):
        elapsed = time.time() - start_time
        eta = (elapsed / i) * (len(pending) - i) if i > 0 else 0

        # 提取来源信息
        parts = chunk_file.stem.split("_", 2)
        if parts[0] == "buffett":
            source_desc = f"巴菲特 {parts[1]}年致股东信"
        else:
            source_desc = f"段永平"

        print(f"\r🔄 [{i}/{remaining}] {chunk_file.name} ({source_desc}) "
              f"ETA:{eta/60:.0f}min ✅{ok_count} ❌{fail_count}  ", end="", flush=True)

        # 读取 chunk
        try:
            chunk_text = chunk_file.read_text("utf-8")
        except Exception as e:
            print(f"\n  ⚠️ 读取失败: {e}")
            progress["completed"].append(chunk_file.name)
            progress["failed"] += 1
            save_progress(progress)
            fail_count += 1
            continue

        # 调用 LLM
        prompt = EXTRACT_PROMPT + "\n---\n" + chunk_text[:4000]
        response = call_openclaw_model(prompt)

        if not response:
            print(f"\n  ⚠️ LLM 无响应")
            progress["completed"].append(chunk_file.name)
            progress["failed"] += 1
            save_progress(progress)
            fail_count += 1
            continue

        # 解析结果
        data = parse_llm_response(response)
        if not data:
            print(f"\n  ⚠️ JSON 解析失败: {response[:200]}")
            progress["completed"].append(chunk_file.name)
            progress["failed"] += 1
            save_progress(progress)
            fail_count += 1
            continue

        # 保存知识点
        try:
            saved_name = save_knowledge(data, chunk_file.name)
            if saved_name:
                ok_count += 1
                progress["extracted"] += 1
            else:
                fail_count += 1
                progress["failed"] += 1
        except Exception as e:
            print(f"\n  ⚠️ 保存失败: {e}")
            fail_count += 1
            progress["failed"] += 1

        progress["completed"].append(chunk_file.name)
        save_progress(progress)

        # 每 5 个保存一次进度，并稍微休息避免被 kill
        if i % 5 == 0:
            time.sleep(2)

    elapsed = time.time() - start_time
    print()
    print()
    print("=" * 60)
    print("📊 提取完成")
    print("=" * 60)
    print(f"  成功: {ok_count}")
    print(f"  失败: {fail_count}")
    print(f"  耗时: {elapsed/60:.1f} 分钟")
    knowledge_count = len(list(KNOWLEDGE_DIR.glob("*.md")))
    print(f"  知识条目: {knowledge_count} 个")
    print()
    print("💡 下一步: python3 build_index.py")


if __name__ == "__main__":
    main()
