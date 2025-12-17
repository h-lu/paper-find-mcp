# MCP 入门快速指南

> **适合完全的初学者**

---

## 什么是 MCP？

**MCP (Model Context Protocol)** 是一个开放标准，让 AI 模型能够与外部世界交互。

### 简单类比

```
普通 LLM:
  用户 → LLM → 文字回复
  
有 MCP 的 LLM:
  用户 → LLM → 调用工具 → 获取真实数据 → 更准确的回复
```

### 核心概念

| 概念 | 说明 | 例子 |
|------|------|------|
| **Server** | 提供工具的服务程序 | 论文搜索服务器 |
| **Tool** | LLM 可调用的函数 | `search_arxiv()` |
| **Resource** | LLM 可读取的数据 | 论文内容 |

---

## 5 分钟创建你的第一个 MCP 工具

### 步骤 1: 安装 FastMCP

```bash
pip install fastmcp
```

### 步骤 2: 创建最简单的 MCP 服务器

创建文件 `my_first_mcp.py`:

```python
from mcp.server.fastmcp import FastMCP

# 创建 MCP 服务器
mcp = FastMCP("my_first_server")

# 定义一个工具
@mcp.tool()
async def add_numbers(a: int, b: int) -> int:
    """Add two numbers together.
    
    Args:
        a: First number
        b: Second number
    Returns:
        Sum of the two numbers
    """
    return a + b

# 运行服务器
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 步骤 3: 测试

```bash
python my_first_mcp.py
# 服务器将等待输入...
```

恭喜！你创建了第一个 MCP 服务器！

---

## 核心代码模式

### 1. 创建服务器

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server_name")
```

### 2. 定义工具

```python
@mcp.tool()
async def my_tool(param1: str, param2: int = 10) -> str:
    """Tool description (LLM will read this!)
    
    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)
    Returns:
        Description of return value
    """
    # 你的逻辑
    return f"Result: {param1}, {param2}"
```

### 3. 运行服务器

```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## 实用示例：天气查询工具

```python
from mcp.server.fastmcp import FastMCP
import requests

mcp = FastMCP("weather_server")

@mcp.tool()
async def get_weather(city: str) -> str:
    """Get current weather for a city.
    
    Args:
        city: City name (e.g., "Beijing", "Tokyo")
    Returns:
        Weather information string
    """
    # 使用免费的 wttr.in API
    response = requests.get(f"https://wttr.in/{city}?format=3")
    return response.text

if __name__ == "__main__":
    mcp.run()
```

---

## 配置 Claude Desktop

编辑配置文件：
- **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "my_first_server": {
      "command": "python",
      "args": ["/path/to/my_first_mcp.py"]
    }
  }
}
```

重启 Claude Desktop，你的工具就可以使用了！

---

## 常见问题

### Q: 为什么要用 `async def`？
A: MCP 支持异步调用，让多个工具可以并发执行。

### Q: docstring 很重要吗？
A: **非常重要！** LLM 会阅读 docstring 来理解如何使用你的工具。

### Q: 工具可以返回什么类型？
A: 建议返回 `str`、`int`、`float`、`bool`、`List`、`Dict` 等 JSON 可序列化的类型。

### Q: 如何处理错误？
A: 可以返回错误信息字符串，或者抛出异常让 MCP 框架处理。

---

## 下一步学习

1. 阅读本项目的详细文档
2. 学习 [02_server.md](./02_server.md) 了解完整的 MCP 服务器实现
3. 尝试添加你自己的搜索平台
4. 参考 [FastMCP 官方文档](https://github.com/jlowin/fastmcp)

---

## 最佳实践

### ✅ 做的事

- 写清晰的 docstring
- 使用类型提示
- 处理可能的错误
- 返回有意义的结果

### ❌ 避免的事

- 复杂的同步阻塞操作
- 返回过大的数据
- 忽略错误处理
- 忘记写 docstring

---

祝你 MCP 开发愉快！ 🚀
