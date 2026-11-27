import { useState } from "react";
import { api, exportUrl, notificationsExportUrl } from "../lib/api";
import type { Source } from "../lib/types";
import { TrashIcon, UploadIcon } from "./Icons";

const SOURCE_LABEL: Record<Source, string> = { live: "live camera", simulation: "simulation" };

/** "Export CSV" + "Clear" for the event log or the notifications, optionally limited to one source. */
export default function LogActions({ source, label, kind = "events", pending = 0, disabled = false, onError, onCleared }: {
  source?: Source;
  label?: string;
  kind?: "events" | "notifications";
  /** Pending approvals that clearing would deny (notifications only), shown in the confirmation. */
  pending?: number;
  disabled?: boolean;
  onError?: (message: string) => void;
  onCleared?: (removed: number) => void;
}) {
  const [busy, setBusy] = useState(false);
  const scope = source ? `${SOURCE_LABEL[source]} ` : "";
  const what = label ?? (kind === "events"
    ? (source ? `${SOURCE_LABEL[source]} log` : "entire log")
    : `${source ? scope : "all "}notifications`);

  const clear = async () => {
    const detail = kind === "events"
      ? "This permanently deletes those events (notifications are kept)."
      : "This permanently deletes them (the visit log is kept)."
        + (pending ? `\n\n${pending} pending approval request(s) will be DENIED and the door stays locked.` : "");
    if (!confirm(`Clear the ${what}? ${detail}`)) return;
    setBusy(true);
    try {
      const { removed } = kind === "events" ? await api.clearEvents(source) : await api.clearNotifications(source);
      onCleared?.(removed);
    } catch (e) {
      onError?.((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="log-actions">
      <a className="btn sm" href={kind === "events" ? exportUrl(source) : notificationsExportUrl(source)} download
        title={`Download the ${what} as CSV`}>
        <UploadIcon size={14} style={{ transform: "rotate(180deg)" }} /> Export CSV
      </a>
      <button className="btn sm bad" onClick={clear} disabled={busy || disabled} title={`Delete the ${what}`}>
        <TrashIcon size={14} /> {kind === "events" ? "Clear log" : "Clear"}
      </button>
    </div>
  );
}
