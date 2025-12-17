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
import pymupdf4llm
import pymupdf
import os
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


class ArxivSearcher(PaperSource):
    """arXiv 论文搜索器
    
    功能：
    - 搜索 arXiv 论文
    - 下载 PDF 文件
    - 提取论文内容（支持 Markdown 和纯文本格式）
    
    2025 最佳实践：
    - 使用 PyMuPDF4LLM 进行 PDF 文本提取
    - 表格自动转换为 Markdown 表格
    - 支持多种表格检测策略
    """
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    # 表格检测策略说明
    TABLE_STRATEGIES = {
        "lines_strict": "严格模式：只检测有完整边框线的表格",
        "lines": "线条模式：检测有部分边框线的表格",
        "text": "文本模式：基于文本对齐检测表格（适合无边框表格）",
        "explicit": "显式模式：只检测 PDF 中明确标记的表格",
    }

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
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"arXiv API request failed: {e}")
            return []
        
        feed = feedparser.parse(response.content)
        papers = []
        
        for entry in feed.entries:
            try:
                authors = [author.name for author in entry.authors]
                published = datetime.strptime(entry.published, '%Y-%m-%dT%H:%M:%SZ')
                updated = datetime.strptime(entry.updated, '%Y-%m-%dT%H:%M:%SZ')
                pdf_url = next(
                    (link.href for link in entry.links if link.type == 'application/pdf'), 
                    ''
                )
                papers.append(Paper(
                    paper_id=entry.id.split('/')[-1],
                    title=entry.title.replace('\n', ' ').strip(),
                    authors=authors,
                    abstract=entry.summary.replace('\n', ' ').strip(),
                    url=entry.id,
                    pdf_url=pdf_url,
                    published_date=published,
                    updated_date=updated,
                    source='arxiv',
                    categories=[tag.term for tag in entry.tags],
                    keywords=[],
                    doi=entry.get('doi', '')
                ))
            except Exception as e:
                logger.warning(f"Error parsing arXiv entry: {e}")
                
        return papers

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """下载 arXiv 论文 PDF
        
        Args:
            paper_id: arXiv 论文 ID (例如 '2106.12345')
            save_path: 保存目录
            
        Returns:
            str: PDF 文件路径
            
        Raises:
            RuntimeError: 下载失败时抛出
        """
        # 确保目录存在
        os.makedirs(save_path, exist_ok=True)
        
        # 构建文件路径
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

    def read_paper(
        self, 
        paper_id: str, 
        save_path: str,
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
                - "lines_strict": 严格模式，只检测有完整边框的表格
                - "lines": 线条模式，检测有部分边框的表格
                - "text": 文本模式，基于对齐检测（适合无边框表格）
                - "explicit": 显式模式，只检测明确标记的表格
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

    def _ensure_pdf_downloaded(self, paper_id: str, save_path: str) -> str:
        """确保 PDF 已下载，返回文件路径"""
        safe_id = paper_id.replace('/', '_').replace(':', '_')
        pdf_path = os.path.join(save_path, f"{safe_id}.pdf")
        
        if not os.path.exists(pdf_path):
            pdf_path = self.download_pdf(paper_id, save_path)
        
        return pdf_path

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
                show_progress=False
            )
            return md_text
        except Exception as e:
            logger.error(f"Markdown extraction failed: {e}")
            # 回退到纯文本提取
            logger.info("Falling back to plain text extraction")
            return self._extract_text(pdf_path, pages)

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


if __name__ == "__main__":
    # 测试 ArxivSearcher 的功能
    logging.basicConfig(level=logging.INFO)
    searcher = ArxivSearcher()
    
    # 测试搜索功能
    print("=" * 60)
    print("1. Testing search functionality...")
    print("=" * 60)
    query = "machine learning"
    max_results = 3
    papers = []
    
    try:
        papers = searcher.search(query, max_results=max_results)
        print(f"Found {len(papers)} papers for query '{query}':")
        for i, paper in enumerate(papers, 1):
            print(f"{i}. {paper.title[:60]}... (ID: {paper.paper_id})")
    except Exception as e:
        print(f"Error during search: {e}")
    
    # 测试 PDF 下载功能
    if papers:
        print("\n" + "=" * 60)
        print("2. Testing PDF download functionality...")
        print("=" * 60)
        paper_id = papers[0].paper_id
        save_path = "./downloads"
        
        try:
            pdf_path = searcher.download_pdf(paper_id, save_path)
            print(f"PDF downloaded successfully: {pdf_path}")
        except Exception as e:
            print(f"Error during PDF download: {e}")

    # 测试 Markdown 提取功能
    if papers:
        print("\n" + "=" * 60)
        print("3. Testing Markdown extraction (PyMuPDF4LLM)...")
        print("=" * 60)
        paper_id = papers[0].paper_id
        
        try:
            md_content = searcher.read_paper(
                paper_id, 
                output_format="markdown",
                table_strategy="lines_strict"
            )
            
            # 保存 Markdown 文件到 downloads 目录
            safe_id = paper_id.replace('/', '_').replace(':', '_')
            md_file_path = os.path.join(save_path, f"{safe_id}.md")
            with open(md_file_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"Markdown saved to: {md_file_path}")
            
            print(f"\nFirst 1000 characters of Markdown content:")
            print("-" * 40)
            print(md_content[:1000])
            print("-" * 40)
            print(f"\nTotal length: {len(md_content)} characters")
        except Exception as e:
            print(f"Error during paper reading: {e}")
    
    # 测试纯文本提取功能
    if papers:
        print("\n" + "=" * 60)
        print("4. Testing plain text extraction...")
        print("=" * 60)
        paper_id = papers[0].paper_id
        
        try:
            text_content = searcher.read_paper(
                paper_id, 
                output_format="text"
            )
            print(f"\nFirst 500 characters of text content:")
            print("-" * 40)
            print(text_content[:500])
            print("-" * 40)
            print(f"\nTotal length: {len(text_content)} characters")
        except Exception as e:
            print(f"Error during paper reading: {e}")