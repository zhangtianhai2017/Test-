// Rendering layer. Takes game state and draws to canvas.

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.dpr = window.devicePixelRatio || 1;
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.round(rect.width * this.dpr);
    this.canvas.height = Math.round(rect.height * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    return { w: rect.width, h: rect.height };
  }

  clear(w, h) {
    this.ctx.clearRect(0, 0, w, h);
  }

  drawBoard(game) {
    const { w, h } = game.size;
    this.clear(w, h);

    // Outline of solved puzzle (subtle target)
    if (game.showTarget) {
      this.ctx.save();
      this.ctx.strokeStyle = "rgba(255,255,255,0.08)";
      this.ctx.lineWidth = 1;
      this.ctx.strokeRect(
        game.anchorX, game.anchorY,
        game.puzzleW, game.puzzleH
      );
      this.ctx.restore();
    }

    // Draw each group in z-order. Within a group, draw pieces in a
    // consistent order (by row then col) so edges overlap nicely.
    for (const group of game.groupOrder) {
      // Slight drop shadow for loose pieces (single-piece groups)
      const isLoose = group.length === 1;
      if (isLoose) {
        this.ctx.save();
        this.ctx.shadowColor = "rgba(0,0,0,0.4)";
        this.ctx.shadowBlur = 8;
        this.ctx.shadowOffsetX = 2;
        this.ctx.shadowOffsetY = 3;
      }
      for (const piece of group) {
        piece.draw(this.ctx);
      }
      if (isLoose) this.ctx.restore();
    }

    // Highlight the active (dragging) group
    if (game.draggingGroup) {
      this.ctx.save();
      this.ctx.strokeStyle = "rgba(77,124,255,0.8)";
      this.ctx.lineWidth = 2;
      for (const piece of game.draggingGroup) {
        this.ctx.save();
        this.ctx.translate(piece.x, piece.y);
        this.ctx.stroke(piece.path);
        this.ctx.restore();
      }
      this.ctx.restore();
    }
  }
}
