# 🔵 Vulkan — Robot Control Application

A standalone control app for the **rcute-cozmars** robot (Raspberry Pi Zero W).
Desktop app + phone app + minigames + chat + STT/TTS, in one small Python project.

This is a separate project from FlameAGI — nothing is shared between them.

---

## ⚠️ Read this first — what is and isn't included

| Deliverable | Status |
|---|---|
| PC application (source, runnable) | ✅ Included |
| Mobile application (source, runnable) | ✅ Included — served by the PC app, opens in the phone browser / installs as a PWA |
| Raspberry Pi setup instructions | ✅ Included — uses the **stock, unmodified** `rcute-cozmars-server` you already have |
| **Built `.apk` file** | ❌ **Not included — I can't build one** |

**About the APK:** building an Android APK needs the Android SDK, Java and Gradle,
none of which are available in the environment I build in — so I can't hand you a
compiled `.apk`. Two working alternatives are included instead:

1. **PWA (works right now, no build)** — open the phone URL in Chrome, tap
   *"Add to Home Screen"*. You get an icon, a fullscreen app, no browser bars.
   For a robot controller on your own Wi-Fi, this is genuinely equivalent to an APK.
2. **Capacitor project (`mobile-apk/`)** — a ready-to-build Android wrapper if you
   specifically need a real installable `.apk`. Build steps are below; it takes
   about 15 minutes on a machine with Android Studio.

**Nothing here has been tested against real hardware** — I have no robot and no
Pi to test with. The Python all compiles cleanly and the protocol usage follows
the official SDK, but expect to shake out small issues on first run with a real
robot. Tell me what breaks and I'll fix it.

---

## Architecture (and why)

```
   Desktop UI  ─┐
                ├─→  Vulkan PC app (Python)  ──websocket──→  Pi robot server
   Phone UI    ─┘      holds ONE robot connection              (stock rcute)
```

**The important constraint:** the Cozmars server accepts **only one connection at
a time** (there's a lock in its `/rpc` handler). So the PC app holds that single
connection and multiplexes everything through it. This is why the phone talks to
the *PC app* and not to the robot directly — otherwise desktop and phone would
lock each other out.

It's also why the UI is web-based rather than a native toolkit: the phone needs a
UI anyway, so one HTML/JS frontend in two layouts beats maintaining a PyQt app
*and* a separate mobile app.

```
vulkan/
├── run_pc.py              # entry point
├── vulkan/
│   ├── config.py          # all tunables
│   ├── robot_link.py      # the only file that talks to the robot SDK
│   ├── auto_mode.py       # autonomous roaming behaviour
│   ├── games.py           # minigame framework + 2 games
│   ├── voice.py           # STT/TTS routing + command parsing + chat
│   └── server.py          # aiohttp: serves both UIs + websocket control
├── web/                   # desktop UI, mobile UI, blue theme, icons
└── mobile-apk/            # optional Capacitor wrapper for a real APK
```

---

## 1. Raspberry Pi setup

You do **not** need to modify the Pi at all — Vulkan uses the stock server.

If the Pi isn't set up yet:

```bash
# On the Pi Zero W (Raspberry Pi OS)
sudo apt update && sudo apt install -y python3-pip
python3 -m pip install rcute-cozmars-server
sudo python3 -m rcute_cozmars_server
```

The server runs on **port 80**. To start it automatically on boot, the upstream
project ships a `cozmars.service` systemd unit — enable it with
`sudo systemctl enable cozmars.service`.

Check it's alive by opening `http://rcute-cozmars-XXXX.local/` (where `XXXX` is
the 4-character serial printed on the robot) in a browser — you should see the
robot's own status page. Note the IP shown there.

---

## 2. PC app setup

Requires **Python 3.7+** (3.9+ recommended).

```bash
cd vulkan
python -m pip install -r requirements.txt
python run_pc.py
```

A window opens, and the console prints two URLs:

```
  === VULKAN ===
  Desktop UI : http://127.0.0.1:8420/
  Phone UI   : http://192.168.1.42:8420/m
```

Useful flags:

```bash
python run_pc.py --robot 1a2b     # connect to a specific serial
python run_pc.py --robot 192.168.1.90
python run_pc.py --browser        # no native window, just serve
python run_pc.py --port 9000
```

> If `pywebview` fails to install (it needs native GUI libraries on some Linux
> setups), just use `--browser` and open the URL yourself — everything works
> identically.

**Connecting:** type the robot's 4-character serial (or its IP) in the top-left
box and hit **Connect**. Leave it blank to auto-discover, which works if there's
exactly one robot on the network. The status pill turns green when connected.

---

## 3. Phone app

**Option A — PWA (recommended, works immediately):**

