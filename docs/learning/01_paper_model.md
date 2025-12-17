# Paper 数据模型详解

> **文件位置**: `paper_search_mcp/paper.py`  
> **难度**: ⭐⭐ (适合入门)  
> **更新**: 2025年12月 - 使用 Pydantic V2 重写

---

## 概述

`Paper` 类是整个项目的**数据核心**，定义了学术论文的标准化格式。

### 2025 最佳实践：Pydantic V2

本项目使用 **Pydantic V2** 替代 Python 原生 `dataclass`：

| 特性 | dataclass | Pydantic V2 |
|------|:---------:|:-----------:|
| 运行时验证 | ❌ | ✅ |
| 类型转换 | ❌ | ✅ 智能 |
| JSON 序列化 | ❌ 手动 | ✅ 内置 |
| 错误提示 | ❌ | ✅ 友好 |
| 默认值工厂 | ⚠️ 易错 | ✅ 简单 |

---

## 完整代码分析

### 1. 导入和模型配置

```python
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from typing import List, Dict, Optional, Any


class Paper(BaseModel):
    """学术论文标准化数据模型"""
    
    # Pydantic 配置
    model_config = ConfigDict(
        extra='ignore',           # 忽略未知字段
        validate_assignment=True, # 赋值时也验证
    )
```

**💡 学习要点**：

1. **`BaseModel`**: Pydantic 的核心基类，继承后自动获得验证能力
2. **`ConfigDict`**: Pydantic V2 的配置方式（V1 使用内部 `Config` 类）
3. **`extra='ignore'`**: 忽略未定义的字段，提高兼容性

---

### 2. 字段定义

```python
class Paper(BaseModel):
    # ========================================
    # 核心字段（必填）
    # ========================================
    paper_id: str = Field(
        ...,                # ... 表示必填
        min_length=1,       # 最少 1 个字符
        description="唯一标识符"
    )
    title: str = Field(..., min_length=1)
    source: str = Field(..., description="来源平台")
    
    # ========================================
    # 核心字段（有默认值）
    # ========================================
    authors: List[str] = Field(default_factory=list)
    abstract: str = Field(default="")
    doi: str = Field(default="")
    published_date: Optional[datetime] = None
    pdf_url: str = Field(default="")
    url: str = Field(default="")
    
    # ========================================
    # 扩展字段
    # ========================================
    updated_date: Optional[datetime] = None
    categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    citations: int = Field(default=0, ge=0)  # ge=0: 大于等于 0
    references: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)
```

**💡 学习要点**：

1. **`Field(...)`**: `...` 是 Python 的 Ellipsis，在 Pydantic 中表示必填
2. **`default_factory=list`**: 每次创建新实例时调用 `list()` 生成新列表（避免可变默认值陷阱）
3. **`ge=0`**: 验证约束，表示 "greater than or equal to 0"
4. **`Optional[datetime]`**: 可以是 `datetime` 或 `None`

---

### 3. 字段验证器

```python
@field_validator('title', 'abstract', mode='before')
@classmethod
def clean_whitespace(cls, v: Any) -> str:
    """清理标题和摘要中的多余空白和换行符
    
    mode='before' 表示在 Pydantic 类型验证之前执行
    这样可以处理原始输入数据
    """
    if v is None:
        return ""
    if isinstance(v, str):
        # 替换换行为空格，合并多个空格
        return ' '.join(v.split())
    return str(v)


@field_validator('authors', mode='before')
@classmethod
def ensure_authors_list(cls, v: Any) -> List[str]:
    """确保作者字段是列表
    
    支持多种输入格式：
    - 列表: ["Alice", "Bob"]
    - 分号字符串: "Alice; Bob"
    - 逗号字符串: "Alice, Bob"
    """
    if v is None:
        return []
    if isinstance(v, str):
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
```

**💡 学习要点**：

