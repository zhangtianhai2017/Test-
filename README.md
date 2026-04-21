# 🧩 Jigsaw Puzzle

A lightweight casual jigsaw puzzle game that runs entirely in the browser. Zero
dependencies, zero build step — just static HTML/CSS/JS.

## Features

- Classic interlocking pieces with procedurally-generated tab/blank edges
- Drag-and-drop with automatic snap-to-neighbor merging
- Three difficulties: easy (3×4), normal (5×6), hard (8×10)
- Three built-in procedurally-drawn images, plus upload-your-own
- Timer, move counter, and progress tracker
- Optional reference-image overlay
- Touch support (mobile/tablet)

## Run it

Because it uses ES modules, serve the folder over HTTP instead of opening
`index.html` directly:

```bash
python3 -m http.server 8000
# then visit http://localhost:8000/
```

## Project layout

```
index.html            # UI shell
css/styles.css        # styling
js/main.js            # entry point, wires UI to game
js/game.js            # game state, win detection, timer
js/puzzleGenerator.js # piece shape generation (Bezier tab/blank)
js/piece.js           # Piece class, group merging
js/renderer.js        # canvas rendering
js/input.js           # pointer events, drag-drop
js/presets.js         # procedural preset images
js/utils.js           # helpers
```
