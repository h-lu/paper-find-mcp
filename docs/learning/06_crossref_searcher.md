# CrossRefSearcher 详解

> **文件位置**: `paper_search_mcp/academic_platforms/crossref.py`  
> **难度**: ⭐⭐⭐ (中级)  
> **特点**: 展示如何与大型引用数据库交互

---

## 概述

`CrossRefSearcher` 展示了如何与 **CrossRef** 这个全球最大的引用数据库交互。它是一个典型的"只读"搜索器：只能搜索元数据，不能下载全文。

---

## CrossRef 简介

**CrossRef** 是一个学术基础设施组织：
- 管理 DOI（数字对象标识符）系统
- 包含 1.4 亿+ 学术记录
- 提供免费的 REST API
- 不提供全文，只提供元数据

---

## 完整代码分析

### 1. 礼貌的 API 使用

```python
class CrossRefSearcher(PaperSource):
    """Searcher for CrossRef database papers"""
    
    BASE_URL = "https://api.crossref.org"
    
    # CrossRef 礼仪建议：提供联系方式
    # 这样 CrossRef 可以在有问题时联系你
    USER_AGENT = (
        "paper-search-mcp/0.1.3 "
        "(https://github.com/Dragonatorul/paper-search-mcp; "
        "mailto:paper-search@example.org)"
    )
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.USER_AGENT,
            'Accept': 'application/json'
        })
```

**💡 学习要点**：

**Polite Pool**: CrossRef 有两个访问池：
- **普通池**: 较低速率限制
- **礼貌池**: 提供 `mailto` 参数可获得更高限制

---

### 2. 搜索实现

```python
def search(self, query: str, max_results: int = 10, **kwargs) -> List[Paper]:
    """Search CrossRef database for papers.
    
    Args:
        query: 搜索查询
        max_results: 最大结果数（最多 1000）
        **kwargs: 额外参数
            - filter: 过滤器字符串
            - sort: 排序字段
            - order: 排序顺序
    """
    try:
        params = {
            'query': query,
            'rows': min(max_results, 1000),  # CrossRef 最大 1000
            'sort': 'relevance',
            'order': 'desc'
        }
        
        # 添加额外参数
        if 'filter' in kwargs:
            params['filter'] = kwargs['filter']
        if 'sort' in kwargs:
            params['sort'] = kwargs['sort']
        if 'order' in kwargs:
            params['order'] = kwargs['order']
            
        # 添加 mailto 进入礼貌池
        params['mailto'] = 'paper-search@example.org'
        
        url = f"{self.BASE_URL}/works"
        response = self.session.get(url, params=params, timeout=30)
        
        # 处理速率限制
        if response.status_code == 429:
            logger.warning("Rate limited, waiting 2 seconds...")
            time.sleep(2)
            response = self.session.get(url, params=params, timeout=30)
        
        response.raise_for_status()
        data = response.json()
        
        # CrossRef 响应格式：
        # {"message": {"items": [...], "total-results": 12345}}
        papers = []
        items = data.get('message', {}).get('items', [])
        
        for item in items:
            try:
                paper = self._parse_crossref_item(item)
                if paper:
                    papers.append(paper)
            except Exception as e:
                logger.warning(f"Error parsing item: {e}")
                continue
                
        return papers
        
    except requests.RequestException as e:
        logger.error(f"Error searching CrossRef: {e}")
        return []
```

---

### 3. 复杂的数据解析

CrossRef 的数据结构比较复杂，需要很多辅助方法：

