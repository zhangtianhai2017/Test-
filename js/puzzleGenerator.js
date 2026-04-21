import { randRange, randSign } from "./utils.js";
import { Piece } from "./piece.js";

// Builds a Path2D for one puzzle piece outline based on its edge polarities.
// Edges: top, right, bottom, left. Polarity: +1 = tab (protrudes outward),
// -1 = blank (cuts inward), 0 = flat (border edge).
// Width/height are the rectangular cell size; tab size is relative.
//
// Coordinate system for the path: (0,0) = top-left of the cell (NOT including
// the tab extrusion). Tabs extend past the cell by TAB_DEPTH on the respective
// side. The piece's bounding box therefore extends TAB_DEPTH on every side
// that has a tab. We handle this outside by offsetting draw position.
function buildEdgePath(w, h, edges, jitter) {
  const TAB = Math.min(w, h) * 0.22; // depth of tab/blank
  const NECK = Math.min(w, h) * 0.15; // width of the "neck" where the tab joins
  const p = new Path2D();

  // Small jitter to make pieces unique
  const j = (seed, amp = 0.03) =>
    (jitter[seed] - 0.5) * 2 * amp * Math.min(w, h);

  p.moveTo(0, 0);

  // TOP edge (left -> right)
  if (edges.top === 0) {
    p.lineTo(w, 0);
  } else {
    const dir = -edges.top; // tab (+1) goes up (negative y); blank (-1) goes down
    const midX = w / 2 + j(0);
    // Pre-neck
    p.lineTo(midX - NECK, 0);
    // Into the tab bulge via bezier
    p.bezierCurveTo(
      midX - NECK * 0.2, dir * TAB * 0.1,
      midX - NECK * 1.1, dir * TAB * 0.9,
      midX - NECK * 0.5, dir * TAB
    );
    // Across the tab top
    p.bezierCurveTo(
      midX - NECK * 0.2, dir * TAB * 1.15,
      midX + NECK * 0.2, dir * TAB * 1.15,
      midX + NECK * 0.5, dir * TAB
    );
    // Back down to edge
    p.bezierCurveTo(
      midX + NECK * 1.1, dir * TAB * 0.9,
      midX + NECK * 0.2, dir * TAB * 0.1,
      midX + NECK, 0
    );
    p.lineTo(w, 0);
  }

  // RIGHT edge (top -> bottom)
  if (edges.right === 0) {
    p.lineTo(w, h);
  } else {
    const dir = edges.right; // +1 tab pushes right (+x); -1 pulls left
    const midY = h / 2 + j(1);
    p.lineTo(w, midY - NECK);
    p.bezierCurveTo(
      w + dir * TAB * 0.1, midY - NECK * 0.2,
      w + dir * TAB * 0.9, midY - NECK * 1.1,
      w + dir * TAB, midY - NECK * 0.5
    );
    p.bezierCurveTo(
      w + dir * TAB * 1.15, midY - NECK * 0.2,
      w + dir * TAB * 1.15, midY + NECK * 0.2,
      w + dir * TAB, midY + NECK * 0.5
    );
    p.bezierCurveTo(
      w + dir * TAB * 0.9, midY + NECK * 1.1,
      w + dir * TAB * 0.1, midY + NECK * 0.2,
      w, midY + NECK
    );
    p.lineTo(w, h);
  }

  // BOTTOM edge (right -> left)
  if (edges.bottom === 0) {
    p.lineTo(0, h);
  } else {
    const dir = edges.bottom; // +1 tab pushes down (+y)
    const midX = w / 2 + j(2);
    p.lineTo(midX + NECK, h);
    p.bezierCurveTo(
      midX + NECK * 0.2, h + dir * TAB * 0.1,
      midX + NECK * 1.1, h + dir * TAB * 0.9,
      midX + NECK * 0.5, h + dir * TAB
    );
    p.bezierCurveTo(
      midX + NECK * 0.2, h + dir * TAB * 1.15,
      midX - NECK * 0.2, h + dir * TAB * 1.15,
      midX - NECK * 0.5, h + dir * TAB
    );
    p.bezierCurveTo(
      midX - NECK * 1.1, h + dir * TAB * 0.9,
      midX - NECK * 0.2, h + dir * TAB * 0.1,
      midX - NECK, h
    );
    p.lineTo(0, h);
  }

  // LEFT edge (bottom -> top)
  if (edges.left === 0) {
    p.lineTo(0, 0);
  } else {
    const dir = -edges.left; // tab(+1) from left means shape extends to -x
    const midY = h / 2 + j(3);
    p.lineTo(0, midY + NECK);
    p.bezierCurveTo(
      dir * TAB * 0.1, midY + NECK * 0.2,
      dir * TAB * 0.9, midY + NECK * 1.1,
      dir * TAB, midY + NECK * 0.5
    );
    p.bezierCurveTo(
      dir * TAB * 1.15, midY + NECK * 0.2,
      dir * TAB * 1.15, midY - NECK * 0.2,
      dir * TAB, midY - NECK * 0.5
    );
    p.bezierCurveTo(
      dir * TAB * 0.9, midY - NECK * 1.1,
      dir * TAB * 0.1, midY - NECK * 0.2,
      0, midY - NECK
    );
    p.lineTo(0, 0);
  }

  p.closePath();
  return { path: p, tabDepth: TAB };
}

