# Examples and Templates Taxonomy for Cryptol RAG (Optimized)

## 1. Purpose

Examples and templates are still implementation-reference layers, but in your current pipeline they should be treated as **late-stage support**, not the first line of defense.

The main lesson from the recent failures is:

- examples help when the task is structurally similar to an existing implementation
- templates help when the structure is known but details differ
- neither one replaces guardrails for scope, type/value separation, dynamic loop bounds, or missing dependencies

---

## 2. Current practical limitation

Your current example layer is DES-heavy.  
That is still useful, but it means:

- DES-like structural retrieval is strong
- ML-KEM / SHAKE / CBD / NTT-specific retrieval is still mostly pattern-driven, not example-driven

So this layer should stay small and clean, but it should not be expected to solve every generation failure by itself.

---

## 3. When to use examples vs templates

### 3.1 Use examples first when
- you need a real working-looking reference
- you want a nearby Cryptol artifact for a similar algorithm step
- the target code is structurally close to an existing example
- the missing piece is “how this kind of thing is typically written”

### 3.2 Use templates first when
- you need a generic skeleton
- the algorithm family is different but the code shape is reusable
- you want a short prompt-friendly scaffold
- the target function is still under-specified

---

## 4. Retrieval order

### 4.1 Generation tasks
Recommended order:

1. `syntax_rules_retrieval`
2. `cryptol_guardrails`
3. `cryptol_patterns`
4. `cryptol_templates`
5. `cryptol_examples`

### 4.2 Repair tasks
Recommended order:

1. compiler feedback / failing code summary
2. `cryptol_guardrails`
3. `syntax_rules_retrieval`
4. `cryptol_patterns`
5. `cryptol_examples`

### 4.3 Why this order
Many recent failures came from:
- dynamic loop bounds forced into finite sequence shapes
- heterogeneous state modeled as a sequence
- generator variables leaking out of comprehensions
- missing dependencies hidden behind comments

Those are guardrail/pattern problems before they are example problems.

---

## 5. Coverage policy

### 5.1 Keep examples small
Preferred chunk size remains:
- 1 function
- 1 property
- 1 constant block
- 1 coherent helper block

### 5.2 Keep templates shorter than examples
Templates should remain:
- short enough to paste into prompts directly
- neutral enough to adapt across algorithms
- explicit about holes and usage notes

### 5.3 Prefer trustworthy examples over many examples
Do not ingest failed or guessed generated code as examples.  
If a source is not known-good, keep it out of the example layer and encode the lesson as:
- a syntax rule
- a pattern
- or a guardrail

---

## 6. New template priorities

Compared with the old DES-first extraction plan, the next high-value templates to add are:

- tuple/record loop accumulator
- value-level recursion for dynamic loop bounds
- generator-scoped helper pattern
- authoritative constant-table lookup
- conservative unresolved skeleton for missing primitives

These are useful across DES, ML-KEM, SHAKE, NTT, CBD, and generic spec translation.

---

## 7. Compile-status discipline

Keep `compile_status` honest:

- `compiles_cleanly`
- `needs_external_dependency`
- `compile_error`
- `unverified_in_session`

Do not promote a code fragment to “example” quality just because it looks plausible.  
If the environment cannot verify it, keep the uncertainty explicit.

---

## 8. Practical recommendation

In your current stage, examples/templates should be viewed as:

- **reference support**
- **shape support**
- **prompt support**

but not as the main mechanism for preventing scope/type/loop-strategy mistakes.

That prevention job should move earlier in retrieval, via syntax + guardrails + patterns.