```python
def _parse_crossref_item(self, item: Dict[str, Any]) -> Optional[Paper]:
    """Parse a CrossRef API item into a Paper object."""
    try:
        # 基本信息
        doi = item.get('DOI', '')
        title = self._extract_title(item)
        authors = self._extract_authors(item)
        abstract = item.get('abstract', '')
        
        # 日期解析（复杂！）
        published_date = self._extract_date(item, 'published')
        if not published_date:
            published_date = self._extract_date(item, 'issued')
        if not published_date:
            published_date = self._extract_date(item, 'created')
        if not published_date:
            published_date = datetime(1970, 1, 1)  # Unix 纪元
        
        # URL
        url = item.get('URL', f"https://doi.org/{doi}" if doi else '')
        pdf_url = self._extract_pdf_url(item)
        
        # 额外元数据
        container_title = self._extract_container_title(item)
        publisher = item.get('publisher', '')
        categories = [item.get('type', '')]
        
        subjects = item.get('subject', [])
        keywords = subjects if isinstance(subjects, list) else []
        
        return Paper(
            paper_id=doi,
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            published_date=published_date,
            pdf_url=pdf_url,
            url=url,
            source='crossref',
            categories=categories,
            keywords=keywords,
            citations=item.get('is-referenced-by-count', 0),
            extra={
                'publisher': publisher,
                'container_title': container_title,
                'volume': item.get('volume', ''),
                'issue': item.get('issue', ''),
                'page': item.get('page', ''),
                'issn': item.get('ISSN', []),
                'isbn': item.get('ISBN', []),
                'crossref_type': item.get('type', ''),
                'member': item.get('member', ''),
                'prefix': item.get('prefix', '')
            }
        )
        
    except Exception as e:
        logger.error(f"Error parsing CrossRef item: {e}")
        return None
```

---

### 4. 辅助解析方法

```python
def _extract_title(self, item: Dict[str, Any]) -> str:
    """Extract title from CrossRef item.
    
    CrossRef 的 title 是一个列表！
    """
    titles = item.get('title', [])
    if isinstance(titles, list) and titles:
        return titles[0]
    return str(titles) if titles else ''


def _extract_authors(self, item: Dict[str, Any]) -> List[str]:
    """Extract author names from CrossRef item.
    
    作者格式：[{"given": "John", "family": "Doe"}, ...]
    """
    authors = []
    author_list = item.get('author', [])
    
    for author in author_list:
        if isinstance(author, dict):
            given = author.get('given', '')
            family = author.get('family', '')
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)
            elif given:
                authors.append(given)
                
    return authors


def _extract_date(self, item: Dict[str, Any], date_field: str) -> Optional[datetime]:
    """Extract date from CrossRef item.
    
    CrossRef 日期格式非常复杂：
    {"published": {"date-parts": [[2023, 5, 15]]}}
    
    date-parts 可能只有年份，或年月，或完整日期
    """
    date_info = item.get(date_field, {})
    if not date_info:
        return None
        
    date_parts = date_info.get('date-parts', [])
    if not date_parts or not date_parts[0]:
        return None
        
    parts = date_parts[0]
    try:
        year = parts[0] if len(parts) > 0 else 1970
        month = parts[1] if len(parts) > 1 else 1
        day = parts[2] if len(parts) > 2 else 1
        return datetime(year, month, day)
    except (ValueError, IndexError):
        return None


def _extract_container_title(self, item: Dict[str, Any]) -> str:
    """Extract container title (journal/book title)."""
    container_titles = item.get('container-title', [])
    if isinstance(container_titles, list) and container_titles:
        return container_titles[0]
    return str(container_titles) if container_titles else ''


def _extract_pdf_url(self, item: Dict[str, Any]) -> str:
    """Extract PDF URL from CrossRef item.
    
    尝试从多个位置提取 PDF URL
    """
    # 检查 resource 字段
    resource = item.get('resource', {})
    if resource:
        primary = resource.get('primary', {})
        if primary and primary.get('URL', '').endswith('.pdf'):
            return primary['URL']
    
    # 检查 link 数组
    links = item.get('link', [])
    for link in links:
        if isinstance(link, dict):
            content_type = link.get('content-type', '')
            if 'pdf' in content_type.lower():
                return link.get('URL', '')
                
    return ''
```

---

### 5. DOI 精确查询

```python
def get_paper_by_doi(self, doi: str) -> Optional[Paper]:
    """Get a specific paper by DOI.
    
    这比搜索更精确：直接用 DOI 获取论文
    
    Args:
        doi: 如 "10.1038/nature12373"
    """
    try:
        url = f"{self.BASE_URL}/works/{doi}"
        params = {'mailto': 'paper-search@example.org'}
        
        response = self.session.get(url, params=params, timeout=30)
        
        if response.status_code == 404:
            logger.warning(f"DOI not found: {doi}")
            return None
            
        response.raise_for_status()
        data = response.json()
        
        item = data.get('message', {})
        return self._parse_crossref_item(item)
        
    except requests.RequestException as e:
        logger.error(f"Error fetching DOI {doi}: {e}")
        return None
```

