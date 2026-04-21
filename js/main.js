import { Renderer } from "./renderer.js";
import { Game } from "./game.js";
import { InputHandler } from "./input.js";
import { PRESETS } from "./presets.js";
import { fileToImage, downscaleImage, formatTime } from "./utils.js";

const $ = (id) => document.getElementById(id);

const canvas = $("board");
const renderer = new Renderer(canvas);
const game = new Game(canvas, renderer);
new InputHandler(canvas, game);

let currentImage = null;

function parseDifficulty(val) {
  const [r, c] = val.split("x").map(Number);
  return { rows: r, cols: c };
}

async function startNewGame() {
  const { rows, cols } = parseDifficulty($("difficulty").value);
  const presetKey = $("presetImage").value;
  if (!currentImage) {
    currentImage = PRESETS[presetKey]();
  }
  // Update reference panel
  const refImg = $("referenceImage");
  refImg.src = currentImage.toDataURL?.() || currentImage.src;

  await game.loadPuzzle(currentImage, rows, cols);
}

$("newGame").addEventListener("click", startNewGame);

$("difficulty").addEventListener("change", startNewGame);

$("presetImage").addEventListener("change", () => {
  currentImage = PRESETS[$("presetImage").value]();
  startNewGame();
});

$("uploadImage").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    const img = await fileToImage(file);
    currentImage = downscaleImage(img, 1600);
    await startNewGame();
  } catch (err) {
    alert("无法加载图片：" + err.message);
  }
});

$("toggleRef").addEventListener("click", () => {
  $("referenceImage").classList.toggle("hidden");
});

$("playAgain").addEventListener("click", () => {
  $("winModal").classList.add("hidden");
  startNewGame();
});

game.onProgressChange = ({ placed, total, moves }) => {
  $("moves").textContent = String(moves);
  $("progress").textContent = `${placed} / ${total}`;
};

game.onWin = ({ time, moves }) => {
  $("winTime").textContent = formatTime(time);
  $("winMoves").textContent = String(moves);
  $("winModal").classList.remove("hidden");
};

// Timer loop
function tick() {
  $("timer").textContent = game.tick(performance.now());
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

window.addEventListener("resize", () => {
  // Re-layout without regenerating pieces (pieces keep their current positions).
  // We just update the canvas size. The solved anchor stays where it was.
  game.onResize();
});

// Boot
(async () => {
  currentImage = PRESETS.landscape();
  await startNewGame();
  if (location.search.includes("debug")) window.__game = game;
})();
