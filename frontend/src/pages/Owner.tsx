import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import AlertPopup from "../components/AlertPopup";
import LogActions from "../components/LogActions";
import WebcamModal from "../components/WebcamModal";
import {
  AlertIcon, BellIcon, CameraIcon, CheckIcon, LockIcon, TrashIcon, UnlockIcon, UploadIcon, UserIcon,
  UsersIcon, XIcon,
} from "../components/Icons";
import { api, snapshotUrl, type EmergencyKind, type NoteAction } from "../lib/api";
import { beep, siren, timeOf, useCountdown, useLive } from "../lib/live";
import type { AccessEvent, DoorStatus, Notification, Person, Role, Source, Status } from "../lib/types";

interface Toast { id: number; kind: "intruder" | "approval" | "info" | "error"; text: string }

export default function Owner() {
  const [notes, setNotes] = useState<Notification[]>([]);
  const [persons, setPersons] = useState<Person[]>([]);
  const [events, setEvents] = useState<AccessEvent[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [door, setDoor] = useState<DoorStatus | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [filter, setFilter] = useState<"all" | "alerts">("all");
  const [logSource, setLogSource] = useState<Source | undefined>(undefined);
  const [noteSource, setNoteSource] = useState<Source | undefined>(undefined);
  const [popupQueue, setPopupQueue] = useState<string[]>([]);
  const toastId = useRef(0);

  const toast = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  const refresh = useCallback(() => {
    api.notifications().then(setNotes).catch((e) => toast("error", e.message));
    api.persons().then(setPersons).catch(() => undefined);
    api.events(100).then(setEvents).catch(() => undefined);
    api.status().then((s) => { setStatus(s); setDoor(s.door); }).catch(() => undefined);
  }, [toast]);

  useEffect(refresh, [refresh]);

  useLive((m) => {
    if (m.type === "notification.new") {
      setNotes((list) => [m.notification, ...list.filter((n) => n.id !== m.notification.id)]);
      toast(m.notification.kind, `${m.notification.title}: ${m.notification.body}`);
      beep(m.notification.kind === "intruder" ? "alert" : "soft");
      if (m.notification.kind !== "info") setPopupQueue((q) => [...q, m.notification.id]);
    }
    if (m.type === "siren") siren();
    if (m.type === "notification.updated") {
      setNotes((list) => list.map((n) => (n.id === m.notification.id ? m.notification : n)));
    }
    if (m.type === "event") {
      setEvents((list) => [m.event, ...list.filter((e) => e.id !== m.event.id)].slice(0, 100));
      if (m.event.stage === "decision") api.status().then(setStatus).catch(() => undefined);
    }
    if (m.type === "notifications.cleared") {
      setNotes((list) => (m.source ? list.filter((n) => n.source !== m.source) : []));
    }
    if (m.type === "events.cleared") {
      setEvents((list) => (m.source ? list.filter((e) => e.source !== m.source) : []));
      api.status().then(setStatus).catch(() => undefined);
    }
    if (m.type === "door") setDoor(m.door);
    if (m.type === "registry") {
      api.persons().then(setPersons).catch(() => undefined);
      api.status().then(setStatus).catch(() => undefined);
    }
  });

  const decide = async (n: Notification, action: NoteAction) => {
    try {
      const updated = await api.decide(n.id, action);
      setNotes((list) => list.map((x) => (x.id === n.id ? updated : x)));
      if (action === "allow") toast("info", `Door unlocked for ${n.name}`);
      if (action === "block") toast("intruder", "Door blocked. Emergency options are available.");
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };

  const emergency = async (n: Notification, action: EmergencyKind) => {
    try {
      const updated = await api.emergency(n.id, action);
      setNotes((list) => list.map((x) => (x.id === n.id ? updated : x)));
      if (action === "police") toast("intruder", "Police notified (simulated 112 call logged)");
    } catch (e) {
      toast("error", (e as Error).message);
    }
  };

  // The popup shows the oldest alert in the queue that still exists (it may have been cleared).
  const popupNote = popupQueue.map((id) => notes.find((n) => n.id === id)).find(Boolean);
  const closePopup = useCallback(() => {
    setPopupQueue((q) => q.filter((id) => id !== popupNote?.id));
  }, [popupNote?.id]);

  const sourceNotes = noteSource ? notes.filter((n) => n.source === noteSource) : notes;
  const shown = filter === "all" ? sourceNotes : sourceNotes.filter((n) => n.kind !== "info");
  const shownEvents = logSource ? events.filter((e) => e.source === logSource) : events;
  const unhandled = notes.filter((n) => n.status === "pending" || (n.kind === "intruder" && n.status === "new")).length;

  return (
    <div className="page owner">
      <div className="page-head">
        <div>
          <span className="eyebrow">Owner dashboard</span>
          <h1>Front door</h1>
          <p className="muted">Live alerts, approvals and the faces your door recognises.</p>
        </div>
        <div className="stat-row">
          <Stat label="Visits" value={status?.stats.visits ?? 0} />
          <Stat label="Granted" value={status?.stats.granted ?? 0} tone="ok" />
          <Stat label="Denied" value={status?.stats.denied ?? 0} tone="bad" />
          <Stat label="Needs action" value={unhandled} tone="warn" />
        </div>
      </div>

      <div className="owner-grid">
        <section className="panel inbox">
          <div className="panel-head">
            <h2><BellIcon size={18} /> Alerts & notifications</h2>
          </div>
          <div className="inbox-tools">
            <div className="seg small" role="radiogroup" aria-label="Notification type">
              <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>All types</button>
              <button className={filter === "alerts" ? "on" : ""} onClick={() => setFilter("alerts")}>Alerts only</button>
            </div>
            <div className="seg small" role="radiogroup" aria-label="Notification source">
              <button className={!noteSource ? "on" : ""} onClick={() => setNoteSource(undefined)}>All</button>
              <button className={noteSource === "live" ? "on" : ""} onClick={() => setNoteSource("live")}>Live camera</button>
              <button className={noteSource === "simulation" ? "on" : ""} onClick={() => setNoteSource("simulation")}>Simulation</button>
            </div>
            <LogActions kind="notifications" source={noteSource} disabled={sourceNotes.length === 0}
              pending={sourceNotes.filter((n) => n.status === "pending").length}
              onError={(m) => toast("error", m)}
              onCleared={(removed) => toast("info", `Cleared ${removed} notification(s)`)} />
          </div>
          {shown.length === 0 ? (
            <div className="empty"><BellIcon size={28} /><p>{notes.length ? "No notifications match this filter." : "No notifications yet. Run a visit in Test Mode or walk a visitor into the PIR range in the simulation."}</p></div>
          ) : (
            <ul className="notes">
              <AnimatePresence initial={false}>
                {shown.map((n) => <NoteCard key={n.id} n={n} onDecide={decide} onEmergency={emergency}
                  onOpen={() => setPopupQueue((q) => [n.id, ...q.filter((id) => id !== n.id)])} />)}
              </AnimatePresence>
            </ul>
          )}
        </section>

        <div className="owner-side">
          <section className={`panel door-status ${door?.unlocked ? "open" : ""}`}>
            <div className="door-status-icon">{door?.unlocked ? <UnlockIcon size={28} /> : <LockIcon size={28} />}</div>
            <div>
              <span className="eyebrow">Door relay (mock)</span>
              <h2>{door?.unlocked ? "Unlocked" : "Locked"}</h2>
              <p className="muted">{door?.unlocked ? `Opened by ${door.opened_by}. Auto-relocks shortly.` : "Relay de-energised."}</p>
            </div>
            <button className="btn" disabled={!door?.unlocked}
              onClick={() => api.lockDoor().then(setDoor).catch((e) => toast("error", e.message))}>
              <LockIcon size={15} /> Lock now
            </button>
          </section>
          <People persons={persons} onChange={refresh} toast={toast} />
        </div>
      </div>

      <section className="panel history">
        <div className="panel-head wrap">
          <h2>Visit history <span className="muted mono small">{shownEvents.length} events</span></h2>
          <div className="history-tools">
            <div className="seg small" role="radiogroup" aria-label="Log source">
              <button className={!logSource ? "on" : ""} onClick={() => setLogSource(undefined)}>All</button>
              <button className={logSource === "live" ? "on" : ""} onClick={() => setLogSource("live")}>Live camera</button>
              <button className={logSource === "simulation" ? "on" : ""} onClick={() => setLogSource("simulation")}>Simulation</button>
            </div>
            <LogActions source={logSource} onError={(m) => toast("error", m)} />
          </div>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Time</th><th>Source</th><th>Stage</th><th>Details</th><th>Person</th><th>Score</th><th>Decision</th></tr></thead>
            <tbody>
              {shownEvents.length === 0 && <tr><td colSpan={7} className="muted">The log is empty.</td></tr>}
              {shownEvents.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{timeOf(e.ts)}</td>
                  <td><span className={`src src-${e.source}`}>{e.source === "simulation" ? "SIM" : "LIVE"}</span></td>
                  <td><span className={`stage s-${e.stage}`}>{e.stage}</span></td>
                  <td>{e.message}</td>
                  <td>{e.name ?? "—"}{e.role && e.role !== "unknown" ? <span className="muted"> · {e.role}</span> : null}</td>
                  <td className="mono">{e.score != null ? e.score.toFixed(2) : "—"}</td>
                  <td>{e.decision ? <span className={`tag ${e.decision === "GRANTED" ? "ok" : e.decision === "PENDING" ? "warn" : "bad"}`}>{e.decision}</span> : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <AnimatePresence>
        {popupNote && (
          <AlertPopup key={popupNote.id} note={popupNote} onDecide={decide} onEmergency={emergency} onClose={closePopup}
            queued={popupQueue.filter((id) => id !== popupNote.id && notes.some((n) => n.id === id)).length} />
        )}
      </AnimatePresence>

      <div className="toasts" aria-live="polite">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div key={t.id} className={`toast k-${t.kind}`} initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}>
              {t.kind === "intruder" || t.kind === "error" ? <AlertIcon size={16} /> : <BellIcon size={16} />} {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "ok" | "bad" | "warn" }) {
  return <div className={`stat ${tone ?? ""}`}><b className="mono">{value}</b><span>{label}</span></div>;
}

function NoteCard({ n, onDecide, onEmergency, onOpen }: {
  n: Notification;
  onDecide: (n: Notification, a: NoteAction) => void;
  onEmergency: (n: Notification, a: EmergencyKind) => void;
  onOpen: () => void;
}) {
  const actionable = n.status === "pending" || (n.kind === "intruder" && n.status === "new");
  const left = useCountdown(n.expires_at, n.status === "pending");
  const policeCalled = (n.emergency ?? "").split(",").includes("police");
  const statusText: Record<string, string> = {
    approved: "Allowed by you", denied: "Denied by you", expired: "Expired, no response", read: "Kept locked",
  };
  return (
    <motion.li layout className={`note k-${n.kind} ${actionable ? "actionable" : ""}`}
      initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      {n.snapshot_id ? <img className="note-snap" src={snapshotUrl(n.snapshot_id)} alt={`Snapshot of ${n.name ?? "visitor"}`} />
        : <div className="note-snap placeholder"><UserIcon size={22} /></div>}
      <div className="note-main">
        <div className="note-top">
          <span className={`note-kind k-${n.kind}`}>
            {n.kind === "intruder" ? <><AlertIcon size={13} /> Intruder</> : n.kind === "approval" ? <><UsersIcon size={13} /> Approval</> : <><CheckIcon size={13} /> Entry</>}
          </span>
          <span className="mono muted">{n.source === "simulation" && <span className="src src-simulation">SIM</span>} {timeOf(n.ts)}</span>
        </div>
        <b className="note-title">{n.title}</b>
        <p className="note-body">{n.body}</p>
        {actionable ? (
          <div className="note-actions">
            <button className="btn ok sm" onClick={() => onDecide(n, "allow")}><UnlockIcon size={14} /> {n.kind === "intruder" ? "Manual allow" : "Allow entry"}</button>
            <button className="btn bad sm" onClick={() => onDecide(n, n.kind === "intruder" ? "block" : "deny")}>
              {n.kind === "intruder" ? <><LockIcon size={14} /> Block door</> : <><XIcon size={14} /> Deny</>}
            </button>
            {n.status === "pending" && <span className="mono countdown-chip">{left}s</span>}
          </div>
        ) : n.status === "blocked" ? (
          <div className="note-actions">
            <span className="note-resolved t-bad"><LockIcon size={13} /> Door blocked</span>
            {policeCalled ? <span className="note-resolved t-warn">🚓 Police notified</span>
              : <button className="btn bad sm" onClick={() => onEmergency(n, "police")}>🚓 Call police</button>}
            <button className="btn sm" onClick={onOpen}>Options</button>
          </div>
        ) : n.kind !== "info" && statusText[n.status] ? (
          <span className={`note-resolved ${n.status === "approved" ? "t-ok" : "t-bad"}`}>{statusText[n.status]}</span>
        ) : null}
      </div>
    </motion.li>
  );
}

function People({ persons, onChange, toast }: {
  persons: Person[]; onChange: () => void; toast: (k: Toast["kind"], t: string) => void;
}) {
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("owner");
  const [busy, setBusy] = useState(false);
  const [capturing, setCapturing] = useState<Person | null>(null);
  const fileFor = useRef<Person | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const person = await api.addPerson(name.trim(), role);
      setName("");
      onChange();
      toast("info", `${person.name} added. Now add 2–3 face photos.`);
      setCapturing(person);
    } catch (err) {
      toast("error", (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const upload = async (person: Person, blob: Blob) => {
    setBusy(true);
    try {
      await api.addPhoto(person.id, blob);
      toast("info", `Face photo saved for ${person.name}`);
      onChange();
    } catch (err) {
      toast("error", (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (person: Person) => {
    if (!confirm(`Remove ${person.name} and all their face photos?`)) return;
    await api.deletePerson(person.id).catch((err) => toast("error", err.message));
    onChange();
  };

  return (
    <section className="panel people">
      <div className="panel-head"><h2><UsersIcon size={18} /> Registered faces</h2></div>
      <form className="add-person" onSubmit={add}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Aayush" maxLength={50} aria-label="Name" />
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Role">
          <option value="owner">Owner</option>
          <option value="relative">Relative</option>
        </select>
        <button className="btn primary" disabled={busy || !name.trim()}>Add</button>
      </form>
      {persons.length === 0 && <p className="muted">Nobody registered yet. Add yourself as an owner, then capture your face.</p>}
      <ul className="person-list">
        {persons.map((p) => (
          <li key={p.id} className="person">
            <div className="person-head">
              <b>{p.name}</b>
              <select className={`role-select r-${p.role}`} value={p.role} aria-label={`Role for ${p.name}`}
                onChange={(e) => api.updatePerson(p.id, e.target.value as Role).then(onChange).catch((err) => toast("error", err.message))}>
                <option value="owner">owner</option>
                <option value="relative">relative</option>
              </select>
              <span className="spacer" />
              <button className="icon-btn" title="Capture from webcam" onClick={() => setCapturing(p)} disabled={busy}><CameraIcon size={17} /></button>
              <button className="icon-btn" title="Upload photo" disabled={busy}
                onClick={() => { fileFor.current = p; fileInput.current?.click(); }}><UploadIcon size={17} /></button>
              <button className="icon-btn danger" title="Remove person" onClick={() => remove(p)}><TrashIcon size={17} /></button>
            </div>
            <div className="thumbs">
              {p.photos.length === 0 && <span className="muted small">No photos — this person can't be recognised yet.</span>}
              {p.photos.map((ph) => (
                <div key={ph.id} className="thumb">
                  <img src={ph.image_url} alt={`${p.name} reference`} loading="lazy" />
                  <button aria-label="Delete photo" onClick={() => api.deletePhoto(ph.id).then(onChange).catch((err) => toast("error", err.message))}><XIcon size={12} /></button>
                </div>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <input ref={fileInput} type="file" accept="image/jpeg,image/png" hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file && fileFor.current) upload(fileFor.current, file);
          e.target.value = "";
        }} />
      <WebcamModal open={!!capturing} mode="single" title={`Register face · ${capturing?.name ?? ""}`}
        subtitle="Face the camera straight on. Take 2–3 photos with slightly different angles for better matching."
        onCapture={(frames) => { const p = capturing; setCapturing(null); if (p) upload(p, frames[0]); }}
        onClose={() => setCapturing(null)} />
    </section>
  );
}
