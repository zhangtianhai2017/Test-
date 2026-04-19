import * as THREE from "three";
import { createGame, type Card, type EngineEvent, type RuleSetId } from "@blackjack/engine";

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x05331a);
scene.fog = new THREE.Fog(0x05331a, 8, 18);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 3.2, 4.6);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(2, devicePixelRatio));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const ambient = new THREE.AmbientLight(0xffffff, 0.35);
scene.add(ambient);
const spot = new THREE.SpotLight(0xfff1c4, 1.1, 20, Math.PI / 5, 0.4, 1.2);
spot.position.set(0, 6, 2);
spot.castShadow = true;
scene.add(spot);

const tableGeo = new THREE.CylinderGeometry(3.2, 3.2, 0.12, 64);
const tableMat = new THREE.MeshStandardMaterial({ color: 0x0b5e2c, roughness: 0.8 });
const table = new THREE.Mesh(tableGeo, tableMat);
table.receiveShadow = true;
scene.add(table);

const rimGeo = new THREE.TorusGeometry(3.2, 0.12, 16, 80);
const rimMat = new THREE.MeshStandardMaterial({ color: 0x2a1a0f, roughness: 0.4, metalness: 0.3 });
const rim = new THREE.Mesh(rimGeo, rimMat);
rim.rotation.x = Math.PI / 2;
rim.position.y = 0.06;
scene.add(rim);

const CARD_W = 0.42;
const CARD_H = 0.6;
const CARD_T = 0.008;

function makeCardTexture(c: Card, faceDown = false): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 360;
  const ctx = canvas.getContext("2d")!;
  if (faceDown) {
    ctx.fillStyle = "#8a1c1c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#631010";
    ctx.lineWidth = 10;
    for (let i = -canvas.height; i < canvas.width; i += 28) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i + canvas.height, canvas.height);
      ctx.stroke();
    }
    ctx.strokeStyle = "#f7e3a1";
    ctx.lineWidth = 4;
    ctx.strokeRect(10, 10, canvas.width - 20, canvas.height - 20);
  } else {
    ctx.fillStyle = "#fafafa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = c.suit === "♥" || c.suit === "♦" ? "#b21318" : "#111";
    ctx.font = "bold 56px ui-sans-serif";
    ctx.textBaseline = "top";
    ctx.fillText(c.rank, 14, 12);
    ctx.font = "bold 48px ui-sans-serif";
    ctx.fillText(c.suit, 14, 64);
    ctx.save();
    ctx.translate(canvas.width - 14, canvas.height - 12);
    ctx.rotate(Math.PI);
    ctx.font = "bold 56px ui-sans-serif";
    ctx.fillText(c.rank, 0, 0);
    ctx.font = "bold 48px ui-sans-serif";
    ctx.fillText(c.suit, 0, 52);
    ctx.restore();
    ctx.font = "bold 120px ui-sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(c.suit, canvas.width / 2, canvas.height / 2 - 60);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.anisotropy = 4;
  return tex;
}

function makeCardMesh(c: Card, faceDown = false): THREE.Mesh {
  const geo = new THREE.BoxGeometry(CARD_W, CARD_T, CARD_H);
  const faceTex = makeCardTexture(c, false);
  const backTex = makeCardTexture(c, true);
  const side = new THREE.MeshStandardMaterial({ color: 0xdddddd });
  const face = new THREE.MeshStandardMaterial({ map: faceTex, roughness: 0.6 });
  const back = new THREE.MeshStandardMaterial({ map: backTex, roughness: 0.6 });
  const mats = [side, side, face, back, side, side];
  const mesh = new THREE.Mesh(geo, mats);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  if (faceDown) mesh.rotation.x = Math.PI;
  return mesh;
}

interface CardSprite {
  mesh: THREE.Mesh;
  targetPos: THREE.Vector3;
  targetRot: THREE.Euler;
  t: number;
  from: THREE.Vector3;
  fromRot: THREE.Euler;
  fromT: number;
}

const cardSprites = new Map<string, CardSprite>();
const deckPos = new THREE.Vector3(-2.2, 0.08, -1.1);

const game = createGame({ ruleSetId: "VEGAS" });

function cardKey(target: "player" | "dealer", handIndex: number, idx: number): string {
  return `${target}:${handIndex}:${idx}`;
}

