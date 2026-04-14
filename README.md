# Agent4Cryptol

基于 LLM Agent 的 Cryptol 密码学代码自动化生成与修复系统。

支持 FIPS 203（ML-KEM）、FIPS 204（ML-DSA）、FIPS 205（SLH-DSA）三项后量子密码标准。

---

## 系统概述

Agent4Cryptol 将密码学算法的 JSON 中间表示（IR）翻译为可编译的 Cryptol 代码，并通过多轮修复 Agent 自动修正编译错误。系统设计支持消融实验，用于量化各组件（提示词、RAG、修复 Agent）对最终生成质量的贡献。

核心工作流：

```
JSON 规范
  │
  ├─ [node_load_json]       读取函数 IR
  ├─ [node_rag_retrieval]   检索 Cryptol 语法规则 / 代码模式
  ├─ [node_translate]       LLM 首次翻译（注入依赖上下文 + RAG）
  ├─ [node_compile]         本地 Cryptol 编译器校验
  │     ├─ 成功 → [node_save]
  │     ├─ 超限 → [node_save_failed]
  │     └─ 失败 → [node_fix] → 回到 compile（最多 max_retries 轮）
  └─ 输出 .cry 文件
```

---

## 环境要求

- Python 3.10+
- [Cryptol](https://cryptol.net) 已安装并在 PATH 中
- 兼容 OpenAI 协议的 LLM（默认：阿里云通义千问 qwen3-max）

---

## 快速开始

### 安装

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml` 中的 LLM 参数：

```yaml
llm:
  model: qwen3-max-2026-01-23
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  api_key_env: DASHSCOPE_API_KEY
  timeout: 120
```

设置 API 密钥：

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY = "your-key"
# Linux/macOS
export DASHSCOPE_API_KEY="your-key"
```

---

## 运行方式

### 单函数处理

```bash
python agent_workflow.py data/FIPS203/ir/functions/alg_003_bits_to_bytes.json
```

输出：
- `Cryptol/fips203/BitsToBytes.cry` — 生成的 Cryptol 代码
- `logger/fips203/BitsToBytes/` — 运行日志和修复过程

### 批量处理

```bash
# 处理 FIPS203 全部函数（按 layer 层级顺序）
python batch_run.py --spec FIPS203

# 查看处理顺序（不执行）
python batch_run.py --spec FIPS203 --dry-run

# 跳过已成功生成的函数（增量运行）
python batch_run.py --spec FIPS203 --skip-existing

# 处理多个标准
python batch_run.py --spec FIPS203 FIPS204
```

批量处理按 `data/FIPS203/source/function_layer.json` 定义的 layer 顺序执行，确保依赖函数先于被依赖函数生成。

输出报告：`results/batch_<timestamp>.json` 和 `.md`

### 消融实验

```bash
# 在 FIPS203 上运行全部 4 个消融条件
python ablation_runner.py --spec FIPS203

# 只运行指定条件
python ablation_runner.py --spec FIPS203 --conditions baseline full

# 快速验证（每个条件只处理前 5 个函数）
python ablation_runner.py --spec FIPS203 --limit 5

# 指定输出目录
python ablation_runner.py --spec FIPS203 --output-dir results/exp_01
```

---

## 消融实验设计

系统采用**递进式消融**：从最弱基线出发，逐步叠加组件，量化每个组件的独立贡献。

| 条件         | 提示词 | RAG | 修复 Agent | 说明                          |
| ---------- | :--: | :-: | :------: | --------------------------- |
| `baseline` | ✓    |     |          | 只有提示词，一次生成，不使用 RAG，不修复      |
| `+rag`     | ✓    | ✓   |          | 提示词 + RAG 知识增强，不修复          |
| `+repair`  | ✓    |     | ✓        | 提示词 + 多轮修复 Agent，不使用 RAG    |
| `full`     | ✓    | ✓   | ✓        | 完整系统（提示词 + RAG + 修复 Agent）  |

各条件的详细配置：

| 条件         | `enable_gen_rag` | `enable_fix_rag` | `max_retries` |
| ---------- | :--------------: | :--------------: | :-----------: |
| `baseline` | False            | False            | 0             |
| `+rag`     | True             | True             | 0             |
| `+repair`  | False            | False            | 3             |
| `full`     | True             | True             | 3             |

评估指标：

| 指标                | 含义                       |
| ----------------- | ------------------------ |
| `pass_rate_0`     | 首次翻译直接编译通过率（Pass@Round-0） |
| `pass_rate_final` | 最终编译通过率（含所有修复轮次）         |
| `avg_repair_rounds` | 成功函数的平均修复轮次            |
| `avg_time_s`      | 每函数平均耗时（秒）               |

对比逻辑：
- `full` vs `baseline`：系统整体提升
- `+rag` vs `baseline`：RAG 的净贡献（`pass_rate_0` 差值）
- `+repair` vs `baseline`：修复 Agent 的净贡献（`pass_rate_final` 差值）
- `full` vs `+rag`：在 RAG 基础上叠加修复的额外增益
- `full` vs `+repair`：在修复基础上叠加 RAG 的额外增益

消融实验输出结构：

```
results/
  experiments/
    fips203/
      baseline_20240414_120000/
        batch_results.json      每函数原始结果
        batch_*.json / .md      聚合统计报告
      +rag_20240414_120030/
      +repair_20240414_121000/
      full_20240414_121500/
  fips203/
    ablation_comparison_<ts>.json   跨条件对比数据
    ablation_comparison_<ts>.md     Markdown 表格报告
    ablation_comparison_<ts>.csv    CSV（供 pandas / Excel 分析）
```

---

## 项目结构

```
Agent4Cryptol/
├── agent_workflow.py           单函数处理入口
├── batch_run.py                批量处理入口（按 layer 顺序）
├── ablation_runner.py          消融实验入口
├── report.py                   单次批量运行报告生成
├── report_ablation.py          消融对比报告生成
├── config.yaml                 运行时配置
├── config.example.yaml         配置模板
├── requirements.txt
│
├── data/                       输入规范数据
│   └── FIPS203/
│       ├── ir/functions/       函数 IR（JSON）
│       └── source/
│           └── function_layer.json   函数依赖层级定义
│
├── Cryptol/                    生成的 Cryptol 代码输出
│   └── fips203/
│
├── RAG/                        检索知识库（JSONL）
│   ├── syntax_rules.jsonl
│   ├── syntax_rules_retrieval.jsonl
│   ├── cryptol_patterns.jsonl
│   ├── cryptol_templates.jsonl
│   └── cryptol_guardrails.jsonl
│
├── prompt/                     提示词模板
│   ├── translation_system.txt
│   ├── translation_user.txt
│   ├── fix_system.txt
│   ├── fix_user.txt
│   ├── fix_followup.txt
│   ├── translation_system_simple.txt   消融用简化版
│   └── fix_system_simple.txt           消融用简化版
│
├── workflow/                   核心工作流
│   ├── graph.py                LangGraph DAG 定义
│   ├── nodes.py                7 个节点实现
│   ├── state.py                WorkflowState 定义
│   ├── runner.py               工作流执行入口
│   ├── fix_agent.py            多轮修复 Agent
│   ├── rag.py                  RAG 检索与评分
│   ├── prompts.py              提示词模板管理
│   ├── cryptol_compiler.py     本地 Cryptol 编译器封装
│   ├── dependency_resolver.py  函数间依赖代码加载
│   ├── function_utils.py       函数元数据与文件管理
│   ├── model.py                LLM 工厂
│   ├── settings.py             配置管理（Pydantic + YAML）
│   ├── logging_utils.py        分层日志
│   └── config.py               向后兼容层
│
└── logger/                     运行日志（按函数分目录）
    └── fips203/BitsToBytes/
        ├── <ts>.workflow.log
        ├── <ts>.error.log
        └── fix_prompts/
```

---

## 函数依赖与 layer 顺序

FIPS 函数之间存在调用依赖关系，系统通过 `function_layer.json` 定义生成顺序：

```
layer 0  BitsToBytes, BytesToBits, SampleNTT, NTT, NTTInverse, BaseCaseMultiply
layer 1  ByteEncode_d, ByteDecode_d, SamplePolyCBD, MultiplyNTTs      （依赖 layer 0）
layer 2  K_PKE_KeyGen, K_PKE_Encrypt, K_PKE_Decrypt                   （依赖 layer 1）
layer 3  ML_KEM_KeyGen_Internal, ML_KEM_Encaps_Internal, ...           （依赖 layer 2）
layer 4  ML_KEM_KeyGen, ML_KEM_Encaps, ML_KEM_Decaps                  （依赖 layer 3）
```

高层函数生成时，其依赖的 `.cry` 文件已存在，系统会自动注入依赖代码到提示词中，并通过 `CRYPTOLPATH` 环境变量让编译器找到依赖模块。

---

## 常见问题

**Cryptol 命令找不到**
```yaml
cryptol:
  cmd: C:/path/to/cryptol.exe   # 使用完整路径
```

**依赖模块 not in scope**  
确认依赖函数已按 layer 顺序生成（`Cryptol/fips203/BitsToBytes.cry` 存在），再重新运行当前函数。

**编译超时**
```yaml
cryptol:
  compile_timeout: 60
```

**LLM 认证失败**  
检查 `DASHSCOPE_API_KEY` 环境变量是否正确设置，以及 `config.yaml` 中的 `base_url` 是否与实际 API 端点一致。
