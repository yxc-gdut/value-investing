#!/usr/bin/env python3
"""
巴菲特 & 段永平 问答系统
Buffett & Duan Yongping Q&A System

基于收集的资料，使用 LLM 回答关于价值投资的问题。
"""

import os
import re
import sys
from pathlib import Path

# API
import requests

# PDF reading
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# ========== 配置 ==========
MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
MOONSHOT_API_URL = "https://api.moonshot.cn/v1/chat/completions"
MODEL = "moonshot-v1-8k"

# 资料目录
BASE_DIR = Path(__file__).parent.resolve()
LETTERS_DIR = BASE_DIR / "buffett-letters-1956-2025" / "letters-en-md"
DUAN_DIR = BASE_DIR / "duanyongping"

# ========== 加载资料 ==========

def load_buffett_letters():
    """加载所有巴菲特股东信"""
    docs = []
    if not LETTERS_DIR.exists():
        print(f"⚠️ 目录不存在: {LETTERS_DIR}")
        return docs
    
    for md_file in sorted(LETTERS_DIR.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            # 提取年份用于标注
            year_match = re.search(r'(\d{4})', md_file.stem)
            year = year_match.group(1) if year_match else "unknown"
            docs.append({
                "source": f"巴菲特 {year}年股东信",
                "file": md_file.name,
                "content": content
            })
        except Exception as e:
            print(f"⚠️ 读取失败 {md_file.name}: {e}")
    return docs

def load_duan_pdfs():
    """加载段永平 PDF"""
    docs = []
    if not DUAN_DIR.exists():
        print(f"⚠️ 目录不存在: {DUAN_DIR}")
        return docs
    
    if PdfReader is None:
        print("⚠️ pypdf 未安装，无法读取 PDF")
        return docs
    
    for pdf_file in DUAN_DIR.glob("*.pdf"):
        try:
            reader = PdfReader(pdf_file)
            text_parts = []
            for i, page in enumerate(reader.pages[:50]):  # 限制前50页
                text = page.extract_text()
                if text:
                    text_parts.append(f"[第{i+1}页]\n{text}")
            
            full_text = "\n".join(text_parts)
            docs.append({
                "source": f"段永平 {pdf_file.stem}",
                "file": pdf_file.name,
                "content": full_text
            })
            print(f"  已加载: {pdf_file.name} ({len(reader.pages)}页)")
        except Exception as e:
            print(f"⚠️ 读取失败 {pdf_file.name}: {e}")
    return docs

# ========== 搜索相关段落 ==========

def simple_search(query, docs, top_k=5):
    """简单关键词搜索，返回最相关的文档"""
    query_words = set(query.lower().split())
    results = []
    
    for doc in docs:
        content_lower = doc["content"].lower()
        # 计算匹配分数
        score = sum(1 for word in query_words if word in content_lower)
        # 额外奖励：标题匹配
        if any(word in doc["file"].lower() for word in query_words):
            score += 2
        if score > 0:
            # 找到相关内容的位置
            lines = doc["content"].split('\n')
            snippet = find_snippet(lines, query_words)
            results.append((score, snippet, doc["source"]))
    
    # 按分数排序
    results.sort(key=lambda x: -x[0])
    return results[:top_k]

def find_snippet(lines, query_words, context_lines=3):
    """找到包含查询词的段落，返回周围上下文"""
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(word in line_lower for word in query_words):
            # 返回周围上下文
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            snippet_lines = lines[start:end]
            return '\n'.join(snippet_lines)
    return lines[0][:500] if lines else ""  # 没找到就返回开头

# ========== LLM 回答 ==========

def ask_llm(question, context):
    """调用 Moonshot API 生成回答"""
    if not MOONSHOT_API_KEY:
        return "❌ 未设置 MOONSHOT_API_KEY"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MOONSHOT_API_KEY}"
    }
    
    system_prompt = """你是一个精通巴菲特和段永平价值投资哲学的专家。你的任务是：

1. 基于提供的参考资料（来自巴菲特股东信和段永平投资问答录），回答用户问题
2. 回答时需要：
   - 引用相关的原文或核心观点
   - 标注观点来源（巴菲特/段永平，年份）
   - 结合两者观点时指出异同
3. 如果资料不足以回答，请明确说明，不要编造

回答风格：简洁、有深度、用中文回答。"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"参考资料：\n\n{context}\n\n---\n\n问题：{question}"}
        ],
        "temperature": 0.3
    }
    
    try:
        resp = requests.post(MOONSHOT_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ API 调用失败: {e}"

# ========== 主程序 ==========

def main():
    print("=" * 60)
    print("🥇 巴菲特 & 段永平 问答系统")
    print("=" * 60)
    
    # 加载资料
    print("\n📚 加载资料...")
    buffett_docs = load_buffett_letters()
    print(f"  巴菲特股东信: {len(buffett_docs)} 份")
    
    duan_docs = load_duan_pdfs()
    print(f"  段永平资料: {len(duan_docs)} 份")
    
    all_docs = buffett_docs + duan_docs
    print(f"  总计: {len(all_docs)} 份资料\n")
    
    if not all_docs:
        print("❌ 没有加载到任何资料")
        return
    
    # 交互式问答
    print("💬 输入问题开始问答（输入 exit 退出）")
    print("-" * 60)
    
    while True:
        try:
            question = input("\n🙋 问题: ").strip()
        except EOFError:
            break
        
        if not question:
            continue
        if question.lower() in ["exit", "quit", "q"]:
            print("👋 再见！")
            break
        
        print("\n🔍 搜索相关资料...")
        results = simple_search(question, all_docs, top_k=3)
        
        if not results:
            print("⚠️ 没有找到相关资料，尝试调整问题")
            continue
        
        print(f"  找到 {len(results)} 条相关内容\n")
        
        # 构建上下文
        context_parts = []
        for i, (score, snippet, source) in enumerate(results, 1):
            context_parts.append(f"【来源 {i}: {source}】\n{snippet}\n")
        context = "\n---\n".join(context_parts)
        
        # 显示搜索到的上下文（调试用）
        print(f"📖 参考资料:\n")
        for i, (score, snippet, source) in enumerate(results, 1):
            print(f"  [{i}] {source}")
            print(f"      {snippet[:200]}...")
            print()
        print("-" * 60)
        
        # 生成回答
        print("🤖 正在思考...")
        answer = ask_llm(question, context)
        print(f"\n💡 回答:\n{answer}\n")
        print("=" * 60)

if __name__ == "__main__":
    main()
