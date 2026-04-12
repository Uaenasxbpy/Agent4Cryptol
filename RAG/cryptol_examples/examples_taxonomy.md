# Examples and Templates Taxonomy for Cryptol RAG

## 1. Purpose

This layer stores **real Cryptol code artifacts** that are meant to be retrieved as implementation references.

It is intentionally separate from:

- `syntax_rules.jsonl`: hard constraints and legality rules
- `cryptol_patterns.jsonl`: reusable structural idioms
- `cryptol_examples.jsonl`: real code examples and constant tables
- `cryptol_templates.jsonl`: abstracted code skeletons derived from examples

The goal of this layer is to answer two different questions:

- **Examples:** “Is there already a real Cryptol implementation that looks like what I need?”
- **Templates:** “Is there a code skeleton I can start from and adapt?”

---

## 2. Core separation

### 2.1 `cryptol_examples.jsonl`
Each entry is a **real code unit** extracted from a source `.cry` file.

Typical units:
- module overview
- function
- property
- constant table
- helper definition block

### 2.2 `cryptol_templates.jsonl`
Each entry is an **abstract template** derived from one or more examples.

Templates should:
- preserve code shape
- replace algorithm-specific details with holes
- keep usage notes explicit
- remain small enough to paste into prompts directly

---

## 3. Topic taxonomy

### 3.1 `crypto_structure_patterns`
Use for algorithm-structure code, especially ciphers and hash-style pipelines.

Subtopics:
- `cipher_api_binding`
- `round_pipeline`
- `feistel_round`
- `round_function_pipeline`
- `key_schedule_entry`
- `key_schedule_rotate_select`
- `permutation_tables`
- `chunked_sbox_pipeline`
- `sbox_lookup_bit_slicing`
- `lookup_tables`

### 3.2 `sequence_reshape`
Use for shape conversion, block splitting, concatenation, flattening, and table-driven rearrangement.

Subtopics:
- `half_swap`
- `permutation_table_application`
- `split_join_reshape`
- `matrix_state_conversion`

### 3.3 `fold_recurrence`
Use for self-referential lists, running states, accumulators, and fold-like Cryptol idioms.

Subtopics:
- `running_prefix_accumulator`
- `round_state_recurrence`
- `stream_equation`
- `running_results`

### 3.4 `type_level_modeling`
Use for code that bridges specification-level notation and Cryptol’s type/index discipline.

Subtopics:
- `spec_table_index_normalization`
- `type_constraint_helper`
- `bitwidth_bridge`
- `named_type_abstraction`

### 3.5 `module_abstraction`
Use for code that demonstrates modularization, import structure, qualified names, interfaces, and functor-like parameterization.

Subtopics:
- `module_header`
- `qualified_import`
- `private_helpers`
- `parameterized_module`

### 3.6 `property_verification`
Use for properties, equivalence checks, test-vector capture, and validation-oriented helpers.

Subtopics:
- `equivalence_property`
- `inverse_property`
- `conditional_property`
- `test_vector_property`

---

## 4. Example entry schema

Each example should include:

- `example_id`
- `kind`
- `title`
- `source_type`
- `source_file`
- `module_name`
- `algorithm_family`
- `topic`
- `subtopic`
- `code`
- `retrieval_tags`
- `retrieval_text`

Recommended fields:

- `code_start_line`
- `code_end_line`
- `symbols_defined`
- `symbols_used`
- `input_signature`
- `explanation`
- `idioms`
- `compile_status`
- `compile_scope`
- `compile_notes`
- `dependencies`
- `quality`

### 4.1 Allowed `kind` values
- `module_overview`
- `function`
- `property`
- `constant_table`
- `helper_block`

### 4.2 Allowed `compile_status` values
- `compiles_cleanly`
- `needs_external_dependency`
- `compile_error`
- `unverified_in_session`

Use `unverified_in_session` when the current environment cannot actually run the Cryptol toolchain.

---

## 5. Template entry schema

Each template should include:

- `template_id`
- `template_type`
- `title`
- `topic`
- `subtopic`
- `derived_from`
- `template_code`
- `holes`
- `retrieval_tags`
- `retrieval_text`

Recommended fields:

- `source_examples`
- `usage_notes`
- `quality`

### 5.1 Allowed `template_type` values
- `code_skeleton`
- `rewrite_pattern`
- `property_skeleton`

---

## 6. Extraction rules

### 6.1 What counts as an example
Keep a code fragment as an example if at least one is true:

- it defines a reusable algorithmic step
- it shows a nontrivial Cryptol idiom
- it is a standard constant-table pattern
- it is likely to be useful as retrieval context for generation or repair

### 6.2 What counts as a template
A template should not be just a verbatim copy of an example.
A template must:
- remove algorithm-specific constants where possible
- introduce holes with descriptions
- preserve the implementation structure
- keep the final code skeleton short

### 6.3 Preferred chunk size
For examples:
- 1 function
- 1 property
- 1 constant block
- 1 coherent helper block

For templates:
- 5 to 15 lines is usually ideal

---

## 7. Retrieval guidance

### 7.1 Query types suited for examples
Use examples first when the user asks for:
- “a working reference”
- “a similar implementation”
- “how DES/AES-like code is written”
- “how to model this real algorithm step in Cryptol”

### 7.2 Query types suited for templates
Use templates first when the user asks for:
- “a skeleton”
- “a generic version”
- “how to start writing this”
- “how to turn this algorithm idea into Cryptol”

### 7.3 Combined retrieval
For generation tasks, preferred order is:
1. `syntax_rules`
2. `cryptol_patterns`
3. `cryptol_templates`
4. `cryptol_examples`

For repair tasks, preferred order is:
1. compiler feedback / error fixes
2. `syntax_rules`
3. `cryptol_examples`

---

## 8. Naming conventions

### 8.1 Example IDs
Pattern:
- `des_func_round_001`
- `aes_table_sbox_001`
- `sha_helper_schedule_001`

Format:
- `<algorithm>_<kind>_<name>_<index>`

### 8.2 Template IDs
Pattern:
- `template_feistel_round_001`
- `template_permutation_table_apply_001`

Format:
- `template_<subtopic>_<index>`

---

## 9. First-pass coverage for DES

For a DES-like source file, the first extraction pass should usually preserve:

- one module overview
- core encryption function
- one Feistel round
- round f-function
- key schedule entry
- key schedule expansion
- cumulative-shift helper
- 1-based to 0-based table conversion helper
- permutation tables
- S-box application function
- per-S-box lookup function
- S-box constant tables

This first-pass set is enough to support both example retrieval and template derivation.

---

## 10. Practical note

This taxonomy is meant to stabilize the dataset before large-scale ingestion.

Do not optimize embedding strategy first.
First make sure the example/template records are:
- small
- semantically labeled
- easy to inspect manually
- traceable back to source files and line ranges
