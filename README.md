# EdgeVision: AI Smart Access Control (software prototype)

This is the software half of the **AI-Enabled IoT Smart Access Control & Visitor
Surveillance System** minor project (ECE, BIT Patna). The laptop webcam stands in
for the ESP32-CAM, and the PIR sensor and door relay/servo are simulated. The
pipeline itself is real: face detection, face embeddings, the access decision,
logging and live owner notifications.

| Part | Stack |
|---|---|
| Backend | Python · FastAPI · OpenCV DNN (YuNet face detector + SFace 128-d embeddings) |
| Database | **SQLite**: a single file, `data/edgevision.sqlite3`, with no database server to install or start |
| Frontend | React + TypeScript (Vite) · react-router · motion |
| Live updates | WebSocket `/ws` |

---

## Step-by-step: start it

### 0. One-time setup (only the first time)

You need **Python 3.11+** and **Node.js 18+**.

**Linux / macOS**
```bash
cd edge-vision-sitl
python3 -m venv .venv-linux                              # Python environment
.venv-linux/bin/pip install -r requirements.txt          # backend libraries
.venv-linux/bin/python scripts/download_models.py        # 2 face models, ~39 MB
cd frontend && npm install && npm run build && cd ..     # build the React app
```

**Windows (PowerShell)**
```powershell
cd edge-vision-sitl
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_models.py
cd frontend; npm install; npm run build; cd ..
```

### 1. Start the backend (this also serves the frontend)
```bash
.venv-linux/bin/python main.py          # Windows: .\.venv\Scripts\python.exe main.py
```
Wait for `Uvicorn running on http://127.0.0.1:8000`.

### 2. Open the app
Open **http://127.0.0.1:8000** in Chrome, Edge or Firefox.

### 3. Database
There is nothing to start. SQLite is built into Python. The file
`data/edgevision.sqlite3` is created on the first run and updated automatically.

### 4. Stop
Press **Ctrl + C** in the terminal that is running `main.py`.

> After you change frontend code, run `npm run build` again in `frontend/`. Or,
> for hot reload while you develop, keep `main.py` running and also run
> `cd frontend && npm run dev`, then open **http://localhost:5173**. Vite
> forwards `/api` and `/ws` to the backend on port 8000.

> The browser allows webcam access only on `localhost` / `127.0.0.1` (or HTTPS).
> Allow the camera when it asks.

---

## Pages and features

| URL | Page | What it does |
|---|---|---|
| **`/`** | **Side by side** | The Project dashboard (left) and the Owner dashboard (right) on one screen. Drag the divider to resize; double-click it to reset. Each pane scrolls on its own, and both update live. On a narrow window the panes become tabs. |
| `/project` | Project dashboard | The explainer, as a page on its own. |
| `/owner` | Owner dashboard | The owner view, as a page on its own (also good on a phone). |
| **`/test`** | **Test Mode** | Opens on its own in a new tab and runs the real pipeline with your webcam. |

### Project dashboard (`/` left pane, or `/project`)
- **Hero** with the project pitch and the six-stage flow (motion → capture → AI → decision → access → logging).
- **Simulation (manual)**: pick *Owner*, *Relative* or *Unknown visitor*, click the
  scene, and walk the visitor with **← ↑ → ↓ / W A S D** or the on-screen pad.
  - Outside the dashed **PIR range**: standby, PIR LOW, camera off.
  - Step into the range: **PIR goes HIGH**, the **camera turns on** and **clicks a photo**
    (shown as a snapshot card).
  - Then the decision runs, and the **log entry and the owner notification are added
    at the same moment**. They appear in the simulation log and on the Owner dashboard
    (tagged `SIM`).
  - Owner: the door opens. Relative: *ask owner*; approve in the Owner pane and the sim
    door opens. Unknown: locked, with an intruder alert.
  - Walk out of the range (or press **Back to start**) to reset, change the visitor,
    and walk in again.
  - **Simulation log** below the scene, with **Export CSV** and **Clear log** (both
    affect simulation events only).
- **Architecture**: the four layers (sensing → AI server → decision engine → dashboards)
  and the rule that recognition alone never drives the lock.
- **Objectives** (9) and a **hardware → software stand-ins** table for this semester.

### Owner dashboard (`/` right pane, or `/owner`)
- **Stats**: visits, granted, denied, and how many need action.
- **Alerts & notifications** (live, with a sound and a pop-up message):
  - **Popup**: every new intruder or relative alert opens a popup with the snapshot,
    score and actions. Several alerts queue up; Esc or ✕ closes a popup.
  - *Intruder*: **Manual allow** or **Block door**. Block door force-locks the door, then
    the popup offers **🚓 Call police (112)** and **🚨 Sound siren**. The call is simulated
    in this prototype and logged; the siren plays in the browser. The card keeps a
    *Call police* button and reopens the options.
  - *Approval* (relative at the door): **Allow entry** or **Deny**, with a 90 s countdown.
    After that it expires and the door stays locked.
  - *Entry*: an owner came in and the door opened automatically.
  - Filter by type (*All types / Alerts only*) and by source (*All / Live camera / Simulation*).
  - **Export CSV** downloads the notifications that match the source filter.
  - **Clear** deletes the notifications that match the source filter, after a confirmation.
    Any pending approval among them is denied first, so no visit is left waiting and the
    door stays locked. The visit log is not touched.
