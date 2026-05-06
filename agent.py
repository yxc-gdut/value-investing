#!/usr/bin/env python3
"""
agent.py — Agent 模式问答（通过 OpenClaw Gateway）
================================================

LLM 自主浏览知识库，根据 index.md 选择相关词条，读取完整内容后综合回答。
通过 openclaw infer model run --gateway 调用 LLM，无需外部 API key。

使用：python3 agent.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ========== 配置 ==========
BASE_DIR = Path(__file__).parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"


# ========== LLM 调用（通过 OpenClaw Gateway） ==========

def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """通过 openclaw infer model run --gateway 调用 LLM。"""
    prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}"

    # 写入临时文件避免 shell 转义问题
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(prompt)
        tmp_path = f.name

    try:
        result = subprocess.run(
            f'openclaw infer model run --gateway --prompt "$(cat {tmp_path})"',
            shell=True, capture_output=True, text=True, timeout=120
        )
        output = result.stdout.strip()

        if not output:
            # 检查 stderr
            err = result.stderr.strip()
            if err:
                return f"❌ LLM 无响应: {err[:200]}"
            return "❌ LLM 无响应"

        # 清理输出中的前缀（如果有的话）
        # openclaw infer 有时会输出一些状态信息
        lines = output.split('\n')
        # 过滤掉非内容行
        content_lines = []
        for line in lines:
            # 跳过空行、进度行、状态行
            if line.strip() and not line.startswith('✅') and not line.startswith('🔄') and not line.startswith('ETA:'):
                content_lines.append(line)

        return '\n'.join(content_lines) if content_lines else output
    except subprocess.TimeoutExpired:
        return "❌ LLM 调用超时"
    except Exception as e:
        return f"❌ LLM 调用失败: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


# ========== 知识库操作 ==========

def load_index() -> str:
    """加载索引内容。"""
    if not INDEX_FILE.exists():
        return ""
    return INDEX_FILE.read_text(encoding="utf-8")


def read_knowledge_files(filenames: list[str]) -> list[dict]:
    """读取指定的知识点文件，返回内容和元数据。"""
    results = []
    for filename in filenames:
        filepath = KNOWLEDGE_DIR / filename
        if not filepath.exists():
            # 尝试模糊匹配
            matched = list(KNOWLEDGE_DIR.glob(f"*{filename}*"))
            if not matched:
                results.append({"file": filename, "error": "文件不存在"})
                continue
            filepath = matched[0]

        try:
            content = filepath.read_text(encoding="utf-8")
            # 解析 frontmatter
            meta = {}
            fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
            if fm_match:
                for line in fm_match.group(1).split('\n'):
                    if ':' in line:
                        key, _, value = line.partition(':')
                        meta[key.strip()] = value.strip()
            results.append({
                "file": filepath.name,
                "topic": meta.get("topic", ""),
                "category": meta.get("category", ""),
                "source": meta.get("source", ""),
                "content": content
            })
        except Exception as e:
            results.append({"file": filename, "error": str(e)})

    return results


# ========== Agent 逻辑 ==========

SELECT_SYSTEM = """你是一个价值投资知识库的检索助手。用户会提出一个关于价值投资的问题，
你的任务是从知识库索引中选择最相关的知识条目。

知识库索引如下：
{index}

请根据用户问题，选择最相关的知识条目文件名。
只返回 JSON 数组，不要输出其他内容：
```json
["filename1.md", "filename2.md", ...]
```

选择规则：
1. 选择 3-8 个最相关的条目
2. 优先选择主题直接匹配的
3. 补充选择相关的上下游主题
4. 如果问题涉及对比，确保选择两边都有"""


QA_SYSTEM = """你是巴菲特和段永平的价值投资专家。基于提供的知识库内容回答用户问题。

要求：
1. 回答要有深度，结合巴菲特和段永平的观点
2. 引用具体观点时标注来源（哪位、哪年的资料）
3. 如果多个条目有相关内容，综合起来分析
4. 如果知识库中没有相关内容，诚实说明
5. 用中文回答，风格简洁有力

