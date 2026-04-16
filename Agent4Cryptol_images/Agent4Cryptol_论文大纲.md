# Agent4Cryptol: A Multi-Agent Framework for Translating Standard Algorithm Specifications into Cryptol



# Abstract

1. **问题背景**：将密码标准文档中的算法规范翻译为 Cryptol 具有重要价值，但人工建模成本高，且标准文档存在排版噪声、隐含参数和跨段落约束；通用 LLM 对 Cryptol 这类强类型、小众形式化语言的生成稳定性不足。
2. **方法概述**：提出 Agent4Cryptol，一个由 Spec2IR Agent、IR2Cryptol Agent 和 Compilation-Fix Agent 组成的多智能体闭环框架，将标准文档翻译为可编译的 Cryptol 模块。
3. **核心机制**：引入面向标准算法文档的中间表示 IR、面向 Cryptol 的专用 RAG 知识库、受控提示模板，以及 compiler-in-the-loop 的自动修复机制。
4. **实验结论**：在 FIPS 203/204/205 构建的 benchmark 上，Agent4Cryptol 显著提升 compile success rate 并降低平均修复轮数；同时，在带官方测试向量或可执行参考实现的子集上，生成结果表现出一定程度的语义有效性。

> 摘要最后一段正式写作时建议至少放一个具体数字，例如“将 compile success rate 从 X% 提升到 Y%”。

---

# I. Introduction

## 1.1 Problem Background

- 形式化密码算法建模是标准实现验证、等价性验证和安全分析的重要基础。
- Cryptol 适合描述位级语义与算法规格，但其语法、类型和模块约束严格，生成质量高度依赖精确的结构信息。
- 标准算法文档通常由伪代码、正文描述、参数表和上下文约束组成，信息分散，且经常存在：
  - 输入输出未显式标注
  - 参数隐藏于正文
  - 算法依赖跨页、跨节出现
  - 同一算法在不同 parameter set 下具有不同实例化方式
- 因此，从标准文档直接端到端生成 Cryptol，既是文档理解问题，也是结构化建模和受约束代码生成问题。

## 1.2 Motivation

- 人工将标准文档翻译为 Cryptol 周期长、成本高，且容易遗漏隐藏参数、类型约束和依赖关系。
- 直接 prompting 往往会同时暴露三类失败模式：
  1. 文档排版噪声干扰模型理解；
  2. 算法结构未被显式建模，导致输入输出与控制流失真；
  3. 模型迁移主流语言先验，产生 Haskell-like 幻觉、错误 import 或不合法运算符用法。
- 因此，这一任务更适合采用“文档理解 → 结构化表示 → 受控生成 → 编译反馈修复”的 staged multi-agent pipeline，而非单轮直接生成。

## 1.3 Key Idea

Agent4Cryptol 的核心思想是不直接从原始文档一步到位生成最终代码，而是将任务拆分为三个互补的 agent：

1. **Spec2IR Agent**：把非结构化标准文档抽取成统一的中间表示 IR；
2. **IR2Cryptol Agent**：基于结构化 IR、Cryptol 专用知识库与受控提示模板生成初版代码；
3. **Compilation-Fix Agent**：利用 Cryptol 编译器报错进行 patch-based 修复，直到得到可编译结果或超过预算终止。

## 1.4 What the Paper Solves—and What It Does Not

- 本文首要解决的是：**从标准文档稳定生成可编译、类型正确、模块结构合法的 Cryptol 代码**。
- 这对应的是 **syntactic correctness / type correctness**。
- 但对于形式化密码学建模而言，真正更强的目标是 **semantic correctness**，即生成代码与标准语义行为一致。
- 因此，本文将 compile success rate 明确界定为**阶段性代理指标**，并在可行子集上进一步报告基于测试向量或参考实现的 semantic pass rate，以避免将“可编译”误表述为“完全正确”。

## 1.5 Contributions

1. 提出 **Agent4Cryptol**，一个面向标准算法文档到 Cryptol 的多智能体闭环生成框架。
2. 设计一个面向标准算法建模的 **Intermediate Representation (IR)**，显式编码函数元信息、输入输出、正文伪代码、隐含参数和 parameter-set 绑定关系，从而连接文档理解与形式化代码生成。
3. 提出面向 Cryptol 的 **specialized generation + compiler-in-the-loop repair** 机制，将领域知识检索、受控提示和编译器反馈结合起来，提升小众形式化语言生成的稳定性。
4. 构建一个覆盖 FIPS 203/204/205 的多层 benchmark，并从端到端有效性、消融、修复效率、错误模式以及受限语义验证等多个角度系统评估 Agent4Cryptol。

