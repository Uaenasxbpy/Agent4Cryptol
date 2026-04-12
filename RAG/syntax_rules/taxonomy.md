# Cryptol Syntax Rules Taxonomy

## 1. 目的

本文件用于约束 `syntax_rules.jsonl` 的分类方式、字段含义、命名规范与抽取边界。
它不是主知识库，而是主知识库的**分类标准**与**录入规范**。

适用目标：
- 为 Cryptol 代码生成提供高精度规则约束
- 为编译报错修复提供可定位的语法/类型规则
- 为后续 RAG 检索提供稳定的 topic / subtopic 元数据

---

## 2. 设计原则

### 2.1 一条规则只表达一个原子约束
每条 rule 应只表达一个稳定、独立、可复用的规则点，例如：
- 标识符命名约束
- `module ... where` 的写法
- record selector 的使用限制
- `case` 分支必须穷尽
- `newtype` 与 `type` 的区别

不要把多个不相关规则塞进同一条记录。

### 2.2 优先保留“硬约束”和“高频模式”
优先抽取以下三类内容：
- **硬约束**：不满足就会语法错误、类型错误或模块错误
- **限制条件**：只有满足条件时才合法
- **高频模式**：在代码生成时高频出现，能显著降低错误率

### 2.3 不按长度切块，按语义切块
`syntax_rules.jsonl` 不是文档分块结果，而是规则库。
切分单位是“规则语义单元”，不是 token 长度。

### 2.4 示例优先
每条规则尽量提供：
- 正例 `positive_example`
- 反例 `negative_example`

对代码生成约束来说，示例比长篇解释更有用。

---

## 3. Topic 总体分类

第一版核心规则库只使用以下 5 个主 topic。

## 3.1 `basic_syntax`
用于描述基础语法层面的规则。

### 包括
- declarations
- layout / indentation
- comments / docstrings
- identifiers
- reserved keywords
- operator precedence
- numeric literals
- type signatures
- numeric constraint guards

### 不包括
- 表达式绑定范围（放入 `expressions`）
- tuple / record / sequence 数据结构规则（放入 `basic_types`）
- `type` / `newtype` / `enum` 声明（放入 `type_declarations`）
- 模块系统（放入 `modules`）

### 推荐 subtopic
- `declarations`
- `layout`
- `comments`
- `docstrings`
- `identifiers`
- `keywords`
- `operator_precedence`
- `numeric_literals`
- `type_signatures`
- `numeric_constraint_guards`

---

## 3.2 `expressions`
用于描述表达式级别的语法与语义约束。

### 包括
- function application
- prefix / infix parsing
- type annotations 的绑定范围
- explicit type instantiation
- local declarations
- block arguments
- conditionals
- demoting numeric types to values

### 不包括
- sequence 类型本身的定义（放入 `basic_types`）
- `case` 对 enum 的约束（放入 `type_declarations`）
- module/import 规则（放入 `modules`）

### 推荐 subtopic
- `function_application`
- `prefix_infix_operators`
- `type_annotations`
- `type_instantiation`
- `local_declarations`
- `block_arguments`
- `conditionals`
- `type_demotion`

---

## 3.3 `basic_types`
用于描述 Cryptol 基础数据结构及其常见操作规则。

### 包括
- tuples
- records
- field selectors
- field updates
- sequences
- sequence operators
- sequence patterns
- lambda / function syntax

### 不包括
- `type` / `newtype` / `enum` 类型声明（放入 `type_declarations`）
- 模块组织（放入 `modules`）

### 推荐 subtopic
- `tuples`
- `records`
- `field_selectors`
- `field_updates`
- `sequences`
- `sequence_patterns`
- `functions`

---

## 3.4 `type_declarations`
用于描述类型声明与代数数据类型相关规则。

### 包括
- type synonyms
- newtypes
- enums
- constructors
- case expressions
- deriving
- exhaustiveness / no-overlap constraints

### 不包括
- 单纯的表达式级 `if` / `where`（放入 `expressions`）
- 模块参数化（放入 `modules`）

### 推荐 subtopic
- `type_synonyms`
- `newtypes`
- `enums`
- `constructors`
- `case_expressions`
- `deriving`

---

## 3.5 `modules`
用于描述模块系统与跨文件组织规则。

### 包括
- module declarations
- hierarchical module names
- imports
- import lists
- hiding imports
- qualified imports
- private blocks
- submodules
- interface modules
- parameter blocks
- module instantiation

### 不包括
- REPL / project tooling
- FFI 的 C 映射细节

### 推荐 subtopic
- `module_declarations`
- `hierarchical_names`
- `imports`
- `import_lists`
- `hiding_imports`
- `qualified_imports`
- `private_blocks`
- `submodules`
- `interface_modules`
- `parameter_blocks`
- `module_instantiation`

---

## 4. 暂不纳入核心 `syntax_rules.jsonl` 的内容

以下内容建议单独维护为扩展知识库，而不是混入首版核心语法规则库：

### 4.1 `repl_tooling_rules.jsonl`
来源：
- `REPLCommands.md`

适合收录：
- `:t`
- `:check`
- `:prove`
- `:safe`
- `:generate-foreign-header`
- `:set monoBinds`

### 4.2 `project_rules.jsonl`
来源：
- `ProjectFiles.md`

适合收录：
- `cryproject.toml`
- `--project`
- project cache

