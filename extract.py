#!/usr/bin/env python3
"""
extract.py — 知识提取（离线批量跑）
===================================

读取原始资料，用 GLM-5-Turbo 批量提取知识点，输出结构化 Markdown。

流程：
  1. 读取 letters/*.md（巴菲特股东信），按 1500-2000 词切分 chunks
  2. 读取 duanyongping/*.pdf（段永平问答录），提取文本后同样切分
  3. 对每个 chunk 调用 LLM，提取结构化知识点
  4. 输出到 knowledge/ 目录

使用：export GLM_API_KEY="your-key" && python3 extract.py
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
    print("⚠️ pypdf 未安装，段永平 PDF 将被跳过。安装: pip install pypdf")

# ========== 配置 ==========
BASE_DIR = Path(__file__).parent
LETTERS_DIR = BASE_DIR / "letters"
DUAN_DIR = BASE_DIR / "duanyongping"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PROGRESS_FILE = KNOWLEDGE_DIR / "progress.json"

# API 配置（优先环境变量，否则用默认值）
API_KEY = os.environ.get("GLM_API_KEY", "")

# 自动选择可用的 API
# 1. 如果设置了 GLM_API_KEY 且 URL 以 https 开头，直接使用
# 2. 否则默认使用通义千问（免费额度充足）
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_API_URL = "https://coding.dashscope.aliyuncs.com/v1/chat/completions"
QWEN_MODEL = "qwen3.5-plus"

if API_KEY and API_KEY.startswith("https://"):
    # 环境变量格式: GLM_API_KEY=https://xxx/key
    parts = API_KEY.rsplit("/", 1)
    API_URL = f"{parts[0]}/chat/completions"
    API_KEY = parts[1]
    MODEL = os.environ.get("GLM_MODEL", "glm-5-turbo")
    API_SOURCE = "custom"
else:
    API_URL = QWEN_API_URL
    API_KEY = QWEN_API_KEY
    MODEL = QWEN_MODEL
    API_SOURCE = "qwen"
MAX_CONCURRENT = 3
MAX_RETRIES = 3
CHUNK_MIN_WORDS = 1500
CHUNK_MAX_WORDS = 2000
# 每个知识点文件保留的原文引用最大字符数，避免文件过大
MAX_QUOTE_CHARS = 1500

# ========== LLM 提取 prompt ==========

EXTRACT_PROMPT = """你是一位精通巴菲特和段永平价值投资哲学的专家研究员。你的任务是从给定的文本片段中提取结构化的知识点。

请仔细阅读以下文本片段，提取出其中的投资知识点。

要求：
1. topic: 知识点的主题名称（中文，简洁精确，如"安全边际"、"护城河"、"能力圈"）
2. category: 归类到以下之一：投资原则、估值方法、商业分析、市场与心理、风险管理、企业管理、宏观经济、人生哲学
3. summary: 用中文概括这个知识点的核心内容（2-4句话）
4. key_points: 提炼 2-5 个核心观点（中文），每个观点一句话
5. quotes: 从原文中摘录 1-3 段最相关的原文引用（保留英文原文，不要翻译）
6. source: 来源信息（如"巴菲特 1992年致股东信"）
7. related_topics: 相关的其他投资主题（中文，2-4个）