---

# II. Background

## 2.1 Cryptol and Formal Modeling

- Cryptol 是一种面向规格描述与验证的领域语言，擅长位向量、序列和参数化类型建模。
- 与主流编程语言相比，Cryptol 有如下特征：
  - 强类型、类型约束严格；
  - 模块边界与命名规则严格；
  - 对位级运算、序列切片、宽度推导高度敏感；
  - 少量语法偏差就可能导致模块无法加载。
- 因此，针对 Cryptol 的代码生成不仅要求“看起来像代码”，更要求模块能被编译器接受，并尽可能保留规范语义。

## 2.2 Standard Algorithm Documents

标准密码文档通常由以下成分构成：

- algorithm box / pseudocode block
- 正文中的文字解释
- 参数表与参数实例
- 符号约定、边界条件和注释说明

其主要困难包括：

- 规范信息分散，难以单点读取；
- 参数常以自然语言形式嵌入正文，而非集中列出；
- 同一函数在不同参数集下有不同实例化；
- 算法调用关系跨页出现，依赖不易直接恢复。

## 2.3 LLM-based Multi-Agent Systems

- 多智能体系统通过任务分解，将复杂流程拆成若干更可控的子任务。
- 对本文而言，任务天然可以分为：
  - 文档理解
  - 结构化表示构建
  - 约束代码生成
  - 编译错误修复
- 因此，相比单 agent，multi-agent pipeline 更能匹配问题结构本身。

## 2.4 Compiler Feedback and Repair

- 对形式化语言而言，编译器不仅是执行前检查器，更是可靠的结构约束来源。
- 编译器返回的错误位置、作用域信息、类型不匹配提示，可以直接作为修复信号。
- 因此，compiler-in-the-loop 往往比纯自然语言自反思更有效，尤其适合 Cryptol 这类高约束语言。

---

# III. Agent4Cryptol Methodology

## 3.1 Overall Framework

**输入与输出**

- **Input:** standard algorithm documents
- **Output:** compilable, type-correct Cryptol modules

**总体流程**

**Standard Document → Spec2IR Agent → IR JSON → IR2Cryptol Agent → Draft Cryptol → Compilation-Fix Agent → Final Cryptol**

**框架特征**

- 整体是**串行闭环**；
- 前两步负责“理解与生成”；
- 最后一步负责“验证与修复”；
- 若超过最大修复轮数则终止并记录失败样例。

**建议图示内容**

图中建议显式标出：

- document parsing path
- IR storage / index
- RAG retrieval path
- compiler feedback loop
- final success / failure branch

## 3.2 Intermediate Representation Design

### 3.2.1 Why IR Is Necessary

IR 的作用不只是“把文档转成 JSON”，而是承担四个关键功能：

1. **去噪（denoising）**：剥离 PDF 排版、分页和冗余自然语言噪声；
2. **结构统一（structural normalization）**：把不同标准文档中的算法统一成相同 schema；
3. **生成约束（generation grounding）**：为后续代码生成提供显式、稳定、可引用的结构化输入；
4. **可检查性（inspectability）**：便于做 schema 校验、交叉验证和数据集质检。

### 3.2.2 Design Goals

建议明确写出 IR 设计目标：

- **G1. Minimal but sufficient**：字段尽量少，但必须覆盖生成所需的核心信息；
- **G2. Explicit parameter binding**：参数来源与 parameter set 绑定关系必须可追踪；
- **G3. Function-level modularity**：支持一个函数一个 JSON 文件，便于索引、检索和逐函数翻译；
- **G4. Cross-function extensibility**：可被 function index 和 dependency graph 扩展；
- **G5. Model-friendly serialization**：字段命名和组织方式适合 LLM 读取与引用。

### 3.2.3 IR Schema

建议在正文中放一个代表性 JSON 示例，并在附录中放完整 schema。正文示例可如下：

