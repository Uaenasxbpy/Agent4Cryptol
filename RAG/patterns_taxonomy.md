# Cryptol Patterns Taxonomy (Optimized)

## 1. 目的

本文件是对现有 `cryptol_patterns.jsonl` 的第二版整理，目标不是扩大数量，而是提高“规格/伪代码 -> Cryptol”与“编译修复”两个阶段的命中率。

相较旧版，本版做了两个关键调整：

- 明确承认并正式纳入 `imperative_to_functional`
- 增加一层与失败样例强相关的 pattern 设计准则，尤其覆盖：
  - 动态循环边界
  - 异构状态表示
  - 生成器作用域
  - 索引位宽链
  - 缺失依赖时的保守降级

---

## 2. 与 `syntax_rules.jsonl` 的边界

- `syntax_rules.jsonl`：回答“什么写法合法 / 什么写法会报错”
- `cryptol_patterns.jsonl`：回答“当要表达这种算法结构时，Cryptol 里通常怎么写”

pattern 不是硬语法，而是**高复用建模套路**。  
只要一条模式能显著减少你前面案例中的失败，就值得入库。

---

## 3. Topic 总体分类

本版建议使用以下 7 个主 topic。

### 3.1 `sequence_reshape`
用于序列、字、矩阵、状态之间的重塑与重排。

推荐 subtopic：
- `typed_split`
- `join_transpose`
- `state_matrix_conversion`
- `word_sequence_view`
- `sequence_comprehension_reshape`
- `generator_scoped_helper`

### 3.2 `fold_recurrence`
用于 running result、递推、流方程、自引用序列。

推荐 subtopic：
- `seeded_running_result`
- `fold_accumulator`
- `scan_running_values`
- `self_referential_stream`
- `parallel_recurrence`

### 3.3 `property_verification`
用于 `property`、等价性、条件性质、测试向量与证明前骨架。

### 3.4 `type_level_modeling`
用于尺寸多态、type demotion、位宽桥接、索引/算术域分离。

推荐 subtopic：
- `size_polymorphic_signature`
- `type_demotion`
- `inline_arg_types`
- `type_constraint_synonyms`
- `newtype_abstraction`
- `index_domain_vs_arithmetic_domain`
- `small_conversion_helpers`

### 3.5 `module_abstraction`
用于模块组织、qualified import、private helper、参数化模块，以及缺依赖时的保守骨架。

推荐 subtopic：
- `qualified_import_wrapper`
- `private_helpers`
- `hierarchical_modules`
- `parameter_blocks`
- `module_instantiation`
- `conservative_unresolved_skeleton`

### 3.6 `crypto_structure_patterns`
用于密码算法中的高频结构写法。

推荐 subtopic：
- `substitution_lookup`
- `inverse_permutation`
- `round_pipeline`
- `stream_cipher_like_state`
- `encrypt_decrypt_inverse`
- `precomputed_table_lookup`

### 3.7 `imperative_to_functional`
正式纳入核心 taxonomy。用于把命令式伪代码翻成纯函数式 Cryptol。

推荐 subtopic：
- `mutable_update_rewrite`
- `nested_fold_translation`
- `heterogeneous_state_accumulator`
- `loop_strategy_selection`
- `value_level_recursion_for_dynamic_counts`

---

## 4. 新增收录优先级

相比旧版，下面这些 pattern 的优先级应明显上升：

1. 运行时循环边界改写为 value-level recursion
2. 混合类型状态改写为 tuple / record accumulator
3. 生成器变量作用域安全改写
4. 索引域与算术域分离
5. 缺失依赖时的 conservative unresolved skeleton
6. 使用权威常量表而不是二次推导 helper

---

## 5. 检索建议

### 5.1 生成阶段
建议顺序：

1. `syntax_rules_retrieval`
2. `cryptol_guardrails`
3. `cryptol_patterns`
4. `cryptol_templates`
5. `cryptol_examples`

### 5.2 修复阶段
建议顺序：

1. 编译器错误
2. `cryptol_guardrails`
3. `syntax_rules_retrieval`
4. `cryptol_patterns`
5. `cryptol_examples`

原因：  
你前面很多失败并不是“没有 DES 例子”，而是缺少 guardrail 与循环/状态建模模式。

---

## 6. 抽取边界

优先纳入：
- 能直接压制高频失败类型的模式
- 能稳定迁移到 ML-KEM / SHAKE / DES 之外的通用骨架
- 代码短、结构清晰、可直接粘贴进 prompt 的模式

不建议纳入：
- 纯语法硬约束（放回 syntax rules）
- 只对单个算法有效且很难迁移的大段实现
- 依赖未提供 primitive 才能看懂的长代码

---

## 7. 维护建议

- `cryptol_patterns.jsonl` 中凡是与循环改写、状态线程、索引位宽、缺失依赖相关的条目，建议长期单独抽样评估
- 若一个 pattern 主要来源于失败修复经验，而不是教材/官方示例，也可以纳入，但 `source_type` 要诚实标为 `assistant_curated`
- 如果后续拿到可靠的 ML-KEM / SHAKE 可编译实例，再优先补 examples，而不是继续堆抽象 pattern