---

### 6. 不支持的功能

```python
def download_pdf(self, paper_id: str, save_path: str) -> str:
    """CrossRef doesn't provide direct PDF downloads."""
    message = (
        "CrossRef does not provide direct PDF downloads. "
        "CrossRef is a citation database that provides metadata. "
        "To access the full text, please use the DOI or URL."
    )
    raise NotImplementedError(message)


def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
    """CrossRef doesn't provide direct paper content."""
    message = (
        "CrossRef papers cannot be read directly. "
        "Only metadata and abstracts are available. "
        "To access the full text, use the DOI or URL."
    )
    return message
```

---

## CrossRef 过滤器

CrossRef API 支持强大的过滤器：

```python
# 示例过滤器
filter_examples = {
    # 只有全文
    "has-full-text:true",
    
    # 从 2020 年开始
    "from-pub-date:2020",
    
    # 特定出版商
    "publisher-name:Elsevier",
    
    # 组合过滤器
    "has-full-text:true,from-pub-date:2020",
    
    # 特定 ISSN
    "issn:0028-0836",
}

# 使用方式
papers = searcher.search(
    "climate change", 
    filter="from-pub-date:2020,has-full-text:true"
)
```

---

## 值得学习的地方

### 1. 礼貌的 API 使用

```python
USER_AGENT = "app-name/version (url; mailto:email)"
params['mailto'] = 'email@example.org'
```

### 2. 复杂数据结构处理

CrossRef 的数据结构非常不规范，需要很多防御性编程：

```python
# 检查类型
if isinstance(titles, list) and titles:
    return titles[0]

# 多层嵌套
date_parts = date_info.get('date-parts', [])
if not date_parts or not date_parts[0]:
    return None
```

### 3. 丰富的元数据

`extra` 字段存储了很多有用的信息：

```python
extra = {
    'publisher': publisher,
    'container_title': container_title,  # 期刊名
    'volume': item.get('volume', ''),
    'issue': item.get('issue', ''),
    'page': item.get('page', ''),
    'issn': item.get('ISSN', []),
    'isbn': item.get('ISBN', []),
}
```

---

## 可以改进的地方

### 1. 添加更多搜索选项

```python
def search(
    self, 
    query: str, 
    max_results: int = 10,
    from_date: str = None,
    to_date: str = None,
    type: str = None,  # journal-article, book-chapter, etc.
    publisher: str = None,
    **kwargs
) -> List[Paper]:
    filters = []
    if from_date:
        filters.append(f"from-pub-date:{from_date}")
    if to_date:
        filters.append(f"until-pub-date:{to_date}")
    if type:
        filters.append(f"type:{type}")
    if publisher:
        filters.append(f"publisher-name:{publisher}")
    
    if filters:
        kwargs['filter'] = ','.join(filters)
    
    # ... rest of search
```

### 2. 分页支持

```python
def search_with_pagination(
    self, 
    query: str, 
    max_results: int = 100,
    cursor: str = "*"
) -> Tuple[List[Paper], str]:
    """返回结果和下一页游标"""
    params = {
        'query': query,
        'rows': min(max_results, 100),
        'cursor': cursor,
    }
    # ...
    next_cursor = data.get('message', {}).get('next-cursor')
    return papers, next_cursor
```

### 3. 缓存 DOI 查询

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_paper_by_doi(self, doi: str) -> Optional[Paper]:
    # ... 原有逻辑
```

---

## 总结

`CrossRefSearcher` 展示了：

| 特点 | 说明 |
|------|------|
| 礼貌 API 使用 | User-Agent 和 mailto |
| 复杂数据解析 | 多个辅助方法 |
| 丰富元数据 | extra 字段 |
| 优雅降级 | 不支持的功能返回友好信息 |
| DOI 查询 | 精确获取论文 |

这是处理复杂 API 响应的好例子！
