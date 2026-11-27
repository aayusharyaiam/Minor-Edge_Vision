export type DoorMode = "locked" | "open" | "waiting" | "alarm" | "idle";

export default function Door({ mode, label }: { mode: DoorMode; label?: string }) {
  return (
    <div className={`door door-${mode}`}>
      <div className="door-frame">
        <div className="door-light" />
        <div className="door-inside" />
        <div className="door-leaf">
          <span className="door-panel" /><span className="door-panel" />
          <span className="door-knob" />
        </div>
      </div>
      <div className="door-floor" />
      {label && <div className="door-label mono">{label}</div>}
    </div>
  );
}
