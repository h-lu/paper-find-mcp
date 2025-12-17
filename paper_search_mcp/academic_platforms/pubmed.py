# paper_search_mcp/academic_platforms/pubmed.py
"""
PubMedSearcher - PubMed 论文搜索

2025 最佳实践版本：
- 支持 NCBI API Key（提升速率限制：3→10 req/s）
- 使用 tool/email 参数（便于 NCBI 联系）
- Session 复用提升性能
- 日志记录和错误处理
- 超时和重试机制
"""
from typing import List, Optional
import requests
from xml.etree import ElementTree as ET
from datetime import datetime
import os
import time
import logging

from ..paper import Paper

logger = logging.getLogger(__name__)


class PaperSource:
    """Abstract base class for paper sources"""
    def search(self, query: str, **kwargs) -> List[Paper]:
        raise NotImplementedError

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        raise NotImplementedError

    def read_paper(self, paper_id: str, save_path: str) -> str:
        raise NotImplementedError


class PubMedSearcher(PaperSource):
    """PubMed 论文搜索器
    
    使用 NCBI E-utilities API 搜索 PubMed 数据库。
    
    2025 最佳实践：
    - 支持 API Key 提升速率限制
    - 使用 requests.Session 复用连接
    - 自动重试和错误处理
    
    环境变量：
    - NCBI_API_KEY: NCBI API 密钥（可选，提升速率限制）
    - NCBI_EMAIL: 联系邮箱（推荐设置）
    
    获取 API Key: https://www.ncbi.nlm.nih.gov/account/settings/
    """
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    SEARCH_URL = f"{BASE_URL}/esearch.fcgi"
    FETCH_URL = f"{BASE_URL}/efetch.fcgi"
    
    # 工具标识（NCBI 推荐设置）
    TOOL_NAME = "paper_search_mcp"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """初始化 PubMed 搜索器
        
        Args:
            api_key: NCBI API Key（默认从环境变量 NCBI_API_KEY 获取）
            email: 联系邮箱（默认从环境变量 NCBI_EMAIL 获取）
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key or os.environ.get('NCBI_API_KEY', '')
        self.email = email or os.environ.get('NCBI_EMAIL', '')
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 复用 Session 提升性能
        self.session = requests.Session()
        
        # 设置 User-Agent
        self.session.headers.update({
            'User-Agent': f'{self.TOOL_NAME}/1.0 (Contact: {self.email})'
        })
        
        # 速率限制：无 API Key = 3/s，有 API Key = 10/s
        self.rate_limit = 10 if self.api_key else 3
        self._last_request_time = 0.0

    def _get_base_params(self) -> dict:
        """获取所有请求的基础参数（NCBI 推荐）"""
        params = {
            'tool': self.TOOL_NAME,
            'db': 'pubmed',
        }
        if self.email:
            params['email'] = self.email
        if self.api_key:
            params['api_key'] = self.api_key
        return params

    def _rate_limit_wait(self):
        """速率限制等待"""
        min_interval = 1.0 / self.rate_limit
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _make_request(
        self, 
        url: str, 
        params: dict,
        retry_count: int = 0
    ) -> Optional[requests.Response]:
        """发送请求，带重试机制
        
        Args:
            url: 请求 URL
            params: 请求参数
            retry_count: 当前重试次数
            
        Returns:
            Response 对象或 None
        """
        self._rate_limit_wait()
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response
            
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429 and retry_count < self.max_retries:
                # 速率限制，指数退避重试
                wait_time = (2 ** retry_count) + 1
                logger.warning(f"Rate limited, retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(url, params, retry_count + 1)
            logger.error(f"HTTP error: {e}")
            return None
            
        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
                return self._make_request(url, params, retry_count + 1)
            logger.error(f"Request failed after {self.max_retries} retries: {e}")
            return None

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """搜索 PubMed 论文
        
        Args:
            query: 搜索关键词，支持 PubMed 查询语法
                   例如: "cancer[Title]", "Smith J[Author]"
            max_results: 最大返回数量（上限 10000）
            
        Returns:
            List[Paper]: 论文列表
        """
        # Step 1: 搜索获取 PMIDs
        search_params = {
            **self._get_base_params(),
            'term': query,
            'retmax': min(max_results, 10000),  # NCBI 限制
            'retmode': 'xml'
        }
        
        search_response = self._make_request(self.SEARCH_URL, search_params)
        if not search_response:
            return []
        
        try:
            search_root = ET.fromstring(search_response.content)
            ids = [id_elem.text for id_elem in search_root.findall('.//Id')]
        except ET.ParseError as e:
            logger.error(f"Failed to parse search response: {e}")
            return []
        
        if not ids:
            logger.info(f"No results found for query: {query}")
            return []
        
        # Step 2: 获取论文详情
        fetch_params = {
            **self._get_base_params(),
            'id': ','.join(ids),
            'retmode': 'xml'
        }
        
        fetch_response = self._make_request(self.FETCH_URL, fetch_params)
        if not fetch_response:
            return []
        
        try:
            fetch_root = ET.fromstring(fetch_response.content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse fetch response: {e}")
            return []
        
        # Step 3: 解析论文数据
        papers = []
        for article in fetch_root.findall('.//PubmedArticle'):
            paper = self._parse_article(article)
            if paper:
                papers.append(paper)
        
        logger.info(f"Found {len(papers)} papers for query: {query}")
        return papers

    def _parse_article(self, article: ET.Element) -> Optional[Paper]:
        """解析单篇论文 XML
        
        Args:
            article: PubmedArticle XML 元素
            
        Returns:
            Paper 对象或 None
        """
        try:
            # 基础字段
            pmid = self._get_text(article, './/PMID')
            if not pmid:
                return None
            
            title = self._get_text(article, './/ArticleTitle') or 'Untitled'
            
            # 作者
            authors = []
            for author in article.findall('.//Author'):
                last_name = self._get_text(author, 'LastName')
                initials = self._get_text(author, 'Initials')
                if last_name:
                    name = f"{last_name} {initials}" if initials else last_name
                    authors.append(name)
            
            # 摘要（可能有多个部分）
            abstract_parts = []
            for abstract_elem in article.findall('.//AbstractText'):
                label = abstract_elem.get('Label', '')
                text = abstract_elem.text or ''
                if label and text:
                    abstract_parts.append(f"{label}: {text}")
                elif text:
                    abstract_parts.append(text)
            abstract = ' '.join(abstract_parts)
            
            # 日期
            published_date = self._parse_date(article)
            
            # DOI
            doi = self._get_text(article, './/ELocationID[@EIdType="doi"]') or ''
            
            # 关键词
            keywords = [
                kw.text for kw in article.findall('.//Keyword')
                if kw.text
            ]
            
            return Paper(
                paper_id=pmid,
                title=title,
                authors=authors,
                abstract=abstract,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                pdf_url='',  # PubMed 不提供直接 PDF
                published_date=published_date,
                source='pubmed',
                keywords=keywords,
                doi=doi
            )
            
        except Exception as e:
            logger.warning(f"Error parsing article: {e}")
            return None

    def _get_text(self, element: ET.Element, path: str) -> Optional[str]:
        """安全获取 XML 元素文本"""
        elem = element.find(path)
        return elem.text if elem is not None and elem.text else None

    def _parse_date(self, article: ET.Element) -> Optional[datetime]:
        """解析发布日期"""
        # 尝试多个日期路径
        date_paths = [
            './/PubDate',
            './/ArticleDate',
            './/DateCompleted'
        ]
        
        for path in date_paths:
            date_elem = article.find(path)
            if date_elem is not None:
                year = self._get_text(date_elem, 'Year')
                month = self._get_text(date_elem, 'Month') or '01'
                day = self._get_text(date_elem, 'Day') or '01'
                
                if year:
                    try:
                        # 处理月份可能是文字（如 "Jan"）
                        if not month.isdigit():
                            month_map = {
                                'jan': '01', 'feb': '02', 'mar': '03',
                                'apr': '04', 'may': '05', 'jun': '06',
                                'jul': '07', 'aug': '08', 'sep': '09',
                                'oct': '10', 'nov': '11', 'dec': '12'
                            }
                            month = month_map.get(month.lower()[:3], '01')
                        
                        return datetime(int(year), int(month), int(day))
                    except (ValueError, TypeError):
                        try:
                            return datetime(int(year), 1, 1)
                        except (ValueError, TypeError):
                            pass
        return None

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """尝试下载 PubMed 论文 PDF（不支持）

        PubMed 是索引数据库，不提供直接 PDF 下载。
        请使用 DOI 或 PubMed Central 获取全文。
        
        Raises:
            NotImplementedError: 始终抛出
        """
        raise NotImplementedError(
            "PubMed does not provide direct PDF downloads. "
            "Please use the paper's DOI to access the publisher's website, "
            "or check if the paper is available on PubMed Central (PMC)."
        )

    def read_paper(self, paper_id: str, save_path: str = "./downloads") -> str:
        """尝试读取 PubMed 论文（不支持）
        
        Returns:
            str: 说明信息
        """
        return (
            "PubMed papers cannot be read directly through this tool. "
            "Only metadata and abstracts are available through PubMed's API. "
            "Please use the paper's DOI to access the full text, "
            "or check if the paper is available on PubMed Central (PMC)."
        )


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    searcher = PubMedSearcher()
    
    # 显示配置信息
    print("=" * 60)
    print("PubMedSearcher Configuration")
    print("=" * 60)
    print(f"API Key: {'Configured' if searcher.api_key else 'Not set (3 req/s limit)'}")
    print(f"Email: {searcher.email or 'Not set'}")
    print(f"Rate limit: {searcher.rate_limit} requests/second")
    
    # 测试搜索功能
    print("\n" + "=" * 60)
    print("1. Testing search functionality...")
    print("=" * 60)
    
    query = "machine learning"
    max_results = 3
    papers = []
    
    try:
        papers = searcher.search(query, max_results=max_results)
        print(f"Found {len(papers)} papers for query '{query}':")
        for i, paper in enumerate(papers, 1):
            print(f"\n{i}. {paper.title[:60]}...")
            print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            print(f"   DOI: {paper.doi or 'N/A'}")
            print(f"   URL: {paper.url}")
            if paper.keywords:
                print(f"   Keywords: {', '.join(paper.keywords[:5])}")
    except Exception as e:
        print(f"Error during search: {e}")
    
    # 测试 PDF 下载（预期失败）
    if papers:
        print("\n" + "=" * 60)
        print("2. Testing PDF download (expected to fail)...")
        print("=" * 60)
        
        try:
            searcher.download_pdf(papers[0].paper_id, "./downloads")
        except NotImplementedError as e:
            print(f"Expected: {e}")
    
    # 测试论文阅读
    if papers:
        print("\n" + "=" * 60)
        print("3. Testing paper reading...")
        print("=" * 60)
        
        message = searcher.read_paper(papers[0].paper_id)
        print(f"Response: {message}")
    
    print("\n✅ All tests completed!")