以下是相关的知识条目内容：
{knowledge}"""


def agent_answer(question: str, index_content: str) -> str:
    """Agent 模式：选择词条 → 读取内容 → 综合回答。"""
    # Step 1: 选择相关词条
    print("  🔍 Step 1: 选择相关词条...")

    select_result = call_llm(
        SELECT_SYSTEM.format(index=index_content),
        f"问题：{question}\n\n请选择最相关的知识条目文件名。",
        temperature=0.1
    )

    # 解析文件名列表
    filenames = []
    json_match = re.search(r'\[([^\]]+)\]', select_result)
    if json_match:
        try:
            filenames = json.loads(f"[{json_match.group(1)}]")
        except json.JSONDecodeError:
            filenames = re.findall(r'([\w-]+\.md)', select_result)

    if not filenames:
        return "⚠️ 未能匹配到相关知识条目，请尝试换个问法。"

    print(f"  📄 选中的条目: {filenames[:5]}{'...' if len(filenames) > 5 else ''}")

    # Step 2: 读取知识内容
    print("  📖 Step 2: 读取知识内容...")
    knowledge_data = read_knowledge_files(filenames)
    knowledge_parts = []
    cited_sources = []

    for kd in knowledge_data:
        if "error" in kd:
            print(f"    ⚠️ {kd['file']}: {kd['error']}")
            continue
        topic = kd.get("topic", kd["file"])
        knowledge_parts.append(f"### {topic}\n{kd['content']}")
        cited_sources.append(f"- {topic}（{kd.get('source', '未知来源')}）")

    if not knowledge_parts:
        return "⚠️ 选中的知识条目读取失败，请尝试换个问法。"

    knowledge_text = "\n\n---\n\n".join(knowledge_parts)

    # Step 3: 综合回答
    print("  🧠 Step 3: 综合回答...")
    answer = call_llm(
        QA_SYSTEM.format(knowledge=knowledge_text),
        f"问题：{question}",
        temperature=0.5
    )

    # 附加引用来源
    source_info = "\n\n📚 **参考知识条目：**\n" + "\n".join(cited_sources)
    return answer + source_info


def search_index(keyword: str, index_content: str) -> str:
    """在索引中搜索关键词，返回匹配的条目。"""
    lines = index_content.split('\n')
    matches = []
    keyword_lower = keyword.lower()

    for i, line in enumerate(lines):
        if keyword_lower in line.lower():
            start = max(0, i - 1)
            end = min(len(lines), i + 3)
            matches.append('\n'.join(lines[start:end]))

    if not matches:
        return f"🔍 未找到与「{keyword}」相关的条目。"

    return f"🔍 找到 {len(matches)} 个相关条目：\n\n" + "\n---\n".join(matches)


def list_topics(index_content: str) -> str:
    """列出所有主题分类。"""
    categories = re.findall(r'## (.+)', index_content)
    if not categories:
        return "索引为空"

    result = "📚 知识库分类：\n\n"
    for cat in categories:
        result += f"  📂 {cat}\n"
    return result


# ========== 主程序 ==========

def main():
    if not INDEX_FILE.exists():
        print("❌ 知识库索引不存在")
        print("   请先运行: python3 build_index.py")
        sys.exit(1)

    index_content = load_index()

    print("=" * 60)
    print("🧠 价值投资 Agent 问答")
    print("=" * 60)
    print("💡 输入问题开始问答")
    print("   topics    — 查看所有主题分类")
    print("   search 关键词 — 搜索索引")
    print("   exit      — 退出")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n🙋 ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ["exit", "quit", "q"]:
            print("👋 再见！")
            break

        if cmd == "topics":
            print(list_topics(index_content))
            continue

        if cmd.startswith("search "):
            keyword = user_input[7:].strip()
            if keyword:
                print(search_index(keyword, index_content))
            continue

        # Agent 问答
        print()
        answer = agent_answer(user_input, index_content)
        print(f"\n💡 {answer}")


if __name__ == "__main__":
    main()
