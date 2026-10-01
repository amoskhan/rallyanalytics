# Strokes are taught from our own Labellers' Checked rallies, not from ShuttleSet

Stroke recognition improves by learning from Checked rallies, and only trusted Labellers can produce them. For now that means our own competitive players with many years of experience. We start by tuning the existing hand-written rules from those labels and move to a trained model once there are a few hundred, keeping the rules as a fallback. We do not train on ShuttleSet data, even though we use its 18 Stroke names. ShuttleSet is professional singles on broadcast TV, while our users film club play on phones, and experienced players labelling our own footage is a better source of truth. Ordinary uploaders' Corrections fix only their own reports, so a careless label can't make the app worse for everyone, and private Videos aren't used without consent. We are starting with singles because each Half has fewer people moving in it.

## Consequences

- A change to stroke recognition is adopted only if it scores better on a test set of Checked rallies that are never used for teaching. A Labeller runs the change and decides whether to keep it; nothing retrains automatically.
- Doubles will need its own Checked rallies before stroke recognition can be trusted there.
