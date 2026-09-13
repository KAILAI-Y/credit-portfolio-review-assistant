# AI Evaluation Results

Recorded outcomes for `app/assistant.py`'s report-draft generation
against `evals/questions.json`, per SPECS.md Section 7. Each entry
records the model, evaluation date, and prompt version; a passing
result on this finite set does not guarantee correctness of all future
answers.

## 2026-09-13 - report-draft-v3 - model: unknown

**Outcome: FAILED.** This is not a passing evaluation.

Source: a saved, human-reviewed Markdown draft downloaded from the
running app (`portfolio_report_draft.md`). The download does not carry
a model identifier, so it is recorded as unknown here rather than
guessed. Prompt version is report-draft-v3, the version in effect when
the draft was generated.

Findings:

1. **Unverified "highest" claim** (`highest-lowest-claims-verified`).
   The draft stated that the lowest credit-limit band combined with
   `PAY_0 >= 2` produced the highest stratified default rate (69.07%),
   but another row in the same stratified-summary section was higher
   (70.74%). The claim was not checked against every row before being
   stated.
2. **Quartile language over-generalized**
   (`quartile-language-scoped-correctly`). The draft described both
   repayment-status groups and credit-limit bands as derived from
   historical quartiles. Only credit-limit bands are quartile-derived;
   repayment-status groups are fixed `PAY_0` code groupings.
3. **"Validated" used where the source states the opposite**
   (`scope-evaluation-language`). The supplied Limitations text says
   scopes were assessed on the historical sample and were *not*
   validated for new clients or later periods. The draft inverted this
   to "validated only on the same historical sample," implying
   validation had occurred.
4. **Trade-offs section omitted incremental counts**
   (`trade-offs-include-incremental-counts`). The Review-Scope
   Trade-offs section reported rates and a percentage-point coverage
   gain but not the incremental population's absolute client and
   positive-label counts, even though both were present in the supplied
   context (`review_scope_increment`).

Remediation: `SYSTEM_PROMPT` was bumped to report-draft-v4 with general
rules (not tied to this dataset's specific numbers) requiring: cross-row
verification before any highest/lowest claim; quartile language scoped
to whichever segmentation the context actually defines that way;
"evaluated on the same historical sample" instead of "validated"; and
incremental client/positive-label counts in scope trade-off discussion.

This entry was recorded from a manual review of a previously saved
draft, not a newly executed live evaluation run. report-draft-v4 has
not yet been verified against a live model call.

## 2026-09-13 - report-draft-v3 - model: Claude Haiku 4.5

**Outcome: FAILED.** This is not a passing evaluation. report-draft-v4's
fixes above had not yet been sent to a live model when this draft was
generated, so this is a second, independent failure of report-draft-v3.

Source: a saved, human-reviewed Markdown draft downloaded from the
running app (`portfolio_report_draft (1).md`).

Findings:

1. **Unverified "highest" claim, repeated**
   (`highest-lowest-claims-verified`). The draft again stated 69.07%
   (`PAY_0 >= 2`, <= 50,000 TWD) as the highest stratified default rate;
   the true maximum in the same section is 70.74%.
2. **Invented interpretation of an undocumented code**
   (`no-invented-pay0-interpretation`, new). The draft described
   `PAY_0 <= 0` as "current or ahead," an interpretation not present
   anywhere in the supplied context - codes 0 and -2 are explicitly
   documented there as having no known interpretation.
3. **Code/count pairing reversed**
   (`code-count-pairing-not-reversed`, new). The draft reported "2,759
   and 14,737 clients respectively" for codes "0 and -2," transposing
   the two counts (the correct pairing is code 0 -> 14,737 clients,
   code -2 -> 2,759 clients).
4. **Incremental positive-label count omitted**
   (`trade-offs-include-incremental-counts`). The draft stated the
   incremental client count (3,688) and the coverage-gain percentage
   points, but never stated the incremental positive-label count
   (1,252).

Remediation: `app/report_context.py` now computes these facts in Python
and adds them to the context as a new `computed_facts` section -
`stratified_extrema` (the exact max/min row labels and rate),
`undocumented_pay0_codes` (explicit `{pay0_code, client_count}` records,
not a mapping the model must pair itself from prose), and
`scope_increment` (both incremental counts together) - so the model is
told the answer rather than asked to derive or recall it.
`app/assistant.py`'s `SYSTEM_PROMPT` was bumped to report-draft-v5,
requiring the draft to use `computed_facts` verbatim for any
highest/lowest claim, to retain each segment's exact supplied label
without an invented interpretation, to keep each code paired only with
its own record's count, and to always state both incremental counts
together. These rules are general (not tied to this dataset's specific
numbers or labels) and were verified with independently hand-calculated
synthetic examples in `tests/test_report_context.py`, not against this
dataset's own figures.

report-draft-v5 has not yet been verified against a live model call.

## 2026-09-13 - report-draft-v5 - model: Claude Haiku 4.5

**Outcome: FAILED.** This is not a passing evaluation.

Finding: the draft again reversed the undocumented-code pairing -
`code-count-pairing-not-reversed` - reporting the counts for PAY_0 codes
0 and -2 swapped.

**Input data vs. model output (verified by direct inspection, no API
call):** ran `build_report_context()` on the bundled dataset and printed
the `computed_facts.undocumented_pay0_codes` records actually sent to
the model:
`[{"pay0_code": -2, "client_count": 2759}, {"pay0_code": 0, "client_count": 14737}]`.
Cross-checked independently against `df["PAY_0"].value_counts()` on the
raw CSV: code `0` -> 14,737 clients, code `-2` -> 2,759 clients. Both
match. **The input context given to the model is correct - this is a
model-output error, not an input-data error.** report-draft-v5's
`computed_facts` records already pair each code with its own count
explicitly; the model still transposed them in prose.

No prompt or code change made for this entry - recorded as a checkpoint
per the requesting instruction. A further prompt revision (e.g.
requiring the draft to quote each `{pay0_code, client_count}` record
inline rather than restating counts in free text) would need its own
version bump and synthetic-data test before another live call.
