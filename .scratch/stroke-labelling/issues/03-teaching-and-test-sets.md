# 03: Teaching and test sets, plus the labelling summary

**What to build:** When a Video's first Rally is checked, the Video is assigned to the **teaching set** or the **test set** (about 1 in 5 to test), and it stays there forever. All of a Video's Rallies are in the same set. The review shows a labelling summary: Checked rallies and Checked Shots in each set, and the number of Videos in each, with Unknown Shots left out of the Shot counts. This tells the Labeller when it's worth running an improvement. See the [spec](../spec.md).

**Blocked by:** 02 (Rally checked)

**Status:** done

- [x] A Video's set is chosen deterministically from its id when its first Rally is checked, and stored.
- [x] The stored set never changes, even if every Rally is later unchecked and re-checked, or the assignment rule changes.
- [x] API returns the labelling summary across all Videos.
- [x] Review shows the summary and which set the current Video is in.
- [x] API tests cover: assignment on first check, assignment never changes, whole Video in one set, Unknown Shots excluded from counts, roughly 1 in 5 Videos go to test across many ids.

## Notes

- The summary counts only Videos with at least one Checked rally; a Video keeps its stored set even when all its rallies are unchecked.
- Saves retry briefly on Windows when another thread is reading the same file, and a damaged review.json is left out of the summary rather than failing it.