1. **`@field_validator`**: Pydantic V2 的字段验证装饰器
2. **`mode='before'`**: 在 Pydantic 内置类型验证之前执行
3. **`@classmethod`**: 验证器必须是类方法
4. **灵活输入**: 接受多种格式，统一输出

---

### 4. 序列化方法

```python
def to_dict(self) -> Dict[str, Any]:
    """转换为字典格式（兼容旧 API）
    
    输出格式与旧 dataclass 版本相同:
    - 列表转为分号分隔的字符串
    - 日期转为 ISO 格式字符串
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
    
    使用 Pydantic 原生序列化:
    - 保持列表格式
    - 日期自动转换为 ISO 字符串
    """
    return self.model_dump(mode='json')
```

**💡 两种序列化方式对比**：

```python
paper = Paper(
    paper_id="test",
    title="Test Paper",
    source="arxiv",
    authors=["Alice", "Bob"]
)

# to_dict() - 兼容旧 API
paper.to_dict()
# {'authors': 'Alice; Bob', ...}

# to_json_dict() - Pydantic 原生
paper.to_json_dict()
# {'authors': ['Alice', 'Bob'], ...}
```

---

## 使用示例

### 基本创建

```python
from paper_search_mcp.paper import Paper
from datetime import datetime

paper = Paper(
    paper_id="2106.12345",
    title="Attention Is All You Need",
    source="arxiv",
    authors=["John Doe", "Jane Smith"],
    abstract="This is a test abstract.",
    published_date=datetime.now(),
)
```

### 自动清理和转换

```python
# 标题中的换行会被自动清理
paper = Paper(
    paper_id="test",
    title="Attention Is\n  All You Need  ",  # 有换行和多余空格
    source="arxiv"
)
print(paper.title)  # "Attention Is All You Need"

# 作者字符串会被自动解析
paper = Paper(
    paper_id="test",
    title="Test",
    source="arxiv",
    authors="Alice; Bob; Charlie"  # 分号分隔的字符串
)
print(paper.authors)  # ['Alice', 'Bob', 'Charlie']
```

### 验证错误

```python
from pydantic import ValidationError

try:
    # paper_id 不能为空
    paper = Paper(paper_id="", title="Test", source="test")
except ValidationError as e:
    print(e)
    # 1 validation error for Paper
    # paper_id
    #   String should have at least 1 character
```

---

## 与 dataclass 对比

### 旧版本 (dataclass)

```python
@dataclass
class Paper:
    paper_id: str
    title: str
    authors: List[str] = None  # ⚠️ 可变默认值问题！
    
    def __post_init__(self):
        # 需要手动处理默认值
        if self.authors is None:
            self.authors = []
```

**问题**：
- 需要 `__post_init__` 处理默认值
- 无运行时验证
- 需要手动实现 `to_dict()`

### 新版本 (Pydantic V2)

```python
class Paper(BaseModel):
    paper_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    authors: List[str] = Field(default_factory=list)  # ✅ 正确的默认值
    
    @field_validator('title', mode='before')
    @classmethod
    def clean_title(cls, v):
        return ' '.join(v.split()) if v else ""
```

**优势**：
- 自动验证
- 简洁的默认值语法
- 内置序列化

---

## 最佳实践总结

| 实践 | 说明 |
|------|------|
| 使用 `Field(...)` 标记必填 | 比直接类型注解更清晰 |
| 使用 `default_factory` | 避免可变默认值问题 |
| 使用 `@field_validator` | 集中处理数据清理逻辑 |
| 提供 `to_dict()` 兼容方法 | 便于与旧代码集成 |
| 使用 `model_dump()` | Pydantic 原生序列化 |

---

## 扩展阅读

- [Pydantic 官方文档](https://docs.pydantic.dev/)
- [Pydantic V2 迁移指南](https://docs.pydantic.dev/latest/migration/)
- [Field 验证器详解](https://docs.pydantic.dev/latest/concepts/validators/)
