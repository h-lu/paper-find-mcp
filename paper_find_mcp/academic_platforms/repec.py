# paper_search_mcp/academic_platforms/repec.py
"""
RePECSearcher - RePEc/IDEAS 经济学论文搜索

通过网页抓取 IDEAS 前端 (ideas.repec.org) 搜索经济学论文。
RePEc (Research Papers in Economics) 是最大的开放经济学文献库。

特点：
- 覆盖工作论文 (NBER, 央行等)、期刊文章、书籍
- 支持 JEL 分类代码
- 支持年份范围过滤
"""
from typing import List, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import time
import random
import re
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


class RePECSearcher(PaperSource):
    """RePEc/IDEAS 经济学论文搜索器
    
    通过网页抓取 IDEAS 前端进行搜索。
    
    搜索类型：
    - Working Papers (工作论文): NBER, 央行, 研究机构
    - Journal Articles (期刊文章): AER, JPE 等顶级经济学期刊
    - Books/Chapters (书籍/章节)
    
    Example:
        >>> searcher = RePECSearcher()
        >>> papers = searcher.search("machine learning economics", max_results=5)
        >>> for paper in papers:
        ...     print(paper.title)
    """
    
    # IDEAS 搜索 URL (使用 htsearch2 POST 端点)
    SEARCH_URL = "https://ideas.repec.org/cgi-bin/htsearch2"
    
    # 搜索字段选项 (wf 参数)
    SEARCH_FIELDS = {
        'all': '4BFF',       # Whole record (默认)
        'abstract': 'F000',  # 仅摘要
        'keywords': '0F00',  # 仅关键词
        'title': '00F0',     # 仅标题
        'author': '000F',    # 仅作者
    }
    
    # 排序选项 (s 参数)
    SORT_OPTIONS = {
        'relevance': 'R',        # 相关性 (默认)
        'newest': 'D',           # 最新发布
        'oldest': 'd',           # 最早发布
        'citations': 'C',         # 被引用最多
        'title': 'T',            # 标题字母序
        'recent_added': 'A',     # 最近添加到 RePEc
        'recent_relevant': 'S',  # 最新且相关
        'relevant_cited': 'Q',   # 相关且被引用
        'recent_cited': 'B',     # 最新且被引用
    }
    
    # 文档类型选项 (ul 参数)
    DOC_TYPES = {
        'all': '',           # 所有类型 (默认)
        'articles': '%/a/%', # 期刊文章
        'papers': '%/p/%',   # 工作论文
        'chapters': '%/h/%', # 书籍章节
        'books': '%/b/%',    # 书籍
        'software': '%/c/%', # 软件组件
    }
    
    # 研究机构/期刊系列 (ul 参数，用于限制搜索范围)
    # 格式: publisher/series
    SERIES = {
        # === 顶级研究机构 ===
        'nber': 'nbr/nberwo',           # NBER 工作论文
        'imf': 'imf/imfwpa',            # IMF 工作论文
        'worldbank': 'wbk/wbrwps',      # 世界银行政策研究
        'ecb': 'ecb/ecbwps',            # 欧洲央行
        'bis': 'bis/biswps',            # 国际清算银行
        'cepr': 'cpr/ceprdp',           # CEPR 讨论论文
        'iza': 'iza/izadps',            # IZA 劳动经济学
        
        # === 美联储系统 ===
        'fed': 'fip/fedgfe',            # 美联储理事会
        'fed_ny': 'fip/fednsr',         # 纽约联储
        'fed_chicago': 'fip/fedhwp',    # 芝加哥联储
        'fed_stlouis': 'fip/fedlwp',    # 圣路易斯联储
        'fed_minneapolis': 'fip/fedmwp',# 明尼阿波利斯联储
        'fed_sf': 'fip/fedfcw',         # 旧金山联储
        
        # === 顶级经济学期刊 (Top 5) ===
        'aer': 'aea/aecrev',            # American Economic Review
        'jpe': 'ucp/jpolec',            # Journal of Political Economy
        'qje': 'oup/qjecon',            # Quarterly Journal of Economics
        'econometrica': 'wly/emetrp',   # Econometrica
        'restud': 'oup/restud',         # Review of Economic Studies
        
        # === 其他重要期刊 ===
        'jfe': 'eee/jfinec',            # Journal of Financial Economics
        'jme': 'eee/moneco',            # Journal of Monetary Economics
        'jeea': 'oup/jeurec',           # J of European Economic Association
        'aej_macro': 'aea/aejmac',      # AEJ: Macroeconomics
        'aej_micro': 'aea/aejmic',      # AEJ: Microeconomics
        'aej_applied': 'aea/aejapp',    # AEJ: Applied Economics
        'aej_policy': 'aea/aejpol',     # AEJ: Economic Policy
    }
    
    # User-Agent 轮换
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    def __init__(self, timeout: int = 30):
        """初始化 RePEc 搜索器
        
        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self._setup_session()
    
    def _setup_session(self):
        """设置 HTTP Session"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })
    
    def _extract_repec_handle(self, url: str) -> str:
        """从 URL 提取 RePEc handle 作为 paper_id
        
        Args:
            url: 论文页面 URL (e.g., https://ideas.repec.org/p/nbr/nberwo/32000.html)
            
        Returns:
            RePEc handle (e.g., RePEc:nbr:nberwo:32000)
        """
        # URL 格式: /p/publisher/series/id.html 或 /a/publisher/journal/vXyY/id.html
        match = re.search(r'ideas\.repec\.org/([pahbc])/([^/]+)/([^/]+)/([^/]+)\.html', url)
        if match:
            doc_type, publisher, series, paper_id = match.groups()
            return f"RePEc:{publisher}:{series}:{paper_id}"
        
        # 回退：使用 URL hash
        return f"repec_{hash(url)}"
    
    def _extract_year(self, text: str) -> Optional[int]:
        """从文本中提取年份
        
        Args:
            text: 包含年份的文本
            
        Returns:
            年份或 None
        """
        # 匹配常见年份格式
        match = re.search(r'\b(19|20)\d{2}\b', text)
        if match:
            year = int(match.group())
            if 1900 <= year <= datetime.now().year:
                return year
        return None
    
    def _is_paper_url(self, url: str) -> bool:
        """检查 URL 是否为论文链接
        
        Args:
            url: URL 字符串
            
        Returns:
            是否为论文链接
        """
        # 论文链接格式: /p/ (working paper), /a/ (article), /h/ (chapter), /b/ (book)
        if not url:
            return False
        return any(f'/{t}/' in url for t in ['p', 'a', 'h', 'b']) and 'ideas.repec.org' in url
    
    def _parse_paper_link(self, link_elem, soup) -> Optional[Paper]:
        """解析论文链接元素
        
        Args:
            link_elem: BeautifulSoup 链接元素
            soup: 整个页面的 BeautifulSoup 对象
            
        Returns:
            Paper 对象或 None
        """
        try:
            url = link_elem.get('href', '')
            title = link_elem.get_text(strip=True)
            
            if not url or not title:
                return None
            
            # 确保是完整 URL
            if not url.startswith('http'):
                url = f"https://ideas.repec.org{url}"
            
            # 提取 RePEc handle 作为 ID
            paper_id = self._extract_repec_handle(url)
            
            # 尝试从周围文本获取更多信息
            parent = link_elem.find_parent()
            context_text = ""
            if parent:
                context_text = parent.get_text(separator=' ', strip=True)
            
            # 提取年份
            year = self._extract_year(context_text) if context_text else None
            
            # 如果没有从上下文找到年份，尝试从 URL 提取
            if not year:
                year_match = re.search(r'y(\d{4})', url)
                if year_match:
                    year = int(year_match.group(1))
            
            return Paper(
                paper_id=paper_id,
                title=title,
                authors=[],  # 从搜索结果中难以准确提取
                abstract="",  # 搜索结果不包含摘要
                url=url,
                pdf_url="",  # IDEAS 不直接提供 PDF
                published_date=datetime(year, 1, 1) if year else None,
                source="repec",
                categories=[],
                keywords=[],
                doi="",
                citations=0,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse RePEc paper link: {e}")
            return None
    
    def get_paper_details(self, url_or_handle: str) -> Optional[Paper]:
        """获取论文详细信息
        
        从 IDEAS 论文详情页获取完整的元数据，包括摘要、作者、关键词等。
        搜索结果中缺少的信息可以通过此方法补充。
        
        Args:
            url_or_handle: 论文 URL 或 RePEc handle
                - URL: https://ideas.repec.org/a/sae/inrsre/v49y2026i1p62-90.html
                - Handle: RePEc:sae:inrsre:v49y2026i1p62-90
                
        Returns:
            Paper: 包含详细信息的论文对象，失败返回 None
            
        Example:
            >>> paper = searcher.get_paper_details("https://ideas.repec.org/p/nbr/nberwo/32000.html")
            >>> print(paper.abstract)
        """
        try:
            # 处理输入：可能是 URL 或 RePEc handle
            if url_or_handle.startswith('RePEc:'):
                # 转换 RePEc handle 为 URL
                # RePEc:sae:inrsre:v49y2026i1p62-90 -> https://ideas.repec.org/a/sae/inrsre/v49y2026i1p62-90.html
                # 注意：需要猜测文档类型（a/p/h/b），默认尝试 paper(p) 和 article(a)
                parts = url_or_handle.replace('RePEc:', '').split(':')
                if len(parts) >= 3:
                    publisher, series, paper_id = parts[0], parts[1], ':'.join(parts[2:])
                    # 尝试不同类型的 URL
                    for doc_type in ['p', 'a', 'h', 'b']:
                        url = f"https://ideas.repec.org/{doc_type}/{publisher}/{series}/{paper_id}.html"
                        response = self.session.head(url, timeout=5)
                        if response.status_code == 200:
                            break
                    else:
                        logger.warning(f"Cannot resolve RePEc handle: {url_or_handle}")
                        return None
                else:
                    logger.warning(f"Invalid RePEc handle format: {url_or_handle}")
                    return None
            elif url_or_handle.startswith('http'):
                url = url_or_handle
            else:
                # 假设是相对路径
                url = f"https://ideas.repec.org{url_or_handle}"
            
            # 随机延迟
            time.sleep(random.uniform(0.3, 0.8))
            
            # 请求页面
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch paper details: HTTP {response.status_code}")
                return None
            
            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 从 META 标签提取信息
            def get_meta(name: str) -> str:
                """获取 META 标签内容"""
                tag = soup.find('meta', attrs={'name': name})
                if tag:
                    return tag.get('content', '').strip()
                return ''
            
            # 提取各字段
            title = get_meta('citation_title') or get_meta('title')
            abstract = get_meta('citation_abstract')
            
            # 作者处理（支持 ; 和 & 分隔）
            authors_str = get_meta('citation_authors') or get_meta('author')
            if authors_str:
                # 替换 & 为 ; 然后分割
                authors = [a.strip() for a in authors_str.replace(' & ', ';').split(';') if a.strip()]
            else:
                authors = []
            
            # 关键词
            keywords_str = get_meta('citation_keywords') or get_meta('keywords')
            if keywords_str:
                keywords = [k.strip() for k in keywords_str.split(';') if k.strip()]
            else:
                keywords = []
            
            # JEL 分类代码
            jel_codes_str = get_meta('jel_code')
            if jel_codes_str:
                categories = [j.strip() for j in jel_codes_str.split(';') if j.strip()]
            else:
                categories = []
            
            # 日期
            date_str = get_meta('date') or get_meta('citation_publication_date')
            published_date = None
            if date_str:
                try:
                    if '-' in date_str:
                        # 格式: 2026-02-02
                        published_date = datetime.strptime(date_str, '%Y-%m-%d')
                    else:
                        # 格式: 2026
                        published_date = datetime(int(date_str), 1, 1)
                except (ValueError, TypeError):
                    pass
            
            # 期刊/系列名称
            journal = get_meta('citation_journal_title')
            
            # 提取 RePEc handle
            paper_id = self._extract_repec_handle(url)
            
            # 尝试查找 DOI（从页面内容）
            doi = ''
            doi_link = soup.find('a', href=re.compile(r'doi\.org/10\.'))
            if doi_link:
                doi_match = re.search(r'10\.\d{4,}/[^\s]+', doi_link.get('href', ''))
                if doi_match:
                    doi = doi_match.group()
            
            # 尝试获取 PDF 链接
            pdf_url = ''
            pdf_link = soup.find('a', href=re.compile(r'\.pdf$', re.I))
            if pdf_link:
                pdf_url = pdf_link.get('href', '')
                if pdf_url and not pdf_url.startswith('http'):
                    pdf_url = f"https://ideas.repec.org{pdf_url}"
            
            return Paper(
                paper_id=paper_id,
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                pdf_url=pdf_url,
                published_date=published_date,
                source="repec",
                categories=categories,
                keywords=keywords,
                doi=doi,
                citations=0,
                extra={'journal': journal} if journal else {},
            )
            
        except requests.Timeout:
            logger.warning(f"Timeout fetching paper details from {url_or_handle}")
            return None
        except requests.RequestException as e:
            logger.warning(f"Request error fetching paper details: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching paper details: {e}")
            return None
    
    def search(
        self, 
        query: str, 
        max_results: int = 10,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        search_field: str = 'all',
        sort_by: str = 'relevance',
        doc_type: str = 'all',
        series: Optional[str] = None,
    ) -> List[Paper]:
        """搜索 RePEc/IDEAS 论文
        
        支持 IDEAS 高级搜索的所有选项。
        
        搜索语法提示:
        - 布尔搜索: + 表示 AND, | 表示 OR, ~ 表示 NOT
        - 短语搜索: 使用双引号, 例如 "monetary policy"
        - 作者(年份): 例如 "Acemoglu (2019)"
        - 自动同义词: labor=labour, USA=United States
        - 词干提取: find 匹配 finds, finding, findings
        
        Args:
            query: 搜索关键词 (支持布尔运算符)
            max_results: 最大返回数量 (默认 10)
            year_from: 起始年份 (可选, 如 2020)
            year_to: 结束年份 (可选, 如 2025)
            search_field: 搜索字段, 可选值:
                - 'all': 全部字段 (默认)
                - 'abstract': 仅摘要
                - 'keywords': 仅关键词
                - 'title': 仅标题
                - 'author': 仅作者
            sort_by: 排序方式, 可选值:
                - 'relevance': 相关性 (默认)
                - 'newest': 最新发布
                - 'oldest': 最早发布
                - 'citations': 被引用最多
                - 'recent_relevant': 最新且相关
                - 'relevant_cited': 相关且被引用
            doc_type: 文档类型, 可选值:
                - 'all': 所有类型 (默认)
                - 'articles': 期刊文章
                - 'papers': 工作论文 (NBER, Fed 等)
                - 'chapters': 书籍章节
                - 'books': 书籍
                - 'software': 软件组件
            series: 研究机构/期刊系列, 可选值:
                - 机构: 'nber', 'imf', 'worldbank', 'ecb', 'bis', 'cepr', 'iza'
                - 美联储: 'fed', 'fed_ny', 'fed_chicago', 'fed_stlouis'
                - 期刊: 'aer', 'jpe', 'qje', 'econometrica', 'restud'
                - 其他: 'jfe', 'jme', 'aej_macro', 'aej_micro', 'aej_applied'
            
        Returns:
            List[Paper]: 论文列表
            
        Example:
            >>> papers = searcher.search("artificial intelligence", max_results=5)
            >>> papers = searcher.search('"monetary policy" +inflation', sort_by='newest')
            >>> papers = searcher.search("inflation", series='nber')  # 仅搜索 NBER
            >>> papers = searcher.search("causal", series='aer')  # 仅搜索 AER
        """
        if not query or not query.strip():
            return []
        
        papers = []
        seen_urls = set()  # 避免重复
        
        try:
            # 获取参数值
            wf = self.SEARCH_FIELDS.get(search_field, self.SEARCH_FIELDS['all'])
            s = self.SORT_OPTIONS.get(sort_by, self.SORT_OPTIONS['relevance'])
            
            # 处理 ul 参数: series 优先于 doc_type
            if series:
                ul = self.SERIES.get(series, series)  # 支持直接传入 handle
            else:
                ul = self.DOC_TYPES.get(doc_type, self.DOC_TYPES['all'])
            
            # 构建 POST 数据
            data = {
                'q': query,
                'wf': wf,     # 搜索字段
                's': s,       # 排序方式
                'form': 'extended',
                'wm': 'wrd',
                'dt': 'range',
            }
            
            # 添加 ul 参数 (仅当非空时)
            if ul:
                data['ul'] = ul
            
            # 添加日期范围
            if year_from:
                data['db'] = f'01/01/{year_from}'
            if year_to:
                data['de'] = f'12/31/{year_to}'
            
            # 随机延迟，避免被封
            time.sleep(random.uniform(0.5, 1.5))
            
            # 发送 POST 请求
            response = self.session.post(
                self.SEARCH_URL,
                data=data,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f"RePEc search failed with status {response.status_code}")
                return []
            
            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有论文链接
            for link in soup.find_all('a', href=True):
                if len(papers) >= max_results:
                    break
                
                href = link.get('href', '')
                
                # 检查是否为论文链接
                if not self._is_paper_url(href):
                    continue
                
                # 避免重复
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # 解析论文
                paper = self._parse_paper_link(link, soup)
                if paper:
                    # 应用年份过滤
                    if year_from or year_to:
                        paper_year = paper.published_date.year if paper.published_date else None
                        if paper_year:
                            if year_from and paper_year < year_from:
                                continue
                            if year_to and paper_year > year_to:
                                continue
                    
                    papers.append(paper)
            
            logger.info(f"RePEc search found {len(papers)} papers for query: {query}")
            
        except requests.Timeout:
            logger.error("RePEc search timed out")
        except requests.RequestException as e:
            logger.error(f"RePEc search request failed: {e}")
        except Exception as e:
            logger.error(f"RePEc search error: {e}")
        
        return papers[:max_results]
    
    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """RePEc/IDEAS 不支持直接 PDF 下载
        
        RePEc 是元数据索引，不托管 PDF 文件。
        PDF 通常在原机构网站（如 NBER、央行官网）。
        
        Args:
            paper_id: RePEc handle (未使用)
            save_path: 保存路径 (未使用)
            
        Returns:
            str: 错误信息和替代方案
        """
        return (
            "RePEc/IDEAS does not host PDF files directly. "
            "PDFs are available from the original institution's website. "
            "ALTERNATIVES:\n"
            "1. Use the paper URL to visit the source (NBER, Fed, etc.)\n"
            "2. If DOI is available, use download_scihub(doi)\n"
            "3. Many NBER/Fed working papers are freely available at source"
        )
    
    def read_paper(self, paper_id: str, save_path: str) -> str:
        """RePEc/IDEAS 不支持直接论文阅读
        
        Args:
            paper_id: RePEc handle (未使用)
            save_path: 保存路径 (未使用)
            
        Returns:
            str: 错误信息和替代方案
        """
        return (
            "RePEc/IDEAS papers cannot be read directly. "
            "Only metadata and abstracts are available through IDEAS. "
            "ALTERNATIVES:\n"
            "1. Visit the paper URL to access full text at the source\n"
            "2. If DOI is available, use read_scihub_paper(doi)\n"
            "3. Many working papers from NBER/Fed are freely downloadable"
        )


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    searcher = RePECSearcher()
    
    print("=" * 60)
    print("Testing RePEc/IDEAS search...")
    print("=" * 60)
    
    papers = searcher.search("machine learning economics", max_results=5)
    
    print(f"\nFound {len(papers)} papers:")
    for i, paper in enumerate(papers, 1):
        print(f"\n{i}. {paper.title}")
        print(f"   ID: {paper.paper_id}")
        print(f"   Authors: {', '.join(paper.authors[:3])}")
        print(f"   Year: {paper.published_date.year if paper.published_date else 'N/A'}")
        print(f"   URL: {paper.url}")
    
    print("\n" + "=" * 60)
    print("Testing year filter...")
    print("=" * 60)
    
    papers_recent = searcher.search("inflation", max_results=3, year_from=2023, year_to=2025)
    print(f"\nFound {len(papers_recent)} papers from 2023-2025:")
    for paper in papers_recent:
        print(f"  - {paper.title[:60]}...")
