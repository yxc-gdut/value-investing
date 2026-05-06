#!/usr/bin/env python3
"""Buffett 年报提取器 v8 - 字符级精准切分"""

import subprocess
import re
import os

PDFS_DIR = "/root/.openclaw/workspace/buffett-knowledge/pdfs"
LETTERS_DIR = "/root/.openclaw/workspace/buffett-knowledge/letters"
FULL_DIR = "/root/.openclaw/workspace/buffett-knowledge/full-text"

os.makedirs(LETTERS_DIR, exist_ok=True)
os.makedirs(FULL_DIR, exist_ok=True)

def extract_text(pdf_path):
    tmp = f"/tmp/_buffett_{os.getpid()}_{os.urandom(4).hex()}.txt"
    try:
        r = subprocess.run(['pdftotext', pdf_path, tmp], capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(tmp):
            return ""
        with open(tmp, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def find_letter_content(text):
    """用字符位置精准定位letter内容"""
    
    # 找起始: "To the Shareholders of Berkshire Hathaway"
    start_kw = "To the Shareholders of Berkshire Hathaway"
    start_pos = text.find(start_kw)
    if start_pos < 0:
        return None, None, None, None
    
    # 找签名 block: "Warren E. Buffett\nChairman of the Board"
    sig_block = "Warren E. Buffett\nChairman of the Board"
    sig_pos = text.find(sig_block, start_pos)
    
    # 备用: "Warren E. Buffett" 单独出现（老格式）
    if sig_pos < 0:
        sig_alt = "Warren E. Buffett"
        alt_pos = text.find(sig_alt, start_pos)
        if alt_pos > 0:
            sig_pos = alt_pos
    
    if sig_pos < 0:
        return None, None, None, None
    
    # signature 前的日期行 = letter 结束
    # 找 sig_pos 前的最后一个日期行
    before_sig = text[start_pos:sig_pos]
    lines = before_sig.split('\n')
    
    DATE_MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'
    DATE_RE = re.compile(rf'^\s*({DATE_MONTHS})\s+\d{{1,2}},\s+\d{{4}}\s*$')
    DATE_RE2 = re.compile(rf'^\s*({DATE_MONTHS})\s+\d{{4}}\s*$')  # e.g. "February 2008"
    
    date_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if DATE_RE.match(stripped) or DATE_RE2.match(stripped):
            date_lines.append((i, stripped))
    
    if not date_lines:
        return None, None, None, None
    
    # 取最后一个日期行（最接近签名）
    last_date_idx, last_date = date_lines[-1]
    
    # 在 before_sig 中找该日期的全局位置
    # last_date_idx 是 before_sig 中的行号，before_sig 从 start_pos 开始
    # 所以全局字符位置 = start_pos + before_sig[:last_date_idx].count('\n') 之前的所有字符
    # 更简单：在 sig_pos 之前向后搜索 date 的全局位置
    date_search = last_date.strip()
    # 在 sig_pos 之前找最后一个匹配
    search_end = sig_pos
    date_global_pos = text.rfind(date_search, start_pos, search_end)
    
    if date_global_pos < 0:
        return None, None, None, None
    
    # 找日期行之后的换行位置 → letter结束
    eof_pos = text.find('\n', date_global_pos)
    if eof_pos < 0 or eof_pos > sig_pos:
        eof_pos = sig_pos
    
    letter_text = text[start_pos:eof_pos]
    
    # 计算行号（用于元数据）
    start_line = text[:start_pos].count('\n') + 1
    end_line = text[:eof_pos].count('\n') + 1
    
    return letter_text, start_pos, eof_pos, start_line, end_line

def process_year(year):
    pdf = f"{PDFS_DIR}/annual_{year}.pdf"
    if not os.path.exists(pdf):
        return f"❌ PDF not found"
    
    size = os.path.getsize(pdf)
    if size < 1000:
        return f"⚠️ PDF too small: {size}B"
    
    text = extract_text(pdf)
    if not text or not text.strip():
        return f"⚠️ Empty text"
    
    result = find_letter_content(text)
    if result[0] is None:
        return f"❌ Could not find letter content"
    
    letter_text, start_pos, eof_pos, start_line, end_line = result
    
    url = f"https://www.berkshirehathaway.com/{year}ar/{year}ar.pdf"
    md = f"""---
source: Berkshire Hathaway Annual Report
year: {year}
type: chairman-letter
url: {url}
extracted_from: line {start_line} - {end_line}
---

{letter_text}
"""
    
    md_file = f"{LETTERS_DIR}/{year}.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md)
    
    size_kb = len(md) // 1024
    return f"✅ {year}: lines {start_line}-{end_line}, {size_kb}K"

def main():
    print("=== Buffett Letter Extraction v8 ===\n")
    
    for fname in sorted(os.listdir(PDFS_DIR)):
        m = re.match(r'annual_(\d{4})\.pdf', fname)
        if m:
            year = m.group(1)
            print(f"  {process_year(year)}")
    
    print(f"\n=== Results ===")
    files = sorted([f for f in os.listdir(LETTERS_DIR) if f.endswith('.md')])
    for f in files:
        size = os.path.getsize(f"{LETTERS_DIR}/{f}") // 1024
        print(f"  {f}: {size}K")

if __name__ == "__main__":
    main()