- **Door relay**: the current lock state and a **Lock now** button.
- **Registered faces**: add a person (name plus *Owner* or *Relative*), add face
  photos with **📷 webcam capture** or **⬆ upload**, change their role, and delete
  photos or people.
- **Visit history**: every pipeline event with time, source (`LIVE` camera or `SIM`),
  stage, person, score and decision. Filter by *All / Live camera / Simulation*.
  **Export CSV** downloads the filtered log (Excel-friendly, with a local-time column).
  **Clear log** deletes the filtered events; notifications are kept.

### Test Mode (`/test`, its own tab)
A roadmap of six checkpoints. Each one unlocks the next:
1. **Motion detected**: click the sensor icon. The mock PIR goes HIGH.
2. **Camera capture**: click the camera icon. The webcam pop-up opens, counts down
   3-2-1, captures 5 frames and closes by itself.
3. **Detecting & recognising**: a scanning animation, then the snapshot with the face
   box, the best similarity score and the threshold.
4. **Who is it?**: Owner, Relative or Intruder lights up.
5. **Door**: opens (owner), shows *waiting for owner* (relative), or stays locked
   with an alarm (intruder).
6. **Owner notified**: a preview of what was sent to the Owner dashboard.

The right side shows the animated door, a live log for the run and the registry stats.
Use **Run again** for the next visitor.

### Suggested demo order
1. Open `/`. In the **Owner** pane, add yourself as **Owner** and capture 2–3 photos.
2. Click **Open Test Mode in a new tab** and go through the checkpoints. You are
   recognised, the door opens, and an *Entry* card appears in the Owner pane.
3. Let a friend try (or cover your face). An **Intruder** alert pops up in the Owner pane.
4. Register the friend as **Relative** and run it again. Test Mode waits; click
   **Allow entry** in the Owner pane and the door opens in Test Mode.
5. Use the **Simulation** in the left pane to explain the flow without a camera: walk
   each visitor type into the PIR range and watch the Owner pane react.

---

## Access rules (`backend/decision.py`)

| Who | Rule | Result |
|---|---|---|
| Owner | similarity ≥ `MATCH_THRESHOLD` (default 0.40) | door unlocks for `RELAY_SECONDS` (10 s), entry logged |
| Relative | similarity ≥ threshold | door stays locked until the owner allows it (90 s timeout) |
| Anyone else | below threshold or not registered | door locked, snapshot saved, intruder alert |

Most of the captured frames must agree on the same person. Repeated failed
attempts within 10 minutes are flagged in the alert. Copy `.env.example` to `.env`
to change the thresholds and timings.

## Where data is stored

| What | Where |
|---|---|
| People, roles, face embeddings, events (live + simulation), notifications | `data/edgevision.sqlite3` (SQLite) |
| Registered face photos | `authorized_faces/<Name>/<id>.jpg` |
| Visitor snapshots (with the face box drawn) | `snapshots/<id>.jpg` |
| Face models | `models/*.onnx` |

To start over with empty data, stop the server and delete `data/edgevision.sqlite3`,
the photo folders inside `authorized_faces/` and the images in `snapshots/`.

To inspect the database, open it with any SQLite viewer (for example "DB Browser for
SQLite"), or run `sqlite3 data/edgevision.sqlite3 "select * from events"`.

## Log API
- `GET /api/events/export.csv?source=live|simulation` (omit `source` for everything)
- `DELETE /api/events?source=live|simulation` (omit `source` to clear everything)
- `POST /api/notifications/{id}/decision` with `allow | deny | block | dismiss`
- `POST /api/notifications/{id}/emergency` with `police | siren` (intruder alerts only)
- `GET /api/notifications/export.csv?source=live|simulation`
- `DELETE /api/notifications?source=live|simulation` (pending approvals are denied first; omit `source` for all)

## Tests
```bash
.venv-linux/bin/python -m pytest
```

## Project layout
```
main.py               start the server (python main.py)
backend/
  main.py             FastAPI routes, WebSocket, serves frontend/dist
  service.py          a visit: PIR → verify → decide → door → notify
  face_engine.py      YuNet detection, SFace embeddings, cosine matching
  decision.py         access rules
  db.py               SQLite tables: persons, face_refs, events, notifications
  hardware_mock.py    mock PIR and door relay with auto-relock
  events.py           live WebSocket fan-out
  config.py           settings (read from .env)
frontend/src/
  pages/              SplitView, Overview (project), Owner, TestMode
  components/         Layout, WebcamModal, Door, Icons
  lib/                API client, live-events hook, types
scripts/download_models.py
tests/                pytest suite and fixture photos
```

## Moving to the real ESP32-CAM later
- The ESP32 POSTs its JPEG frames to `POST /api/runs`, then `POST /api/runs/{id}/verify`.
  These are the same endpoints Test Mode uses.
- Replace `MockRelayDriver` in `backend/hardware_mock.py` with a serial or HTTP relay driver.
- SQLite can be swapped for MongoDB inside `backend/db.py` without changing the API.