1. Make sure the phone is on the **same Wi-Fi** as the PC.
2. Open the Phone URL printed by the PC app (e.g. `http://192.168.1.42:8420/m`).
3. Chrome menu → **Add to Home Screen**. It installs with the blue Vulkan icon
   and opens fullscreen.

**Option B — build a real APK:**

```bash
cd mobile-apk
npm install
npx cap add android
npx cap sync android
npx cap open android      # opens Android Studio → Build → Build APK
```

Or without Android Studio, if you have the SDK and Java installed:

```bash
cd mobile-apk/android
./gradlew assembleDebug           # Windows: gradlew.bat assembleDebug
# APK lands in android/app/build/outputs/apk/debug/app-debug.apk
```

The wrapper app asks for the PC's IP on first launch and remembers it.

---

## 4. Using it

### Manual mode
You drive. Everything is direct control.

- **Keyboard:** `W A S D` or arrow keys to drive, `Space` to stop.
  Keys are hold-to-drive — the app re-sends while held, and the robot stops the
  moment you release (a dead-man's switch, so it can't run away if the app hangs).
- **On-screen D-pad:** click and hold, same behaviour.
- **Arms:** the *Arms* slider, or the Down / Mid / Up buttons.
- **Head:** the *Head* slider.
- **Lights:** Blue / Cyan / White buttons.

### Auto mode
Vulkan roams on its own. Each tick it reads the sonar and picks a weighted action
— drive, turn, look around, move its arms, change its lights, or pause — so it
reads as a robot with its own agenda rather than a fixed loop. Obstacle avoidance
always overrides: if the sonar sees anything closer than 20cm it backs off and
turns away.

**Wake word:** while in Auto, say **"Vulkan"** (tap the 🎤 button first — see the
STT note below). It stops, looks up, and greets you out loud, then carries on
roaming. You can also give it commands while it's roaming.

### Camera
The feed appears in the centre panel on desktop and under the *Camera* tab on
mobile, at ~6 fps (tunable via `CAMERA_FPS` in `config.py` — the Pi Zero W is not
fast, so pushing this much higher will stutter).

### Chat + STT/TTS

The **target selector** decides where speech and replies go:

| Target | What happens |
|---|---|
| 🤖 **To robot** | Reply is spoken through the **robot's** speaker; commands drive the robot |
| 💻 **To PC** | Reply is spoken through the **PC/phone** speakers; it's a normal chat |

You can override it per-message by prefixing:
- `"Vulkan, go forward"` → forced to the robot
- `"Computer, what's the weather like"` → forced to the PC

**Movement commands are matched literally**, not sent to a model — "go forward",
"turn left", "stop", "arms up", "look down", "auto mode" all work instantly and
work with **no AI model installed at all**.

**Conversational replies are optional.** If you have [Ollama](https://ollama.com)
running with `gemma2:2b` pulled, non-command messages get a real reply. Without
it, chat degrades to a short canned response and every robot control still works.

**Speech recognition runs in the browser** (Web Speech API), not on the Pi — the
Pi Zero W has nowhere near the headroom for it. This means: it works well in
Chrome/Edge, and may not work at all in Firefox or some browsers. That's a browser
limitation, not a bug in Vulkan.

### Joystick (mobile)
The *Drive* tab has an analog stick. It transmits continuously (~8×/sec) and
converts the stick vector into differential track speeds, so it's true
proportional control — push halfway for half speed, push diagonally to arc —
rather than discrete commands. Release and the robot stops immediately.

### Minigames

Two games ship, and the framework takes about 20 lines to add another
(subclass `BaseGame` in `games.py`, add it to the `GAMES` tuple — the UI picks it
up automatically, no UI changes needed).

- **Red Light, Green Light** — the robot drives on green and you have to hit STOP
  before it turns red.
- **Follow the Leader** — the robot performs a move and you copy it with the
  direction buttons before time runs out.

---

## Troubleshooting

| Problem | Cause / fix |
|---|---|
| "Connection failed" | Robot busy (Scratch or another app holds the single connection), wrong serial, or Pi not on the network. Open `http://rcute-cozmars-XXXX.local/` to verify the Pi is up. |
| Phone can't reach the PC URL | Different Wi-Fi networks, or the PC firewall is blocking port 8420. Allow Python through the firewall. |
| Camera stays blank | `opencv-python` missing, or the robot connected but the camera failed to start. Check the PC console for "Camera capture failed". |
| Mic button does nothing | Browser doesn't support Web Speech API — use Chrome or Edge. |
| Chat says "can't reach my chat brain" | Ollama isn't running. This is optional; commands still work. |
| Robot keeps moving after release | Shouldn't happen (movements have a short duration and auto-expire), but hit `Space` or the ■ button. |
