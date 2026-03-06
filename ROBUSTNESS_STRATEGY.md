# Superbill Agent Robustness Strategy

## 1) Core Problem Statement

Current output drift comes from three main sources:

- Retrieval mismatch: wrong code families are retrieved for the note context.
- Prompt ambiguity: model has too much freedom when context is sparse.
- Postprocess over-correction: many local rules can conflict and create instability.

Goal: make decisions stable across note types using a **retrieval-first, constrained-generation** design.

## 2) Clean Architecture (Target)

Use a strict 4-stage pipeline:

1. **Context Extraction**
	 - Normalize note fields (chief complaint, HPI/history, exam, assessment, procedure facts).
	 - Emit a compact structured summary (`encounter_facts`) with predictable keys.

2. **Knowledge Retrieval**
	 - Retrieve procedure, ENM, and modifier candidates with explicit type filters.
	 - Keep top-k per category and rank by encounter fit (site, visit type, patient type, complexity).

3. **Constrained LLM Selection**
	 - Prompt receives:
		 - encounter facts
		 - ranked candidates
		 - policy text
	 - LLM must choose only from candidate codes.

4. **Thin Postprocess**
	 - Parse JSON, normalize formats, dedupe, and output audit trails.
	 - Avoid adding medical decisions that were not selected by LLM/candidate policy.

## 3) Decision Stability Rules

- No note-specific hardcoding.
- No fallback to previous superbill for final coding.
- Candidate set determines output space (prevents hallucinated codes).
- If candidate confidence is low, return `needs_review` rather than forcing code.

## 4) Retrieval Quality Plan

Implement a retrieval quality layer:

- Build separate candidate pools:
	- `procedure_candidates`
	- `enm_candidates`
	- `modifier_candidates`
- Add ranking signals:
	- visit type (office/new/follow-up)
	- diagnosis overlap
	- procedure evidence overlap
	- facility/place-of-service compatibility
- Persist retrieval diagnostics in output:
	- chosen candidate IDs/codes
	- rejected top candidates + reason

## 5) Prompt Contract (Must-Have)

The prompt should enforce:

- Return valid JSON only.
- Choose CPT/E/M/modifier only from provided candidates.
- Every selected code must include evidence sentence from encounter facts.
- If no valid candidate exists, output empty list + explicit reason.

## 6) Evaluation Harness

Create a small regression suite (20-50 representative notes):

- Track:
	- CPT precision/recall vs historical audited target
	- E/M presence + level agreement
	- modifier agreement
	- run-to-run variance (same note, repeated runs)
- Gate changes on score improvements, not anecdotal note checks.

## 7) Immediate Next Steps

1. Freeze postprocess to normalization-only behavior.
2. Add retrieval ranking output payload (`candidate_reasoning`).
3. Update prompt to candidate-constrained selection.
4. Build baseline regression report and compare every change.

This keeps the system robust with less ad-hoc validation code and more stable, explainable decision paths.

## 8) Repo Implementation Backlog (File-Level)

### A) Add `note_fact_extractor_llm` stage

- Create [src/agent/fact_extractor_node.py](src/agent/fact_extractor_node.py)
	- Input: `notes`, `biopsy`, `mohs`, `prescriptions` (without previous superbill)
	- Output: `encounter_facts` with strict keys:
		- `visit_type`, `patient_type`, `documented_procedures`, `documented_dx`, `sites`, `laterality`, `closure_type`, `evidence_snippets`
	- Rule: if unknown, return `unknown` (no guessing)
- Create extraction prompt in [src/services/prompts.py](src/services/prompts.py)
	- Add a dedicated extractor prompt template with JSON schema contract

### B) Add `candidate_selection_node`

- Create [src/agent/candidate_selection_node.py](src/agent/candidate_selection_node.py)
	- Input: `encounter_facts`, `retrieval`
	- Output:
		- `procedure_candidates`
		- `enm_candidates`
		- `modifier_candidates`
		- `candidate_reasoning`
	- Ranking score components:
		- diagnosis overlap
		- procedure evidence overlap
		- visit/facility compatibility
		- add-on pairing compatibility

### C) Constrain final coding node

- Update [src/agent/llm_node.py](src/agent/llm_node.py)
	- Pass only `encounter_facts`, candidates, policy text
	- Do not pass broad raw contexts once extractor is live
- Update coding prompt in [src/services/prompts.py](src/services/prompts.py)
	- Hard rule: selected CPT/E/M/modifiers must be from candidates
	- Require per-code evidence citation text from `encounter_facts.evidence_snippets`

### D) Keep postprocess thin

- Refactor [src/agent/postprocess_node.py](src/agent/postprocess_node.py)
	- Keep only parse/normalize/dedupe/audit
	- Do not add new coding decisions
	- Preserve `modifier_decisions` and `em_decisions` as transparent output only

### E) Wire graph order

- Update [src/agent/graph.py](src/agent/graph.py)
	- New order:
		1. notes/biopsy/mohs/prescriptions
		2. retrieval
		3. fact extractor
		4. candidate selection
		5. coding llm
		6. postprocess

## 9) Acceptance Criteria Per Stage

### Fact Extractor
- Output always valid JSON with required keys.
- Unknowns explicit (`unknown`), no empty implicit guesses.
- At least one evidence snippet for every non-unknown field.

### Candidate Selection
- Candidate pools never empty when retrieval has matching types.
- Ranking includes score + reason for top candidates.
- Office notes should prioritize `estPat/newPat/consult` ENM over preventive `other` unless evidence indicates preventive.

### Final Coding
- 0 hallucinated codes outside candidates.
- Every selected row has evidence-linked reasoning.
- If no valid candidate exists, output `needs_review=true` with reason.

### Postprocess
- No business-rule invention.
- Stable deterministic output shape.

## 10) Regression & Release Checklist

### Benchmark Set
- Build `eval/notes_gold.jsonl` with 200+ notes (balanced across note types).
- Include expected CPT/E/M/modifiers/ICD + short adjudication notes.

### Evaluation Script
- Add [eval/run_eval.py](eval/run_eval.py)
	- Metrics:
		- CPT exact match
		- E/M family + level agreement
		- modifier agreement
		- run-to-run variance across 3 repeated runs/note

### CI Gate
- Add threshold policy (example):
	- CPT exact >= 0.85
	- E/M agreement >= 0.90
	- modifier agreement >= 0.75
	- variance <= 0.05

### Production Rollout
- Stage rollout: 10% → 50% → 100%
- Daily drift report for first 2 weeks
- Human-review queue for `needs_review=true`

## 11) Priority Order (Do First)

1. Implement `fact_extractor_node` schema + prompt.
2. Implement `candidate_selection_node` with scoring.
3. Constrain final coding LLM to candidates only.
4. Add eval harness + thresholds.
5. Remove remaining non-essential prompt complexity.

This is the shortest path to stable, explainable, and scalable coding decisions without piling on ad-hoc validations.
