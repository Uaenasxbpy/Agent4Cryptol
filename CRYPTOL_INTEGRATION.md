# CryptolAPI 集成改进 - 从独立服务到工作流内置模块

## 📋 背景

原始设计中，Cryptol 编译功能是通过独立的 HTTP API 服务（CryptolAPI）提供的。这引入了以下问题：

1. **架构复杂**：需要运行两个独立的进程（工作流 + API 服务）
2. **网络开销**：每次编译都需要 HTTP 请求/响应循环，增加延迟
3. **部署麻烦**：需要同时启动两个服务，管理复杂
4. **可靠性问题**：API 服务可能崩溃或不可用
5. **依赖过重**：引入了 FastAPI、uvicorn 等不必要的依赖

## ✨ 改进方案

我们将编译逻辑直接集成到工作流中，作为一个内置模块 `workflow/cryptol_compiler.py`。

### 架构对比

**原始架构**：
```
工作流 (workflow/)
    ↓ HTTP POST /cryptolCompile
API 服务器 (CryptolAPI/)
    ↓
本地 Cryptol
```

**新架构**：
```
工作流 (workflow/)
    ↓ 直接调用
编译器模块 (workflow/cryptol_compiler.py)
    ↓
本地 Cryptol
```

## 🚀 主要改进

### 1. **性能提升**
- **消除网络开销**：不再需要 HTTP 序列化/反序列化
- **直接进程调用**：Python 直接调用 subprocess 执行 Cryptol
- **预期改进**：~50-100ms 的网络延迟完全消除

### 2. **简化部署**
- **单进程运行**：只需运行 `python agent_workflow.py`
- **不需要独立服务**：无需在后台运行 API 服务器
- **减少依赖**：移除 FastAPI、uvicorn 等不必要的库

### 3. **提高可靠性**
- **失败立即反馈**：编译异常直接捕获，无网络延迟
- **简化错误处理**：不用处理连接错误、超时等网络问题
- **减少故障点**：少一个可能崩溃的服务

### 4. **降低依赖复杂度**
```
原始依赖（15+ 包）：
  langgraph, langchain, langchain-community
  requests, dashscope
  fastapi, uvicorn, starlette, pydantic-core
  ...

新依赖（8 包）：
  langgraph, langchain, langchain-community
  requests, dashscope
  pydantic, pydantic-settings
```

## 📂 文件结构变化

### 删除/弃用的文件
```
CryptolAPI/
├── app/
│   ├── compiler.py          ❌ 编译逻辑已移到 workflow/cryptol_compiler.py
│   ├── utils.py             ❌ 工具函数已合并到 workflow/cryptol_compiler.py
│   ├── main.py              ❌ API 端点已移除
│   ├── schemas.py           ❌ 不再需要 Pydantic 请求/响应模型
│   └── config.py            ❌ 配置已合并到 workflow/settings.py
└── requirements.txt         ❌ API 依赖已整合到主项目
```

### 新增/修改的文件
```
workflow/
├── cryptol_compiler.py      ✅ 新增：编译器模块（包含编译和辅助函数）
├── settings.py              🔄 修改：更新配置（移除 API 相关配置）
├── nodes.py                 🔄 修改：node_compile 改为直接调用编译器
└── ...

项目根
├── requirements.txt         🔄 修改：简化依赖列表
├── .env.example            🔄 修改：更新配置示例
└── ...
```

## 🔧 如何使用

### 安装（简化版）
```bash
# 安装依赖（现在简单多了）
pip install -r requirements.txt
```

### 配置（可选）
```bash
# 如果 Cryptol 不在 PATH 中，或命令名不同，可配置
echo "CRYPTOL_CMD=/path/to/cryptol" > .env

# 或设置其他参数
echo "COMPILE_TIMEOUT=60" >> .env
```

### 运行
```bash
# 直接运行工作流，不需要启动 API 服务器
python agent_workflow.py

# 或指定函数 JSON 文件
python agent_workflow.py data/FIPS203/ir/functions/alg_001_for_example.json
```

就这么简单！🎉

## 📊 功能等价性

新的编译器模块提供与原 CryptolAPI 相同的功能：

| 功能 | 原 API | 新模块 |
|------|--------|--------|
| 编译 Cryptol 代码 | ✓ | ✓ |
| 解析编译输出 | ✓ | ✓ |
| 分离 info/warning/error | ✓ | ✓ |
| 临时文件管理 | ✓ | ✓ |
| 错误处理 | ✓ | ✓ |
| 日志记录 | ✓ | ✓ |

## 🔀 迁移指南

如果有其他代码依赖原 CryptolAPI 的接口，可以这样迁移：

### 原代码
```python
import requests

response = requests.post(
    "http://localhost:8000/cryptolCompile",
    json={"cryptCode": code}
)
result = response.json()
success = result["success"]
```

### 新代码
```python
from workflow.cryptol_compiler import compile_cryptol_code

success, compile_text, info_text, warning_text, error_text = compile_cryptol_code(
    cryptol_code=code
)
```

## ⚠️ 注意事项

1. **Cryptol 必须在 PATH 中**
   - 或通过 `CRYPTOL_CMD` 环境变量指定完整路径
   
2. **不再通过 HTTP 调用**
   - 如果有外部系统依赖旧 API，需要重新集成或建立新的 HTTP 包装层

3. **原 CryptolAPI 项目可以保留或删除**
   - 建议保留作为历史参考，但不再使用

## 🎯 后续优化机会

1. **并行编译**：支持多个编译任务同时进行
2. **缓存编译结果**：避免重复编译相同代码
3. **编译器版本管理**：支持多个 Cryptol 版本切换
4. **增量编译**：只编译变化部分

---

**改进完成时间**：2026年4月8日
**改进类型**：架构优化、依赖简化、性能提升
