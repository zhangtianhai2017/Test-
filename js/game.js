import { generatePuzzle } from "./puzzleGenerator.js";
import { mergeGroups } from "./piece.js";
import { formatTime } from "./utils.js";

export class Game {
  constructor(canvas, renderer) {
    this.canvas = canvas;
    this.renderer = renderer;
    this.pieces = [];
    this.groupOrder = []; // array of groups in z-order (last = top)
    this.rows = 0;
    this.cols = 0;
    this.cellW = 0;
    this.cellH = 0;
    this.puzzleW = 0;
    this.puzzleH = 0;
    this.anchorX = 0;
    this.anchorY = 0;
    this.size = { w: 0, h: 0 };
    this.showTarget = true;

    this.draggingGroup = null;
    this.dirty = false;

    this.moves = 0;
    this.startTime = 0;
    this.elapsed = 0;
    this.finished = false;

    this.onProgressChange = null;
    this.onWin = null;

    this._rafPending = false;
  }

  async loadPuzzle(image, rows, cols) {
    this.size = this.renderer.resize();
    const { pieces, cellW, cellH, puzzleW, puzzleH } = generatePuzzle(
      image, rows, cols, this.size.w, this.size.h
    );
    this.pieces = pieces;
    this.rows = rows;
    this.cols = cols;
    this.cellW = cellW;
    this.cellH = cellH;
    this.puzzleW = puzzleW;
    this.puzzleH = puzzleH;
    // Center the solved-puzzle anchor on the canvas
    this.anchorX = (this.size.w - puzzleW) / 2;
    this.anchorY = (this.size.h - puzzleH) / 2;

    // Scatter pieces around the board
    this._scatterPieces();

    // Initialize group order: each piece in its own group initially
    this.groupOrder = this.pieces.map((p) => p.group);

    this.moves = 0;
    this.startTime = performance.now();
    this.elapsed = 0;
    this.finished = false;

    this._emitProgress();
    this.requestDraw();
  }

  _scatterPieces() {
    const { w, h } = this.size;
    const margin = 20;
    for (const p of this.pieces) {
      // Avoid placing directly on top of the target area if possible;
      // place into one of the 4 side bands.
      const band = Math.floor(Math.random() * 4);
      let x, y;
      const maxX = w - p.cellW - margin;
      const maxY = h - p.cellH - margin;
      if (band === 0) { // top strip
        x = margin + Math.random() * (w - 2 * margin - p.cellW);
        y = margin + Math.random() * Math.max(0, this.anchorY - 2 * margin - p.cellH);
      } else if (band === 1) { // bottom strip
        x = margin + Math.random() * (w - 2 * margin - p.cellW);
        const bandTop = this.anchorY + this.puzzleH + margin;
        y = bandTop + Math.random() * Math.max(0, h - bandTop - p.cellH - margin);
      } else if (band === 2) { // left strip
        x = margin + Math.random() * Math.max(0, this.anchorX - 2 * margin - p.cellW);
        y = margin + Math.random() * (h - 2 * margin - p.cellH);
      } else { // right strip
        const bandLeft = this.anchorX + this.puzzleW + margin;
        x = bandLeft + Math.random() * Math.max(0, w - bandLeft - p.cellW - margin);
        y = margin + Math.random() * (h - 2 * margin - p.cellH);
      }
      // If the band was empty (no space), fall back to anywhere on canvas.
      if (!isFinite(x) || !isFinite(y) || x < 0 || y < 0) {
        x = margin + Math.random() * Math.max(0, maxX);
        y = margin + Math.random() * Math.max(0, maxY);
      }
      p.x = x;
      p.y = y;
    }
  }

  // Find topmost piece at board coords
  pickPieceAt(bx, by) {
    const ctx = this.renderer.ctx;
    // Iterate groupOrder top-down
    for (let i = this.groupOrder.length - 1; i >= 0; i--) {
      const group = this.groupOrder[i];
      // Iterate pieces in group (any piece hit returns this group's top one)
      for (let j = group.length - 1; j >= 0; j--) {
        if (group[j].hitTest(ctx, bx, by)) return group[j];
      }
    }
    return null;
  }

  startDrag(group) {
    this.draggingGroup = group;
    // Move this group to the top of z-order
    const idx = this.groupOrder.indexOf(group);
    if (idx !== -1) {
      this.groupOrder.splice(idx, 1);
      this.groupOrder.push(group);
    }
    this.requestDraw();
  }

