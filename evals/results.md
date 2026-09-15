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

report-draft-v5 had not yet been verified against a live model call as
of this entry - see the report-draft-v5 entries below, where it was.

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

## 2026-09-13 - report-draft-v5 - model: Sonnet

**Numeric checks passed; citation corrections required.**

Numeric statements matched the supplied context (no invented,
mis-transposed, or unverified highest/lowest values were found in this
run). Citation formatting and/or citation IDs required correction
before the draft's citations were all valid - see
`app/citation_validator.py` (added this entry's session) for the
offline, non-API check now run against every generated draft: it
confirms each `(source: <source_id>)` citation names a real
`sections[*].source_id` or supported metadata key, and that at least
one citation is present. A passing citation check does not by itself
confirm numeric accuracy, and vice versa - both were assessed
separately for this entry.

## 2026-09-15 - report-draft-v5 - model: Sonnet

**Outcome: PASSED (one reviewed sample).** This confirms only that this
specific draft's citations and numeric claims check out - it is not a
general accuracy guarantee for future report-draft-v5 output.

Source: a saved, unmodified Markdown draft downloaded from the running
app (`portfolio_report_draft.md`, Downloads, generated 2026-09-15). The
download does not carry a model identifier; it is recorded as Sonnet per
the session that generated it, not from anything embedded in the file
itself. Saved verbatim as
[`evals/examples/sonnet-v5-reviewed.md`](examples/sonnet-v5-reviewed.md).

**Citation validation (offline, no API call):** ran
`app.citation_validator.validate_citations()` against
`build_report_context()` on the bundled dataset. Result: `is_valid=True`,
23 citations found, zero unknown IDs, zero malformed citations, zero
unclosed citation groups - including two repeated-prefix multi-source
citations (`source: review_scope_increment; source: computed_facts` and
`source: limitations; source: data_quality`), both parsed correctly.

**Numeric verification (manual cross-check against the calculated
context, no API call):** every quantitative statement in the draft was
compared against the corresponding `build_report_context()` value on the
bundled dataset - portfolio overview (30,000 clients, 6,636 positive
labels, 22.12%); all three repayment-status group counts, portfolio
shares, label rates, and coverage figures; all four credit-limit band
label rates and portfolio shares; the stratified highest/lowest label
rates from `computed_facts.stratified_extrema` (70.74% max at `PAY_0 >=
2` / `50,000-140,000`, 9.89% min at `PAY_0 <= 0` / `> 240,000`); the
undocumented-code pairing from `computed_facts.undocumented_pay0_codes`
(code -2 -> 2,759 clients, code 0 -> 14,737 clients, correctly paired);
Scope A and Scope B's clients, workload share, label rate, and coverage;
and the incremental population's client count, positive-label count,
label rate, and percentage-point coverage gain. All matched exactly, and
`coverage_gain` was correctly labeled in percentage points rather than a
plain percentage.

One drafting artifact, not a numeric error: the Scope B sentence reads
"a label rate of 50.29%, and 50.29%... specifically 51.67% positive-label
coverage" - both 50.29% (Scope B's own label rate) and 51.67% (its
positive-label coverage) are individually correct and distinctly cited,
but the sentence is awkwardly self-corrected mid-clause.

No prompt or code change made for this entry. This is a single reviewed
sample, not a live-model evaluation run over `evals/questions.json` and
not evidence that every report-draft-v5 output will pass citation
validation or numeric review.

**Editorial correction applied (human review, no API call, no
regeneration).** Source-ID citation validation and the numeric
cross-check above both still passed; two wording issues were found on
closer read and corrected by hand. Both versions are kept:
[`evals/examples/sonnet-v5-reviewed.md`](examples/sonnet-v5-reviewed.md)
is the original, unmodified raw draft;
[`evals/examples/sonnet-v5-human-reviewed.md`](examples/sonnet-v5-human-reviewed.md)
is the corrected, clearly human-edited copy. Only the two items below
changed - no cited number, source ID, or other wording was altered.

1. The Scope B sentence's mid-clause drafting artifact ("a label rate of
   50.29%, and 50.29%... specifically 51.67% positive-label coverage")
   was corrected to state each value once: a label rate of 50.29% and a
   positive-label coverage of 51.67%. Both figures were already
   individually correct; only the garbled duplication was removed.
2. The Limitations section's undefined-rate explanation was corrected.
   The original wording ("a segment with zero clients or zero positive
   labels" makes a rate undefined) conflates two different cases: an
   undefined rate depends on its own denominator being zero, not merely
   a segment-level zero anywhere. A segment with zero clients has an
   undefined label rate (0/0); a portfolio with zero positive labels
   overall has undefined positive-label coverage. A segment with a
   nonzero client count but zero positive labels instead has a real,
   defined label rate of 0% - this case was previously, incorrectly,
   implied to be undefined too.
