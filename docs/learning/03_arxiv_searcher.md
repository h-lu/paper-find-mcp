# ArxivSearcher 详解

> **文件位置**: `paper_search_mcp/academic_platforms/arxiv.py`  
> **难度**: ⭐⭐ (适合入门)  
> **更新**: 2025年12月 - 使用 PyMuPDF4LLM 替代 PyPDF2

---

## 概述

`ArxivSearcher` 是一个完整的学术平台搜索器实现，展示了：

- 如何调用 arXiv API
- 如何解析 Atom/RSS 格式的响应
- **如何使用 PyMuPDF4LLM 进行高质量 PDF 文本提取**（2025 最佳实践）
- 如何生成 LLM 友好的 Markdown 输出

---

## 2025 最佳实践更新

### 为什么从 PyPDF2 迁移到 PyMuPDF4LLM？

| 特性 | PyPDF2 (旧) | PyMuPDF4LLM (新) |
|------|:-----------:|:----------------:|
| 表格提取 | ⭐ 差 | ⭐⭐⭐⭐⭐ 优秀 |
| 数学公式 | ⭐ 乱码 | ⭐⭐⭐ 可读 |
| Markdown 输出 | ❌ 不支持 | ✅ 原生支持 |
| LLM 友好度 | ⭐ 低 | ⭐⭐⭐⭐⭐ 高 |
| 速度 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 快 |

### PyMuPDF4LLM 特点

```python
import pymupdf4llm

# 一行代码提取 Markdown 格式内容
md_text = pymupdf4llm.to_markdown("paper.pdf")

# 支持表格检测策略
md_text = pymupdf4llm.to_markdown(
    "paper.pdf",
    table_strategy="lines_strict"  # 严格表格检测
)
```

---

## 完整代码分析

### 1. 导入和配置

```python
# paper_search_mcp/academic_platforms/arxiv.py
"""
ArxivSearcher - arXiv 论文搜索、下载与阅读

2025 年最佳实践版本：
- 使用 PyMuPDF4LLM 替代 PyPDF2，提供更好的表格和公式提取
- 输出 Markdown 格式，对 LLM 更友好
- 支持多种表格检测策略
"""
from typing import List, Literal, Optional
from datetime import datetime
import requests
import feedparser
import pymupdf4llm    # 2025 最佳实践：专为 LLM 优化的 PDF 提取
import pymupdf        # 底层 PDF 库，用于备用文本提取
import os
import logging

from ..paper import Paper

logger = logging.getLogger(__name__)
```

**💡 学习要点**：

1. **模块文档字符串**: 简要说明模块功能和版本特点
2. **类型提示**: 使用 `Literal` 限定参数取值范围
3. **日志**: 使用 `logging` 而不是 `print`

---

### 2. 表格检测策略

```python
class ArxivSearcher(PaperSource):
    """arXiv 论文搜索器"""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    # 表格检测策略说明
    TABLE_STRATEGIES = {
        "lines_strict": "严格模式：只检测有完整边框线的表格",
        "lines": "线条模式：检测有部分边框线的表格",
        "text": "文本模式：基于文本对齐检测表格（适合无边框表格）",
        "explicit": "显式模式：只检测 PDF 中明确标记的表格",
    }
```

**💡 如何选择表格策略**：

| 策略 | 适用场景 | 准确度 | 速度 |
|------|---------|:------:|:----:|
| `lines_strict` | 有完整边框的表格 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| `lines` | 有部分边框的表格 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| `text` | 无边框的对齐文本 | ⭐⭐⭐ | ⭐⭐⭐ |
| `explicit` | PDF 明确标记的表格 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

### 3. 搜索功能

```python
def search(self, query: str, max_results: int = 10) -> List[Paper]:
    """搜索 arXiv 论文
    
    Args:
        query: 搜索关键词，支持 arXiv 查询语法
               例如: "ti:attention" (标题), "au:hinton" (作者)
        max_results: 最大返回数量
        
    Returns:
        List[Paper]: 论文列表
    """
    params = {
        'search_query': query,
        'max_results': max_results,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending'
    }
    
    try:
        # 添加超时防止阻塞
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()  # 检查 HTTP 状态码
    except requests.RequestException as e:
        logger.error(f"arXiv API request failed: {e}")
        return []  # 返回空列表而不是抛出异常
    
    feed = feedparser.parse(response.content)
    papers = []
    
    for entry in feed.entries:
        try:
            # 清理标题和摘要中的换行符
            papers.append(Paper(
                paper_id=entry.id.split('/')[-1],
                title=entry.title.replace('\n', ' ').strip(),
                abstract=entry.summary.replace('\n', ' ').strip(),
                # ... 其他字段
            ))
        except Exception as e:
            logger.warning(f"Error parsing arXiv entry: {e}")
            
    return papers
```

**💡 改进点**：
- 添加了 `timeout=30` 防止网络阻塞
- 使用 `raise_for_status()` 检查 HTTP 状态码
- 清理文本中的换行符

---

### 4. 下载功能

```python
def download_pdf(self, paper_id: str, save_path: str = "./downloads") -> str:
    """下载 arXiv 论文 PDF
    
    改进：
    - 自动创建目录
    - 检查文件是否已存在（避免重复下载）
    - 处理特殊文件名（斜杠、冒号等）
    """
    # 确保目录存在
    os.makedirs(save_path, exist_ok=True)
    
    # 处理带版本号的 ID (例如 2106.12345v2)
    safe_id = paper_id.replace('/', '_').replace(':', '_')
    output_file = os.path.join(save_path, f"{safe_id}.pdf")
    
    # 检查文件是否已存在
    if os.path.exists(output_file):
        logger.info(f"PDF already exists: {output_file}")
        return output_file
    
    # 下载 PDF
    pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
    
    try:
        response = requests.get(pdf_url, timeout=60)
        response.raise_for_status()
        
        with open(output_file, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"PDF downloaded: {output_file}")
        return output_file
        
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download PDF: {e}")
```