  endDrag() {
    const group = this.draggingGroup;
    this.draggingGroup = null;
    if (!group) return;
    this.moves++;
    this._tryMerges(group);
    this._emitProgress();
    this.requestDraw();
    this._checkWin();
  }

  _tryMerges(group) {
    const SNAP = Math.min(this.cellW, this.cellH) * 0.22;
    let merged = true;
    while (merged) {
      merged = false;
      // For each piece in group, check each neighbor (up/down/left/right)
      for (const p of [...group]) {
        const neighbors = this._neighborsOf(p);
        for (const { neighbor, dx, dy } of neighbors) {
          if (neighbor.group === p.group) continue;
          // Expected position: neighbor.x = p.x + dx, neighbor.y = p.y + dy
          const expX = p.x + dx;
          const expY = p.y + dy;
          const gap = Math.hypot(neighbor.x - expX, neighbor.y - expY);
          if (gap < SNAP) {
            // Snap the entire neighbor group so neighbor lands exactly
            const offX = expX - neighbor.x;
            const offY = expY - neighbor.y;
            for (const np of neighbor.group) {
              np.x += offX;
              np.y += offY;
            }
            mergeGroups(p.group, neighbor.group);
            this._rebuildGroupOrder();
            merged = true;
            break;
          }
        }
        if (merged) break;
      }
    }
  }

  _rebuildGroupOrder() {
    const seen = new Set();
    const order = [];
    // Preserve old relative order where possible
    for (const g of this.groupOrder) {
      // After merge, some pieces in g may now belong to a new group
      // so extract unique groups via piece.group
      for (const p of g) {
        if (!seen.has(p.group)) {
          seen.add(p.group);
          order.push(p.group);
        }
      }
    }
    this.groupOrder = order;
  }

  _neighborsOf(piece) {
    const { row, col } = piece;
    const out = [];
    // Neighbor mapping. dx, dy = expected displacement from piece to neighbor
    // in board coords, assuming both are placed correctly.
    const candidates = [
      { dr: -1, dc: 0, dx: 0, dy: -this.cellH },
      { dr: 1, dc: 0, dx: 0, dy: this.cellH },
      { dr: 0, dc: -1, dx: -this.cellW, dy: 0 },
      { dr: 0, dc: 1, dx: this.cellW, dy: 0 },
    ];
    for (const cand of candidates) {
      const nr = row + cand.dr;
      const nc = col + cand.dc;
      if (nr < 0 || nr >= this.rows || nc < 0 || nc >= this.cols) continue;
      const neighbor = this.pieces.find((p) => p.row === nr && p.col === nc);
      if (neighbor) {
        out.push({ neighbor, dx: cand.dx, dy: cand.dy });
      }
    }
    return out;
  }

  _checkWin() {
    if (this.finished) return;
    if (this.groupOrder.length === 1 &&
        this.groupOrder[0].length === this.pieces.length) {
      this.finished = true;
      this.elapsed = (performance.now() - this.startTime) / 1000;
      // Snap the whole puzzle into perfect alignment with the anchor
      const first = this.pieces[0];
      const correctX = this.anchorX + first.col * this.cellW;
      const correctY = this.anchorY + first.row * this.cellH;
      const dx = correctX - first.x;
      const dy = correctY - first.y;
      for (const p of this.pieces) {
        p.x += dx;
        p.y += dy;
      }
      this.requestDraw();
      if (this.onWin) this.onWin({
        time: this.elapsed,
        moves: this.moves,
      });
    }
  }

  _emitProgress() {
    if (!this.onProgressChange) return;
    // "Progress" = number of pieces merged into groups beyond singletons,
    // measured as (total pieces - number of groups). Max = total - 1.
    const placed = this.pieces.length - this.groupOrder.length;
    this.onProgressChange({
      placed,
      total: this.pieces.length - 1,
      moves: this.moves,
    });
  }

  tick(now) {
    if (!this.finished && this.startTime > 0) {
      this.elapsed = (now - this.startTime) / 1000;
    }
    return formatTime(this.elapsed);
  }

  requestDraw() {
    if (this._rafPending) return;
    this._rafPending = true;
    requestAnimationFrame(() => {
      this._rafPending = false;
      this.renderer.drawBoard(this);
    });
  }

  onResize() {
    this.size = this.renderer.resize();
    this.requestDraw();
  }
}