```json
{
  "function_id": "alg_003_bits_to_bytes",
  "name": "BitsToBytes",
  "label": "Algorithm 3",
  "page_start": 20,
  "page_end": 20,
  "inputs": [
    {
      "name": "b",
      "type": "bit_array",
      "description": "Bit array of length multiple of 8"
    }
  ],
  "outputs": [
    {
      "name": "B",
      "type": "byte_array",
      "description": "Converted byte array"
    }
  ],
  "body_raw": [
    "B ← (0, … , 0)",
    "for (i ← 0; i < 8ℓ; i ++)",
    "    B[⌊i/8⌋] ← B[⌊i/8⌋] + b[i] ⋅ 2^(i mod 8)",
    "end for",
    "return B"
  ],
  "layer": 0,
  "dependencies": {
    "direct_calls": [],
    "parameterized_calls": [],
    "trusted_primitives": [],
    "support_functions": [],
    "import_strategy": "none"
  },
  "parameter_resolution": {
    "active_parameter_set": "ML-KEM-512",
    "project_mode": "specialized_code_generation",
    "fixed_parameters": {
      "n": 256,
      "q": 3329,
      "k": 2,
      "eta1": 3,
      "eta2": 2,
      "du": 10,
      "dv": 4
    },
    "local_symbols_detected": [],
    "resolved_symbols": [
      {
        "symbol": "n",
        "value": 256,
        "source": "document_constant"
      }
    ],
    "specializations": [],
    "translation_note": "该函数本身与参数集弱相关，可直接生成通用实现。"
  }
}
```

### 3.2.4 Field Design Rationale

建议逐类说明字段为什么这样设计：

- **function_id / name / label / pages**：用于索引、追溯和结果对齐；
- **inputs / outputs**：显式给出接口边界，避免模型从正文中猜测；
- **body_raw**：保留原始伪代码顺序，作为最核心语义载体；
- **parameter_refs**：显式列出本函数涉及的参数名，便于后续检索 parameter_sets；
- **parameter_binding**：解决同一算法在不同 parameter set 下的实例化差异；
- **dependencies**：为后续多函数联合翻译与调用图驱动翻译预留接口；
- **notes.hidden_constraints**：容纳正文中隐式但关键的条件信息。

### 3.2.5 Edge Cases and Parameter Set Handling

这一部分要专门解释“隐藏参数”和“多参数实例”问题。

- 对显式参数，直接写入 inputs 或 parameter_refs；
- 对隐藏于正文的参数，写入 `notes.hidden_constraints` 或 `parameter_binding`；
- 对 parameter-set-specific 的实例化，如 Kyber-512 / 768 / 1024，统一写入全局 `parameter_sets.json`，并在函数级 IR 中通过 `parameter_binding` 建立引用，而不是把所有实例值硬编码进单函数正文。

### 3.2.6 Relation to Existing Structured Representations

建议明确区分本文 IR 与现有结构化表示：

- **不同于 AST**：AST 面向源代码语法树，而本文输入是标准文档，不具备现成编程语言语法；
- **不同于 OpenAPI / schema-only 格式**：本文 IR 不只是接口签名，还保留了算法伪代码主体与隐藏约束；
- **不同于纯 extraction JSON**：本文 IR 的目标不是存档，而是为后续 Cryptol 生成提供稳定中间层。

## 3.3 Spec2IR Agent

Spec2IR Agent 负责从标准文档中抽取结构化 IR，是整个系统的文档理解前端。

**输入**

- PDF / 标准文档页面
- 算法框、章节文本、参数描述
- 算法标签与页码信息

**输出**

- 单函数 JSON
- `function_index.json`
- `parameter_sets.json`
- 可选的 `dependency_graph.json`

**核心子任务**

1. 算法定位与切分；
2. 伪代码块提取；
3. 输入输出识别；
4. 隐含参数抽取；
5. label / page 对齐；
6. 函数依赖识别；
7. schema 校验与缺失项标记。

** 输出质量控制**

建议加入以下自动校验：

- JSON schema validation；
- `function_index` 与单函数文件的数量一致性检查；
- `parameter_refs` 与 `parameter_sets` 的交叉检查；
- 重复函数、缺页函数、空 body 函数的异常标记。

## 3.4 IR2Cryptol Agent

IR2Cryptol Agent 负责把结构化 IR 翻译成初版 Cryptol 代码。

**输入**

- 单函数 IR JSON
- `parameter_sets.json`
- Cryptol RAG 检索结果
- 提示词模板与 few-shot 示例

