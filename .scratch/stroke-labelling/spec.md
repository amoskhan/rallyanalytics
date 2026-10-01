# Stroke labelling and training

Status: done

## Problem Statement

The app gives every Shot a Stroke using fixed hand-written rules, and some are wrong, most often a Clear called a Lob. A Labeller can correct a Stroke in the review, but that Correction only fixes that one Video's report. The app never learns from it, even though the review page claims corrections are "used to improve the rules". There is no way to tell which Strokes a Labeller has actually confirmed, no fair way to measure whether a change makes stroke recognition better, and no way to bring older reports up to date when it does.

## Solution

A Labeller goes through a Rally in the review. They correct wrong Strokes and mark Shots they can't judge as Unknown, then press **Rally checked**. That makes it a Checked rally. Each Video's Checked rallies are permanently assigned to either the teaching set or the test set. When enough new Checked rallies have come in, the Labeller presses **Run improvement**. The app tunes the stroke rules' cut-offs on the teaching set, scores the current and tuned rules on the test set, and shows a before/after report. The Labeller then keeps or discards the result. Kept results apply to new analyses straight away. An older report picks them up only when its owner presses **Re-check strokes**, and Corrections are never overwritten.

## User Stories

1. As a Labeller, I want a "Rally checked" button on each Rally in the review, so that I can confirm I have looked at every Shot in it.
2. As a Labeller, I want "Rally checked" to confirm the Strokes I left alone as well as the ones I corrected, so that the app learns from what it got right and not only from its mistakes.
3. As a Labeller, I want to choose Unknown for a Shot I can't judge, so that a guess doesn't teach the app the wrong thing.
4. As a Labeller, I want Unknown Shots left out of teaching and scoring while the rest of the Rally still counts, so that one hidden Shot doesn't waste a whole Rally.
5. As a Labeller, I want to see at a glance which Rallies in a Video are checked, so that I know where I left off.
6. As a Labeller, I want to uncheck a Rally, so that I can fix a mistake I made when checking it.
7. As a Labeller, I want changing a Stroke in a Checked rally to keep it checked with the new Stroke, so that a late fix doesn't make me check the whole Rally again.
8. As a Labeller, I want to be stopped from checking a Rally until every Shot has a Stroke or Unknown, so that no Shot is confirmed by accident.
9. As a Labeller, I want a count of Checked rallies and Checked Shots, split into teaching and test, so that I know when it's worth running an improvement.
10. As a Labeller, I want each Video's Checked rallies to go into the teaching set or the test set automatically, so that I don't have to manage the split myself.
11. As a Labeller, I want a Video's set to stay the same forever once it's been chosen, so that test scores stay honest.
12. As a Labeller, I want all Rallies from one Video in the same set, so that near-identical Rallies don't leak between teaching and testing.
13. As a Labeller, I want about 1 in 5 Videos to go to the test set, so that there are enough test Shots to measure against without starving the teaching set.
14. As a Labeller, I want a "Run improvement" button, so that I can improve stroke recognition without using a terminal.
15. As a Labeller, I want the improvement to learn only from the teaching set, so that the test score is a fair measure.
16. As a Labeller, I want to see overall Stroke accuracy before and after on the test set, so that I can tell whether the change helps.
17. As a Labeller, I want to see accuracy for each Stroke, so that an overall gain can't hide a Stroke that got worse.
18. As a Labeller, I want to see the most common mix-ups before and after (for example Clear called Lob), so that I can see which confusions were fixed.
19. As a Labeller, I want to see how many test Shots each number is based on, so that I don't trust a change measured on a handful of Shots.
20. As a Labeller, I want to see which cut-offs changed and by how much, so that I can judge whether the change makes badminton sense.
21. As a Labeller, I want to keep or discard the result myself, so that nothing changes without my say-so.
22. As a Labeller, I want a clear warning when the result is worse overall or a common Stroke got clearly worse, so that I don't keep a bad change by accident.
23. As a Labeller, I want a message instead of a report when there aren't enough Checked rallies yet, so that I don't read meaning into noise.
24. As a Labeller, I want every improvement run recorded with its date, set sizes, before/after accuracy and whether it was kept, so that I have a history of progress.
25. As a Labeller, I want to undo the last kept improvement, so that I can recover if it turns out to be wrong in practice.
26. As an uploader, I want new analyses to use the latest kept improvement, so that my reports get better over time.
27. As an uploader, I want my existing reports to stay as they are until I choose to update them, so that a report doesn't change under me.
28. As an uploader, I want a "Re-check strokes" button on an older report, so that I can bring its Strokes up to date with the latest improvement.
29. As an uploader, I want Re-check strokes to never overwrite a Stroke I corrected by hand, so that my Corrections are never lost.
30. As an uploader, I want Re-check strokes to be quick and not re-analyse the video, so that I'm not waiting on the GPU queue.
31. As an uploader, I want to see how many Strokes Re-check strokes changed, so that I know whether it made a difference.
32. As a Labeller, I want re-checking a Video's strokes to leave its Checked rallies and their labels alone, so that teaching data is never changed by the app.
33. As an uploader, I want the review page to describe Corrections accurately, so that I'm not told they improve the app when they don't.
34. As an uploader who isn't a Labeller, I want my Corrections to fix my own report only, so that the app's behaviour doesn't depend on unchecked labels.

## Implementation Decisions

