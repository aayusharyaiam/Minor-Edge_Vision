import { useCallback, useEffect, useRef, useState } from "react";
import { DashboardIcon, PlayIcon, ShieldIcon } from "../components/Icons";

const MIN = 28; // percent

/** Project dashboard (with the simulation) and the Owner dashboard side by side.
 *  Each pane is its own page in an iframe, so it scrolls and adapts to its width independently. */
export default function SplitView() {
  const [split, setSplit] = useState(() => Number(localStorage.getItem("ev-split")) || 55);
  const [dragging, setDragging] = useState(false);
  const [narrow, setNarrow] = useState(() => window.innerWidth < 1000);
  const [tab, setTab] = useState<"project" | "owner">("project");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < 1000);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => { localStorage.setItem("ev-split", String(Math.round(split))); }, [split]);

  const onMove = useCallback((e: PointerEvent) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return;
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    setSplit(Math.min(100 - MIN, Math.max(MIN, pct)));
  }, []);

  useEffect(() => {
    if (!dragging) return;
    const stop = () => setDragging(false);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stop);
    };
  }, [dragging, onMove]);

  const pane = (which: "project" | "owner") => (
    <section className="pane" style={narrow ? undefined : { flexBasis: `${which === "project" ? split : 100 - split}%` }}
      hidden={narrow && tab !== which}>
      <header className="pane-bar">
        {which === "project" ? <><DashboardIcon size={15} /> Project dashboard · simulation</> : <><ShieldIcon size={15} /> Owner dashboard</>}
        <a href={which === "project" ? "/project" : "/owner"} target="_blank" rel="noreferrer">open alone ↗</a>
      </header>
      <iframe src={which === "project" ? "/project" : "/owner"} title={which === "project" ? "Project dashboard" : "Owner dashboard"}
        allow="camera; autoplay" style={dragging ? { pointerEvents: "none" } : undefined} />
    </section>
  );

  return (
    <div className="split-page">
      <div className="split-toolbar">
        {narrow ? (
          <div className="seg small">
            <button className={tab === "project" ? "on" : ""} onClick={() => setTab("project")}>Project</button>
            <button className={tab === "owner" ? "on" : ""} onClick={() => setTab("owner")}>Owner</button>
          </div>
        ) : <span className="muted small">Drag the divider to resize. Both panes update live.</span>}
        <a className="btn primary sm" href="/test" target="_blank" rel="noreferrer"><PlayIcon size={14} /> Open Test Mode in a new tab</a>
      </div>
      <div className={`split ${dragging ? "dragging" : ""}`} ref={box}>
        {pane("project")}
        {!narrow && (
          <div className="divider" role="separator" aria-orientation="vertical" aria-valuenow={Math.round(split)}
            tabIndex={0} onPointerDown={(e) => { e.preventDefault(); setDragging(true); }}
            onDoubleClick={() => setSplit(55)}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") setSplit((s) => Math.max(MIN, s - 2));
              if (e.key === "ArrowRight") setSplit((s) => Math.min(100 - MIN, s + 2));
            }}><span /></div>
        )}
        {pane("owner")}
      </div>
    </div>
  );
}
