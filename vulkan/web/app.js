import { VK, Speech } from "/static/common.js";

const $ = (id) => document.getElementById(id);
let mode = "manual";
let gameRunning = false;
let frames = 0;

/* ---------- connection status ---------- */

VK.on("link", ({ up }) => {
  if (!up) setConnected(false, "App offline");
});

VK.on("status", (s) => {
  setConnected(s.connected, s.connected ? "Connected" : "Offline");
  mode = s.mode;
  $("btnManual").classList.toggle("on", mode === "manual");
  $("btnAuto").classList.toggle("on", mode === "auto");
  $("robotInfo").textContent = s.info?.ip ? `${s.info.hostname || "robot"} · ${s.info.ip}` : "";
  gameRunning = !!s.game;
  $("btnGameStop").style.display = gameRunning ? "block" : "none";
});

function setConnected(ok, text) {
  $("dot").className = "dot " + (ok ? "on" : "off");
  $("connText").textContent = text;
}

/* ---------- camera ---------- */

VK.on("camera", ({ jpeg }) => {
  const img = $("cam");
  img.src = "data:image/jpeg;base64," + jpeg;
  img.style.display = "block";
  $("camEmpty").style.display = "none";
  frames++;
});

setInterval(() => {
  $("fpsChip").textContent = frames ? `${frames} fps` : "no feed";
  frames = 0;
}, 1000);

/* ---------- connect / disconnect ---------- */

$("btnConnect").onclick = async () => {
  addLine("sys", "Connecting…");
  const r = await VK.call("connect", { serial: $("serial").value.trim() });
  addLine("sys", r.connected ? "Robot connected." : `Connection failed: ${r.error}`);
};

$("btnDisconnect").onclick = () => VK.call("disconnect");

/* ---------- modes ---------- */

$("btnManual").onclick = () => VK.call("mode", { mode: "manual" });
$("btnAuto").onclick = () => VK.call("mode", { mode: "auto" });

VK.on("auto", (m) => {
  if (m.action === "greet") addLine("sys", "Heard its name — greeting you.");
  else if (m.action === "avoid") addLine("sys", `Obstacle at ${Math.round(m.distance)}cm — backing off.`);
});

/* ---------- driving: buttons + keyboard ---------- */

document.querySelectorAll("[data-move]").forEach((b) => {
  const dir = b.dataset.move;
  // Hold-to-drive: repeat while held so movement is continuous, not a
  // single pulse per click.
  let timer = null;
  const start = () => {
    VK.send("move", { direction: dir });
    if (dir !== "stop") timer = setInterval(() => VK.send("move", { direction: dir }), 300);
  };
  const end = () => {
    clearInterval(timer);
    timer = null;
    if (dir !== "stop") VK.send("move", { direction: "stop" });
  };
  b.addEventListener("mousedown", start);
  b.addEventListener("mouseup", end);
  b.addEventListener("mouseleave", end);
});

const KEYS = {
  w: "forward", arrowup: "forward",
  s: "backward", arrowdown: "backward",
  a: "left", arrowleft: "left",
  d: "right", arrowright: "right",
  " ": "stop",
};
const held = new Set();

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  const dir = KEYS[e.key.toLowerCase()];
  if (!dir) return;
  e.preventDefault();
  if (held.has(dir)) return;
  held.add(dir);
  VK.send("move", { direction: dir });
});

document.addEventListener("keyup", (e) => {
  const dir = KEYS[e.key.toLowerCase()];
  if (!dir) return;
  held.delete(dir);
  if (dir !== "stop") VK.send("move", { direction: "stop" });
});

// Re-send while a key is held so the robot keeps moving (the server
// applies a short duration per pulse as a dead-man's switch).
setInterval(() => {
  held.forEach((dir) => dir !== "stop" && VK.send("move", { direction: dir }));
}, 300);

/* ---------- arms / head / lights ---------- */