function layout(): void {
  const s = game.getState();
  const dealerZ = -0.9;
  const playerZ = 1.0;
  s.dealer.forEach((c, i) => {
    const key = cardKey("dealer", 0, i);
    let sp = cardSprites.get(key);
    const targetPos = new THREE.Vector3(-0.7 + i * 0.28, 0.08 + i * 0.002, dealerZ);
    const faceDown = i === 1 && s.dealerHoleHidden;
    const targetRot = new THREE.Euler(0, 0, faceDown ? Math.PI : 0);
    if (!sp) {
      const mesh = makeCardMesh(c, false);
      mesh.position.copy(deckPos);
      mesh.rotation.y = Math.PI * 0.12;
      scene.add(mesh);
      sp = {
        mesh,
        targetPos: targetPos.clone(),
        targetRot: targetRot.clone(),
        t: 0,
        from: mesh.position.clone(),
        fromRot: mesh.rotation.clone(),
        fromT: performance.now(),
      };
      cardSprites.set(key, sp);
    } else {
      if (!sp.targetPos.equals(targetPos) || sp.targetRot.z !== targetRot.z) {
        sp.from = sp.mesh.position.clone();
        sp.fromRot = sp.mesh.rotation.clone();
        sp.targetPos = targetPos;
        sp.targetRot = targetRot;
        sp.fromT = performance.now();
      }
    }
  });
  s.hands.forEach((h, hi) => {
    const offsetX = (hi - (s.hands.length - 1) / 2) * 1.8;
    h.cards.forEach((c, i) => {
      const key = cardKey("player", hi, i);
      let sp = cardSprites.get(key);
      const targetPos = new THREE.Vector3(offsetX - 0.7 + i * 0.28, 0.08 + i * 0.002, playerZ);
      const targetRot = new THREE.Euler(0, 0, 0);
      if (!sp) {
        const mesh = makeCardMesh(c, false);
        mesh.position.copy(deckPos);
        mesh.rotation.y = Math.PI * 0.12;
        scene.add(mesh);
        sp = {
          mesh,
          targetPos: targetPos.clone(),
          targetRot: targetRot.clone(),
          t: 0,
          from: mesh.position.clone(),
          fromRot: mesh.rotation.clone(),
          fromT: performance.now(),
        };
        cardSprites.set(key, sp);
      } else if (!sp.targetPos.equals(targetPos)) {
        sp.from = sp.mesh.position.clone();
        sp.fromRot = sp.mesh.rotation.clone();
        sp.targetPos = targetPos;
        sp.targetRot = targetRot;
        sp.fromT = performance.now();
      }
    });
  });
}

function clearCards(): void {
  for (const sp of cardSprites.values()) scene.remove(sp.mesh);
  cardSprites.clear();
}

function render(): void {
  const now = performance.now();
  for (const sp of cardSprites.values()) {
    const dt = Math.min(1, (now - sp.fromT) / 380);
    const e = 1 - Math.pow(1 - dt, 3);
    sp.mesh.position.lerpVectors(sp.from, sp.targetPos, e);
    sp.mesh.rotation.x = THREE.MathUtils.lerp(sp.fromRot.x, sp.targetRot.x, e);
    sp.mesh.rotation.z = THREE.MathUtils.lerp(sp.fromRot.z, sp.targetRot.z, e);
  }
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
requestAnimationFrame(render);

// HUD + controls
const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;
const bankrollEl = $("bankroll");
const phaseEl = $("phase");
const logEl = $("log");

function log(msg: string): void {
  const line = document.createElement("div");
  line.textContent = msg;
  logEl.prepend(line);
}

function updateHUD(): void {
  const s = game.getState();
  bankrollEl.textContent = `bankroll: ${s.bankroll}`;
  phaseEl.textContent = `phase: ${s.phase}`;
  const legal = new Set(s.legalActions);
  document.querySelectorAll<HTMLButtonElement>("#actGroup button").forEach((b) => {
    b.disabled = !legal.has(b.dataset.action as never);
  });
  ($("deal") as HTMLButtonElement).disabled = s.phase !== "betting";
}

game.on((e: EngineEvent) => {
  switch (e.type) {
    case "CARD_DEALT":
      log(`${e.to}[${e.handIndex}] ← ${e.card.rank}${e.card.suit}${e.faceDown ? " (hole)" : ""}`);
      break;
    case "HOLE_CARD_REVEALED":
      log(`dealer reveals: ${e.card.rank}${e.card.suit}`);
      break;
    case "NATURAL_BLACKJACK":
      log("★ BLACKJACK!");
      break;
    case "HAND_BUST":
      log(`hand ${e.handIndex} BUST`);
      break;
    case "SIDEBET_WIN":
      log(`side bet: ${e.label} +${e.payout}`);
      break;
    case "ROUND_OVER":
      for (const r of e.results) log(`hand ${r.handIndex}: ${r.outcome} +${r.payout}`);
      break;
    case "PHASE_CHANGED":
      if (e.phase === "betting") clearCards();
      break;
    case "ERROR":
      log(`! ${e.code}: ${e.message}`);
      break;
  }
  layout();
  updateHUD();
});

$("deal").addEventListener("click", () => {
  game.dispatch({ type: "PLACE_BET", amount: Number(($("betAmount") as HTMLInputElement).value) });
});
document.querySelectorAll<HTMLButtonElement>("#actGroup button").forEach((b) => {
  b.addEventListener("click", () => {
    const a = b.dataset.action!;
    game.dispatch({ type: a } as Parameters<typeof game.dispatch>[0]);
  });
});
$("ruleSet").addEventListener("change", (e) => {
  const v = (e.target as HTMLSelectElement).value as RuleSetId;
  game.setRuleSet(v);
  clearCards();
  log(`ruleset → ${v}`);
});

updateHUD();
layout();
