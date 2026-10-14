# CrossStitchHelper — what the application will do, once finished

*This document describes the application in its complete version, with every feature from the specification built — not an intermediate state. Goal: check together whether anything is missing before starting to build.*

---

## What the application will do

### Import a pattern

- Load a PDF (or an existing image — scan, screenshot) of a cross-stitch chart and turn it into a pattern the app understands and displays, via a multi-step wizard that automatically proposes a complete configuration.
- **Automatically recognise each cell's colour and symbol**, whatever the style of the original file: export from charting software, a chart drawn for publication (like official DMC charts), a pattern spread over two separate grids (one for colours, one for symbols), a pattern spread over several pages to stitch back together, or a grid made of small reused images (closed catalogue of colour+symbol icons, third-party publishers).
- Give each pattern labels (Mini, Animals, Landscape…), when importing it or later from the library, and filter the library by label.
- Automatically reuse the configuration of an already validated import when a new file comes from the same source (same publisher, same software) — import becomes almost instant for someone who regularly buys from the same seller.
- **Always keep the ability to correct by hand** what the wizard proposed: re-crop the area, adjust the number of cells, fix a colour or a symbol, paint areas as full, 1/2 or 1/4 stitches, complete the legend. The imported file stays visible next to the proposed grid, page by page and zoomable, to check one against the other. Even when finished, the application remains an assistant that proposes and can be corrected, not a black box you have to take at its word.

### Track your stitching

- Check off cells as you go, cell by cell, by group, or "all of this colour in the visible area".
- Move around the grid with your fingers (zoom, pan), including on a pattern of several tens of thousands of cells, with smoothness designed for iPhone/iPad.
- Highlight a specific colour to easily spot where it goes (while it is highlighted, only that colour can be checked off), hide what is already done, see the current row and column.
- Undo an action, pick up where you left off, including on another device (tracking is not lost if you switch iPhone or tablet).
- Keep checking cells even without an internet connection (data updates automatically as soon as the network returns).

### Know which colour to use

- Show, for each cell, the colour code (DMC by default) and its symbol.
- Provide a complete legend of the pattern: all colours used, their name, their code.
- Handle the common special stitches: full stitch, half stitch, quarter stitch, backstitch, French knot.

### Provide statistics

- Overall and per-colour completion percentage.
- Number of remaining stitches, per colour and per stitch type.
- Estimate of the number of thread skeins needed (and those still to be used), depending on the chosen fabric.
- Progress history over time.

### Stitch as a household or group

- Several profiles on one instance, each with its own private library and progress: nobody sees the patterns of another profile.
- "Who's stitching?" on opening the app: pick your profile, enter your password — on a shared iPad, switching person takes two taps.
- An administrator adds the people (with an initial password they choose), edits them, resets a forgotten password, removes them. There is always at least one administrator.

### Share patterns within the group

- A shared library next to everyone's own: anyone in the group can add a pattern to it (when importing, or from one of their patterns) and copy a shared pattern into their library to stitch it — progress always stays personal.
- Only administrators rename, replace or remove a shared pattern. Anyone else asks them: a removal request, or a proposal to replace a pattern with their own version. Everyone sees what became of their requests.
- When a shared pattern is replaced, everyone who copied it sees "Update" on their copy; updating is their choice and never loses the stitching already done.

### Stay at home

- The application is installed on your own hardware (computer, NAS, personal mini-server) — no data is sent to an external service.
- Patterns and progress are never stored anywhere other than on your server. Each profile's library is private; a pattern is shared with the group only when someone shares it, and progress never is.
- The app is free and the code is open: nothing to pay, nothing that could shut down or become paid overnight.
- Usable like a real app on iPhone/iPad (home screen icon, full screen), without going through the App Store.

---

## What the application will never do

These are deliberate scope choices, not features still missing — they remain true even once the application is entirely finished.

- **It does not create patterns.** It does not turn a personal photo into a chart to stitch (it is not a creation tool, only a tool for reading/tracking an existing pattern).
- **It does not offer photo capture or automatic recognition from a free-form photo of a paper chart.** A decision made along the way (not in the initial plan): with no real reference file to verify such detection, and full-frame computer vision too uncertain to be honestly automated in this application — see specification §13 (decision log). The universal manual import (cropping, dimensions, palette and painting by hand) remains available for any file, images included, if you drop one yourself.
- **It neither offers nor sells patterns.** No library of charts to download in the app: everyone imports the files they already own.
- **It is not a social network.** Sharing stays within the instance's group (and, later, one paired instance): no public catalogue, no "see what others are stitching", nothing ever sent to a third-party service. Whoever shares a pattern remains responsible for having the right to share it.
- **It will not be a "native" iPhone/iPad app** downloadable from the App Store — it will be a web page you install on the home screen, which amounts to the same thing in use but avoids Apple's fees and constraints. *(To be validated together: this is a deliberate trade-off to stay free, not a technical limitation that could not be lifted later if needed.)*
- **It has no sign-up and sends no email.** Profiles are created by an administrator of the instance; a forgotten password is reset by an administrator, not by an email link.
- **It does not sync with a public cloud** (no iCloud, no Google Drive) — backup and synchronisation stay internal to the app, on the server you host yourself.

---

## Limits that will remain, even once the application is finished

These are not unfinished features: they are limits inherent to the problem, which will remain whatever the level of polish of the software.

- **Displayed colours remain approximations.** The thread colour charts used are not official manufacturer data (DMC does not publish its real colour values): the shade shown on screen remains indicative. When the original file gives the exact code as text, that code is always authoritative — but the app cannot guarantee that the colour *shown on screen* is a perfectly faithful rendering of the real thread.
- **Automatic recognition (colour and symbol) remains probabilistic, never 100% guaranteed.** On PDFs hand-drawn for publication, the app aims for high reliability, but a small proportion of cells — flagged as such — may need manual checking or correction. This is not a teething problem to fix over time: it is a limit inherent to automatically recognising shapes and colours from a document, however much care goes into development.
- **Smoothness on a very large pattern depends on the device used.** An old iPhone will always be less smooth than a recent model on a pattern of several tens of thousands of cells.
- **Accessing your app from outside your home** requires a little technical setup (a tunnel or remote access to set up), by design — it is not automatic like a typical cloud service, and that will not change.
- **An instance remains designed for a household or a small group**: profiles keep libraries apart, but anyone who opens the app sees the list of profile first names on the login screen.

---

## For discussion: what might be missing?

This document is precisely meant to check together whether an important feature is missing before starting to build. A few open questions, not yet settled one way or the other:

- Should the Apple Pencil be usable on iPad to mark cells or annotate the grid?
- Is a "print" mode needed to output a paper version of the pattern or the legend?
- Should it be possible to share a pattern (just the file, not via the app) with another person who has their own instance?
- Is Android support necessary, or does use remain strictly iPhone/iPad?
- Should the time actually spent stitching be tracked (a stopwatch), in addition to the completion percentage?

Feel free to add any other feature you think of while reading this document — this is the cheapest moment to do so.
