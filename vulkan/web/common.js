/* Shared between the desktop and mobile UIs: the websocket link to the
   Python app, plus browser speech (STT/TTS).

   Speech recognition runs here in the browser rather than on the Pi —
   the Pi Zero W has nowhere near the headroom for it, and the browser's
   Web Speech API is already available wherever this UI is open. */

export const VK = {
  ws: null,
  reqId: 0,
  pending: new Map(),
  handlers: {},
  connected: false,

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);

    this.ws.onopen = () => {
      this.connected = true;
      this.emit("link", { up: true });
    };
    this.ws.onclose = () => {
      this.connected = false;
      this.emit("link", { up: false });
      setTimeout(() => this.connect(), 2000); // auto-reconnect
    };
    this.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "result" && this.pending.has(msg.id)) {
        this.pending.get(msg.id)(msg);
        this.pending.delete(msg.id);
        return;
      }
      this.emit(msg.type, msg);
    };
  },

  on(type, fn) {
    (this.handlers[type] ||= []).push(fn);
  },

  emit(type, msg) {
    (this.handlers[type] || []).forEach((fn) => fn(msg));
  },

  /** Fire-and-forget — used for high-rate joystick/keyboard input. */
  send(action, payload = {}) {
    if (!this.connected) return;
    this.ws.send(JSON.stringify({ action, ...payload }));
  },

  /** Request/response — used when the UI needs the result back. */
  call(action, payload = {}) {
    return new Promise((resolve) => {
      if (!this.connected) return resolve({ ok: false, error: "not connected" });
      const id = ++this.reqId;
      this.pending.set(id, resolve);
      this.ws.send(JSON.stringify({ action, id, ...payload }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          resolve({ ok: false, error: "timeout" });
        }
      }, 65000);
    });
  },
};

/* ---------------- speech ---------------- */

export const Speech = {
  recog: null,
  listening: false,

  supported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  },

  /** Speak on the PC/phone this UI is open on. Robot-side speech goes
      through the server instead (robot.say), so it comes out of the
      robot's own speaker. */
  speak(text) {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    speechSynthesis.speak(u);
  },

  listen(onResult, onEnd, lang = "en-US") {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) {
      onEnd?.("Speech recognition isn't supported in this browser.");
      return;
    }
    this.recog = new Rec();
    this.recog.lang = lang;
    this.recog.continuous = false;
    this.recog.interimResults = false;

    this.recog.onresult = (e) => {
      const t = e.results?.[0]?.[0]?.transcript;
      if (t) onResult(t);
    };
    this.recog.onerror = (e) => onEnd?.(`Speech error: ${e.error}`);
    this.recog.onend = () => {
      this.listening = false;
      onEnd?.();
    };
    this.listening = true;
    this.recog.start();
  },

  stop() {
    this.recog?.stop();
    this.listening = false;
  },
};
