# Rally Analytics

Badminton match analysis for clubs, players and coaches: upload a video of a match and get back its rallies, who won each one, and how.

## Language

### Videos and reports

**Video**:
A recording of all or part of a badminton match, uploaded for analysis. It is the main thing users work with. Every Video is either a Clip or a Full match.
_Avoid_: Footage, upload

**Clip**:
A Video of one or a few Rallies, with no game score.
_Avoid_: Snippet, highlight

**Full match**:
A Video of a whole match, from which game scores and the match result can be worked out.
_Avoid_: Game (for the whole match)

**Rally report**:
What a Clip produces: its Rallies, Shots and Strokes, and which Side won each Rally.

**Match report**:
What a Full match produces: a Rally report plus the score sheet, game scores and match result, which the uploader can come back to and study later.
_Avoid_: Scorebook (as a name for the report), scoresheet

**Correction**:
A change the uploader makes to the analysis, such as fixing a Stroke or which Side won a Rally.
_Avoid_: Edit, override

**Labeller**:
A trusted badminton player whose Corrections are used to teach the app to recognise Strokes. Other uploaders' Corrections only fix their own reports.
_Avoid_: Annotator, tagger

**Checked rally**:
A Rally whose every Stroke a Labeller has confirmed, corrected or marked Unknown (can't tell). Only Checked rallies are used to teach the app, and Unknown Shots are left out.
_Avoid_: Labelled rally, verified rally

**Teaching set**:
The Checked rallies the app learns Strokes from: those of about 4 in 5 Videos.
_Avoid_: Training set

**Test set**:
The Checked rallies kept back to score how well the app recognises Strokes, never learned from: those of about 1 in 5 Videos. A Video's Checked rallies are all in one set, and it never moves.
_Avoid_: Validation set, holdout

### Play within a rally

**Rally**:
One exchange of play from the Serve until the shuttle is no longer in play, won by one Side.
_Avoid_: Point, exchange

**Serve**:
The Shot that starts a Rally. "Short service" and "long service" are only used as Stroke names.
_Avoid_: Service (for the act)

**Contact**:
The instant a player's racket meets the shuttle.
_Avoid_: Hit

**Shot**:
The shuttle's flight from one Contact to the next Contact or to where it lands.

**Stroke**:
The type of a Shot, one of the 18 ShuttleSet types such as smash, net shot or lob.
_Avoid_: Shot type

**Clear**:
A Stroke hit overhead from the mid or rear court that sends the shuttle high to the back of the other Half.

**Lob**:
A Stroke hit underarm, usually from the front court, that sends the shuttle high to the back of the other Half.
_Avoid_: Lift

### How a rally ends

**Outcome**:
How a Rally ended: a Clean winner, Forced error, Unforced error or Service fault.
_Avoid_: Result (for how it ended)

**Clean winner**:
An Outcome where the last Shot could not be reached by the other Side.
_Avoid_: Winner (that word is only for who won the Rally or match)

**Forced error**:
An Outcome where a good Shot drew a mistake from the other Side.

**Unforced error**:
An Outcome where a Side made a mistake without being put under pressure.

**Service fault**:
An Outcome where the Serve itself was illegal or failed.

### Who and where

**Side**:
One of the two teams in a match, A or B. A Side keeps its identity when players change ends.
_Avoid_: Team, player (for a pair)

**Half**:
The near or far half of the court as the camera sees it. Which Side is in which Half changes when players change ends.
_Avoid_: End, side (for a court half)