** 输出**

- 初版 Cryptol 模块

** 核心机制**

- 基于 IR 的受控生成；
- Cryptol 专用 RAG；
- few-shot / one-shot 示例；
- 语法与模块命名约束；
- 针对常见幻觉模式的显式提示。

**为什么 IR 比原始文档更利于生成**

- 原始文档中参数、正文和上下文分散，模型容易误绑定；
- IR 把接口、伪代码主体和参数引用显式分层；
- 生成模型不再需要先做文档重建，而只需完成结构到代码的映射。

### 3.4.1 Cryptol-specific RAG Design

这一节必须单列说明。

**知识库来源**

RAG 知识库建议由三部分组成：

1. **官方语法与语义规则**：如 Cryptol manual 中的模块声明、函数定义、序列/位向量、类型约束等；
2. **可编译模式库**：人工整理的 compilable snippets、idioms、模板和常见写法；
3. **错误经验库**：历史编译报错与对应修复示例，例如 import 错误、作用域错误、类型宽度不匹配等。

**检索粒度**

建议明确三种粒度：

- **Rule-level**：语法规则、类型规则、模块规范；
- **Pattern-level**：常见位操作、序列转换、参数化函数写法；
- **Example-level**：少量完整的可编译函数示例。

**检索策略**

- 先根据 IR 中的 `function_name`、`inputs/outputs`、`parameter_refs`、`body_raw` 提取检索 query；
- 分层检索 rule / pattern / example 三类片段；
- 再通过 reranking 过滤低相关片段，避免噪声干扰生成。

**如何避免 RAG 干扰**

建议明确写出三条控制原则：

1. 优先短而精确的语法规则，不堆砌长文档；
2. 每类知识最多返回固定数量片段；
3. 对与当前函数无关的库函数、证明语法和高级特性进行过滤。

## 3.5 Compilation-Fix Agent

Compilation-Fix Agent 负责利用编译器反馈修复初版代码。

**输入**

- 初版 Cryptol 代码
- 编译器错误消息
- 上一轮修复历史
- 原始 IR 与相关 RAG 片段

**输出**

- 修复后的 Cryptol 代码

**流程**

1. 调用 Cryptol 编译 / 加载；
2. 收集并结构化错误信息；
3. 对错误进行分类；
4. 生成局部 patch；
5. 回写并重新编译；
6. 成功则终止，失败则进入下一轮。

**错误分类**

- syntax error
- scope / name resolution error
- type mismatch
- import / module error
- operator misuse
- width / sequence shape inconsistency

**关键设计**

- **error message structuring**：提取位置、错误类型、相关标识符；
- **patch-based repair**：尽量做局部修复而非整段重写；
- **history-aware repair**：保留修复历史，避免反复震荡；
- **bounded iteration**：设置最大轮数，控制成本并保留失败案例用于分析。

## 3.6 Implementation Details

建议写清楚以下内容：

- agent orchestration framework（如 LangGraph / workflow engine）
- RAG 索引构建与检索接口
- Cryptol compiler wrapper
- 中间产物与日志保存方式
- 修复终止条件
- failure recovery 与异常记录方式

---

# IV. Experimental Evaluation

实验部分建议严格写成 **RQ-driven**，同时显式区分 **syntactic correctness** 与 **semantic correctness**。

## 4.1 Research Questions

建议定义 4 个 RQ：

- **RQ1 (End-to-End Effectiveness):** Agent4Cryptol 相比直接 prompting，能在标准文档到 Cryptol 的端到端任务上带来多大的 compile success 提升？
- **RQ2 (Value of Structured IR):** 将非结构化文档转为 IR 后，是否能显著提升后续代码生成的稳定性与可控性？
- **RQ3 (Contribution of Specialized Generation and Repair):** 在给定 IR 的前提下，专用 IR2Cryptol Agent 与 Compilation-Fix Agent 各自贡献了多少性能提升？
- **RQ4 (Semantic Validity on a Verified Subset):** 在具备官方测试向量或可执行参考实现的子集上，compile-success 的样例中有多少能够通过基础行为验证？

> 修复效率可以作为 5.4 的 Additional Analysis，而不再错误挂在 RQ3 名下。

## 4.2 Benchmark / Dataset Construction

**三层数据组织**