- **Vocabulary** follows GLOSSARY.md: Checked rally, Labeller, Correction, Stroke, Shot, Unknown. ADR 0001 sets the approach: only our own Labellers' Checked rallies are used, singles first, rules tuned first and a trained model later. A trained model is out of scope here.
- **Stroke classification takes its cut-offs as a parameter.** Where the front and rear court start, the overhead and underarm wrist heights, and the smash and wrist-smash speeds stop being fixed constants. They become a set of rule parameters passed into classification. The current values are the default.
- **Rule parameters are stored as a saved, versioned file outside the code**, alongside a history of earlier versions. Analysis and Re-check strokes always read the current version. Keeping an improvement writes a new version; undo restores the previous one.
- **Re-classification works from saved results.** Every Shot's measurements (contact wrist height, court zones, front-foot depth, flight time, speed, arc, direction, previous Stroke, whether it was the Serve) are already saved in each Video's result. Tuning, scoring and Re-check strokes re-run classification on those, never on the video. Any measurement classification needs that isn't saved yet must be added to the saved result.
- **Checked state is stored with the Video's review**, next to the existing Corrections and player names. For each Checked rally it records the Rally's identity and the Stroke confirmed for every Shot (or Unknown), as they were at the moment of checking. Later Correction changes inside a Checked rally update that record.
- **Shot identity** reuses the existing Correction key, Rally plus Contact frame, so Corrections and checked labels refer to the same Shot.
- **Set assignment is per Video**, chosen when that Video's first Rally is checked, deterministically from the Video's id (about 1 in 5 to test), and stored so it never changes even if the rule changes.
- **The Labeller role is implicit for now.** The app has no sign-in and is used locally by one trusted Labeller, so every user of the local server is treated as a Labeller. The check button, improvement and undo are grouped so they can be restricted to Labellers once sign-in exists.
- **API additions** (all on the existing server):
  - mark or unmark a Rally checked for a Video (every Shot always shows a Stroke, so there is nothing to refuse)
  - read the labelling summary: Checked rallies and Shots per set, and Videos per set
  - run an improvement: gather Checked Shots from every Video, tune on the teaching set, score current and tuned parameters on the test set, return the report and hold the tuned parameters as a pending result
  - keep or discard the pending result
  - undo the last kept improvement
  - read the improvement history
  - Re-check strokes for a Video: re-classify every Shot with the current parameters, keep Corrections, return how many Strokes changed
- **Tuning** searches the cut-offs over sensible ranges for the values that get the most teaching Shots right, with Unknown Shots excluded. It is cheap enough to run on request, because it only re-runs rule classification on saved measurements.
- **The report** contains overall accuracy before/after, per-Stroke accuracy with Shot counts, the top mix-ups before/after, the parameter changes, and a warning flag when overall accuracy falls or a Stroke with enough test Shots drops noticeably. Below a minimum number of Checked test Shots, the run returns "not enough Checked rallies yet" instead of a report.
- **History** of each run (date, set sizes, accuracy before/after, kept or discarded, parameter version) is stored on the server and shown in the app. The log table in the training process doc becomes a pointer to it.
- **Review page**: a Rally checked toggle and badge on each Rally, a labelling summary, an improvement panel showing the report with Keep / Discard, an Undo, and Re-check strokes on the Video. The text claiming Corrections "improve the rules" is replaced with an accurate description.

## Testing Decisions

- **One seam: the server's HTTP API**, exercised with FastAPI's test client. Tests set up a temporary data folder holding a few small sample Videos (saved results and reviews only, no video files or GPU) and drive everything through the endpoints. They check behaviour the user would notice: what is checked, which set a Video is in, what the report says, which Strokes change on Re-check, that Corrections survive. They don't test internal function calls.
- **Sample data** is hand-written so the right answers are known. Include a Video whose Clears are labelled Lob by the current cut-offs, so that an improvement measurably fixes it and the report shows the gain.
- **Behaviours to cover:**
  - Unknown Shots are excluded from both sets
  - a Video's set never changes
  - teaching data never affects the test score
  - discard leaves parameters unchanged
  - keep makes new analyses and Re-check strokes use the new parameters
  - undo restores the old parameters
  - Re-check strokes never overwrites Corrections or Checked rallies
  - "not enough Checked rallies" below the threshold
- **Prior art:** the repo has no tests yet, so this sets the pattern. Add pytest and FastAPI's test client to the requirements, and keep tests GPU-free so they run anywhere.

## Out of Scope

- A trained stroke model (stage 2 in the training process). Only rule cut-off tuning is in scope.
- Sign-in, user accounts, or more than one Labeller.
- Doubles. Labelling and scoring assume singles.
- Asking at upload whether a Video is a Clip or a Full match.
- Recognising Outcomes automatically (Clean winner, Forced error, Unforced error, Service fault).
- Forehand/backhand labels; only the 18 ShuttleSet Strokes.
- The written definitions of the confusable Strokes in the labelling guide.
- Fixing missed Contacts or wrongly split Rallies. That's rally detection, not stroke recognition.
- Mobile and public access.

## Further Notes

- docs/labelling-guide.md and docs/training-process.md describe this process with "not built yet" notes. Remove each note as its part ships, and replace the training process doc's log table with a pointer to the in-app history.
- Rally identity depends on the Video's analysis. Re-analysing a Video, for example after re-marking court corners, can change its Rallies. That should either clear that Video's Checked rallies with a warning, or be refused while the Video has any. Pick the simpler option and say so in the review.
- A useful minimum before a report is shown is a few dozen Checked test Shots. Make it a single setting so it's easy to adjust.
