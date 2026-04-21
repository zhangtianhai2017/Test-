// Pointer-based drag-and-drop for puzzle pieces.

export class InputHandler {
  constructor(canvas, game) {
    this.canvas = canvas;
    this.game = game;
    this.dragStart = null; // {x,y} in board coords
    this.groupStartPositions = null; // Map<piece, {x,y}>

    canvas.addEventListener("pointerdown", this._onDown);
    canvas.addEventListener("pointermove", this._onMove);
    canvas.addEventListener("pointerup", this._onUp);
    canvas.addEventListener("pointercancel", this._onUp);
  }

  _toBoard = (e) => {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  };

  _onDown = (e) => {
    const { x, y } = this._toBoard(e);
    const piece = this.game.pickPieceAt(x, y);
    if (!piece) return;

    this.canvas.setPointerCapture(e.pointerId);
    this.canvas.classList.add("grabbing");

    this.dragStart = { x, y };
    this.groupStartPositions = new Map();
    for (const p of piece.group) {
      this.groupStartPositions.set(p, { x: p.x, y: p.y });
    }
    this.game.startDrag(piece.group);
  };

  _onMove = (e) => {
    if (!this.dragStart) return;
    const { x, y } = this._toBoard(e);
    const dx = x - this.dragStart.x;
    const dy = y - this.dragStart.y;
    for (const [p, start] of this.groupStartPositions) {
      p.x = start.x + dx;
      p.y = start.y + dy;
    }
    this.game.requestDraw();
  };

  _onUp = (e) => {
    if (!this.dragStart) return;
    this.canvas.releasePointerCapture?.(e.pointerId);
    this.canvas.classList.remove("grabbing");
    this.dragStart = null;
    this.groupStartPositions = null;
    this.game.endDrag();
  };
}