1. **Document Layer**：标准 PDF、章节、算法页码与标签；
2. **IR Layer**：单函数 JSON、`parameter_sets.json`、`function_index.json`、可选依赖图；
3. **Code Layer**：人工编写或人工校正的 Cryptol 参考答案。

**数据来源**

- FIPS 203  21个函数
- FIPS 204  49个函数
- FIPS 205  25个函数

**必须补充的可复现性信息**

这一节要明确写出：

- 共抽取多少个函数；
- 来自多少份标准文档；
- 覆盖多少个 parameter set 实例；
- 有多少样例具备 reference Cryptol 或可执行参考实现；
- 有多少样例可进行测试向量验证。

**参考答案构建方式**

建议明确：

- 初始参考答案由具备 Cryptol / 标准文档背景的作者或研究助理编写；
- 之后由另一名标注者进行人工校正；
- 若存在歧义，由第三人复核或协商定稿；
- 最终得到 gold / silver 两级参考答案：
  - **gold**：可编译且通过人工审定；
  - **silver**：可编译但仅经过单人校正。

**难度分级标准**

Easy / Medium / Hard 不要只写概念，要写可操作规则。建议如下：

- **Easy**：无跨函数依赖；隐藏参数少；位操作或局部循环为主；
- **Medium**：存在 parameter-set 实例化、条件分支或中等长度循环；
- **Hard**：存在跨函数依赖、隐藏参数、复杂索引/数学语义或对外部原语依赖。

最好给出每级至少一个判定标准，如：

- 隐含参数数量
- 依赖函数数量
- 伪代码行数
- 是否涉及外部 primitive

## 4.3 End-to-End Baselines and System Variants

这一节必须补上 **B3.5**。

| Variant | Spec2IR | Specialized IR2Cryptol | Compilation-Fix |
|---|---:|---:|---:|
| **B1** Direct Prompting | ✗ | ✗ | ✗ |
| **B2** Prompting + Fix | ✗ | ✗ | ✓ |
| **B3** Spec2IR + Prompting | ✓ | ✗ | ✗ |
| **B3.5** Spec2IR + Prompting + Fix | ✓ | ✗ | ✓ |
| **B4** Spec2IR + IR2Cryptol | ✓ | ✓ | ✗ |
| **B5** Agent4Cryptol (Full) | ✓ | ✓ | ✓ |

**每个变体的作用**

- **B1**：衡量无框架直接生成的效果；
- **B2**：衡量仅靠修复闭环是否足够；
- **B3**：衡量 IR 结构化本身的增益；
- **B3.5**：控制变量后，单独观测“IR + 修复”但无专用生成器时的效果；
- **B4**：衡量专用生成器的增益；
- **B5**：完整系统。

这样之后：

- **B1 → B3** 看 IR 的价值；
- **B3 → B3.5** 看在无专用生成器时 Fix Agent 的价值；
- **B3.5 → B5** 看专用生成器在带修复闭环情况下的额外价值；
- **B4 → B5** 看 Fix Agent 在 full setting 下的兜底能力。

## 4.4 Evaluation Metrics

这一节要分成两层：

### 4.4.1 IR-stage Metrics

- **Schema Validity**：IR 是否满足预定义 schema；
- **Function Coverage**：抽取到的函数数量是否与人工索引一致；
- **Field Completeness**：输入、输出、页码、label、body 等关键字段完整率；
- **Cross-file Consistency**：单函数 JSON、`function_index.json`、`parameter_sets.json` 间的一致性。

### 4.4.2 Cryptol-stage Syntactic Metrics

- **Compile Success Rate**：最终模块是否成功编译/加载；
- **Initial Compile Rate**：未经 Fix Agent 时的初始可编译率；
- **Repair Success Rate**：进入修复后最终被救回的比例；
- **Average Repair Iterations**：平均修复轮数；
- **Pass@k**：多次采样场景下的最优成功率。

### 4.4.3 Semantic Metrics on a Verified Subset

- **Vector Pass Rate**：对具备官方测试向量的样例，生成结果通过测试向量的比例；
- **Reference Equivalence Pass Rate**：与参考实现或参考 Cryptol 行为一致的比例；
- **Conditional Semantic Pass Rate**：在“先可编译”的前提下，通过基础行为验证的比例。

### 4.4.4 指标解释原则

建议明确写一句：

