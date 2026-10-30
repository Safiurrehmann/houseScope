# One live development baseline

One actual Luna analysis was run on the public 56-page Kentucky inspection report. It used five section calls, 56,894 input tokens and 9,036 output tokens. Recorded token-based cost was **$0.0102074**; original pipeline duration was **82.7 seconds**. No additional model run was made to refine local postprocessing.

The model returned 52 observations. Initial local consolidation produced 32 records, including inspection limitations. The initial reference-match precision and recall were each 95.8%, with 95.7% detail citation localization on matched references.

The observed errors were:

- The additional smoke-detector recommendation on page 18 continued the page-17 finding without repeating its inspection reference. Initial binding treated it as a separate, unmatched prediction.
- The mystery-switch observation was classified as a limitation in the detail extraction. Its summary/detail kind disagreement is now visible as a review flag. It remains a missed defect in the original-extraction evaluation until the model output or independent evaluation definition changes. Human correction does not alter that score.

A local continuation adapter was added. It requires a following recommendation page, no new numbered section, and at least two shared subject terms with the preceding detail heading. The source record identifies the inferred continuation and parent page. Using **the same saved model output**, local replay merged the extra detector passage and produced 31 records.

| Development metric | Initial processing | After local refinement |
|---|---:|---:|
| Reference-match precision | 95.8% (23/24) | 100% (23/23) |
| Reference coverage / recall | 95.8% (23/24) | 95.8% (23/24) |
| Detail-page quote + coordinate localization | 95.7% (22/23) | 100% (23/23) |
| Unmatched defect predictions | 1 | 0 |
| Missed labeled defects | 1 | 1 |
| Additional model calls for refinement | — | 0 |

The priority policy was also tightened so prevention language about moisture and missing bulbs does not automatically imply an urgent damage condition. A reviewer can correct observation type, description, location or priority with append-only provenance.

## Interpretation limits

These are reference matching and mechanical localization metrics on **one agent-curated development fixture**. The same example informed the adapter refinement. This is not held-out validation, independently audited ground truth, semantic accuracy, safety certification or a generalization claim. The next credible measurement would use a separately annotated report without adjusting the rules to its outcomes.

Machine-readable results are in `baseline-before-refinement.json` and `baseline-after-refinement.json`. Offline annotation integrity is separately recorded in `reference-integrity.json`; its 24/24 source-anchor matches are not model-quality results.
