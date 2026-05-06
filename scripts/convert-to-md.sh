#!/bin/bash
# Buffett 年报 PDF → Markdown 转换脚本 v5 (final)
# 精准策略: 找 SEC 标题前的签名行作为结束

PDFS_DIR="/root/.openclaw/workspace/buffett-knowledge/pdfs"
LETTERS_DIR="/root/.openclaw/workspace/buffett-knowledge/letters"
FULL_DIR="/root/.openclaw/workspace/buffett-knowledge/full-text"

mkdir -p "$LETTERS_DIR" "$FULL_DIR"

convert_pdf() {
  local pdf="$1"
  local year="$2"
  local base=$(basename "$pdf" .pdf)
  
  echo "Processing $year..."
  
  # 提取纯文本
  local txt="$FULL_DIR/${base}.txt"
  pdftotext "$pdf" "$txt" 2>/dev/null
  
  if [ ! -s "$txt" ]; then
    echo "  ⚠️ Empty output"
    return
  fi
  
  # Step 1: 找 "To the Shareholders" 起始行
  local letter_start=$(grep -n "To the Shareholders of Berkshire Hathaway" "$txt" 2>/dev/null | head -1 | cut -d: -f1)
  if [ -z "$letter_start" ]; then
    echo "  ⚠️ No 'To the Shareholders' found"
    return
  fi
  
  # Step 2: 找 "SECURITIES AND EXCHANGE COMMISSION" (SEC 10-K 开始)
  # 只在 letter_start 之后 +2000 行内找，避免匹配到目录
  local sec_line=$(awk -v start="$letter_start" -v range="2000" \
    'NR > start && NR <= start + range && /^SECURITIES AND EXCHANGE COMMISSION$/ {print NR; exit}' "$txt" 2>/dev/null)
  
  if [ -z "$sec_line" ]; then
    echo "  ⚠️ No SEC header found"
    return
  fi
  
  # Step 3: 信结束于 SEC 标题前 2 行（签名日期行）
  local letter_end=$((sec_line - 2))
  
  if [ "$letter_end" -le "$letter_start" ]; then
    echo "  ⚠️ End before start"
    return
  fi
  
  # 验证结束区域确实有签名
  local check=$(sed -n "${letter_end},${sec_line}p" "$txt" 2>/dev/null | grep -c "Warren E. Buffett")
  if [ "$check" -eq 0 ]; then
    # 尝试往前找签名
    letter_end=$(awk -v start="$letter_start" -v sec="$sec_line" \
      'NR > start && NR < sec && /Warren E\. Buffett/ {print NR; exit}' "$txt" 2>/dev/null)
    if [ -n "$letter_end" ]; then
      letter_end=$((letter_end + 2))  # 包含签名后两行
    fi
  fi
  
  # 提取
  sed -n "${letter_start},${letter_end}p" "$txt" > "$LETTERS_DIR/${year}.txt"
  
  # 生成 MD
  {
    echo "---"
    echo "source: Berkshire Hathaway Annual Report"
    echo "year: $year"
    echo "type: chairman-letter"
    echo "url: https://www.berkshirehathaway.com/${year}ar/${year}ar.pdf"
    echo "extracted_from: line $letter_start - $letter_end"
    echo "---"
    echo ""
    cat "$LETTERS_DIR/${year}.txt"
  } > "$LETTERS_DIR/${year}.md"
  
  local size=$(wc -c < "$LETTERS_DIR/${year}.md")
  echo "  ✅ $year: lines $letter_start-$letter_end, $((size/1024))K"
}

# 处理所有有效 PDF
for pdf in "$PDFS_DIR"/annual_*.pdf; do
  size=$(stat -c%s "$pdf" 2>/dev/null || echo 0)
  [ "$size" -lt 1000 ] && continue
  year=$(echo "$pdf" | grep -oE '[0-9]{4}')
  [ -n "$year" ] && convert_pdf "$pdf" "$year"
done

# 处理 1995 HTML
if [ -s "$PDFS_DIR"/annual_1995.html ]; then
  echo "Processing 1995 HTML..."
  sed -n '/<pre>/,/<\/pre>/p' "$PDFS_DIR"/annual_1995.html | \
    sed 's/<[^>]*>//g' | sed 's/&amp;/\&/g' | \
    sed '/^[[:space:]]*$/d' > "$LETTERS_DIR/1995_raw.txt"
  start=$(grep -n "To the Shareholders" "$LETTERS_DIR/1995_raw.txt" 2>/dev/null | head -1 | cut -d: -f1)
  if [ -n "$start" ]; then
    # 1995 HTML 结构：找到 SEC 行之前的签名
    end_line=$(awk -v s="$start" 'NR>s && /Warren E\. Buffett/ {print NR+2; exit}' "$LETTERS_DIR/1995_raw.txt" 2>/dev/null)
    [ -n "$end_line" ] && sed -n "${start},${end_line}p" "$LETTERS_DIR/1995_raw.txt" > "$LETTERS_DIR/1995.txt"
    if [ -s "$LETTERS_DIR/1995.txt" ]; then
      {
        echo "---"
        echo "source: Berkshire Hathaway Annual Report (HTML)"
        echo "year: 1995"
        echo "type: chairman-letter"
        echo "url: https://www.berkshirehathaway.com/1995ar/1995ar.html"
        echo "---"
        echo ""
        cat "$LETTERS_DIR/1995.txt"
      } > "$LETTERS_DIR/1995.md"
      echo "  ✅ 1995 extracted"
    fi
  fi
fi

echo ""
echo "=== 完成 ==="
ls -lh "$LETTERS_DIR"/*.md 2>/dev/null | awk '{print $9, $5}' | sort -t'/' -k6 -n
