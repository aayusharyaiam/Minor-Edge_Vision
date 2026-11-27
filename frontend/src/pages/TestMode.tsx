import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import Door, { type DoorMode } from "../components/Door";
import WebcamModal from "../components/WebcamModal";
import {
  AlertIcon, BellIcon, CameraIcon, CheckIcon, DoorIcon, MotionIcon, RefreshIcon, ScanIcon,
  UserIcon, UsersIcon,
} from "../components/Icons";
import { api, ApiError } from "../lib/api";
import { timeOf, useLive } from "../lib/live";
import type { AccessEvent, Run, Status } from "../lib/types";

const STEPS = [
  { key: "motion", icon: MotionIcon, title: "Motion detected", hint: "Click the sensor to simulate a visitor walking up to the door (PIR → HIGH)." },
  { key: "camera", icon: CameraIcon, title: "Camera capture", hint: "Click the camera to open the laptop webcam. It captures a short burst and closes itself." },
  { key: "detecting", icon: ScanIcon, title: "Detecting & recognising", hint: "Face is located, aligned and turned into an embedding, then compared with registered faces." },
  { key: "identity", icon: UserIcon, title: "Who is it?", hint: "Owner, relative, or an unknown visitor (intruder)." },
  { key: "door", icon: DoorIcon, title: "Door", hint: "Opens for owners, waits for approval for relatives, stays locked for intruders." },
  { key: "notified", icon: BellIcon, title: "Owner notified", hint: "The event and snapshot are pushed live to the owner dashboard." },
] as const;

const REVEAL_MS = 1100;