// Produce a set of edge polarities such that shared edges between neighbors
// have opposite signs (so a tab on one side mates a blank on the other).
function generateEdgeGrid(rows, cols) {
  // horizontal edges: between row r and r+1, for each col c
  // hEdge[r][c] means the polarity of the BOTTOM edge of piece (r,c) = +1 tab
  // which then becomes TOP edge of piece (r+1,c) with same absolute direction
  // but reversed sign from that piece's perspective.
  const h = []; // rows-1 entries, cols each
  for (let r = 0; r < rows - 1; r++) {
    const row = [];
    for (let c = 0; c < cols; c++) row.push(randSign());
    h.push(row);
  }
  const v = []; // rows entries, cols-1 each
  for (let r = 0; r < rows; r++) {
    const row = [];
    for (let c = 0; c < cols - 1; c++) row.push(randSign());
    v.push(row);
  }
  return { h, v };
}

function edgesForCell(r, c, rows, cols, grid) {
  // top: shared with (r-1,c)'s bottom. grid.h[r-1][c] is bottom of (r-1,c).
  // top of (r,c) = -grid.h[r-1][c] so they mate.
  const top = r === 0 ? 0 : -grid.h[r - 1][c];
  const bottom = r === rows - 1 ? 0 : grid.h[r][c];
  const left = c === 0 ? 0 : -grid.v[r][c - 1];
  const right = c === cols - 1 ? 0 : grid.v[r][c];
  return { top, right, bottom, left };
}

// Render a single piece's image into an offscreen canvas.
// The canvas is large enough to hold the whole piece INCLUDING any tab extrusion.
function renderPieceCanvas(image, imgCellW, imgCellH, row, col, edges, pathInfo) {
  const { path, tabDepth } = pathInfo;
  // The piece's rectangle in image coords:
  const ix = col * imgCellW;
  const iy = row * imgCellH;

  // Canvas extends by tabDepth on every side to cover tabs & jitter.
  const pad = Math.ceil(tabDepth * 1.3);
  const canvasW = Math.ceil(imgCellW) + pad * 2;
  const canvasH = Math.ceil(imgCellH) + pad * 2;

  const c = document.createElement("canvas");
  c.width = canvasW;
  c.height = canvasH;
  const ctx = c.getContext("2d");

  ctx.save();
  ctx.translate(pad, pad);

  // Clip to piece shape (path is in local coords with (0,0) = cell top-left)
  ctx.clip(path);

  // Draw the image chunk. Source: full image, offset so this piece's cell
  // aligns with (0,0) locally. Because tabs extrude outside the cell, we
  // need to draw the surrounding image region too.
  ctx.drawImage(
    image,
    ix - pad, iy - pad,         // source
    canvasW, canvasH,
    -pad, -pad,                  // dest (in local translated coords)
    canvasW, canvasH
  );

  ctx.restore();

  // Edge stroke
  ctx.save();
  ctx.translate(pad, pad);
  ctx.strokeStyle = "rgba(0,0,0,0.55)";
  ctx.lineWidth = 1.2;
  ctx.stroke(path);

  // Subtle inner highlight for depth
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 0.6;
  ctx.stroke(path);
  ctx.restore();

  return { canvas: c, pad };
}

export function generatePuzzle(image, rows, cols, boardW, boardH) {
  // Figure out the image-area we'll use: fit image into boardW*0.75 x boardH*0.75
  // preserving aspect ratio, so there's space around it for scattered pieces.
  const maxW = boardW * 0.6;
  const maxH = boardH * 0.65;
  const imgAspect = image.width / image.height;
  const boxAspect = maxW / maxH;
  let puzzleW, puzzleH;
  if (imgAspect > boxAspect) {
    puzzleW = maxW;
    puzzleH = maxW / imgAspect;
  } else {
    puzzleH = maxH;
    puzzleW = maxH * imgAspect;
  }

  const cellW = puzzleW / cols;
  const cellH = puzzleH / rows;

  // image-space cell size (for drawImage)
  const imgCellW = image.width / cols;
  const imgCellH = image.height / rows;

  const grid = generateEdgeGrid(rows, cols);

  const pieces = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const edges = edgesForCell(r, c, rows, cols, grid);
      // Build path at image-space scale for rendering...
      const jitter = [Math.random(), Math.random(), Math.random(), Math.random()];
      const imgPathInfo = buildEdgePath(imgCellW, imgCellH, edges, jitter);
      const { canvas, pad } = renderPieceCanvas(
        image, imgCellW, imgCellH, r, c, edges, imgPathInfo
      );

      // Rebuild path at display-space scale (for hit-testing)
      const displayPathInfo = buildEdgePath(cellW, cellH, edges, jitter);

      const scale = cellW / imgCellW;
      const piece = new Piece({
        row: r,
        col: c,
        rows,
        cols,
        cellW,
        cellH,
        edges,
        path: displayPathInfo.path,
        tabDepth: displayPathInfo.tabDepth,
        image: canvas,
        imagePad: pad * scale,
        imageScale: scale,
      });
      pieces.push(piece);
    }
  }

  return {
    pieces,
    rows,
    cols,
    cellW,
    cellH,
    puzzleW,
    puzzleH,
  };
}
