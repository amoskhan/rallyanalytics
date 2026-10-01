# Labelling guide

For Labellers: experienced players who check the strokes the app gives each shot, so it can learn to get them right. Words in **bold** are defined in [GLOSSARY.md](../GLOSSARY.md).

> **Partly built.** Correcting strokes, *Unknown* and the **Rally checked** button work today. The Clip / Full match choice at upload and the test set don't exist yet. Each part's note is removed when it's built.

## Why your labels matter

The app guesses each **Stroke** with fixed rules, such as "the wrist was above the head, so it was overhead". It gets some wrong, for example calling a **Clear** a **Lob**. Every rally you check tells the app what the right answers were. We use your checks, and not a public dataset, because experienced players looking at club footage are a better source of truth than professional TV matches ([why](adr/0001-stroke-learning-from-labeller-corrections.md)).

Only Labellers' checks are used for teaching. When other users correct strokes, that only fixes their own reports.

## 1. Film a training clip

- **Singles only** for now.
- Landscape, on a tripod, high and behind one baseline, with all four court corners in view the whole time.
- One or a few rallies is enough. When you upload, choose **Clip**. *(Not built yet: the app doesn't ask yet.)*
- Mix up the play. Clips full of the same stroke teach the app less than clips with a variety of clears, lobs, drops, drives and net play.

## 2. Analyse it

1. Upload the clip on the video page.
2. Click the 4 outer court corners in the order shown.
3. Wait for the analysis to finish.

## 3. Check a rally

Open the rally and play it back. Go through the shot table below the video one shot at a time:

- **The stroke is right**: leave it.
- **The stroke is wrong**: pick the right one from the menu. Your choice is saved straight away.
- **You can't tell** (the shuttle left the picture, a player blocked the view, the racket arm is hidden): choose **Unknown**. Don't guess. A wrong label teaches the app the wrong thing, while an Unknown shot is simply left out and the rest of the rally still counts.

When every shot is right, corrected or Unknown, press **Rally checked** above the shot table. That turns it into a **Checked rally**: it confirms the shots you left alone as well as the ones you changed. Only Checked rallies are used to teach the app, so don't press it until you have looked at every shot. Checked rallies show a ✓ in the rally list. If you spot a mistake later, just fix the stroke: the rally stays checked with your new answer. Press the button again to uncheck it.

Re-analysing a video (re-marking the court, changing a racket hand, or *Try again*) can change its rallies, so the app asks first and then unchecks all of that video's rallies.

If the app missed a shot completely or split one rally into two, don't mark the rally as checked. Note the video and the rally number and pass it on, because that's a fault in finding the rallies, not in naming the strokes.

## 4. Which stroke is which

All Labellers have to use the same definitions, or the app learns from labels that disagree with each other. We use the 18 ShuttleSet stroke types:

net shot, return net, cross-court net shot, smash, wrist smash, rush, push, drop, passive drop, clear, lob, defensive return lob, drive, driven flight, back-court drive, defensive return drive, short service, long service.

Agreed so far:

- **Clear**: hit overhead from the mid or rear court, sending the shuttle high to the back of the other half.
- **Lob**: hit underarm, usually from the front court, sending the shuttle high to the back of the other half. "Lift" means the same thing, so use Lob.

> **To be agreed.** Definitions of the pairs that are easy to confuse still need writing: drive / driven flight / back-court drive / defensive return drive, push / rush, net shot / return net, smash / wrist smash, drop / passive drop, and lob / defensive return lob. Until then, label by your own experience and choose Unknown when you're torn between two.
