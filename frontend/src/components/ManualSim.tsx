import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import Door, { type DoorMode } from "./Door";
import LogActions from "./LogActions";
import {
  AlertIcon, ArrowIcon, BellIcon, CameraIcon, ChipIcon, DatabaseIcon, DoorIcon, MotionIcon,
  RefreshIcon, ScanIcon, ShieldIcon, UserIcon, UsersIcon,
} from "./Icons";
import { api } from "../lib/api";
import { timeOf, useLive } from "../lib/live";
import type { AccessEvent, DoorStatus, Run } from "../lib/types";

type Visitor = "owner" | "relative" | "intruder";
type Phase = "outside" | "pir" | "camera" | "photo" | "decided" | "error";

const VISITORS: Record<Visitor, { label: string; name: string; skin: string; body: string }> = {
  owner: { label: "Owner", name: "Aayush (sim)", skin: "#d6b48c", body: "#34d399" },
  relative: { label: "Relative", name: "Rudrodeep (sim)", skin: "#b98a63", body: "#fbbf24" },
  intruder: { label: "Unknown visitor", name: "Unknown", skin: "#3b4250", body: "#4b5563" },
};

const STEPS = [
  { icon: ShieldIcon, title: "Standby", text: "Visitor is outside the PIR range. Camera off, relay locked." },
  { icon: MotionIcon, title: "PIR triggered", text: "Visitor stepped into the dashed zone: PIR goes HIGH, a run starts." },
  { icon: CameraIcon, title: "Camera on + photo", text: "Camera wakes only now and clicks a photo of the visitor." },
  { icon: ScanIcon, title: "Recognition", text: "Photo is matched against registered faces (simulated score)." },
  { icon: ChipIcon, title: "Decision", text: "Identity + score vs threshold + role decide." },
  { icon: DoorIcon, title: "Door", text: "Owner: unlock. Relative: ask owner. Unknown: stay locked." },
  { icon: DatabaseIcon, title: "Log + notification", text: "Added at the same moment to the log and the Owner dashboard." },
];

// Scene geometry, in percent of the scene box. y = depth on the ground (0 = at the wall, 100 = front).
const START = { x: 12, y: 70 };
const DOOR_X = 80;
const ZONE = { cx: DOOR_X, cy: 18, rx: 15, ry: 34 };
const SPEED = 32; // units per second
const feetTop = (y: number) => 56 + y * 0.4;
const inZone = (p: { x: number; y: number }) =>
  ((p.x - ZONE.cx) / ZONE.rx) ** 2 + ((p.y - ZONE.cy) / ZONE.ry) ** 2 <= 1;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const KEYS: Record<string, [number, number]> = {
  ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
  w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0], W: [0, -1], S: [0, 1], A: [-1, 0], D: [1, 0],
};

/** Draws the illustrated "camera photo" that is uploaded as the visit snapshot. */
function renderPhoto(visitor: Visitor): Promise<Blob> {
  const v = VISITORS[visitor];
  const canvas = document.createElement("canvas");
  canvas.width = 480;
  canvas.height = 360;
  const g = canvas.getContext("2d")!;
  const bg = g.createLinearGradient(0, 0, 0, 360);
  bg.addColorStop(0, "#1b2836");
  bg.addColorStop(1, "#0c1219");
  g.fillStyle = bg;
  g.fillRect(0, 0, 480, 360);
  g.fillStyle = "#2b3a4c";
  g.fillRect(40, 30, 400, 330);
  g.fillStyle = "#121a23";
  g.fillRect(56, 46, 368, 314);
  // visitor (head + shoulders, slightly fish-eyed like a doorbell cam)
  g.fillStyle = v.body;
  g.beginPath();
  g.ellipse(240, 380, 150, 120, 0, Math.PI, 0);
  g.fill();
  g.fillStyle = v.skin;
  g.beginPath();
  g.ellipse(240, 180, 72, 86, 0, 0, Math.PI * 2);
  g.fill();
  if (visitor === "intruder") {
    g.fillStyle = "#0b0e12";
    g.fillRect(170, 160, 140, 30);
    g.beginPath();
    g.ellipse(240, 120, 80, 50, 0, Math.PI, 0);
    g.fill();
  } else {
    g.fillStyle = "#1b1410";
    g.beginPath();
    g.ellipse(240, 118, 74, 40, 0, Math.PI, 0);
    g.fill();
    g.fillStyle = "#1b1410";
    g.beginPath(); g.arc(214, 176, 6, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.arc(266, 176, 6, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "#7a4b3a";
    g.lineWidth = 4;
    g.beginPath(); g.arc(240, 214, 18, 0.15 * Math.PI, 0.85 * Math.PI); g.stroke();
  }
  // HUD overlay
  g.strokeStyle = "#34d399";
  g.lineWidth = 3;
  for (const [x, y, dx, dy] of [[14, 14, 1, 1], [466, 14, -1, 1], [14, 346, 1, -1], [466, 346, -1, -1]]) {
    g.beginPath(); g.moveTo(x, y + dy * 22); g.lineTo(x, y); g.lineTo(x + dx * 22, y); g.stroke();
  }
  g.fillStyle = "rgba(0,0,0,0.55)";
  g.fillRect(14, 322, 300, 24);
  g.fillStyle = "#e6edf3";
  g.font = "13px monospace";
  g.fillText(`CAM-01 · PIR TRIGGER · ${new Date().toLocaleTimeString()}`, 22, 339);
  g.fillStyle = "#f87171";
  g.beginPath(); g.arc(452, 30, 6, 0, Math.PI * 2); g.fill();
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.88));
}

