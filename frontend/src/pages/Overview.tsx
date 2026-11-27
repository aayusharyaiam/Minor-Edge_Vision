import { Link } from "react-router-dom";
import { motion } from "motion/react";
import ManualSim from "../components/ManualSim";
import { embedded } from "../components/Layout";
import {
  ArrowIcon, CameraIcon, ChipIcon, DashboardIcon, DatabaseIcon, LockIcon, MotionIcon, PlayIcon,
  ScanIcon, ShieldIcon,
} from "../components/Icons";

const LAYERS = [
  { icon: MotionIcon, n: "01", title: "Physical sensing", body: "PIR sensor + ESP32-CAM capture JPEG frames on motion.", now: "Now: laptop webcam + simulated PIR" },
  { icon: ScanIcon, n: "02", title: "AI / CV server", body: "Python + OpenCV: YuNet face detector and SFace embeddings.", now: "Runs on the laptop (FastAPI)" },
  { icon: ChipIcon, n: "03", title: "Decision engine", body: "Confidence threshold, per-role permissions, failed-attempt count, owner override.", now: "backend/decision.py" },
  { icon: DashboardIcon, n: "04", title: "Data & dashboards", body: "REST + WebSocket API, SQLite event store, React dashboards.", now: "This website" },
];

const OBJECTIVES = [
  ["Motion detection", "PIR triggers the pipeline"],
  ["Event-driven capture", "Frames only when someone arrives"],
  ["Face detection", "Locate the face in each frame"],
  ["Face recognition", "Embedding similarity vs registered users"],
  ["Automated decision", "Threshold + role rules"],
  ["Actuation", "Relay / servo door lock (mocked)"],
  ["Security logging", "Identity, time, decision, snapshot"],
  ["Web dashboard", "Live monitoring, alerts, management"],
  ["Low-power design", "Idle until motion"],
];

const MAPPING = [
  ["ESP32-CAM (OV2640)", "Laptop webcam via the browser", "Done"],
  ["HC-SR501 PIR on IO13", "Click the Motion checkpoint (mock PIR)", "Simulated"],
  ["Relay / servo on IO14–15", "Software door with 10 s auto-relock", "Simulated"],
  ["Face recognition server", "FastAPI + OpenCV YuNet/SFace", "Done"],
  ["Database", "SQLite (MongoDB later)", "Done"],
  ["Dashboard", "React: side-by-side Project + Owner, standalone Test Mode", "Done"],
];

export default function Overview() {
  return (
    <div className="page overview">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Minor project · ECE · BIT Patna</span>
          <h1>Cameras that <em>verify</em>, not just watch.</h1>
          <p className="lede">
            An event-driven access-control system: a motion sensor wakes the camera, AI checks the visitor's face against
            registered owners, the door opens or stays locked, and every visit lands on the owner's dashboard.
          </p>
          <div className="hero-cta">
            <a href="/test" target="_blank" rel="noreferrer" className="btn primary lg"><PlayIcon size={16} /> Start Test Mode ↗</a>
            {!embedded && <Link to="/owner" className="btn lg"><DashboardIcon size={16} /> Owner dashboard</Link>}
          </div>
          <div className="team mono">Aayush Arya · Rudrodeep Chatterjee · Avi Singh</div>
        </div>
        <div className="hero-flow" aria-hidden="true">
          {[MotionIcon, CameraIcon, ScanIcon, ChipIcon, LockIcon, DatabaseIcon].map((Icon, i) => (
            <motion.div key={i} className="flow-chip" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 * i }}>
              <Icon size={18} />
              <span>{["Motion", "Capture", "AI recognition", "Decision", "Access control", "Logging"][i]}</span>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="panel sim">
        <div className="section-head">
          <div>
            <span className="eyebrow">Simulation</span>
            <h2>Walk a visitor up to the door</h2>
            <p className="muted">Move the visitor yourself. Entering the dashed PIR range wakes the camera, clicks a photo and runs the
              real decision engine. The log entry and the owner notification are created at the same moment.</p>
          </div>
        </div>
        <ManualSim />
      </section>

      <section>
        <div className="section-head"><div><span className="eyebrow">Architecture</span><h2>Four layers, motion sensor to dashboard</h2></div></div>
        <div className="layers">
          {LAYERS.map((layer, i) => {
            const Icon = layer.icon;
            return (
              <div key={layer.n} className="layer">
                <div className="layer-top"><span className="layer-n mono">{layer.n}</span><Icon size={22} /></div>
                <h3>{layer.title}</h3>
                <p>{layer.body}</p>
                <span className="layer-now mono">{layer.now}</span>
                {i < LAYERS.length - 1 && <span className="layer-arrow"><ArrowIcon size={18} /></span>}
              </div>
            );
          })}
        </div>
        <div className="rules">
          <h3><ShieldIcon size={18} /> Recognition alone never drives the lock</h3>
          <div className="rule-grid">
            <div><b className="t-ok">Owner</b><span>score ≥ threshold → door unlocks automatically, owner gets an entry log.</span></div>
            <div><b className="t-warn">Relative</b><span>recognised, but the owner approves or denies from the dashboard (90 s timeout).</span></div>
            <div><b className="t-bad">Unknown</b><span>door stays locked, snapshot stored, intruder alert with manual allow.</span></div>
          </div>
        </div>
      </section>

      <section className="two-col">
        <div className="panel">
          <span className="eyebrow">Objectives</span>
          <h2>Nine objectives, one prototype</h2>
          <div className="objectives">
            {OBJECTIVES.map(([title, text], i) => (
              <div key={title} className="objective"><span className="mono">{String(i + 1).padStart(2, "0")}</span><b>{title}</b><p>{text}</p></div>
            ))}
          </div>
        </div>
        <div className="panel">
          <span className="eyebrow">This semester</span>
          <h2>Hardware → software stand-ins</h2>
          <table className="table">
            <thead><tr><th>Final hardware</th><th>Current prototype</th><th /></tr></thead>
            <tbody>
              {MAPPING.map(([hw, sw, state]) => (
                <tr key={hw}><td>{hw}</td><td>{sw}</td><td><span className={`tag ${state === "Done" ? "ok" : "warn"}`}>{state}</span></td></tr>
              ))}
            </tbody>
          </table>
          <a href="/test" target="_blank" rel="noreferrer" className="btn primary block">Try it with your laptop camera <ArrowIcon size={16} /></a>
        </div>
      </section>
    </div>
  );
}
