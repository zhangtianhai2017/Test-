// A single jigsaw piece.
// The "logical" position is (x, y) — the top-left of its cell rectangle in
// board coordinates (NOT including tab extrusion). When rendering, we offset
// by imagePad so the tabs extend outside.
//
// Pieces are grouped into connected clusters. All pieces in a group share
// the same group reference (an array). When any piece in a group moves, the
// whole group moves together. Each piece stores an "anchor" offset relative
// to the group's reference piece so the relative layout is preserved.

export class Piece {
  constructor(opts) {
    this.row = opts.row;
    this.col = opts.col;
    this.rows = opts.rows;
    this.cols = opts.cols;
    this.cellW = opts.cellW;
    this.cellH = opts.cellH;
    this.edges = opts.edges;
    this.path = opts.path;           // Path2D in local cell coords
    this.tabDepth = opts.tabDepth;
    this.image = opts.image;         // offscreen canvas with the piece art
    this.imagePad = opts.imagePad;   // padding on canvas (display-space px)
    this.imageScale = opts.imageScale; // scale from image canvas px -> display px

    // Position in board coordinates (top-left of the cell rectangle)
    this.x = 0;
    this.y = 0;

    // Group: array of pieces that are connected. Initially singleton.
    this.group = [this];
  }

  get width() { return this.cellW; }
  get height() { return this.cellH; }

  // Draw the piece at its current (x, y).
  draw(ctx) {
    const pad = this.imagePad;
    const imgW = this.image.width * this.imageScale;
    const imgH = this.image.height * this.imageScale;
    // Shadow: only draw if pieces are still loose-ish
    ctx.drawImage(
      this.image,
      0, 0, this.image.width, this.image.height,
      this.x - pad, this.y - pad, imgW, imgH
    );
  }

  // Hit-test: is (bx, by) in board coords inside this piece?
  hitTest(ctx, bx, by) {
    // Transform to local coords
    const lx = bx - this.x;
    const ly = by - this.y;
    return ctx.isPointInPath(this.path, lx, ly);
  }

  // Correct position for the piece, given a puzzle anchor (top-left of the
  // solved puzzle on the board).
  correctX(anchorX) { return anchorX + this.col * this.cellW; }
  correctY(anchorY) { return anchorY + this.row * this.cellH; }
}

// Merge two groups into one. After merge, all pieces reference the same
// group array. Positions are unchanged (caller should already have snapped
// them). We mutate group A to absorb group B.
export function mergeGroups(a, b) {
  if (a === b) return a;
  for (const p of b) {
    p.group = a;
    a.push(p);
  }
  return a;
}