export default function ManualSim() {
  const [visitor, setVisitor] = useState<Visitor>("owner");
  const [pos, setPos] = useState(START);
  const [phase, setPhase] = useState<Phase>("outside");
  const [run, setRun] = useState<Run | null>(null);
  const [door, setDoor] = useState<DoorStatus | null>(null);
  const [error, setError] = useState("");
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [log, setLog] = useState<AccessEvent[]>([]);
  const [threshold, setThreshold] = useState(0.4);
  const held = useRef(new Set<string>());
  const sceneRef = useRef<HTMLDivElement>(null);
  const runRef = useRef<string | null>(null);
  const busy = useRef(false);
  const inside = inZone(pos);

  useEffect(() => {
    api.status().then((s) => { setDoor(s.door); setThreshold(s.threshold); }).catch(() => undefined);
    api.events(40, "simulation").then(setLog).catch(() => undefined);
  }, []);

  useLive((m) => {
    if (m.type === "door") setDoor(m.door);
    if (m.type === "status") setDoor(m.status.door);
    if (m.type === "run.update" && m.run.id === runRef.current) setRun((r) => (r ? { ...r, ...m.run } : r));
    if (m.type === "event" && m.event.source === "simulation") {
      setLog((list) => [m.event, ...list.filter((e) => e.id !== m.event.id)].slice(0, 40));
    }
    if (m.type === "events.cleared" && (m.source === null || m.source === "simulation")) setLog([]);
  });

  // ---- movement: keyboard (when the scene is focused) and on-screen pad -----------------------
  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (held.current.size) {
        let dx = 0, dy = 0;
        held.current.forEach((k) => { const v = KEYS[k]; if (v) { dx += v[0]; dy += v[1]; } });
        if (dx || dy) {
          const len = Math.hypot(dx, dy);
          setPos((p) => ({
            x: Math.max(2, Math.min(96, p.x + (dx / len) * SPEED * dt)),
            y: Math.max(0, Math.min(100, p.y + (dy / len) * SPEED * 1.6 * dt)),
          }));
        }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    const up = () => held.current.clear();
    window.addEventListener("blur", up);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("blur", up); };
  }, []);

  const onKey = (e: React.KeyboardEvent, down: boolean) => {
    if (!(e.key in KEYS)) return;
    e.preventDefault();
    if (down) held.current.add(e.key);
    else held.current.delete(e.key);
  };
  const pad = (key: string) => ({
    onPointerDown: (e: React.PointerEvent) => { e.preventDefault(); held.current.add(key); sceneRef.current?.focus(); },
    onPointerUp: () => held.current.delete(key),
    onPointerLeave: () => held.current.delete(key),
  });

  // ---- the pipeline: entering the zone triggers PIR → camera → photo → decision -------------
  const trigger = useCallback(async (who: Visitor) => {
    busy.current = true;
    setError("");
    setPhotoUrl(null);
    try {
      setPhase("pir");
      const created = await api.createRun("simulation");
      runRef.current = created.id;
      setRun(created);
      await sleep(700);
      setPhase("camera");
      await sleep(800);
      setPhase("photo");
      const photo = await renderPhoto(who);
      setPhotoUrl(URL.createObjectURL(photo));
      await sleep(250);
      const result = await api.simulate(created.id, who, photo);
      setRun(result);
      setPhase("decided");
    } catch (e) {
      setError((e as Error).message);
      setPhase("error");
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    if (inside && phase === "outside" && !busy.current) trigger(visitor);
    if (!inside && (phase === "decided" || phase === "error") && !busy.current) {
      setPhase("outside");
      setRun(null);
      runRef.current = null;
    }
  }, [inside, phase, visitor, trigger]);

  const reset = () => {
    held.current.clear();
    setPos(START);
  };

  // ---- derived view state ----------------------------------------------------------------
  const v = VISITORS[visitor];
  const decision = run?.decision ?? null;
  const step = phase === "outside" ? 0 : phase === "pir" ? 1 : phase === "camera" || phase === "photo" ? 2
    : phase === "decided" ? 6 : 1;
  const doorMode: DoorMode = phase !== "decided" ? "locked"
    : decision === "PENDING" ? "waiting"
    : decision === "GRANTED" ? (door?.unlocked ? "open" : "locked")
    : "alarm";
  const score = run?.result?.score;
  const depth = 0.75 + pos.y * 0.004;

  return (
    <div className="msim">
      <div className="sim-controls">
        <div className="seg" role="radiogroup" aria-label="Visitor">
          {(Object.keys(VISITORS) as Visitor[]).map((key) => (
            <button key={key} className={visitor === key ? "on" : ""} disabled={phase !== "outside"}
              title={phase !== "outside" ? "Walk out of the PIR zone to change visitor" : undefined}
              onClick={() => setVisitor(key)}>
              {key === "owner" ? <UserIcon size={15} /> : key === "relative" ? <UsersIcon size={15} /> : <AlertIcon size={15} />}
              {VISITORS[key].label}
            </button>
          ))}
        </div>
        <button className="btn" onClick={reset}><RefreshIcon size={15} /> Back to start</button>
      </div>

      <div className="sim-grid">
        <div>
          <div ref={sceneRef} className={`scene manual ${inside ? "zone-hit" : ""}`} tabIndex={0}
            onKeyDown={(e) => onKey(e, true)} onKeyUp={(e) => onKey(e, false)}
            onBlur={() => held.current.clear()}
            aria-label="Simulation scene. Focus it and use the arrow keys or W A S D to move the visitor.">
            <div className="scene-sky" />
            <div className="house" />
            <div className="pir-zone" style={{
              left: `${ZONE.cx - ZONE.rx}%`, width: `${ZONE.rx * 2}%`,
              top: `${feetTop(ZONE.cy - ZONE.ry)}%`, height: `${feetTop(ZONE.cy + ZONE.ry) - feetTop(ZONE.cy - ZONE.ry)}%`,
            }}><span>PIR range</span></div>
            <div className={`pir-sensor ${phase !== "outside" ? "on" : ""}`} style={{ left: `${DOOR_X - 13}%` }}><span /> PIR</div>
            <div className={`cam-unit ${phase === "camera" || phase === "photo" ? "on" : phase === "decided" ? "done" : ""}`}
              style={{ left: `${DOOR_X + 7}%` }}>
              <CameraIcon size={16} />
              {phase === "photo" && <span className="cam-flash" />}
            </div>
            <div className="scene-door" style={{ left: `${DOOR_X}%` }}><Door mode={doorMode} /></div>
            <div className={`visitor v-${visitor}`}
              style={{ left: `${pos.x}%`, top: `${feetTop(pos.y)}%`, transform: `translate(-50%, -100%) scale(${depth})`, zIndex: 2 + Math.round(pos.y) }}>
              <div className="visitor-head">{(phase === "camera" || phase === "photo") && <span className="scanline" />}</div>
              <div className="visitor-body" />
              <span className="visitor-tag">{v.label}</span>
            </div>
            <div className="scene-hud">
              <div className="hud-row"><span>PIR</span><b className={phase !== "outside" ? "t-bad" : ""}>{phase !== "outside" ? "HIGH" : "LOW"}</b></div>
              <div className="hud-row"><span>Camera</span>
                <b className={phase === "camera" || phase === "photo" ? "t-ok" : ""}>
                  {phase === "outside" ? "OFF" : phase === "pir" ? "WAKING" : phase === "camera" ? "ON" : phase === "photo" ? "CLICK!" : "OFF"}
                </b>
              </div>
              <div className="hud-row"><span>Match</span><b>{score != null && phase === "decided" ? score.toFixed(2) : "—"}</b></div>
              <div className="score-bar">
                <motion.span style={{ background: decision === "DENIED" ? "var(--bad)" : decision === "PENDING" ? "var(--warn)" : "var(--ok)" }}
                  animate={{ width: score != null && phase === "decided" ? `${Math.max(0, score) * 100}%` : "0%" }} transition={{ duration: 0.8 }} />
                <i style={{ left: `${threshold * 100}%` }} />
              </div>
              <div className="hud-row"><span>Decision</span>
                <b className={decision === "GRANTED" ? "t-ok" : decision === "PENDING" ? "t-warn" : decision === "DENIED" ? "t-bad" : ""}>
                  {phase !== "decided" ? "—" : decision === "GRANTED" ? "GRANTED" : decision === "PENDING" ? "ASK OWNER" : "DENIED"}
                </b>
              </div>
            </div>
            <AnimatePresence>
              {photoUrl && phase !== "outside" && (
                <motion.figure className="sim-photo" initial={{ scale: 0.6, opacity: 0, rotate: -4 }} animate={{ scale: 1, opacity: 1, rotate: 0 }} exit={{ opacity: 0 }}>
                  <img src={photoUrl} alt="Photo captured by the simulated door camera" />
                  <figcaption className="mono">captured photo</figcaption>
                </motion.figure>
              )}
            </AnimatePresence>
            <AnimatePresence>
              {phase === "decided" && run?.notification && (
                <motion.div key={run.id + (decision ?? "")} className={`scene-toast t-${run.identity ?? "owner"}`}
                  initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}>
                  {run.identity === "intruder" ? <AlertIcon size={16} /> : <BellIcon size={16} />}
                  {decision === "PENDING" ? "Approval request sent to the owner" : decision === "GRANTED"
                    ? (run.identity === "owner" ? "Owner entered: logged + notified" : "Owner allowed entry: door open")
                    : run.identity === "intruder" ? "Intruder alert + photo sent to owner" : "Entry denied by owner"}
                </motion.div>
              )}
            </AnimatePresence>
            {phase === "error" && <div className="scene-toast t-intruder"><AlertIcon size={16} /> {error}</div>}
            {phase === "outside" && pos.x === START.x && pos.y === START.y && (
              <div className="scene-hint mono">Click here, then use ← ↑ → ↓ / W A S D (or the pad) to walk to the door</div>
            )}
          </div>
          <div className="dpad" aria-label="Movement pad">
            <span />
            <button aria-label="Move up" {...pad("ArrowUp")}><ArrowIcon size={18} style={{ transform: "rotate(-90deg)" }} /></button>
            <span />
            <button aria-label="Move left" {...pad("ArrowLeft")}><ArrowIcon size={18} style={{ transform: "rotate(180deg)" }} /></button>
            <span className="dpad-mid">{inside ? "IN RANGE" : "MOVE"}</span>
            <button aria-label="Move right" {...pad("ArrowRight")}><ArrowIcon size={18} /></button>
            <span />
            <button aria-label="Move down" {...pad("ArrowDown")}><ArrowIcon size={18} style={{ transform: "rotate(90deg)" }} /></button>
            <span />
          </div>
        </div>

        <ol className="sim-steps">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const state = i < step || (step === 6 && i === 6) ? "done" : i === step ? "active" : "";
            return (
              <li key={s.title} className={state}>
                <span className="sim-ic"><Icon size={16} /></span>
                <div><b>{i + 1}. {s.title}</b><p>{s.text}</p></div>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="sim-log">
        <div className="panel-head">
          <h3>Simulation log</h3>
          <LogActions source="simulation" onError={setError} />
        </div>
        {log.length === 0 ? <p className="muted small">Walk a visitor into the PIR range: each step is logged here and on the Owner dashboard.</p> : (
          <ul>
            <AnimatePresence initial={false}>
              {log.map((e) => (
                <motion.li key={e.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                  <span className="mono">{timeOf(e.ts)}</span>
                  <b className={`stage s-${e.stage}`}>{e.stage}</b>
                  <span className="msg">{e.message}</span>
                  {e.decision && <span className={`tag ${e.decision === "GRANTED" ? "ok" : e.decision === "PENDING" ? "warn" : "bad"}`}>{e.decision}</span>}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </div>
  );
}