> Compile success rate 主要衡量 syntactic / type correctness，而非完整 semantic correctness；因此本文在可验证子集上额外报告 semantic metrics，以评估 compile success 作为代理指标的有效程度。

## 4.5 Experimental Setup

建议至少报告：

- base model / model version
- decoding settings（temperature, top-p）
- prompt templates
- RAG corpus composition
- 检索器与 reranker 配置
- Cryptol compiler version
- 最大修复轮数
- 硬件环境
- 重复次数与随机种子

---

# V. Results and Analysis

## 5.1 RQ1: End-to-End Effectiveness

建议先给主结果表，比较 B1–B5 在 Easy / Medium / Hard 上的 compile success rate。

**主要论点**

- B5 相比 B1 显著提升 compile success rate，说明 staged multi-agent pipeline 的整体有效性；
- 难度越高，full system 的优势越明显，说明框架对复杂样例更有价值；
- 若能提供 semantic subset 结果，也可在这一节先给一个总览列。

## 5.2 RQ2: The Value of Structured IR

重点比较 **B1 vs B3**。

**主要论点**

- IR 显式暴露函数接口、参数引用和正文主体，减少了模型对原始 PDF 噪声的误读；
- 对存在隐藏参数和 parameter binding 的样例，IR 的收益尤为明显；
- IR 同时提高了输入可解释性，使后续失败分析更容易进行。

可以补一个小案例：同一个函数在 B1 中遗漏隐藏参数，但在 B3 中由于 IR 中存在 `parameter_binding` 或 `hidden_constraints` 而生成正确。

## 5.3 RQ3: The Contribution of Specialized Generation and Repair

这一节建议按三段展开：

### 5.3.1 B3 vs B4: The Value of Specialized Generation

- 解释为何在已有 IR 的前提下，专门面向 Cryptol 的 IR2Cryptol Agent 仍然必要；
- 强调其优势来自：
  - Cryptol RAG
  - few-shot examples
  - 显式语法约束
  - 对常见 Haskell 幻觉的抑制。

### 5.3.2 B3 vs B3.5: The Value of Fix without Specialized Generation

- 这一步是新增后才能成立的分析；
- 它回答“只有 IR + Prompting 时，Fix Agent 能救回多少错误”。

### 5.3.3 B4 vs B5: The Value of Fix in the Full Pipeline

- 分析 Fix Agent 在 full system 中的兜底作用；
- 重点展示它修回了哪些典型错误：
  - 命名错误
  - import 错误
  - 模块声明错误
  - 局部类型不一致。

## 5.4 RQ4: Semantic Validity on a Verified Subset

这一节用于正面回应“compile success ≠ semantic correctness”。

**建议报告方式**

- 从全 benchmark 中选出带官方测试向量、公开 reference implementation，或能构造基础行为检查的子集；
- 报告：
  - compile success 样例数
  - 其中通过 vector/reference check 的样例数
  - 条件 semantic pass rate

**主要论点**

- compile success 并不自动等价于语义正确，但它对 semantic validity 具有一定预测作用；
- full system 在 verified subset 上优于 baseline，说明 staged generation 不只是“把代码写得像”，而是在一定程度上提升了行为有效性。

## 5.5 Additional Analysis: Efficiency and Repair Iteration

这一节不再冒充 RQ，而作为附加分析。

**重点比较**

- B2 vs B3.5 vs B5

**主要论点**

- B2 虽然有 Fix Agent，但初始草稿质量低，平均修复轮数高，且常无法收敛；
- B3.5 说明 IR 可降低修复难度；
- B5 则进一步说明“更好的初稿 + 修复闭环”才是高效率收敛的关键。

建议统计：

- 平均修复轮数
- 第一次成功轮次分布
- 超过最大轮数的失败占比

---

# VI. Discussion

## 6.1 Why IR Matters

这一节从更高层总结：

- IR 不是简单的数据格式，而是系统稳定性的核心接口层；
- IR 同时提升了 controllability、inspectability 和 debuggability；
- 对形式化语言生成而言，中间表示比“端到端大 prompt”更重要。

## 6.2 Common Error Patterns

这一节建议必须量化，而不是只列名字。

**建议错误类别**

- import / module declaration errors
- operator misuse
- type mismatch / width mismatch
- missing hidden parameters
- function dependency mismatch
- Haskell-like hallucination

**建议报告方式**

