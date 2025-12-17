# PubMedSearcher 详解

> **文件位置**: `paper_search_mcp/academic_platforms/pubmed.py`  
> **难度**: ⭐⭐⭐ (中等)  
> **更新**: 2025年12月 - NCBI E-utilities 最佳实践

---

## 概述

`PubMedSearcher` 使用 NCBI E-utilities API 搜索 PubMed 数据库，展示了：

- API Key 支持（提升速率限制）
- 速率限制和重试机制
- Session 复用和连接优化
- 健壮的 XML 解析

### 2025 最佳实践

| 实践 | 说明 |
|------|------|
| API Key | 提升速率限制 3→10 req/s |
| tool/email 参数 | 便于 NCBI 联系 |
| Session 复用 | 减少连接开销 |
| 指数退避重试 | 处理 429 错误 |

---

## NCBI 速率限制

| 配置 | 速率限制 | 获取方式 |
|------|:--------:|----------|
| 无 API Key | 3 req/s | - |
| 有 API Key | 10 req/s | [NCBI Settings](https://www.ncbi.nlm.nih.gov/account/settings/) |

---

## 完整代码分析

### 1. 初始化和配置

```python
class PubMedSearcher(PaperSource):
    """PubMed 论文搜索器"""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    TOOL_NAME = "paper_search_mcp"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        # 从环境变量读取配置
        self.api_key = api_key or os.environ.get('NCBI_API_KEY', '')
        self.email = email or os.environ.get('NCBI_EMAIL', '')
        
        # Session 复用
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'{self.TOOL_NAME}/1.0'
        })
        
        # 速率限制
        self.rate_limit = 10 if self.api_key else 3
```

**💡 学习要点**：

1. **环境变量配置**: 敏感信息不硬编码
2. **Session 复用**: 提升连接性能
3. **动态速率限制**: 根据 API Key 调整

---

### 2. 基础参数（NCBI 推荐）

```python
def _get_base_params(self) -> dict:
    """获取所有请求的基础参数"""
    params = {
        'tool': self.TOOL_NAME,  # 工具标识
        'db': 'pubmed',
    }
    if self.email:
        params['email'] = self.email
    if self.api_key:
        params['api_key'] = self.api_key
    return params
```

NCBI 推荐设置 `tool` 和 `email` 参数，便于问题追踪。

---

### 3. 速率限制和重试

```python
def _rate_limit_wait(self):
    """速率限制等待"""
    min_interval = 1.0 / self.rate_limit
    elapsed = time.time() - self._last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    self._last_request_time = time.time()


def _make_request(self, url, params, retry_count=0):
    """发送请求，带重试机制"""
    self._rate_limit_wait()
    
    try:
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response
        
    except requests.exceptions.HTTPError as e:
        if response.status_code == 429 and retry_count < self.max_retries:
            # 指数退避重试
            wait_time = (2 ** retry_count) + 1
            logger.warning(f"Rate limited, retrying in {wait_time}s...")
            time.sleep(wait_time)
            return self._make_request(url, params, retry_count + 1)
        return None
```

**💡 指数退避公式**: `wait = 2^retry + 1` 秒

---

### 4. 搜索流程

```python
def search(self, query: str, max_results: int = 10) -> List[Paper]:
    # Step 1: ESearch - 获取 PMIDs
    search_params = {
        **self._get_base_params(),
        'term': query,
        'retmax': min(max_results, 10000),
        'retmode': 'xml'
    }
    search_response = self._make_request(self.SEARCH_URL, search_params)
    ids = [id_elem.text for id_elem in search_root.findall('.//Id')]
    
    # Step 2: EFetch - 获取论文详情
    fetch_params = {
        **self._get_base_params(),
        'id': ','.join(ids),
        'retmode': 'xml'
    }
    fetch_response = self._make_request(self.FETCH_URL, fetch_params)
    
    # Step 3: 解析 XML
    papers = []
    for article in fetch_root.findall('.//PubmedArticle'):
        paper = self._parse_article(article)
        if paper:
            papers.append(paper)
    
    return papers
```

---

### 5. XML 解析技巧

```python
def _parse_article(self, article: ET.Element) -> Optional[Paper]:
    # 安全获取文本
    pmid = self._get_text(article, './/PMID')
    title = self._get_text(article, './/ArticleTitle') or 'Untitled'
    
    # 处理多部分摘要
    abstract_parts = []
    for elem in article.findall('.//AbstractText'):
        label = elem.get('Label', '')
        text = elem.text or ''
        if label and text:
            abstract_parts.append(f"{label}: {text}")
        elif text:
            abstract_parts.append(text)
    abstract = ' '.join(abstract_parts)
    
    return Paper(
        paper_id=pmid,
        title=title,
        abstract=abstract,
        ...
    )


def _get_text(self, element, path) -> Optional[str]:
    """安全获取 XML 元素文本"""
    elem = element.find(path)
    return elem.text if elem is not None and elem.text else None
```

**💡 处理结构化摘要**: PubMed 论文的摘要可能分为多个部分（Background, Methods, Results, Conclusion）。

---

## 环境变量配置

```bash
# 设置 NCBI API Key（推荐）
export NCBI_API_KEY="your_api_key_here"

# 设置联系邮箱（推荐）
export NCBI_EMAIL="your_email@example.com"
```

---

## 使用示例

```python
from paper_search_mcp.academic_platforms.pubmed import PubMedSearcher

# 默认使用环境变量
searcher = PubMedSearcher()

# 或手动指定
searcher = PubMedSearcher(
    api_key="your_key",
    email="your@email.com"
)

# 搜索论文
papers = searcher.search("cancer treatment", max_results=10)

for paper in papers:
    print(f"{paper.title}")
    print(f"  DOI: {paper.doi}")
    print(f"  Keywords: {paper.keywords}")
```

---

## PubMed 查询语法

| 语法 | 示例 | 说明 |
|------|------|------|
| 标题搜索 | `cancer[Title]` | 标题包含 cancer |
| 作者搜索 | `Smith J[Author]` | 作者姓名 |
| 日期范围 | `2020:2024[dp]` | 发布日期范围 |
| MeSH 术语 | `diabetes[MeSH]` | 医学主题词 |
| 布尔运算 | `cancer AND therapy` | 组合查询 |

---

## 限制说明

| 功能 | 状态 | 说明 |
|------|:----:|------|
| 搜索 | ✅ | 完整支持 |
| 下载 PDF | ❌ | PubMed 不提供直接下载 |
| 读取全文 | ❌ | 只能获取摘要 |

如需全文，请：
1. 使用 DOI 访问出版商网站
2. 检查 PubMed Central (PMC) 是否有免费版本

---

## 参考资料

- [NCBI E-utilities 文档](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [PubMed 搜索语法](https://pubmed.ncbi.nlm.nih.gov/help/)
- [Biopython Entrez 教程](https://biopython.org/wiki/Documentation)