export default function TestMode() {
  const [run, setRun] = useState<Run | null>(null);
  const [progress, setProgress] = useState(0); // number of completed checkpoints
  const [busy, setBusy] = useState(false);
  const [camOpen, setCamOpen] = useState(false);
  const [error, setError] = useState<{ step: number; message: string } | null>(null);
  const [events, setEvents] = useState<AccessEvent[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const timers = useRef<number[]>([]);
  const runId = run?.id;

  useEffect(() => { api.status().then(setStatus).catch(() => undefined); }, []);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  useLive((m) => {
    if (m.type === "event" && m.event.run_id && m.event.run_id === runId) {
      setEvents((list) => (list.some((e) => e.id === m.event.id) ? list : [...list, m.event]));
    }
    if (m.type === "run.update" && m.run.id === runId) {
      // Owner decision for a waiting relative arrives here.
      setRun((current) => (current ? { ...current, ...m.run } : current));
    }
    if (m.type === "door") setRun((current) => (current ? { ...current, door: m.door } : current));
    if (m.type === "status") setStatus(m.status);
  });

  const finalDecision = run?.decision && run.decision !== "PENDING";

  // When a pending relative gets decided by the owner, finish the last two checkpoints.
  useEffect(() => {
    if (progress === 4 && finalDecision) {
      timers.current.push(window.setTimeout(() => setProgress(5), 500));
      timers.current.push(window.setTimeout(() => setProgress(6), 500 + REVEAL_MS));
    }
  }, [progress, finalDecision]);

  const startMotion = async () => {
    setError(null);
    setBusy(true);
    try {
      const created = await api.createRun();
      setRun(created);
      setEvents([]);
      setProgress(1);
      api.getRun(created.id).then((r) => setEvents(r.events ?? [])).catch(() => undefined);
    } catch (e) {
      setError({ step: 0, message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const onFrames = useCallback(async (frames: Blob[]) => {
    if (!run) return;
    setCamOpen(false);
    setError(null);
    setProgress(2);
    setBusy(true);
    const started = Date.now();
    try {
      const result = await api.verify(run.id, frames);
      // Let the scanning animation play for a moment even if the server is fast.
      await new Promise((r) => setTimeout(r, Math.max(0, 1500 - (Date.now() - started))));
      setRun(result);
      setEvents(result.events ?? []);
      setProgress(3);
      timers.current.push(window.setTimeout(() => setProgress(4), REVEAL_MS));
      if (result.decision !== "PENDING") {
        timers.current.push(window.setTimeout(() => setProgress(5), REVEAL_MS * 2));
        timers.current.push(window.setTimeout(() => setProgress(6), REVEAL_MS * 3));
      }
    } catch (e) {
      setProgress(1);
      setError({ step: 1, message: e instanceof ApiError ? e.message : "Verification failed" });
      api.getRun(run.id).then((r) => setEvents(r.events ?? [])).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }, [run]);

  const reset = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setRun(null);
    setProgress(0);
    setEvents([]);
    setError(null);
    api.status().then(setStatus).catch(() => undefined);
  };

  const noFaces = status && status.registry.photos === 0;
  const doorMode: DoorMode = useMemo(() => {
    if (!run || progress < 4) return "idle";
    if (run.decision === "PENDING") return "waiting";
    if (run.decision === "GRANTED") return run.door.unlocked ? "open" : "locked";
    return "alarm";
  }, [run, progress]);

  return (
    <div className="page testmode">
      <div className="page-head">
        <div>
          <span className="eyebrow">Test mode · live pipeline</span>
          <h1>Walk through a visit, checkpoint by checkpoint</h1>
          <p className="muted">Each checkpoint unlocks the next. Your laptop camera plays the part of the ESP32-CAM at the door.</p>
        </div>
        <button className="btn" onClick={reset} disabled={busy}><RefreshIcon size={16} /> {progress ? "Run again" : "Reset"}</button>
      </div>

      {noFaces && (
        <div className="banner warn">
          <AlertIcon size={18} />
          <span>No faces are registered yet, so everyone will be treated as an intruder. <Link to="/owner" target="_blank">Add an owner photo ↗</Link> first to see the door open.</span>
        </div>
      )}

      <div className="test-grid">
        <ol className="roadmap">
          {STEPS.map((step, i) => {
            const state = i < progress ? "done" : i === progress ? "active" : "locked";
            const clickable = state === "active" && (i === 0 || i === 1) && !busy;
            const Icon = step.icon;
            return (
              <motion.li key={step.key} className={`checkpoint ${state} ${i === 2 && busy && progress === 2 ? "scanning" : ""}`}
                initial={false} animate={{ opacity: state === "locked" ? 0.45 : 1 }}>
                <div className="spine"><span className="spine-fill" /></div>
                <button className="node" disabled={!clickable}
                  onClick={() => (i === 0 ? startMotion() : setCamOpen(true))}
                  aria-label={step.title}>
                  {state === "done" ? <CheckIcon size={24} /> : <Icon size={26} />}
                  {clickable && <span className="node-ping" />}
                </button>
                <div className="cp-card">
                  <div className="cp-head">
                    <span className="cp-n mono">{String(i + 1).padStart(2, "0")}</span>
                    <h3>{step.title}</h3>
                    {state === "done" && <span className="tag ok">done</span>}
                    {state === "active" && <span className="tag live">{clickable ? "click the icon" : "in progress"}</span>}
                  </div>
                  <p className="muted">{step.hint}</p>
                  <AnimatePresence initial={false}>
                    {(state !== "locked") && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                        <StepBody index={i} state={state} run={run} busy={busy} doorMode={doorMode} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                  {error?.step === i && (
                    <div className="cp-error"><AlertIcon size={16} /> {error.message}
                      {i === 1 && <button className="btn sm" onClick={() => setCamOpen(true)}>Retry camera</button>}
                      {i === 0 && <button className="btn sm" onClick={startMotion}>Retry</button>}
                    </div>
                  )}
                </div>
              </motion.li>
            );
          })}
        </ol>

        <aside className="test-side">
          <div className="panel door-panel">
            <Door mode={doorMode} label={doorMode === "open" ? "UNLOCKED"
              : doorMode === "waiting" ? "AWAITING OWNER" : doorMode === "alarm" ? "LOCKED · ALERT"
              : run?.decision === "GRANTED" && progress >= 4 ? "RELOCKED" : "LOCKED"} />
          </div>
          <div className="panel log">
            <h3>Run log</h3>
            {events.length === 0 ? <p className="muted">Events for this visit will appear here.</p> : (
              <ul>
                {events.map((e) => (
                  <motion.li key={e.id} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
                    <span className="mono">{timeOf(e.ts)}</span>
                    <b className={`stage s-${e.stage}`}>{e.stage}</b>
                    <span>{e.message}</span>
                  </motion.li>
                ))}
              </ul>
            )}
          </div>
          {status && (
            <div className="panel mini-stats">
              <div><span>Registered</span><b>{status.registry.owners} owner · {status.registry.relatives} relative</b></div>
              <div><span>Reference photos</span><b>{status.registry.photos}</b></div>
              <div><span>Threshold</span><b className="mono">{status.threshold.toFixed(2)}</b></div>
              <div><span>Engine</span><b>{status.engine}</b></div>
            </div>
          )}
        </aside>
      </div>

      <WebcamModal open={camOpen} mode="burst" frames={5} title="Front-door camera"
        subtitle="Look at the camera. A short burst of frames is captured automatically."
        onCapture={onFrames} onClose={() => setCamOpen(false)} />
    </div>
  );
}

function StepBody({ index, state, run, busy, doorMode }: {
  index: number; state: string; run: Run | null; busy: boolean; doorMode: DoorMode;
}) {
  const result = run?.result;
  if (index === 0) {
    return state === "done" && run ? (
      <div className="cp-body row"><span className="led on" /> PIR HIGH at <span className="mono">{timeOf(run.created_at)}</span>. Camera subsystem woken.</div>
    ) : null;
  }
  if (index === 1) {
    if (state === "done" && result) {
      return <div className="cp-body row"><CameraIcon size={16} /> {result.frames} frames captured · face in {result.frames_with_face}</div>;
    }
    return <div className="cp-body row muted"><span className="led" /> Camera is off until you click it (event-driven, no streaming).</div>;
  }
  if (index === 2) {
    if (state === "active" && busy) {
      return <div className="cp-body"><div className="scanbar"><span /></div><span className="mono muted">detect → align → embed → compare…</span></div>;
    }
    if (result) {
      const [w, h] = result.image_size;
      const [x, y, bw, bh] = result.box;
      const pct = Math.max(0, Math.min(1, result.score));
      return (
        <div className="cp-body detect">
          <div className="snap">
            <img src={result.snapshot_url} alt="Captured visitor with detected face" />
            <span className="snap-box" style={{ left: `${(x / w) * 100}%`, top: `${(y / h) * 100}%`, width: `${(bw / w) * 100}%`, height: `${(bh / h) * 100}%` }} />
          </div>
          <div className="detect-meta">
            <div className="kv"><span>Best similarity</span><b className="mono">{result.score.toFixed(2)}</b></div>
            <div className="score-bar big">
              <motion.span className={result.role === "unknown" ? "bad" : "ok"} initial={{ width: 0 }} animate={{ width: `${pct * 100}%` }} transition={{ duration: 0.9 }} />
              <i style={{ left: `${result.threshold * 100}%` }} />
            </div>
            <div className="kv"><span>Threshold</span><b className="mono">{result.threshold.toFixed(2)}</b></div>
            <div className="kv"><span>Compared with</span><b>{result.registered_faces} reference photo(s)</b></div>
          </div>
        </div>
      );
    }
    return null;
  }
  if (index === 3 && run?.identity) {
    const options = [
      { key: "owner", label: "Owner", icon: UserIcon },
      { key: "relative", label: "Relative", icon: UsersIcon },
      { key: "intruder", label: "Intruder", icon: AlertIcon },
    ];
    return (
      <div className="cp-body branches">
        {options.map((o) => {
          const Icon = o.icon;
          const hit = run.identity === o.key;
          return (
            <motion.div key={o.key} className={`branch b-${o.key} ${hit ? "hit" : ""}`} animate={hit ? { scale: [1, 1.06, 1] } : {}} transition={{ duration: 0.5 }}>
              <Icon size={20} />
              <b>{o.label}</b>
              {hit && <span>{o.key === "intruder" ? "not recognised" : run.result?.name}</span>}
            </motion.div>
          );
        })}
      </div>
    );
  }
  if (index === 4 && run) {
    const text = doorMode === "open" || run.decision === "GRANTED" ? "Door unlocked: relay energised, auto-relocks after a few seconds."
      : doorMode === "waiting" ? "Door held locked. Approval request is waiting on the owner dashboard."
      : "Door stays LOCKED. Access denied.";
    return (
      <div className={`cp-body row door-msg ${run.decision === "GRANTED" ? "t-ok" : run.decision === "PENDING" ? "t-warn" : "t-bad"}`}>
        <DoorIcon size={16} /> {text}
        {doorMode === "waiting" && <Link className="btn sm" to="/owner" target="_blank">Open owner dashboard ↗</Link>}
      </div>
    );
  }
  if (index === 5 && run?.notification) {
    const n = run.notification;
    return (
      <div className="cp-body">
        <div className={`notif-preview k-${n.kind}`}>
          {n.kind === "intruder" ? <AlertIcon size={18} /> : <BellIcon size={18} />}
          <div><b>{n.title}</b><p>{run.reason ?? n.body}</p></div>
        </div>
        <Link className="btn sm" to="/owner" target="_blank">See it on the owner dashboard ↗</Link>
      </div>
    );
  }
  return null;
}
