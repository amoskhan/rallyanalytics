# 04: Re-check strokes

**What to build:** A **Re-check strokes** button on a Video's review re-works out every Shot's Stroke with the current cut-offs, using the saved result and not the video. It never overwrites a Stroke the uploader corrected, and never changes Checked rallies. It reports how many Strokes changed. Older reports only change when someone presses this button. See the [spec](../spec.md).

**Blocked by:** 01 (Stroke rules read saved cut-offs, plus the test setup), 02 (Rally checked)

**Status:** done

- [x] API re-classifies a Video's Shots with the current cut-offs and saves the updated result; returns the number of Strokes changed.
- [x] Corrections are kept and still shown in place of the re-classified Stroke.
- [x] Checked rallies and their stored Strokes are untouched.
- [x] Runs without the GPU queue and returns quickly.
- [x] Review has a Re-check strokes button that shows the result and refreshes the shot table.
- [x] API tests cover: Strokes change after the cut-offs change, Corrections survive, Checked rallies untouched, no change when the cut-offs are the same.

## Notes

- Checked rallies are skipped entirely, so they keep showing the Strokes the Labeller confirmed. Unchecking one and pressing Re-check strokes again brings it up to date.
- The count is what the uploader will see change: Shots with a Correction aren't counted, because the Correction is shown instead.
- Refused while the Video is converting, queued or being analysed; a result from an older analysis without saved Shot measurements gets a message to re-run it. Re-check and a finishing analysis share a lock on result.json.
