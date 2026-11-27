import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { snapshotUrl, type EmergencyKind, type NoteAction } from "../lib/api";
import { timeOf, useCountdown } from "../lib/live";
import type { Notification } from "../lib/types";
import { AlertIcon, BellIcon, CheckIcon, LockIcon, ShieldIcon, UnlockIcon, UsersIcon, XIcon } from "./Icons";

interface Props {
  note: Notification;
  queued: number; // other alerts waiting behind this one
  onDecide: (n: Notification, action: NoteAction) => Promise<void>;
  onEmergency: (n: Notification, action: EmergencyKind) => Promise<void>;
  onClose: () => void;
}

/** Full-attention popup for a new intruder or relative-approval alert. */
export default function AlertPopup({ note: n, queued, onDecide, onEmergency, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const left = useCountdown(n.expires_at, n.status === "pending");
  const intruder = n.kind === "intruder";
  const emergency = (n.emergency ?? "").split(",").filter(Boolean);
  const policeCalled = emergency.includes("police");
  const sirenOn = emergency.includes("siren");
  const resolved = !(n.status === "pending" || n.status === "new" || n.status === "blocked");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Relative allowed/denied (here or elsewhere): show the outcome briefly, then move on.
  useEffect(() => {
    if (!intruder && resolved) {
      const t = setTimeout(onClose, 1800);
      return () => clearTimeout(t);
    }
  }, [intruder, resolved, onClose]);

  const run = (fn: () => Promise<void>) => async () => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  const outcome: Record<string, [string, string]> = {
    approved: ["t-ok", intruder ? "Entry allowed manually: door unlocked" : "Entry allowed: door unlocked"],
    denied: ["t-bad", "Entry denied: door stays locked"],
    expired: ["t-bad", "No response in time: request expired, door locked"],
    read: ["t-bad", "Dismissed: door stays locked"],
  };

  return (
    <motion.div className="modal-backdrop alert-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div className={`modal alert-pop k-${n.kind} ${n.status === "blocked" ? "blocked" : ""}`} role="alertdialog" aria-modal="true"
        aria-label={n.title} initial={{ scale: 0.9, y: 30, opacity: 0 }} animate={{ scale: 1, y: 0, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }} transition={{ type: "spring", stiffness: 340, damping: 26 }}>
        <header className="alert-head">
          <span className="alert-icon">{intruder ? <AlertIcon size={22} /> : <UsersIcon size={22} />}</span>
          <div>
            <span className="eyebrow">{intruder ? "Security alert" : "Approval request"} · {timeOf(n.ts)}
              {n.source === "simulation" && <span className="src src-simulation">SIM</span>}</span>
            <h2>{intruder ? (n.status === "blocked" ? "Door blocked: intruder outside" : "Intruder at the front door!") : n.title}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close popup"><XIcon size={18} /></button>
        </header>

        <div className="alert-body">
          {n.snapshot_id && <img className="alert-snap" src={snapshotUrl(n.snapshot_id)} alt={`Snapshot of ${n.name ?? "visitor"}`} />}
          <div className="alert-info">
            <p>{n.body}</p>
            <div className="kv"><span>Identity</span><b>{intruder ? "Unknown person" : `${n.name} (relative)`}</b></div>
            <div className="kv"><span>Match score</span><b className="mono">{n.score != null ? n.score.toFixed(2) : "—"}</b></div>
            {n.status === "pending" && <div className="kv"><span>Auto-deny in</span><b className="mono t-warn">{left}s</b></div>}
          </div>
        </div>

        {/* Step 1: decide */}
        {(n.status === "pending" || (intruder && n.status === "new")) && (
          <div className="alert-actions">
            <button className="btn ok lg" disabled={busy} onClick={run(() => onDecide(n, "allow"))}>
              <UnlockIcon size={16} /> {intruder ? "Manual allow" : "Allow entry"}
            </button>
            <button className="btn bad lg" disabled={busy} onClick={run(() => onDecide(n, intruder ? "block" : "deny"))}>
              {intruder ? <><LockIcon size={16} /> Block door</> : <><XIcon size={16} /> Deny</>}
            </button>
          </div>
        )}

        {/* Step 2 (intruder blocked): emergency options */}
        {intruder && n.status === "blocked" && (
          <div className="emergency">
            <div className="emergency-head"><ShieldIcon size={18} /> Door is locked. What next?</div>
            <div className="emergency-grid">
              <button className={`em-btn police ${policeCalled ? "done" : ""}`} disabled={busy || policeCalled}
                onClick={run(() => onEmergency(n, "police"))}>
                <span className="em-ic">{policeCalled ? <CheckIcon size={22} /> : "🚓"}</span>
                <b>{policeCalled ? "Police notified" : "Call police"}</b>
                <small>{policeCalled ? "Simulated call to 112 logged" : "Emergency 112 (simulated)"}</small>
              </button>
              <button className={`em-btn siren ${sirenOn ? "done" : ""}`} disabled={busy}
                onClick={run(() => onEmergency(n, "siren"))}>
                <span className="em-ic">🚨</span>
                <b>{sirenOn ? "Sound siren again" : "Sound siren"}</b>
                <small>Scare the intruder away</small>
              </button>
            </div>
            <p className="muted small">Calls are simulated in this prototype and recorded in the visit log.{" "}
              On a phone you can also <a href="tel:112">dial 112 directly</a>.</p>
            <div className="alert-actions end"><button className="btn" onClick={onClose}><CheckIcon size={15} /> Done</button></div>
          </div>
        )}

        {resolved && outcome[n.status] && (
          <div className={`alert-outcome ${outcome[n.status][0]}`}><BellIcon size={16} /> {outcome[n.status][1]}
            {intruder && <button className="btn sm" onClick={onClose}>Close</button>}
          </div>
        )}

        {queued > 0 && <div className="alert-queue mono">+{queued} more alert{queued > 1 ? "s" : ""} waiting</div>}
      </motion.div>
    </motion.div>
  );
}
