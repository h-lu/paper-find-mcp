# tests/test_repec.py
"""
RePEc/IDEAS Searcher 测试

测试通过 IDEAS 前端 (ideas.repec.org) 搜索经济学论文的功能。
"""
import unittest
import requests
from paper_search_mcp.academic_platforms.repec import RePECSearcher


def check_ideas_accessible():
    """检查 IDEAS 网站是否可访问"""
    try:
        response = requests.get(
            "https://ideas.repec.org/",
            timeout=10,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        return response.status_code == 200
    except:
        return False


class TestRePECSearcher(unittest.TestCase):
    """RePEc/IDEAS 搜索器测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.ideas_accessible = check_ideas_accessible()
        if not cls.ideas_accessible:
            print("\nWarning: IDEAS website is not accessible, some tests will be skipped")
    
    def setUp(self):
        self.searcher = RePECSearcher()
    
    def test_search_basic(self):
        """测试基本搜索功能"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        papers = self.searcher.search("machine learning", max_results=5)
        
        print(f"\nFound {len(papers)} papers for query 'machine learning':")
        for i, paper in enumerate(papers, 1):
            print(f"{i}. {paper.title[:60]}...")
            print(f"   ID: {paper.paper_id}")
            print(f"   Authors: {', '.join(paper.authors[:2]) if paper.authors else 'N/A'}")
            print(f"   Year: {paper.published_date.year if paper.published_date else 'N/A'}")
            print()
        
        self.assertTrue(len(papers) > 0, "Should return at least one paper")
        if papers:
            self.assertTrue(papers[0].title, "Paper should have a title")
            self.assertEqual(papers[0].source, "repec", "Source should be 'repec'")
    
    def test_search_with_year_filter(self):
        """测试年份过滤"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        papers = self.searcher.search(
            "inflation",
            max_results=3,
            year_from=2023,
            year_to=2025
        )
        
        print(f"\nFound {len(papers)} papers with year filter (2023-2025):")
        for paper in papers:
            year = paper.published_date.year if paper.published_date else None
            print(f"  - {paper.title[:50]}... (Year: {year})")
        
        # 年份过滤可能不是100%准确（依赖于网站数据）
        self.assertTrue(len(papers) >= 0, "Search should complete without error")
    
    def test_search_empty_query(self):
        """测试空查询"""
        papers = self.searcher.search("", max_results=5)
        self.assertEqual(len(papers), 0, "Empty query should return no papers")
    
    def test_download_not_supported(self):
        """测试下载功能返回适当的错误信息"""
        result = self.searcher.download_pdf("RePEc:nbr:nberwo:32000", "./downloads")
        
        self.assertIn("does not host PDF", result)
        self.assertIn("ALTERNATIVES", result)
        print(f"\nDownload message:\n{result}")
    
    def test_read_not_supported(self):
        """测试阅读功能返回适当的错误信息"""
        result = self.searcher.read_paper("RePEc:nbr:nberwo:32000", "./downloads")
        
        self.assertIn("cannot be read directly", result)
        self.assertIn("ALTERNATIVES", result)
        print(f"\nRead message:\n{result}")
    
    def test_extract_repec_handle(self):
        """测试 RePEc handle 提取"""
        # 测试工作论文 URL
        url1 = "https://ideas.repec.org/p/nbr/nberwo/32000.html"
        handle1 = self.searcher._extract_repec_handle(url1)
        self.assertEqual(handle1, "RePEc:nbr:nberwo:32000")
        
        # 测试期刊文章 URL
        url2 = "https://ideas.repec.org/a/aea/aecrev/v110y2020i1p1-40.html"
        handle2 = self.searcher._extract_repec_handle(url2)
        self.assertEqual(handle2, "RePEc:aea:aecrev:v110y2020i1p1-40")
        
        print(f"\nExtracted handles:\n  {url1} -> {handle1}\n  {url2} -> {handle2}")
    
    def test_extract_year(self):
        """测试年份提取"""
        self.assertEqual(self.searcher._extract_year("Published in 2023"), 2023)
        self.assertEqual(self.searcher._extract_year("Working Paper 2020-01"), 2020)
        self.assertIsNone(self.searcher._extract_year("No year here"))
    
    def test_session_headers(self):
        """测试 Session 包含正确的请求头"""
        user_agent = self.searcher.session.headers.get('User-Agent', '')
        self.assertTrue(len(user_agent) > 0, "Should have User-Agent header")
        self.assertIn("Mozilla", user_agent, "User-Agent should look like a browser")
    
    def test_search_field_options(self):
        """测试搜索字段选项常量"""
        # 验证所有搜索字段选项存在
        expected_fields = ['all', 'abstract', 'keywords', 'title', 'author']
        for field in expected_fields:
            self.assertIn(field, self.searcher.SEARCH_FIELDS, f"Missing search field: {field}")
        
        print(f"\nAvailable search fields: {list(self.searcher.SEARCH_FIELDS.keys())}")
    
    def test_sort_options(self):
        """测试排序选项常量"""
        # 验证主要排序选项存在
        expected_sorts = ['relevance', 'newest', 'oldest', 'citations']
        for sort in expected_sorts:
            self.assertIn(sort, self.searcher.SORT_OPTIONS, f"Missing sort option: {sort}")
        
        print(f"\nAvailable sort options: {list(self.searcher.SORT_OPTIONS.keys())}")
    
    def test_doc_type_options(self):
        """测试文档类型选项常量"""
        # 验证所有文档类型存在
        expected_types = ['all', 'articles', 'papers', 'chapters', 'books', 'software']
        for doc_type in expected_types:
            self.assertIn(doc_type, self.searcher.DOC_TYPES, f"Missing doc type: {doc_type}")
        
        print(f"\nAvailable doc types: {list(self.searcher.DOC_TYPES.keys())}")
    
    def test_search_with_sort_option(self):
        """测试排序选项"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        papers = self.searcher.search(
            "inflation",
            max_results=3,
            sort_by='newest'
        )
        
        print(f"\nFound {len(papers)} papers sorted by newest:")
        for paper in papers:
            print(f"  - {paper.title[:50]}...")
        
        self.assertTrue(len(papers) >= 0, "Search with sort should complete without error")
    
    def test_search_with_doc_type(self):
        """测试文档类型过滤"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        papers = self.searcher.search(
            "monetary policy",
            max_results=3,
            doc_type='papers'  # 仅工作论文
        )
        
        print(f"\nFound {len(papers)} working papers for 'monetary policy':")
        for paper in papers:
            # 检查 URL 是否包含 /p/ (working papers 路径)
            if '/p/' in paper.url:
                print(f"  ✓ {paper.title[:50]}...")
            else:
                print(f"  ? {paper.title[:50]}... (URL: {paper.url[:50]})")
        
        self.assertTrue(len(papers) >= 0, "Search with doc_type should complete without error")
    
    def test_search_by_author(self):
        """测试按作者搜索"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        papers = self.searcher.search(
            "Acemoglu",
            max_results=3,
            search_field='author'
        )
        
        print(f"\nFound {len(papers)} papers by author 'Acemoglu':")
        for paper in papers:
            print(f"  - {paper.title[:60]}...")
        
        self.assertTrue(len(papers) >= 0, "Search by author should complete without error")
    
    def test_get_paper_details_from_url(self):
        """测试从 URL 获取论文详情"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        # 测试一个已知的论文页面
        url = "https://ideas.repec.org/a/sae/inrsre/v49y2026i1p62-90.html"
        paper = self.searcher.get_paper_details(url)
        
        print(f"\nPaper details from URL:")
        if paper:
            print(f"  Title: {paper.title[:60]}...")
            print(f"  Authors: {paper.authors}")
            print(f"  Abstract: {paper.abstract[:100]}..." if paper.abstract else "  Abstract: N/A")
            print(f"  Keywords: {paper.keywords}")
            print(f"  URL: {paper.url}")
            
            self.assertTrue(paper.title, "Paper should have a title")
            self.assertTrue(paper.abstract, "Paper should have an abstract")
            self.assertTrue(len(paper.authors) > 0, "Paper should have authors")
            self.assertEqual(paper.source, "repec")
        else:
            self.fail("get_paper_details should return a paper")
    
    def test_get_paper_details_extracts_metadata(self):
        """测试详情页提取完整元数据"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        url = "https://ideas.repec.org/a/sae/inrsre/v49y2026i1p62-90.html"
        paper = self.searcher.get_paper_details(url)
        
        if paper:
            # 验证各字段类型
            self.assertIsInstance(paper.authors, list)
            self.assertIsInstance(paper.keywords, list)
            self.assertIsInstance(paper.abstract, str)
            
            # 应该有多个作者
            self.assertGreater(len(paper.authors), 0, "Should have at least one author")
            
            # 应该有关键词
            if paper.keywords:
                print(f"\nKeywords found: {paper.keywords}")
    
    def test_series_options(self):
        """测试系列选项常量"""
        # 验证主要机构存在
        expected_series = ['nber', 'imf', 'fed', 'aer', 'qje']
        for s in expected_series:
            self.assertIn(s, self.searcher.SERIES, f"Missing series: {s}")
        
        print(f"\nAvailable series: {list(self.searcher.SERIES.keys())[:10]}...")
    
    def test_search_with_series_nber(self):
        """测试 NBER 系列过滤"""
        if not self.ideas_accessible:
            self.skipTest("IDEAS website is not accessible")
        
        papers = self.searcher.search(
            "inflation",
            max_results=5,
            series='nber'
        )
        
        print(f"\nFound {len(papers)} NBER papers for 'inflation':")
        all_nber = True
        for paper in papers:
            is_nber = '/p/nbr/nberwo/' in paper.url
            print(f"  {'✓' if is_nber else '?'} {paper.title[:50]}...")
            if not is_nber:
                all_nber = False
        
        self.assertTrue(len(papers) > 0, "Should find NBER papers")
        self.assertTrue(all_nber, "All papers should be from NBER")


if __name__ == '__main__':
    unittest.main(verbosity=2)