---

### 5. 核心：read_paper() 方法

```python
def read_paper(
    self, 
    paper_id: str, 
    save_path: str = "./downloads",
    output_format: Literal["markdown", "text"] = "markdown",
    table_strategy: Literal["lines_strict", "lines", "text", "explicit"] = "lines_strict",
    pages: Optional[List[int]] = None
) -> str:
    """读取论文并提取内容
    
    使用 PyMuPDF4LLM 进行高质量文本提取，支持：
    - Markdown 格式输出（推荐，对 LLM 友好）
    - 表格自动转换为 Markdown 表格
    - 多种表格检测策略
    
    Args:
        paper_id: arXiv 论文 ID
        save_path: PDF 存储目录
        output_format: 输出格式
            - "markdown": Markdown 格式（推荐，包含表格）
            - "text": 纯文本格式
        table_strategy: 表格检测策略
        pages: 要提取的页面列表（0-indexed），None 表示全部页面
        
    Returns:
        str: 提取的论文内容
    """
    # 确保 PDF 已下载
    pdf_path = self._ensure_pdf_downloaded(paper_id, save_path)
    
    if output_format == "markdown":
        return self._extract_markdown(pdf_path, table_strategy, pages)
    else:
        return self._extract_text(pdf_path, pages)
```

**💡 设计模式**：
- 使用 `Literal` 类型提示限定参数取值
- 分离下载和提取逻辑
- 支持两种输出格式

---

### 6. Markdown 提取实现

```python
def _extract_markdown(
    self, 
    pdf_path: str, 
    table_strategy: str,
    pages: Optional[List[int]] = None
) -> str:
    """使用 PyMuPDF4LLM 提取 Markdown 格式内容
    
    PyMuPDF4LLM 特点：
    - 专为 LLM 优化的输出格式
    - 自动检测并格式化表格
    - 保留文档结构（标题、列表等）
    """
    try:
        md_text = pymupdf4llm.to_markdown(
            pdf_path,
            pages=pages,
            table_strategy=table_strategy,
            show_progress=False  # 静默模式
        )
        return md_text
    except Exception as e:
        logger.error(f"Markdown extraction failed: {e}")
        # 回退到纯文本提取
        logger.info("Falling back to plain text extraction")
        return self._extract_text(pdf_path, pages)
```

**💡 学习要点**：
- 优雅降级：Markdown 提取失败时回退到纯文本
- 静默模式：`show_progress=False` 避免输出进度条

---

### 7. 纯文本提取（备用）

```python
def _extract_text(
    self, 
    pdf_path: str, 
    pages: Optional[List[int]] = None
) -> str:
    """使用 PyMuPDF 提取纯文本内容"""
    try:
        doc = pymupdf.open(pdf_path)
        text_parts = []
        
        page_range = pages if pages else range(len(doc))
        
        for page_num in page_range:
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                text_parts.append(page.get_text())
        
        doc.close()
        return "\n".join(text_parts)
        
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        return f"Error extracting text: {e}"
```

---

## 输出示例对比

### PyPDF2 (旧) 输出

```
Table 1: Results
Model Accuracy F1
BERT 0.89 0.87
GPT 0.92 0.90
```

表格结构完全丢失！

### PyMuPDF4LLM (新) 输出

```markdown
**Table 1: Results**

| Model | Accuracy | F1 |
|-------|----------|-----|
| BERT  | 0.89     | 0.87 |
| GPT   | 0.92     | 0.90 |
```

表格结构完美保留！

---

## 使用示例

```python
from paper_search_mcp.academic_platforms.arxiv import ArxivSearcher

searcher = ArxivSearcher()

# 搜索论文
papers = searcher.search("attention mechanism", max_results=5)

# 下载并读取（Markdown 格式）
content = searcher.read_paper(
    papers[0].paper_id,
    output_format="markdown",
    table_strategy="lines_strict"
)

# 只提取前两页
content = searcher.read_paper(
    papers[0].paper_id,
    pages=[0, 1]
)
```

---

## 可以继续改进的地方

### 1. 添加数学公式转 LaTeX

如果需要完美的数学公式转换，可以考虑添加 `marker-pdf`：

```python
# 安装: pip install marker-pdf

# 使用 marker 转换（速度较慢但公式更准确）
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

converter = PdfConverter(artifact_dict=create_model_dict())
result = converter("paper.pdf")
```

### 2. 添加缓存

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def read_paper_cached(self, paper_id: str, output_format: str) -> str:
    return self.read_paper(paper_id, output_format=output_format)
```

### 3. 异步下载

```python
import aiohttp
import asyncio

async def download_pdf_async(self, paper_id: str, save_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://arxiv.org/pdf/{paper_id}.pdf") as response:
            content = await response.read()
            # ...
```

---

## 依赖要求

```toml
# pyproject.toml
dependencies = [
    "pymupdf4llm>=0.2.0",  # 替代 PyPDF2
    "requests",
    "feedparser",
    # ...
]
```

---

## 总结

更新后的 `ArxivSearcher` 体现了 2025 年 PDF 提取最佳实践：

| 改进 | 效果 |
|------|------|
| PyMuPDF4LLM | 高质量 Markdown 输出 |
| 表格策略 | 灵活的表格检测 |
| 优雅降级 | 失败时自动回退 |
| 类型提示 | 更好的代码提示 |
| 日志记录 | 便于调试 |

这是一个生产级别的 PDF 提取实现！
