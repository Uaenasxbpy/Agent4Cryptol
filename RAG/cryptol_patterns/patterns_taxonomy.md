# Cryptol Patterns Taxonomy

## 1. 目的

本文件用于约束 `cryptol_patterns.jsonl` 的分类方式、字段含义、命名规范与抽取边界。

它和 `syntax_rules.jsonl` 的定位不同：

- `syntax_rules.jsonl` 解决“什么写法合法、哪些约束不能违反”
- `cryptol_patterns.jsonl` 解决“Cryptol 代码通常如何组织、如何建模、如何复用”

因此，pattern 不是原子语法规则，而是**高复用代码模板/建模套路**。

适用目标：

- 为“规格/伪代码 -> Cryptol”生成提供可复用模板
- 为编译修复阶段提供更高层次的替代写法
- 为 RAG 检索提供“任务 -> 模式”级别的上下文

---

## 2. 设计原则

### 2.1 一条 pattern 只表达一种可复用写法
每条 pattern 应聚焦于一个稳定套路，例如：

- 用 `split` + 类型注解重塑序列
- 用 `[seed] # [...]` 编写 running result / recurrence
- 用 `property f = g === h` 表达函数等价性
- 用 `module ... where` + `private` 组织公开 API 与内部 helper
- 用 `type constraint` 复用尺寸约束

不要把多个不同层次的技巧混在同一条 pattern 中。

### 2.2 pattern 要回答“什么时候用、怎么改”
每条 pattern 至少应能回答：

- 适合什么任务
- 关键结构是什么
- 典型输入输出形态是什么
- 容易犯什么错
- 可以如何改写

### 2.3 优先选择“高复用、强约束、贴近密码建模”的模式
第一版优先抽取：

- sequence reshape
- fold / recurrence / stream equation
- property / prove / check 周边模式
- type-level modeling
- module abstraction
- crypto-oriented structure patterns

### 2.4 pattern 允许包含一小段代码骨架
与语法规则不同，pattern 的核心价值就是“模板化代码骨架”。

因此可以包含：

- `pattern_template`
- `positive_example`
- `variation_notes`

但不要把整页教材原样塞入知识库。

---

## 3. Topic 总体分类

第一版 `cryptol_patterns.jsonl` 使用以下 6 个主 topic。

## 3.1 `sequence_reshape`
用于表达序列、字、矩阵、状态之间的重塑模式。

### 包括
- `split` / `join`
- `transpose`
- `groupBy`
- bitvector 视作 sequence
- 通过显式结果类型驱动重塑
- state/byte/message 之间的变换

### 不包括
- 递推、running result（放入 `fold_recurrence`）
- 单纯的序列合法性语法规则（放入 `syntax_rules.jsonl`）

### 推荐 subtopic
- `typed_split`
- `join_transpose`
- `state_matrix_conversion`
- `word_sequence_view`
- `sequence_comprehension_reshape`

---

## 3.2 `fold_recurrence`
用于表达累积、running result、递推、流方程等模式。

### 包括
- `[seed] # [...]`
- `foldl` / `foldr`
- `scanl`
- 自引用序列
- 并行 comprehension 做 zipper-style recurrence
- stream equation

### 不包括
- 仅仅是 `map` 一类逐元素变换
- 单纯的 sequence slicing

### 推荐 subtopic
- `seeded_running_result`
- `fold_accumulator`
- `scan_running_values`
- `self_referential_stream`
- `parallel_recurrence`

---

## 3.3 `property_verification`
用于表达性质、测试向量、条件性质、证明/检查使用模式。

### 包括
- `property` 声明
- `===` / `!==`
- test-vector style property
- 条件性质 `==>` / `if ... then ... else True`
- 单态化后 `:prove`
- `:check` / `:exhaust` 使用前提

### 不包括
- 具体 REPL 命令全集（那是 tooling）
- 低层求解器参数

### 推荐 subtopic
- `property_as_function`
- `function_equivalence`
- `conditional_property`
- `test_vector_property`
- `monomorphic_proof`

---

## 3.4 `type_level_modeling`
用于表达尺寸多态、类型约束、类型别名、新类型封装等建模模式。

