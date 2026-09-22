import { VK, Speech } from "/static/common.js";

const $ = (id) => document.getElementById(id);

/* ---------- tabs ---------- */

const pages = { tDrive: "pDrive", tCam: "pCam", tChat: "pChat" };
Object.entries(pages).forEach(([btn, page]) => {
  $(btn).onclick = () => {
    Object.entries(pages).forEach(([b, p]) => {
      $(b).classList.toggle("on", b === btn);
      $(p).classList.toggle("on", p === page);
    });
  };
});

/* ---------- status ---------- */

VK.on("link", ({ up }) => { if (!up) setConn(false, "App offline"); });

VK.on("status", (s) => {
  setConn(s.connected, s.connected ? "Connected" : "Offline");
  $("mManual").classList.toggle("on", s.mode === "manual");
  $("mAuto").classList.toggle("on", s.mode === "auto");
});

function setConn(ok, text) {
  $("dot").className = "dot " + (ok ? "on" : "off");
  $("connText").textContent = text;
}

// The phone doesn't manage the robot connection — the PC app owns the
// single allowed robot connection. The phone just drives through it.

$("mManual").onclick = () => VK.call("mode", { mode: "manual" });
$("mAuto").onclick = () => VK.call("mode", { mode: "auto" });

/* ---------- joystick ---------- */

const base = $("base");
const knob = $("knob");
const MAX_R = 70;           // px the knob can travel from centre
let active = false;
let vec = { x: 0, y: 0 };

function setKnob(dx, dy) {
  knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
}

function handle(clientX, clientY) {
  const r = base.getBoundingClientRect();
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  let dx = clientX - cx;
  let dy = clientY - cy;

  const dist = Math.hypot(dx, dy);
  if (dist > MAX_R) {
    dx = (dx / dist) * MAX_R;
    dy = (dy / dist) * MAX_R;
  }
  setKnob(dx, dy);
  // y inverted: pushing up = forward
  vec = { x: dx / MAX_R, y: -dy / MAX_R };
}

function release() {
  active = false;
  vec = { x: 0, y: 0 };
  setKnob(0, 0);
  VK.send("drive", { left: 0, right: 0 });
}

base.addEventListener("touchstart", (e) => {
  active = true;
  handle(e.touches[0].clientX, e.touches[0].clientY);
  e.preventDefault();
}, { passive: false });

base.addEventListener("touchmove", (e) => {
  if (!active) return;
  handle(e.touches[0].clientX, e.touches[0].clientY);
  e.preventDefault();
}, { passive: false });

base.addEventListener("touchend", release);
base.addEventListener("touchcancel", release);

// Mouse support too, so the mobile UI is testable on a desktop browser.
base.addEventListener("mousedown", (e) => { active = true; handle(e.clientX, e.clientY); });
window.addEventListener("mousemove", (e) => active && handle(e.clientX, e.clientY));
window.addEventListener("mouseup", () => active && release());

/* Continuous send loop — this is what makes the joystick real-time
   control rather than occasional commands. Converts the stick vector to
   differential track speeds (classic arcade mixing), and only transmits
   when the value actually changed or the stick is live. */
let lastSent = "";
setInterval(() => {
  const { x, y } = vec;
  let left = y + x;
  let right = y - x;
  const peak = Math.max(1, Math.abs(left), Math.abs(right));
  left = +(left / peak).toFixed(2);
  right = +(right / peak).toFixed(2);

  const key = `${left},${right}`;
  if (key === "0,0" && lastSent === "0,0") return;
  lastSent = key;
  VK.send("drive", { left, right, duration: 0.3 });
}, 120);

/* ---------- arms / head / lights ---------- */

$("mLift").oninput = (e) => VK.send("lift", { height: e.target.value / 100 });
$("mHead").oninput = (e) => VK.send("head", { angle: e.target.value / 100 });

document.querySelectorAll("[data-color]").forEach((b) => {
  b.onclick = () => VK.send("lights", { color: b.dataset.color });
});

/* ---------- camera ---------- */

VK.on("camera", ({ jpeg }) => {
  $("mcam").src = "data:image/jpeg;base64," + jpeg;
  $("mcam").style.display = "block";
  $("mcamEmpty").style.display = "none";
});

/* ---------- chat ---------- */

function addLine(role, text) {
  const d = document.createElement("div");
  d.className = "line " + (role === "you" ? "you" : role === "sys" ? "sys" : "vulkan");
  d.textContent = text;
  $("mlog").appendChild(d);
  $("mlog").scrollTop = $("mlog").scrollHeight;
}

async function send(text) {
  const t = (text ?? $("mmsg").value).trim();
  if (!t) return;
  addLine("you", t);
  $("mmsg").value = "";
  const r = await VK.call("chat", { text: t, target: $("mTarget").value });
  if (r.reply && r.spoken_by === "pc") Speech.speak(r.reply);
}

$("mSend").onclick = () => send();
$("mmsg").addEventListener("keydown", (e) => e.key === "Enter" && send());

VK.on("chat", (m) => m.role === "vulkan" && addLine("vulkan", m.text));

$("mMic").onclick = () => {
  if (!Speech.supported()) return addLine("sys", "Speech recognition isn't available in this browser.");
  if (Speech.listening) return Speech.stop();
  $("mMic").classList.add("on");
  addLine("sys", "Listening…");
  Speech.listen(
    (t) => send(t),
    (err) => {
      $("mMic").classList.remove("on");
      if (err) addLine("sys", err);
    }
  );
};

VK.connect();
