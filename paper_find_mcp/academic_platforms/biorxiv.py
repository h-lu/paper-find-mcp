# paper_search_mcp/academic_platforms/biorxiv.py
"""
BioRxivSearcher - bioRxiv 预印本搜索

2025 最佳实践版本：
- 使用 PyMuPDF4LLM 提取 PDF
- 日志记录
- 分页处理
- 速率限制（1秒间隔）
"""
from typing import List, Optional
import requests
import os
import time
from datetime import datetime, timedelta
import logging

from ..paper import Paper
import pymupdf4llm

logger = logging.getLogger(__name__)


class PaperSource:
    """Abstract base class for paper sources"""
    def search(self, query: str, **kwargs) -> List[Paper]:
        raise NotImplementedError

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        raise NotImplementedError

    def read_paper(self, paper_id: str, save_path: str) -> str:
        raise NotImplementedError


class BioRxivSearcher(PaperSource):
    """bioRxiv 预印本搜索器
    
    使用 bioRxiv API 搜索生物学预印本。
    
    2025 最佳实践：
    - 分页获取（每页 100 篇）
    - 请求间隔 1 秒
    - 指数退避重试
    """
    
    BASE_URL = "https://api.biorxiv.org/details/biorxiv"
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'paper_search_mcp/1.0'
        })
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time = 0.0

    def _rate_limit_wait(self):
        """速率限制：1秒间隔"""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, url: str, retry_count: int = 0) -> Optional[requests.Response]:
        """发送请求，带重试机制"""
        self._rate_limit_wait()
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code == 429:
                if retry_count < self.max_retries:
                    wait_time = (2 ** retry_count) + 1
                    logger.warning(f"Rate limited, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    return self._make_request(url, retry_count + 1)
                return None
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
                return self._make_request(url, retry_count + 1)
            logger.error(f"Request failed after {self.max_retries} retries: {e}")
            return None

    def search(self, query: str, max_results: int = 10, days: int = 30) -> List[Paper]:
        """搜索 bioRxiv 论文
        
        Args:
            query: 分类名称（如 "cell biology", "neuroscience"）
            max_results: 最大返回数量
            days: 搜索最近 N 天的论文
            
        Returns:
            List[Paper]: 论文列表
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 格式化分类
        category = query.lower().replace(' ', '_')
        
        papers = []
        cursor = 0
        
        while len(papers) < max_results:
            url = f"{self.BASE_URL}/{start_date}/{end_date}/{cursor}"
            if category:
                url += f"?category={category}"
            
            response = self._make_request(url)
            if not response:
                break
            
            try:
                data = response.json()
                collection = data.get('collection', [])
            except Exception as e:
                logger.error(f"Failed to parse response: {e}")
                break
            
            if not collection:
                break
            
            for item in collection:
                if len(papers) >= max_results:
                    break
                paper = self._parse_item(item)
                if paper:
                    papers.append(paper)
            
            if len(collection) < 100:
                break  # 没有更多结果
            
            cursor += 100
        
        logger.info(f"Found {len(papers)} papers for query: {query}")
        return papers[:max_results]

    def _parse_item(self, item: dict) -> Optional[Paper]:
        """解析 API 返回的论文数据"""
        try:
            doi = item.get('doi', '')
            version = item.get('version', '1')
            date_str = item.get('date', '')
            
            published_date = None
            if date_str:
                try:
                    published_date = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    pass
            
            return Paper(
                paper_id=doi,
                title=item.get('title', ''),
                authors=item.get('authors', '').split('; '),
                abstract=item.get('abstract', ''),
                url=f"https://www.biorxiv.org/content/{doi}v{version}",
                pdf_url=f"https://www.biorxiv.org/content/{doi}v{version}.full.pdf",
                published_date=published_date,
                source="biorxiv",
                categories=[item.get('category', '')],
                doi=doi
            )
        except Exception as e:
            logger.warning(f"Failed to parse item: {e}")
            return None

    def download_pdf(self, paper_id: str, save_path: str) -> str:
        """下载 PDF
        
        Args:
            paper_id: bioRxiv DOI
            save_path: 保存目录
            
        Returns:
            下载的文件路径或错误信息
        """
        if not paper_id:
            return "Error: paper_id is empty"
        
        pdf_url = f"https://www.biorxiv.org/content/{paper_id}v1.full.pdf"
        
        try:
            response = self.session.get(
                pdf_url, 
                timeout=self.timeout,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            response.raise_for_status()
            
            os.makedirs(save_path, exist_ok=True)
            filename = f"{paper_id.replace('/', '_')}.pdf"
            pdf_path = os.path.join(save_path, filename)
            
            with open(pdf_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"PDF downloaded: {pdf_path}")
            return pdf_path
            
        except Exception as e:
            logger.error(f"PDF download failed: {e}")
            return f"Error downloading PDF: {e}"

    def read_paper(self, paper_id: str, save_path: str) -> str:
        """下载并提取论文文本
        
        Args:
            paper_id: bioRxiv DOI
            save_path: 保存目录
            
        Returns:
            提取的 Markdown 文本
        """
        pdf_path = os.path.join(save_path, f"{paper_id.replace('/', '_')}.pdf")
        
        if not os.path.exists(pdf_path):
            result = self.download_pdf(paper_id, save_path)
            if result.startswith("Error"):
                return result
            pdf_path = result
        
        try:
            text = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
            logger.info(f"Extracted {len(text)} characters from {pdf_path}")
            return text
        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            return f"Error extracting text: {e}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    searcher = BioRxivSearcher()
    
    print("=" * 60)
    print("Testing BioRxivSearcher...")
    print("=" * 60)
    
    papers = searcher.search("neuroscience", max_results=2, days=7)
    print(f"Found {len(papers)} papers")
    
    for i, paper in enumerate(papers, 1):
        print(f"\n{i}. {paper.title[:60]}...")
        print(f"   DOI: {paper.doi}")
        print(f"   PDF: {paper.pdf_url}")
    
    print("\n✅ Test completed!")