### 包括
- `{n, a}` / `(fin n)` 风格签名
- type demotion `` `n ``
- inline argument type annotations
- `type` / `newtype`
- `type constraint`
- named / positional type application

### 不包括
- enum/case 的纯语法限制
- module parameterization（放入 `module_abstraction`）

### 推荐 subtopic
- `size_polymorphic_signature`
- `type_demotion`
- `inline_arg_types`
- `type_constraint_synonyms`
- `newtype_abstraction`

---

## 3.5 `module_abstraction`
用于表达模块组织、参数化模块、命名空间隔离的模式。

### 包括
- `module ... where`
- hierarchical module names
- qualified import
- `private`
- parameterized module / parameter block
- functor-like instantiation

### 不包括
- FFI
- project file / cache
- REPL tooling

### 推荐 subtopic
- `qualified_import_wrapper`
- `private_helpers`
- `hierarchical_modules`
- `parameter_blocks`
- `module_instantiation`

---

## 3.6 `crypto_structure_patterns`
用于表达密码算法中高频出现的结构性写法。

### 包括
- substitution / permutation lookup
- inverse substitution
- round pipeline
- state transform
- encrypt/decrypt inverse property
- rotor/stream/state style chained update

### 不包括
- 单纯通用函数式模式
- 与密码建模无关的抽象例子

### 推荐 subtopic
- `substitution_lookup`
- `inverse_permutation`
- `round_pipeline`
- `stream_cipher_like_state`
- `encrypt_decrypt_inverse`

---

## 4. JSONL 字段规范

每条 pattern 统一使用下列字段。

### 4.1 必填字段
- `pattern_id`
- `topic`
- `subtopic`
- `title`
- `kind`
- `priority`
- `keywords`
- `intent`
- `pattern_summary`
- `pattern_template`
- `positive_example`
- `applicable_when`
- `source_type`
- `source_file`
- `confidence`

### 4.2 推荐字段
- `rationale`
- `variation_notes`
- `anti_pattern`
- `constraints`
- `retrieval_hints`

### 4.3 字段含义
- `intent`：一句话说明这个 pattern 的目标
- `pattern_summary`：对核心写法的抽象描述
- `pattern_template`：可复用骨架，可带占位符
- `positive_example`：教材/官方风格下的有效实例
- `anti_pattern`：常见误用、低质量替代方案或容易失败的写法
- `variation_notes`：该模式常见变体
- `retrieval_hints`：供检索时增强召回的关键词短语

---

## 5. 命名规范

### 5.1 `pattern_id`
统一格式：

- `pattern_seq_001`
- `pattern_fold_003`
- `pattern_prop_004`
- `pattern_type_006`
- `pattern_mod_002`
- `pattern_crypto_005`

### 5.2 `topic`
固定使用以下值：

- `sequence_reshape`
- `fold_recurrence`
- `property_verification`
- `type_level_modeling`
- `module_abstraction`
- `crypto_structure_patterns`

### 5.3 `priority`
固定使用以下值：

- `high`：对生成质量影响非常大，且高频复用
- `medium`：常用模式，但非所有任务都需要
- `low`：进阶模式或场景较窄

### 5.4 `confidence`
固定使用以下值：

- `high`：可直接从官方/教材材料稳定归纳
- `medium`：从多个例子抽象而来，合理但不是逐字规则

---

## 6. 抽取边界

## 6.1 应纳入 pattern 的内容
- 教材中重复出现的写法骨架
- 官方 primitive 签名支持的常见建模套路
- 示例代码中可复用的局部结构
- 能直接帮助“伪代码 -> Cryptol”的典型模板

## 6.2 不应纳入 pattern 的内容
- 单纯语法合法性说明
- 只包含背景知识、不形成模板的叙述
- 过于具体、无法迁移的长代码
- 某一算法的完整实现全文

---

## 7. 与 `syntax_rules.jsonl` 的关系

推荐使用方式：

1. 先用 `syntax_rules.jsonl` 约束合法写法
2. 再用 `cryptol_patterns.jsonl` 提供结构模板
3. 最后结合编译反馈做修复

一个常见的生成顺序是：

- 先检索 `type_level_modeling.*` 决定签名
- 再检索 `sequence_reshape.*` 或 `fold_recurrence.*` 决定主体结构
- 最后检索 `property_verification.*` 追加性质/测试

---

## 8. 第一版建议覆盖范围

第一版建议先做 15~25 条高价值 pattern，优先顺序如下：

1. `typed_split`
2. `join_transpose`
3. `seeded_running_result`
4. `self_referential_stream`
5. `function_equivalence`
6. `conditional_property`
7. `test_vector_property`
8. `size_polymorphic_signature`
9. `type_demotion`
10. `type_constraint_synonyms`
11. `newtype_abstraction`
12. `qualified_import_wrapper`
13. `private_helpers`
14. `substitution_lookup`
15. `encrypt_decrypt_inverse`

---

## 9. 维护建议

- 新增 pattern 前，先检查是否已被现有 pattern 覆盖
- 优先增加“高频复用模板”，不要先追求数量
- 尽量为每个 pattern 提供简短而完整的代码骨架
- 如果某模式强依赖某个 primitive，建议在 `retrieval_hints` 中加入该 primitive 名称
