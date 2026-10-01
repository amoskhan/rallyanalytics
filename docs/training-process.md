# Training process

How stroke recognition is improved from **Checked rallies**, measured, and either kept or thrown away. This is for whoever runs the improvements. Labellers produce the Checked rallies ([labelling guide](labelling-guide.md)). Terms are defined in [GLOSSARY.md](../GLOSSARY.md), and the reasons for this approach are in [ADR 0001](adr/0001-stroke-learning-from-labeller-corrections.md).

> Everything on this page works from the review page, except stage 2 (a trained model), which comes once there are enough Checked rallies.

## The two sets

Every Checked rally belongs to exactly one set:

- **Teaching set**: about 4 in 5 Checked rallies. Improvements learn from these.
- **Test set**: about 1 in 5. These are never used for learning, only for scoring.

A rally is put in a set when it is checked and **never moves**. If test rallies were used for learning, the score would look better without the app actually getting better. Put whole Videos in one set rather than splitting their rallies, because rallies from the same Video look alike and would leak between the sets.

"Unknown" shots are left out of both learning and scoring.

## Stages

1. **Tuning the rules** (now). The rules in [server/pipeline/strokes.py](../server/pipeline/strokes.py) depend on a few cut-offs: where the front and rear court begin, how high the wrist must be to count as overhead or underarm, and how fast a smash and a wrist smash are. Tuning searches for the cut-offs that get the most teaching-set strokes right.
2. **A trained model** (once there are a few hundred Checked shots of the common strokes). A model learns strokes from the same measurements: wrist height, court zones, speed, arc and the previous stroke. The rules stay as a fallback for strokes the model hasn't seen enough examples of.

## Running an improvement

Run an improvement whenever a useful number of new Checked rallies has come in, for example after a training session's clips have been checked. Nothing runs automatically.

1. Press **Run improvement** on the review page. It tunes the cut-offs on the teaching set...
2. ...and scores the current and the tuned cut-offs on the **test set**. Below 30 Checked test shots it says there isn't enough yet.
3. Read the report:
   - **Overall stroke accuracy**, before and after, for example 71% → 78%.
   - **Accuracy per stroke**: an overall gain can hide a stroke that got worse.
   - **The most common mix-ups**, for example clear called lob 9 → 3.
   - **How many test shots** each number is based on. A stroke with 4 test shots can't show a reliable change.
4. **Keep it** only if overall accuracy goes up and no common stroke gets clearly worse. Otherwise throw it away and work out why: often it's labels that disagree, and that's fixed by writing the stroke definitions more clearly.
5. Nothing to write down: every run is logged automatically (see below).

## Old reports

Keeping an improvement doesn't change existing reports. A report's strokes update only when its owner presses **Re-check strokes**, and strokes that someone corrected by hand are never overwritten.

## History and undo

Every run is logged in the app: open **Improvement history** under the improvement panel on the review page. Each entry shows the date, what became of the run (kept as version N, discarded, replaced by a newer run, or still waiting), test accuracy before → after, and how many Checked rallies and shots each set had.

If a kept improvement turns out worse in practice, press **Undo last improvement** there. It goes back to the stroke rules in use before that Keep, and is logged too. Videos only pick up the change when **Re-check strokes** is pressed on them.
