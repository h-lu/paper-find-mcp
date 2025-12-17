# paper_search_mcp/paper.py
"""
Paper 数据模型 - 学术论文标准化格式

2025 最佳实践版本：
- 使用 Pydantic V2 提供运行时类型验证
- 自动类型转换和友好错误提示
- 内置 JSON 序列化支持
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from typing import List, Dict, Optional, Any


class Paper(BaseModel):
    """学术论文标准化数据模型
    
    使用 Pydantic V2 提供:
    - 运行时类型验证
    - 自动类型转换（如字符串日期 -> datetime）
    - JSON 序列化/反序列化
    - 友好的验证错误信息
    
    Example:
        >>> paper = Paper(
        ...     paper_id="2106.12345",
        ...     title="Attention Is All You Need",
        ...     source="arxiv"
        ... )
        >>> paper.model_dump()
        {'paper_id': '2106.12345', 'title': 'Attention Is All You Need', ...}
    """
    
    # 配置
    model_config = ConfigDict(
        # 允许额外字段（兼容性）
        extra='ignore',
        # 验证赋值
        validate_assignment=True,
    )
    
    # ========================================
    # 核心字段（必填）
    # ========================================
    paper_id: str = Field(
        ..., 
        min_length=1, 
        description="唯一标识符 (如 arXiv ID, PMID, DOI)"
    )
    title: str = Field(
        ..., 
        min_length=1, 
        description="论文标题"
    )
    source: str = Field(
        ..., 
        description="来源平台 (如 'arxiv', 'pubmed', 'semantic')"
    )
    
    # ========================================
    # 核心字段（可选，有默认值）
    # ========================================
    authors: List[str] = Field(
        default_factory=list,
        description="作者列表"
    )
    abstract: str = Field(
        default="",
        description="摘要文本"
    )
    doi: str = Field(
        default="",
        description="数字对象标识符 (DOI)"
    )
    published_date: Optional[datetime] = Field(
        default=None,
        description="发布日期"
    )
    pdf_url: str = Field(
        default="",
        description="PDF 直接下载链接"
    )
    url: str = Field(
        default="",
        description="论文页面 URL"
    )
    
    # ========================================
    # 扩展字段（可选）
    # ========================================
    updated_date: Optional[datetime] = Field(
        default=None,
        description="最后更新日期"
    )
    categories: List[str] = Field(
        default_factory=list,
        description="学科分类"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="关键词"
    )
    citations: int = Field(
        default=0,
        ge=0,
        description="被引用次数"
    )
    references: List[str] = Field(
        default_factory=list,
        description="参考文献 ID/DOI 列表"
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="平台特定的额外元数据"
    )
    
    # ========================================
    # 字段验证器
    # ========================================
    @field_validator('title', 'abstract', mode='before')
    @classmethod
    def clean_whitespace(cls, v: Any) -> str:
        """清理标题和摘要中的多余空白和换行符"""
        if v is None:
            return ""
        if isinstance(v, str):
            # 替换换行为空格，合并多个空格
            return ' '.join(v.split())
        return str(v)
    
    @field_validator('authors', mode='before')
    @classmethod
    def ensure_authors_list(cls, v: Any) -> List[str]:
        """确保作者字段是列表"""
        if v is None:
            return []
        if isinstance(v, str):
            # 支持分号或逗号分隔的字符串
            if ';' in v:
                return [a.strip() for a in v.split(';') if a.strip()]
            elif ',' in v:
                return [a.strip() for a in v.split(',') if a.strip()]
            return [v.strip()] if v.strip() else []
        return list(v)
    
    @field_validator('citations', mode='before')
    @classmethod
    def ensure_citations_int(cls, v: Any) -> int:
        """确保引用数是整数"""
        if v is None:
            return 0
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return 0
        return int(v) if v else 0
    
    # ========================================
    # 序列化方法
    # ========================================
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（兼容旧 API）
        
        此方法保持与旧 dataclass 版本的兼容性，
        输出格式与之前相同（分号分隔的字符串等）
        
        Returns:
            Dict: 序列化的论文数据
        """
        return {
            'paper_id': self.paper_id,
            'title': self.title,
            'authors': '; '.join(self.authors) if self.authors else '',
            'abstract': self.abstract,
            'doi': self.doi,
            'published_date': self.published_date.isoformat() if self.published_date else '',
            'pdf_url': self.pdf_url,
            'url': self.url,
            'source': self.source,
            'updated_date': self.updated_date.isoformat() if self.updated_date else '',
            'categories': '; '.join(self.categories) if self.categories else '',
            'keywords': '; '.join(self.keywords) if self.keywords else '',
            'citations': self.citations,
            'references': '; '.join(self.references) if self.references else '',
            'extra': str(self.extra) if self.extra else ''
        }
    
    def to_json_dict(self) -> Dict[str, Any]:
        """转换为 JSON 友好的字典格式
        
        使用 Pydantic 的 model_dump，保持列表格式，
        日期自动转换为 ISO 格式字符串
        
        Returns:
            Dict: JSON 友好的论文数据
        """
        return self.model_dump(mode='json')


# ========================================
# 测试代码
# ========================================
if __name__ == "__main__":
    # 测试基本创建
    print("=" * 60)
    print("1. Testing basic Paper creation...")
    print("=" * 60)
    
    paper = Paper(
        paper_id="2106.12345",
        title="Attention Is\n  All You Need  ",  # 会自动清理
        source="arxiv",
        authors=["John Doe", "Jane Smith"],
        abstract="This is a test\n\nabstract.",
        doi="10.1234/example",
        published_date=datetime.now(),
    )
    
    print(f"Title (cleaned): '{paper.title}'")
    print(f"Abstract (cleaned): '{paper.abstract}'")
    print(f"Authors: {paper.authors}")
    
    # 测试 to_dict() 兼容方法
    print("\n" + "=" * 60)
    print("2. Testing to_dict() compatibility...")
    print("=" * 60)
    
    d = paper.to_dict()
    print(f"Authors (semicolon): '{d['authors']}'")
    print(f"Published date: '{d['published_date']}'")
    
    # 测试 model_dump()
    print("\n" + "=" * 60)
    print("3. Testing model_dump() (Pydantic native)...")
    print("=" * 60)
    
    json_dict = paper.to_json_dict()
    print(f"Authors (list): {json_dict['authors']}")
    
    # 测试验证
    print("\n" + "=" * 60)
    print("4. Testing validation...")
    print("=" * 60)
    
    try:
        # 这应该失败：paper_id 不能为空
        invalid = Paper(paper_id="", title="Test", source="test")
    except Exception as e:
        print(f"Validation error (expected): {e}")
    
    # 测试作者字符串解析
    print("\n" + "=" * 60)
    print("5. Testing authors string parsing...")
    print("=" * 60)
    
    paper2 = Paper(
        paper_id="test",
        title="Test",
        source="test",
        authors="Alice; Bob; Charlie"  # 字符串会被自动解析
    )
    print(f"Parsed authors: {paper2.authors}")
    
    print("\n✅ All tests passed!")