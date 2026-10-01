# 02: Rally checked

**What to build:** A Labeller goes through a Rally in the review, fixes wrong Strokes, sets Shots they can't judge to Unknown, and presses **Rally checked**. That makes it a Checked rally, which records the confirmed Stroke (or Unknown) for every Shot. A badge shows which Rallies are checked, and a Labeller can uncheck one. Fixing a Stroke inside a Checked rally keeps it checked with the new Stroke. Because re-analysing a Video can change its Rallies, re-analysing a Video that has Checked rallies is either refused or clears them after a warning. Pick the simpler option and say which in the review. See the [spec](../spec.md).

**Blocked by:** 01 (Stroke rules read saved cut-offs, plus the test setup)

**Status:** done

- [x] API to mark and unmark a Rally checked for a Video; the Checked state is stored with the Video's review, keyed so it matches the existing Corrections (Rally plus Contact frame).
- [x] ~~Checking is refused while any Shot in the Rally has no Stroke~~; Unknown is allowed. *Dropped: every Shot always shows a Stroke (the app's, which may be unknown, or a Correction), so there is nothing to refuse.*
- [x] A Checked rally stores the Stroke or Unknown for every Shot as confirmed; a later Correction in that Rally updates it.
- [x] Review shows a Rally checked toggle and a checked badge on each Rally.
- [x] Re-analysing a Video with Checked rallies is refused, or clears them after a clear warning. *Chosen: the server refuses (409) unless asked to clear them; the page asks the Labeller to confirm, then re-analyses and unchecks that Video's rallies.*
- [x] The review text claiming Corrections are "used to improve the rules" is replaced with an accurate description.
- [x] The labelling guide's "not built yet" note no longer mentions Rally checked.
- [x] API tests cover: check, uncheck, Unknown accepted, later Correction updates the Checked rally, re-analysis rule.

## Notes

- Old stroke names in Corrections (lift, long serve, ...) are stored under their ShuttleSet name when a Rally is checked.
- Review saves are serialised per Video, and the page sends any pending stroke change before checking, so a quick fix-then-check confirms what's on screen.
