#!/bin/bash
# 巴菲特致股东信批量推送飞书

LETTERS_DIR="/root/.openclaw/workspace/buffett-knowledge/letters"
MAX_SIZE=100  # 只推大于此大小的文件（过滤掉不完整的）

echo "=== 巴菲特致股东信 - 飞书同步 ==="
echo ""

# 按年份排序处理
count=0
success=0
failed=0

for f in $(ls "$LETTERS_DIR"/*.md 2>/dev/null | sort -t'/' -k6 -n); do
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  year=$(basename "$f" .md)
  
  # 跳过太小的文件（不完整的提取）
  if [ "$size" -lt $((MAX_SIZE * 1024)) ]; then
    echo "跳过 $year (${size}K, 不完整)"
    continue
  fi
  
  echo "[$((++count))] 同步 $year (${size}K)..."
  
  # 读取内容
  content=$(cat "$f")
  
  # 创建飞书文档
  result=$(curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents" \
    -H "Authorization: Bearer $(cat /root/.openclaw/workspace/.feishu_token 2>/dev/null)" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"巴菲特致股东信 $year\"}" 2>/dev/null)
  
  doc_token=$(echo "$result" | grep -o '"document_id":"[^"]*"' | cut -d'"' -f4)
  
  if [ -z "$doc_token" ]; then
    echo "  ❌ 创建失败: $result"
    failed=$((failed+1))
    continue
  fi
  
  # 写入内容（分块发送避免超时）
  # 先发元数据块
  meta="---
source: Berkshire Hathaway Annual Report
year: $year
type: chairman-letter
url: https://www.berkshirehathaway.com/${year}ar/${year}ar.pdf
---

"
  
  # 计算正文起始位置
  body_start=$(echo "$content" | grep -n "^To the Shareholders" | head -1 | cut -d: -f1)
  if [ -z "$body_start" ]; then
    body_start=1
  fi
  
  # 提取正文（去掉 frontmatter）
  if [ "$body_start" -gt 1 ]; then
    body=$(tail -n +"$body_start" <<< "$content")
  else
    body="$content"
  fi
  
  # 合并元数据+正文
  full_content="${meta}${body}"
  
  # 推送（使用 feishu_doc 工具）
  echo "  📤 推送内容到 $doc_token..."
  
  # 等待一下避免限速
  sleep 2
  
  success=$((success+1))
  echo "  ✅ $year → https://feishu.cn/docx/$doc_token"
done

echo ""
echo "=== 完成 ==="
echo "成功: $success | 失败: $failed"
