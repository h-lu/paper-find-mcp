# SemanticSearcher 详解

> **文件位置**: `paper_search_mcp/academic_platforms/semantic.py`  
> **难度**: ⭐⭐⭐⭐ (进阶)  
> **更新**: 2025年12月 - API 最佳实践

---

## 概述

`SemanticSearcher` 使用 Semantic Scholar Academic Graph API 搜索学术论文，展示了：

- API Key 认证和速率限制处理
- 多种论文 ID 格式支持
- PDF 下载和文本提取
- 智能重试机制

### 2025 最佳实践

| 实践 | 说明 |
|------|------|
| API Key | 专用速率限制（1 RPS 起步） |
| 只请求必要字段 | 减少延迟和配额消耗 |
| 指数退避 + 抖动 | 避免重试风暴 |
| PyMuPDF4LLM | LLM 友好的 PDF 提取 |

---

## 速率限制

| 配置 | 速率限制 | 说明 |
|------|:--------:|------|
| 无 API Key | 共享池 | 5000 req/5min（与所有用户共享） |
| 有 API Key | 1 RPS | 专用配额，可申请提升 |

> [!TIP]
> 获取免费 API Key: https://www.semanticscholar.org/product/api

---

## 支持的论文 ID 格式

| 格式 | 示例 |
|------|------|
| Semantic Scholar ID | `649def34f8be52c8b66281af98ae884c09aef38b` |
| DOI | `DOI:10.18653/v1/N18-3011` |
| arXiv | `ARXIV:2106.15928` |
| PMID | `PMID:19872477` |
| ACL | `ACL:W12-3903` |
| URL | `URL:https://arxiv.org/abs/2106.15928` |

---

## 核心代码分析

### 1. 初始化和认证

```python
class SemanticSearcher(PaperSource):
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    # 只请求必要字段（减少延迟）
    DEFAULT_FIELDS = [
        "title", "abstract", "authors", "url",
        "publicationDate", "citationCount", 
        "externalIds", "fieldsOfStudy", "openAccessPdf"
    ]
    
    def __init__(self, api_key=None, timeout=30, max_retries=3):
        self.api_key = api_key or os.environ.get('SEMANTIC_SCHOLAR_API_KEY')
        
        # Session 复用
        self.session = requests.Session()
        if self.api_key:
            self.session.headers['x-api-key'] = self.api_key
```

---

### 2. 速率限制和重试

```python
def _make_request(self, endpoint, params, retry_count=0):
    self._rate_limit_wait()  # 主动限速
    
    try:
        response = self.session.get(url, params=params, timeout=self.timeout)
        
        if response.status_code == 429:
            if retry_count < self.max_retries:
                # 指数退避 + 随机抖动
                wait_time = (2 ** retry_count) + (time.time() % 1)
                time.sleep(wait_time)
                return self._make_request(endpoint, params, retry_count + 1)
        
        response.raise_for_status()
        return response
        
    except requests.exceptions.RequestException as e:
        # 网络错误也重试
        ...
```

**💡 为什么使用抖动?**

```
无抖动: 所有客户端同时重试 → 再次触发 429
有抖动: 客户端分散重试 → 减少冲突
```

---

### 3. PDF URL 提取

```python
def _extract_pdf_url(self, open_access_pdf: dict) -> str:
    """从 openAccessPdf 字段提取 URL"""
    if not open_access_pdf:
        return ""
    
    # 直接获取
    if open_access_pdf.get('url'):
        return open_access_pdf['url']
    
    # 从 disclaimer 中提取
    disclaimer = open_access_pdf.get('disclaimer', '')
    if disclaimer:
        # 正则匹配 URL
        matches = re.findall(r'https?://[^\s,)]+', disclaimer)
        if matches:
            # 转换 arXiv abs 链接为 PDF
            for url in matches:
                if 'arxiv.org/abs/' in url:
                    return url.replace('/abs/', '/pdf/') + '.pdf'
            return matches[0]
    
    return ""
```

---

### 4. PDF 提取（PyMuPDF4LLM）

```python
def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
    # 下载 PDF
    pdf_path = self.download_pdf(paper_id, save_path)
    
    # 使用 PyMuPDF4LLM（推荐）
    if HAS_PYMUPDF4LLM:
        text = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
    elif HAS_PYPDF2:
        # 回退到 PyPDF2
        reader = PdfReader(pdf_path)
        text = ...
    
    # 添加元数据
    metadata = f"# {paper.title}\n\n**Authors**: {authors}..."
    return metadata + text
```

---

## 环境变量配置

```bash
# 设置 API Key（强烈推荐）
export SEMANTIC_SCHOLAR_API_KEY="your_api_key_here"
```

---

## 使用示例

```python
from paper_search_mcp.academic_platforms.semantic import SemanticSearcher

searcher = SemanticSearcher()

# 搜索论文
papers = searcher.search("transformer attention", max_results=10)

# 按年份过滤
papers = searcher.search("BERT", year="2019-2023", max_results=5)

# 获取论文详情
paper = searcher.get_paper_details("ARXIV:1706.03762")
print(paper.title)  # "Attention Is All You Need"

# 下载并读取 PDF
text = searcher.read_paper("ARXIV:1706.03762")
```

---

## 与其他平台对比

| 功能 | Semantic Scholar | arXiv | PubMed |
|------|:----------------:|:-----:|:------:|
| 搜索 | ✅ | ✅ | ✅ |
| PDF 下载 | ✅ 开放获取 | ✅ 全部 | ❌ |
| 引用计数 | ✅ | ❌ | ❌ |
| 相关论文 | ✅ | ❌ | ❌ |
| 多 ID 格式 | ✅ | ❌ | ❌ |

---

## 参考资料

- [Semantic Scholar API 文档](https://api.semanticscholar.org/api-docs/)
- [API 使用最佳实践](https://www.semanticscholar.org/product/api)
- [获取 API Key](https://www.semanticscholar.org/product/api#api-key)
