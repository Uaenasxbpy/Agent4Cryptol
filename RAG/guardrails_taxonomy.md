# Cryptol Guardrails Taxonomy

## 1. 目的

`cryptol_guardrails.jsonl` 不是官方语法手册摘要，也不是普通代码模板库。  
它的用途是：把**高频失败案例**沉淀成可检索的“生成/修复防撞栏”。

它主要回答下面这类问题：

- 这段代码虽然看起来像 Cryptol，但为什么仍然高风险？
- 哪种局部修补方式其实在继续把代码往错误方向推？
- 遇到这类报错时，应该先重建表示方式，还是先修括号/类型？

---

## 2. 与其他层的关系

- `syntax_rules.jsonl`：语言硬规则
- `cryptol_patterns.jsonl`：常见建模套路
- `cryptol_templates.jsonl`：可直接复用的短骨架
- `cryptol_examples.jsonl`：真实代码参考
- `cryptol_guardrails.jsonl`：失败导向的防错规则

Guardrail 适合放在 retrieval 链路较前位置，因为它们经常能在模型动手写代码之前就阻断错误表示方式。

---

## 3. 推荐字段

每条 guardrail 建议至少包含：

- `guardrail_id`
- `phase`
- `priority`
- `title`
- `trigger`
- `rule`
- `positive_strategy`
- `anti_pattern`
- `applicable_when`
- `derived_from_cases`
- `retrieval_tags`
- `retrieval_text`

---

## 4. 推荐分类角度

### 4.1 按 phase
- `generation`
- `repair`

### 4.2 按常见触发器
- scope / `not in scope`
- type/value confusion
- runtime length vs finite sequence
- heterogeneous state packing
- index width chain mismatch
- missing dependency / pseudo-complete body
- parameter-family ambiguity

---

## 5. 何时应优先检索 guardrails

### 生成阶段
当任务包含以下特征时，应在 pattern/template 之前先检索 guardrails：

- 动态循环边界
- 多层命令式循环
- 异构状态
- 依赖未提供的外部 primitive
- 参数只解析到 family 而未解析到具体值
- comprehension + helper 的组合

### 修复阶段
当报错呈现以下信号时，应优先检索 guardrails：

- `not in scope`
- `unexpected =`
- `Expected a type named ... but found a value instead`
- `Ambiguous numeric type`
- `Type mismatch` 且与索引/位宽相关
- 修复两轮后仍在同一区域打转

---

## 6. 边界

适合写进 guardrails 的内容：
- 从多次失败中稳定抽象出来的防错策略
- 与“先重建表示方式还是先补局部语法”有关的判断
- 能直接改变修复顺序的高价值规则

不适合写进 guardrails 的内容：
- 单纯的语法合法性
- 普通可复用代码骨架
- 某个算法的完整实现细节
