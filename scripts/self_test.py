#!/usr/bin/env python3
"""
Buffett Letter Extraction Self-Test System
每次 extract_letters.py 修改后自动运行，确保提取质量

测试维度：
1. 文件存在性 + 大小
2. Frontmatter 完整性
3. 内容起始/结束正确性
4. 无 10-K 污染
5. 内容完整性（关键段落存在）
"""

import os
import re
import sys

LETTERS_DIR = "/root/.openclaw/workspace/buffett-knowledge/letters"
YEARS = list(range(1995, 2025))
YEARS.remove(1996)
YEARS.remove(1997)

# 已知的签名日期（用于验证结束行）
KNOWN_SIGNATURES = {
    1995: "March 1, 1996",
    1998: "March 1, 1999",
    1999: "March 1, 2000",
    2000: "February 28, 2001",
    2001: "February 28, 2002",
    2002: "February 21, 2003",
    2003: "February 27, 2004",
    2004: "February 28, 2005",
    2005: "February 28, 2006",
    2006: "February 28, 2007",
    2007: "February 2008",
    2008: "February 27, 2009",
    2009: "February 26, 2010",
    2010: "February 26, 2011",
    2011: "February 25, 2012",
    2012: "March 1, 2013",
    2013: "February 28, 2014",
    2014: "February 27, 2015",
    2015: "February 27, 2016",
    2016: "February 25, 2017",
    2017: "February 24, 2018",
    2018: "February 23, 2019",
    2019: "February 22, 2020",
    2020: "February 27, 2021",
    2021: "February 26, 2022",
    2022: "February 25, 2023",
    2023: "February 24, 2024",
    2024: "February 22, 2025",
}

MIN_SIZE = {
    1995: 50_000, 1998: 50_000, 1999: 50_000, 2000: 50_000,
    2001: 50_000, 2002: 60_000, 2003: 60_000, 2004: 60_000,
    2005: 60_000, 2006: 60_000, 2007: 60_000, 2008: 60_000,
    2009: 50_000, 2010: 60_000, 2011: 60_000, 2012: 60_000,
    2013: 60_000, 2014: 60_000, 2015: 80_000, 2016: 70_000,
    2017: 40_000, 2018: 30_000, 2019: 30_000, 2020: 30_000,
    2021: 20_000, 2022: 15_000, 2023: 20_000, 2024: 20_000,
}

CONTAMINATION_PATTERNS = [
    "Item 8. Financial Statements",
    "REPORT OF INDEPENDENT",
    "Consolidated Balance Sheets",
    "Consolidated Statements of Earnings",
    "Notes to Consolidated Financial Statements",
    "Schedule of Valuation Accounts",
]


class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = True
        self.errors = []
    
    def fail(self, msg):
        self.passed = False
        self.errors.append(msg)


def test_file_exists(year: int) -> TestResult:
    t = TestResult(f"文件存在 [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        t.fail(f"文件不存在: {path}")
    return t


def test_file_size(year: int) -> TestResult:
    t = TestResult(f"文件大小 [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        return t
    
    size = os.path.getsize(path)
    min_expected = MIN_SIZE.get(year, 30_000)
    if size < min_expected:
        t.fail(f"文件过小: {size/1024:.0f}K < {min_expected/1024:.0f}K")
    return t


def test_frontmatter(year: int) -> TestResult:
    t = TestResult(f"Frontmatter [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        return t
    
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    required = ['source:', 'year:', 'type:', 'url:', 'extracted_from:']
    for field in required:
        if not re.search(rf'^{field}', content, re.MULTILINE):
            t.fail(f"缺少字段: {field}")
    
    # 验证 year 字段
    m = re.search(r'^year:\s*(\d{4})', content, re.MULTILINE)
    if m and int(m.group(1)) != year:
        t.fail(f"year 字段不匹配: {m.group(1)} != {year}")
    
    return t


def test_start_content(year: int) -> TestResult:
    t = TestResult(f"起始内容 [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        return t
    
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # 去掉 frontmatter 后找正文
    body_start = content.find('\n---\n\n')
    if body_start < 0:
        t.fail("找不到 frontmatter 分隔符")
        return t
    
    body = content[body_start + 5:]
    
    if not body.strip().startswith('To the Shareholders'):
        t.fail(f"正文不是以 'To the Shareholders' 开头，而是: {body.strip()[:60]!r}")
    
    return t


def test_end_content(year: int) -> TestResult:
    t = TestResult(f"结束内容 [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        return t
    
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # 去掉 frontmatter
    body_start = content.find('\n---\n\n')
    if body_start < 0:
        t.fail("找不到 frontmatter 分隔符")
        return t
    body = content[body_start + 5:]
    
    # 去掉末尾空白
    body = body.rstrip()
    
    # 结束应该包含签名日期
    expected_sig = KNOWN_SIGNATURES.get(year)
    if expected_sig and expected_sig not in body:
        # 检查最后几行
        last_lines = body.split('\n')[-10:]
        t.fail(f"未找到签名日期 {expected_sig!r}，最后几行: {last_lines[-3:]}")
    
    return t


def test_no_contamination(year: int) -> TestResult:
    t = TestResult(f"无 10-K 污染 [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        return t
    
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # 去掉 frontmatter
    body_start = content.find('\n---\n\n')
    if body_start >= 0:
        body = content[body_start + 5:]
    else:
        body = content
    
    for pattern in CONTAMINATION_PATTERNS:
        if pattern in body:
            # 找到位置，确认不是标题页
            idx = body.find(pattern)
            context = body[max(0, idx-50):idx+50]
            t.fail(f"发现污染内容 '{pattern}'，上下文: {context!r}")
            break
    
    return t


def test_key_content(year: int) -> TestResult:
    """验证关键段落存在"""
    t = TestResult(f"关键内容 [{year}]")
    path = f"{LETTERS_DIR}/{year}.md"
    if not os.path.exists(path):
        return t
    
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # 去掉 frontmatter
    body_start = content.find('\n---\n\n')
    body = content[body_start + 5:] if body_start >= 0 else content
    
    # 每个 letter 都应该有 "Berkshire" 和 "shareholders"
    if 'Berkshire' not in body:
        t.fail("缺少 'Berkshire'")
    if len(body) < 5000:
        t.fail(f"内容过短: {len(body)} chars")
    
    return t


def run_tests():
    """运行全部测试"""
    print("=" * 60)
    print("  Buffett Letter 自测系统")
    print("=" * 60)
    print()
    
    all_results = {}
    total_pass = 0
    total_fail = 0
    
    for year in YEARS:
        tests = [
            lambda y=year: test_file_exists(y),
            lambda y=year: test_file_size(y),
            lambda y=year: test_frontmatter(y),
            lambda y=year: test_start_content(y),
            lambda y=year: test_end_content(y),
            lambda y=year: test_no_contamination(y),
            lambda y=year: test_key_content(y),
        ]
        
        results = []
        for test_fn in tests:
            results.append(test_fn())
        
        all_results[year] = results
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        total_pass += passed
        total_fail += failed
        
        status = "✅ PASS" if failed == 0 else f"❌ FAIL ({failed}/{len(results)})"
        print(f"  {year}: {status}")
        
        if failed > 0:
            for r in results:
                if not r.passed:
                    for err in r.errors:
                        print(f"       - {err}")
    
    print()
    print("=" * 60)
    print(f"  汇总: {total_pass} 通过 / {total_fail} 失败")
    print("=" * 60)
    
    # 返回退出码
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
