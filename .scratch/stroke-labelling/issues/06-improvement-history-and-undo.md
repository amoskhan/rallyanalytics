# 06: Improvement history and undo

**What to build:** Every improvement run is logged with its date, the number of Checked rallies in each set, accuracy before → after, whether it was kept, and the cut-off version it produced. The Labeller can view the history in the app and press **Undo last improvement** to restore the previous cut-offs. The training process doc's log table is replaced with a pointer to the in-app history. See the [spec](../spec.md).

**Blocked by:** 05 (Run improvement: tune, score, keep or discard)

**Status:** done

- [x] Every run (kept or discarded) is recorded on the server.
- [x] API returns the history, newest first.
- [x] API undoes the last kept improvement, restoring the previous cut-off version; refused when only the default version exists.
- [x] Review shows the history and an Undo button.
- [x] docs/training-process.md: the log table is replaced with a pointer to the in-app history, and the "not built yet" note is removed once tickets 02–06 are all done.
- [x] API tests cover: kept and discarded runs both logged, undo restores the previous version, undo refused at the default version.

## Notes

- The history also records runs still waiting for a decision (pending) and runs overtaken by a newer one (replaced), and logs each Undo.
- Undo steps back one Keep at a time; the history response says whether there's anything to undo, so the button only shows when there is.