给出每类错误在失败样例或修复样例中的占比，例如：

| Error Type | Percentage | Typical Cause |
|---|---:|---|
| Import / module error | xx% | Incorrect module declaration or illegal import style |
| Type / width mismatch | xx% | Missing width constraints or wrong sequence sizes |
| Hidden parameter omission | xx% | Parameter only described in prose |
| Haskell-like hallucination | xx% | Transfer from mainstream functional language prior |

然后再解释为什么 Fix Agent 要做 patch-based repair，为什么 RAG 要重点覆盖规则与模式而非长文档。

## 6.3 Limitations

### 1. Error Cascading in Dependent Functions

当前框架以单函数或自底向上生成为主。对于存在深层函数依赖的算法，如果底层函数逻辑错误，错误会沿调用链向上传播。未来可引入 dependency graph 约束、接口契约生成或联合多函数修复机制。

### 2. External Primitive Dependency

对于依赖外部复杂密码学原语（如 SHA-3）的函数，当前系统通常采用抽象接口声明或占位模块方式，以保证当前函数的类型检查能够通过。这意味着部分结果只达到局部可编译，而非完整跨模块可执行。

### 3. Limited Semantic Verification Coverage

本文目前仍以 compile success 为主要评估指标。虽然我们在可验证子集上加入了测试向量或参考实现对齐，但完整端到端 semantic verification 的覆盖范围仍有限。未来可结合 Cryptol property testing、SAW 等工具，进一步实现从 type-correct generation 到 equivalence-level verification 的过渡。

---

# VII. Related Work

建议 Related Work 的总体顺序改为：

1. 专用语言 / DSL / 形式化语言代码生成
2. agent-based code generation and repair
3. specification-to-code / document-to-code
4. formal modeling and cryptographic specification languages

## 7.1 LLM-based Code Generation for Specialized Languages

- 小众语言、DSL、形式化语言上的代码生成工作；
- 强调此类任务通常比 Python/Java 更依赖约束、模板与反馈闭环。

**本文定位**

与上述工作不同，本文面向的是 **Cryptol** 这类对语法、类型和模块边界极其敏感的形式化规格语言。对这类语言而言，单纯依赖 LLM 泛化能力往往不足，必须引入结构化中间层与编译器反馈。

## 7.2 Multi-Agent Code Generation and Repair

- ChatDev
- MetaGPT
- MapCoder
- AgentCoder
- AutoSafeCoder

**本文定位**

与这些通用多智能体代码生成系统相比，本文不追求通用软件工程流程，而是面向“标准文档 → 形式化语言”这一高约束窄任务，重点在于 IR grounding、Cryptol-specific RAG 和 compiler-guided repair。

## 7.3 Specification-to-Code / Document-to-Code

- 从自然语言、规范、伪代码到程序代码的工作；
- 可以涵盖 PLC、协议实现、规范驱动代码生成等方向。

**本文定位**

已有 doc-to-code 工作主要面向 Python、Java、C 等主流语言，尚缺少针对密码标准文档到形式化语言的系统性研究。本文聚焦的不是通用代码生成，而是面向密码标准的形式化建模。

## 7.4 Formal Modeling and Cryptographic Specification Languages

- Cryptol
- SAW
- 形式化规格与密码学建模工作

**本文定位**

现有 Cryptol / SAW 相关工作更多关注人工建模、验证工作流和等价性证明；本文进一步关注标准文档到 Cryptol 的自动化生成问题，尝试将 LLM-based agent 技术引入形式化建模前端。

---

# VIII. Conclusion and Future Work

## Conclusion

结论建议收束为三点：

1. Agent4Cryptol 提供了一个从标准文档到可编译、类型正确 Cryptol 代码的多智能体闭环框架；
2. 以 IR 为中心的 staged pipeline 和 compiler-in-the-loop repair 显著提升了 Cryptol 生成的稳定性；
3. 在可验证子集上的结果表明，该框架不仅提升了 syntactic correctness，也在一定程度上改善了 semantic validity。

## Future Work

- 引入 SAW / property-level verification；
- 支持多函数联合生成与联合修复；
- 引入 dependency-graph-driven 拓扑翻译；
- 扩展 benchmark 规模与标准覆盖范围；
- 增强 parameter instantiation 与跨算法上下文推理；
- 引入更系统的语义验证协议与官方测试向量集成。