### 4.3 `ffi_rules.jsonl`
来源：
- `ForeignFunctionInterface.md`

适合收录：
- `foreign`
- C calling convention
- abstract calling convention
- Cryptol/C type mapping

---

## 5. JSONL 字段规范

每条规则记录是一行 JSON，对应一个规则对象。

### 5.1 必填字段
- `rule_id`
- `topic`
- `subtopic`
- `title`
- `kind`
- `priority`
- `keywords`
- `rule`
- `positive_example`
- `applicable_when`
- `source_type`
- `source_file`
- `confidence`

### 5.2 推荐字段
- `rationale`
- `negative_example`
- `constraints`
- `notes`

### 5.3 字段含义

#### `rule_id`
规则唯一标识，建议格式：
- `syntax_basic_001`
- `syntax_expr_003`
- `syntax_types_007`
- `syntax_tdecl_004`
- `syntax_modules_010`

#### `topic`
一级分类，必须取自本文件定义的 topic：
- `basic_syntax`
- `expressions`
- `basic_types`
- `type_declarations`
- `modules`

#### `subtopic`
二级分类，使用小写下划线命名。

#### `title`
规则标题，简洁明确，适合展示给人读。

#### `kind`
规则类型，建议从下面选择：
- `syntax_rule`
- `typing_rule`
- `module_rule`
- `pattern_rule`
- `semantic_rule`

#### `priority`
规则优先级：
- `high`：极易导致编译失败或严重偏离
- `medium`：重要但不一定立即报错
- `low`：风格、辅助、低频高级特性

#### `keywords`
用于检索增强的关键词数组。应尽量包含：
- 语法关键字
- 运算符
- 常见报错关联 token

#### `rule`
规则本体。要求是一句或几句**可执行、可约束**的描述，不要照抄长段文档。

#### `positive_example`
合法或推荐写法。

#### `negative_example`
错误写法、易错写法或高风险写法。不是所有规则都必须有。

#### `constraints`
列出额外前提、限制条件或补充要求。

#### `applicable_when`
描述本规则在什么生成场景下应被检索出来。

#### `source_type`
来源类型。当前统一使用：
- `official_manual`

#### `source_file`
来源文件名，例如：
- `BasicSyntax.md`
- `Expressions.md`
- `BasicTypes.md`
- `TypeDeclarations.md`
- `Modules.md`

#### `confidence`
人工抽取置信度：
- `high`
- `medium`
- `low`

---

## 6. 命名规范

### 6.1 `rule_id`
使用固定前缀 + 三位编号：

- `syntax_basic_001`
- `syntax_expr_001`
- `syntax_types_001`
- `syntax_tdecl_001`
- `syntax_modules_001`

### 6.2 `topic`
统一小写，使用下划线连接单词。

### 6.3 `subtopic`
统一小写，不使用空格，不使用驼峰。

### 6.4 `keywords`
保持短词和符号混合：
- 可放关键字：`module`, `import`, `where`
- 可放运算符：`::`, `@`, `#`
- 可放术语：`selector`, `annotation`, `exhaustive`

---

## 7. 抽取规则时的判断标准

当你从官方资料中看到一段说明时，按下面顺序判断是否入库：

### 7.1 这是硬约束吗？
如果不遵守会直接导致：
- parse error
- type error
- module resolution error
- pattern coverage error

若是，优先入库。

### 7.2 这是带前提的合法性条件吗？
例如：
- selector 只有在类型已知时才合法
- numeric constraint guards 只支持 numeric literal constraints
- `case` 必须穷尽且模式不能重叠

若是，优先入库。

### 7.3 这是高频生成模式吗？
例如：
- `module X where`
- `import M as P`
- `f (x : [8]) = ...`
- `type T = [8]`

若是，建议入库。

### 7.4 只是背景介绍吗？
如果只是概念解释、实现背景、工程说明，不建议放到核心 syntax 规则库。

---

## 8. 编写规则的推荐模板

```json
{
  "rule_id": "syntax_modules_001",
  "topic": "modules",
  "subtopic": "qualified_imports",
  "title": "Qualified imports require qualified references",
  "kind": "module_rule",
  "priority": "medium",
  "keywords": ["import", "as", "qualified", "::"],
  "rule": "After `import M as P`, imported names should be referenced as `P::name`.",
  "rationale": "Qualified imports avoid name collisions and make symbol origin explicit.",
  "positive_example": "import M as P\nx = P::f",
  "negative_example": "import M as P\nx = f",
  "constraints": [
    "Qualified imports may be combined with import lists or hiding clauses"
  ],
  "applicable_when": [
    "generating module imports",
    "avoiding name collisions"
  ],
  "source_type": "official_manual",
  "source_file": "Modules.md",
  "confidence": "high"
}
```

---

## 9. 第一版建议规模

建议第一版先做 **20–30 条高价值规则**，不要一开始做成几百条。

推荐顺序：
1. `basic_syntax`
2. `expressions`
3. `basic_types`
4. `type_declarations`
5. `modules`

---

## 10. 建议目录

```text
knowledge_base/
  syntax_rules/
    taxonomy.md
    syntax_rules.jsonl
    extraction_notes.md
```

其中：
- `taxonomy.md`：分类法与标注规范
- `syntax_rules.jsonl`：正式规则数据
- `extraction_notes.md`：抽取进度和待补说明
