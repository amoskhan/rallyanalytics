# RallyBook

A courtside badminton scorer with BWF rally scoring, service-court tracking, rally tagging and match analysis. It's a single HTML file with no build step.

## Features

- **Scoring:** games to 21 with a 2-point lead from 20-all and a cap at 30. Best of 3 games. Games to 11 or 15 are available for short PE rotations.
- **Match prompts:** intervals at 11, change of ends, and game point, match point, deuce and golden point.
- **Service diagram:** shows the server and receiver on a court drawing, including the doubles serving rotation.
- **Rally tags:** optionally record how each rally ended (winner, forced error, unforced error, service fault), the final shot and a rough rally length.
- **Analysis:** a momentum chart, how points were won, rallies won on serve and on receive, winners and errors by shot type, win rates by rally length, and short plain-English findings.
- **Export:** copy all rallies as CSV.
- **Undo:** remove the last rally with the button or the U key.

Matches are saved in the browser's localStorage, on this device only.

## Run

Open `index.html` in a browser, or turn on GitHub Pages (Settings → Pages → Deploy from branch → `main` / root).

## Keyboard

`1` / `2` award the rally to side A / B · `U` undoes the last rally
