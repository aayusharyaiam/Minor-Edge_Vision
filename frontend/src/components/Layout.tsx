import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { useLive } from "../lib/live";
import type { DoorStatus } from "../lib/types";
import { LockIcon, UnlockIcon } from "./Icons";

/** Inside the side-by-side view each pane is an iframe: render only the page itself. */
export const embedded = window.self !== window.top;

export default function Layout({ standalone = false }: { standalone?: boolean }) {
  const location = useLocation();
  const [door, setDoor] = useState<DoorStatus | null>(null);
  const [pending, setPending] = useState(0);
  const connected = useLive((m) => {
    if (embedded) return;
    if (m.type === "door") setDoor(m.door);
    if (m.type === "status") { setDoor(m.status.door); setPending(m.status.pending_approvals); }
    if (m.type === "notification.new" && m.notification.status === "pending") setPending((p) => p + 1);
    if (m.type === "notifications.cleared") api.status().then((s) => setPending(s.pending_approvals)).catch(() => undefined);
    if (m.type === "notification.updated") api.status().then((s) => setPending(s.pending_approvals)).catch(() => undefined);
  });
  useEffect(() => {
    if (!embedded) api.status().then((s) => { setDoor(s.door); setPending(s.pending_approvals); }).catch(() => undefined);
  }, []);

  if (embedded) return <main className="embedded"><Outlet /></main>;
  const split = location.pathname === "/";

  return (
    <div className={`shell ${split ? "full" : ""}`}>
      <header className="topbar">
        <NavLink to="/" className="brand">
          <span className="brand-mark"><span /></span>
          <span>EdgeVision<small>AI Smart Access Control</small></span>
        </NavLink>
        {standalone ? (
          <nav><span className="standalone-tag">Test Mode</span></nav>
        ) : (
          <nav>
            <NavLink to="/" end>Side by side</NavLink>
            <NavLink to="/project">Project</NavLink>
            <NavLink to="/owner">Owner {pending > 0 && <span className="badge">{pending}</span>}</NavLink>
            <a href="/test" target="_blank" rel="noreferrer">Test Mode ↗</a>
          </nav>
        )}
        <div className="top-status">
          {door && (
            <span className={`pill ${door.unlocked ? "ok" : ""}`}>
              {door.unlocked ? <UnlockIcon size={14} /> : <LockIcon size={14} />} Door {door.state.toLowerCase()}
            </span>
          )}
          <span className={`pill ${connected ? "ok" : "bad"}`}><span className="dot" />{connected ? "Live" : "Offline"}</span>
        </div>
      </header>
      <main><Outlet /></main>
      {!split && <footer className="foot">BIT Patna · ECE 5th semester minor project · software prototype (laptop camera stands in for the ESP32-CAM)</footer>}
    </div>
  );
}