严格输出 JSON，不要输出任何其他内容：
```json
{
  "topic": "主题名称",
  "category": "分类",
  "summary": "中文摘要",
  "key_points": ["观点1", "观点2"],
  "quotes": ["原文引用1", "原文引用2"],
  "source": "来源",
  "related_topics": ["相关主题1", "相关主题2"]
}
```"""

# ========== 文本处理 ==========

def split_into_chunks(text: str, min_words: int = CHUNK_MIN_WORDS, max_words: int = CHUNK_MAX_WORDS) -> list[str]:
    """将长文本按词数切分成 chunks，尽量在段落边界切分。"""
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = []
    current_word_count = 0

    for para in paragraphs:
        para_words = len(para.split())
        # 如果单段就超过 max，强制切分
        if para_words > max_words:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_word_count = 0
            # 按句子切分长段落
            sentences = re.split(r'(?<=[.!?])\s+', para)
            sub_chunk = []
            sub_count = 0
            for sent in sentences:
                sent_words = len(sent.split())
                if sub_count + sent_words > max_words and sub_chunk:
                    chunks.append('\n'.join(sub_chunk))
                    sub_chunk = []
                    sub_count = 0
                sub_chunk.append(sent)
                sub_count += sent_words
            if sub_chunk:
                chunks.append('\n'.join(sub_chunk))
            continue

        if current_word_count + para_words > max_words and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = []
            current_word_count = 0

        current_chunk.append(para)
        current_word_count += para_words

        if current_word_count >= min_words:
            chunks.append('\n'.join(current_chunk))
            current_chunk = []
            current_word_count = 0

    if current_chunk and current_word_count > 100:  # 丢弃太短的残余
        chunks.append('\n'.join(current_chunk))

    return chunks


def sanitize_filename(name: str) -> str:
    """清理文件名，只保留安全字符。"""
    name = name.lower().strip()
    name = re.sub(r'[^\w\u4e00-\u9fff]+', '-', name)
    name = re.sub(r'-+', '-', name).strip('-')
    return name[:60]


# ========== 资料加载 ==========

def load_buffett_letters() -> list[dict]:
    """加载巴菲特股东信 Markdown，返回 chunks 列表。"""
    chunks = []
    if not LETTERS_DIR.exists():
        print(f"⚠️ 目录不存在: {LETTERS_DIR}")
        return chunks

    md_files = sorted(LETTERS_DIR.glob("*.md"))
    print(f"📄 找到 {len(md_files)} 份巴菲特股东信")

    for md_file in md_files:
        year_match = re.search(r'(\d{4})', md_file.stem)
        year = year_match.group(1) if year_match else "unknown"
        source = f"巴菲特 {year}年致股东信"

        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️ 读取失败 {md_file.name}: {e}")
            continue

        file_chunks = split_into_chunks(content)
        for i, chunk in enumerate(file_chunks, 1):
            chunks.append({
                "source": source,
                "file": md_file.name,
                "chunk_index": i,
                "total_chunks": len(file_chunks),
                "text": chunk,
                "prefix": f"buffett_{year}"
            })
        print(f"  ✅ {md_file.name}: {len(file_chunks)} chunks")

    return chunks


def load_duan_pdfs() -> list[dict]:
    """加载段永平 PDF，提取文本后切分。"""
    chunks = []
    if not DUAN_DIR.exists():
        print(f"⚠️ 目录不存在: {DUAN_DIR}")
        return chunks

    if PdfReader is None:
        print("⚠️ pypdf 未安装，跳段永平 PDF")
        return chunks

    pdf_files = sorted(DUAN_DIR.glob("*.pdf"))
    print(f"📄 找到 {len(pdf_files)} 份段永平资料")

    for pdf_file in pdf_files:
        try:
            reader = PdfReader(pdf_file)
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(text.strip())
            full_text = '\n\n'.join(text_parts)
        except Exception as e:
            print(f"  ⚠️ 读取失败 {pdf_file.name}: {e}")
            continue

        if not full_text.strip():
            print(f"  ⚠️ {pdf_file.name} 提取为空")
            continue

        source = f"段永平 {pdf_file.stem}"
        file_chunks = split_into_chunks(full_text)
        for i, chunk in enumerate(file_chunks, 1):
            chunks.append({
                "source": source,
                "file": pdf_file.name,
                "chunk_index": i,
                "total_chunks": len(file_chunks),
                "text": chunk,
                "prefix": f"duan_{sanitize_filename(pdf_file.stem)}"
            })
        print(f"  ✅ {pdf_file.name} ({len(reader.pages)}页): {len(file_chunks)} chunks")

    return chunks


# ========== LLM 调用 ==========

async def call_llm(text: str, session: requests.Session) -> dict | None:
    """调用 GLM-5-Turbo 提取知识点，返回 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": f"请从以下文本片段中提取知识点：\n\n---\n{text[:4000]}\n---"}
        ],
        "temperature": 0.3,
        "max_tokens": 1024
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: session.post(API_URL, json=payload, timeout=60)
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            # 提取 JSON
            json_match = re.search(r'```json\s*\n(.*?)\n\s*```', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            # 尝试直接解析
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"    ⚠️ JSON 解析失败 (尝试 {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                return None
        except requests.exceptions.RequestException as e:
            print(f"    ⚠️ API 请求失败 (尝试 {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                return None
        except Exception as e:
            print(f"    ⚠️ 未知错误 (尝试 {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                return None
        await asyncio.sleep(2 * attempt)  # 指数退避

    return None


# ========== 知识点写入 ==========

def save_knowledge(data: dict, chunk_info: dict, knowledge_dir: Path) -> str | None:
    """将提取的知识点保存为 Markdown 文件，返回文件名。"""
    topic = data.get("topic", "unknown")
    prefix = chunk_info["prefix"]
    chunk_idx = chunk_info["chunk_index"]

    filename = f"{prefix}_{sanitize_filename(topic)}_{chunk_idx:02d}.md"
    filepath = knowledge_dir / filename

    # 处理重名：如果文件已存在，追加编号
    counter = 1
    while filepath.exists():
        filename = f"{prefix}_{sanitize_filename(topic)}_{chunk_idx:02d}_{counter}.md"
        filepath = knowledge_dir / filename
        counter += 1

    # 截断过长的引用
    quotes = data.get("quotes", [])
    trimmed_quotes = []
    total_chars = 0
    for q in quotes:
        if total_chars + len(q) > MAX_QUOTE_CHARS:
            break
        trimmed_quotes.append(q)
        total_chars += len(q)

    related = ", ".join(data.get("related_topics", []))
    key_points = data.get("key_points", [])

    md = f"""---
topic: {topic}
category: {data.get("category", "未分类")}
source: {data.get("source", chunk_info["source"])}
related: {related}
---

# {topic}

## 摘要
{data.get("summary", "")}

## 核心观点
{chr(10).join(f"{i+1}. {p}" for i, p in enumerate(key_points))}

## 原文引用
{chr(10).join(f"> {q}" for q in trimmed_quotes)}

## 来源
{data.get("source", chunk_info["source"])}

## 相关主题
{chr(10).join(f"- {t}" for t in data.get("related_topics", []))}
"""

    filepath.write_text(md, encoding="utf-8")
    return filename


# ========== 断点续传 ==========

def load_progress() -> dict:
    """加载进度记录。"""
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"completed": [], "extracted": 0, "skipped": 0, "failed": 0}


def save_progress(progress: dict):
    """保存进度记录。"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def chunk_key(chunk_info: dict) -> str:
    """生成 chunk 的唯一标识。"""
    return f"{chunk_info['file']}#{chunk_info['chunk_index']}"


# ========== 主流程 ==========

async def extract_chunk(chunk: dict, session: requests.Session, progress: dict, semaphore: asyncio.Semaphore) -> dict | None:
    """处理单个 chunk 的提取。"""
    key = chunk_key(chunk)
    if key in progress["completed"]:
        return None

    async with semaphore:
        data = await call_llm(chunk["text"], session)

    if data:
        filename = save_knowledge(data, chunk, KNOWLEDGE_DIR)
        progress["completed"].append(key)
        progress["extracted"] += 1
        return {"status": "ok", "topic": data.get("topic"), "file": filename, "source": chunk["source"]}
    else:
        progress["completed"].append(key)
        progress["failed"] += 1
        return {"status": "fail", "source": chunk["source"]}

    # 每完成 10 个保存一次进度
    if len(progress["completed"]) % 10 == 0:
        save_progress(progress)


async def main():
    if not API_KEY:
        print("❌ 请设置环境变量 GLM_API_KEY")
        print("   export GLM_API_KEY='your-key'")
        sys.exit(1)

    print("=" * 60)
    print("📖 LLM Wiki 知识提取")
    print("=" * 60)
    print()

    # 创建输出目录
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    # 加载资料
    print("📚 加载原始资料...\n")
    all_chunks = load_buffett_letters() + load_duan_pdfs()
    total = len(all_chunks)

    if not all_chunks:
        print("❌ 没有加载到任何资料")
        sys.exit(1)

    print(f"\n📊 共 {total} 个 chunks 待处理\n")

    # 加载进度
    progress = load_progress()
    already_done = sum(1 for c in all_chunks if chunk_key(c) in progress["completed"])
    remaining = total - already_done

    print(f"✅ 已完成: {already_done}")
    print(f"⏳ 剩余: {remaining}")
    if remaining == 0:
        print("\n🎉 所有 chunks 已处理完毕！")
        print(f"   提取成功: {progress['extracted']}")
        print(f"   提取失败: {progress['failed']}")
        return

    print()

    # 准备
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    })

    # 过滤未完成的 chunks
    pending_chunks = [c for c in all_chunks if chunk_key(c) not in progress["completed"]]

    # 开始提取
    start_time = time.time()
    results = {"ok": 0, "fail": 0}

    for i, chunk in enumerate(pending_chunks, 1):
        elapsed = time.time() - start_time
        eta = (elapsed / i) * (len(pending_chunks) - i) if i > 0 else 0
        print(f"\r🔄 [{i}/{len(pending_chunks)}] 提取中... ETA: {eta/60:.0f}min  "
              f"✅{results['ok']} ❌{results['fail']}  "
              f"({chunk['source']} #{chunk['chunk_index']})", end="", flush=True)

        result = await extract_chunk(chunk, session, progress, semaphore)
        if result:
            if result["status"] == "ok":
                results["ok"] += 1
            else:
                results["fail"] += 1

    print()

    # 保存最终进度
    save_progress(progress)

    # 统计
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 提取完成")
    print("=" * 60)
    print(f"  总 chunks: {total}")
    print(f"  成功提取: {progress['extracted']}")
    print(f"  失败: {progress['failed']}")
    print(f"  耗时: {elapsed/60:.1f} 分钟")
    print(f"  知识文件: {len(list(KNOWLEDGE_DIR.glob('*.md')))} 个")
    print()
    print("💡 下一步: python3 build_index.py")


if __name__ == "__main__":
    asyncio.run(main())
