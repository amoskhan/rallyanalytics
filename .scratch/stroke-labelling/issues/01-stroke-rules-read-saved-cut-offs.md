# 01: Stroke rules read saved cut-offs, plus the test setup

**What to build:** Preparatory work for the rest of the stroke-labelling feature ([spec](../spec.md)). The stroke rules' cut-offs move out of the code into a saved, versioned settings file:

- where the front and rear court start
- the overhead and underarm wrist heights
- the smash and wrist-smash speeds

Today's values become version 1. A Rally's Strokes can be re-worked out from its saved result alone (its saved Contacts, Shot measurements and landing), without touching the video. The analysis uses that same path, so both always agree. A pytest + FastAPI test client setup is added with a temporary data folder and a few small hand-written sample Videos (results and reviews only, no video files, no GPU). Nothing visible changes for users.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Stroke classification takes its cut-offs as a parameter; the current values are the default and live in a saved settings file with a version number and room for earlier versions.
- [x] Analysis reads the current cut-offs from that file when classifying Strokes.
- [x] One function re-works out every Shot's Stroke for a Rally from its saved result and a set of cut-offs; analysis uses it too.
- [x] Any measurement classification needs that isn't saved in the result yet is added to it.
- [x] pytest and the FastAPI test client are in the requirements; tests run without a GPU or model weights.
- [x] Sample Videos include one whose Clears come out as Lob with the default cut-offs (needed later to show an improvement).
- [x] Test: with the default cut-offs, re-classifying each sample Video's saved result gives exactly the Strokes stored in it.
- [x] Existing analysis output is unchanged for an already-analysed Video.
