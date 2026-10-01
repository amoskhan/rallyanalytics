# 05: Run improvement: tune, score, keep or discard

**What to build:** A Labeller presses **Run improvement**. The app gathers every Checked Shot (leaving out Unknown) and tunes the cut-offs on the teaching set. It then scores the current and tuned cut-offs on the test set and shows a report:

- overall accuracy before → after
- accuracy per Stroke, with Shot counts
- the most common mix-ups before → after, such as Clear called Lob
- which cut-offs changed and by how much
- a warning if overall accuracy fell or a Stroke with enough test Shots got noticeably worse

Below a minimum number of Checked test Shots (one easy-to-change setting, about a few dozen), the app shows "not enough Checked rallies yet" instead. The tuned cut-offs wait as a pending result until the Labeller presses **Keep** or **Discard**. Kept cut-offs become the new current version, used by new analyses and by Re-check strokes. See the [spec](../spec.md) and [ADR 0001](../../../docs/adr/0001-stroke-learning-from-labeller-corrections.md).

**Blocked by:** 03 (Teaching and test sets, plus the labelling summary)

**Status:** done

- [x] API runs an improvement and returns the report, or "not enough Checked rallies yet" below the threshold.
- [x] Tuning only ever sees teaching-set Shots; test-set Shots only affect the score.
- [x] The tuned cut-offs are held as pending; Keep saves them as a new version, Discard drops them.
- [x] After Keep, new analyses and Re-check strokes use the new cut-offs.
- [x] Review has an improvement panel showing the report with Keep / Discard and the warning when present.
- [x] API tests cover: the sample Video's Clear/Lob mix-up is fixed and the report shows the gain, changing teaching data never changes the "before" score, Discard leaves cut-offs unchanged, Keep changes them, threshold message, warning flag.

## Notes

- Tuning is greedy: one cut-off at a time over a fixed range, repeated up to 5 passes, moving only on a strict gain. Fast for a few hundred labelled Shots; with thousands it may take tens of seconds in the request, and per-rally caching or a background job would be the next step.
- The warning lists both an overall drop and every Stroke (8+ test Shots) that fell 10 points or more.
- Keep is refused when the stroke rules changed since the run. A damaged pending file counts as no result.
- The panel sits under the shot table, so a Rally must be open to see it.