$("lift").oninput = (e) => {
  const v = e.target.value / 100;
  $("liftVal").textContent = `${e.target.value}%`;
  VK.send("lift", { height: v });
};

$("head").oninput = (e) => {
  const v = e.target.value / 100;
  $("headVal").textContent = `${e.target.value}%`;
  VK.send("head", { angle: v });
};

document.querySelectorAll("[data-lift]").forEach((b) => {
  b.onclick = () => {
    const v = parseFloat(b.dataset.lift);
    $("lift").value = v * 100;
    $("liftVal").textContent = `${Math.round(v * 100)}%`;
    VK.send("lift", { height: v });
  };
});

document.querySelectorAll("[data-color]").forEach((b) => {
  b.onclick = () => VK.send("lights", { color: b.dataset.color });
});

/* ---------- chat ---------- */

function addLine(role, text) {
  const d = document.createElement("div");
  d.className = "line " + (role === "you" ? "you" : role === "sys" ? "sys" : "vulkan");
  d.textContent = text;
  $("log").appendChild(d);
  $("log").scrollTop = $("log").scrollHeight;
}

async function send(text) {
  const t = (text ?? $("msg").value).trim();
  if (!t) return;
  addLine("you", t);
  $("msg").value = "";
  const r = await VK.call("chat", { text: t, target: $("target").value });
  // The robot speaks its own replies through its speaker; PC-targeted
  // replies are spoken here in the browser.
  if (r.reply && r.spoken_by === "pc") Speech.speak(r.reply);
}

$("btnSend").onclick = () => send();
$("msg").addEventListener("keydown", (e) => e.key === "Enter" && send());

VK.on("chat", (m) => {
  if (m.role === "vulkan") addLine("vulkan", m.text);
});

$("btnMic").onclick = () => {
  if (!Speech.supported()) return addLine("sys", "Speech recognition isn't available in this browser.");
  if (Speech.listening) return Speech.stop();
  $("btnMic").classList.add("on");
  addLine("sys", "Listening…");
  Speech.listen(
    (transcript) => send(transcript),
    (err) => {
      $("btnMic").classList.remove("on");
      if (err) addLine("sys", err);
    }
  );
};

/* ---------- games ---------- */

VK.on("game", (m) => {
  const d = document.createElement("div");
  d.textContent = m.text + (m.score !== undefined ? ` (score ${m.score})` : "");
  $("gameLog").appendChild(d);
  $("gameLog").scrollTop = $("gameLog").scrollHeight;
});

(async () => {
  const r = await VK.call("game_list");
  (r.games || []).forEach((g) => {
    const b = document.createElement("button");
    b.textContent = g.name;
    b.title = g.description;
    b.onclick = async () => {
      $("gameLog").innerHTML = "";
      await VK.call("game_start", { game: g.id });
      $("btnGameStop").style.display = "block";
      if (g.id === "red_light") showStopButton();
      if (g.id === "follow") showFollowButtons();
    };
    $("gameList").appendChild(b);
  });
})();

$("btnGameStop").onclick = async () => {
  await VK.call("game_stop");
  $("btnGameStop").style.display = "none";
  document.querySelectorAll(".game-ctl").forEach((e) => e.remove());
};

function showStopButton() {
  const b = document.createElement("button");
  b.className = "game-ctl danger";
  b.style.width = "100%";
  b.style.marginTop = "8px";
  b.textContent = "STOP!";
  b.onclick = () => VK.call("game_action", { action: "stop_press" });
  $("gameList").appendChild(b);
}

function showFollowButtons() {
  const wrap = document.createElement("div");
  wrap.className = "game-ctl";
  wrap.style.cssText = "display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px";
  ["forward", "backward", "left", "right"].forEach((m) => {
    const b = document.createElement("button");
    b.textContent = { forward: "▲", backward: "▼", left: "◀", right: "▶" }[m];
    b.onclick = () => VK.call("game_action", { action: "answer", move: m });
    wrap.appendChild(b);
  });
  $("gameList").appendChild(wrap);
}

VK.connect();
