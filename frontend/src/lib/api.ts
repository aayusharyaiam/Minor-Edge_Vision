import type { AccessEvent, DoorStatus, Notification, Person, Role, Run, Source, Status } from "./types";

export type NoteAction = "allow" | "deny" | "dismiss" | "block";
export type EmergencyKind = "police" | "siren";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("Backend is not reachable. Is `python main.py` running?", 0);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: data === undefined ? undefined : JSON.stringify(data),
});

export const api = {
  status: () => request<Status>("/api/status"),
  createRun: (source: Source = "live") => request<Run>(`/api/runs?source=${source}`, { method: "POST" }),
  simulate: (id: string, visitor: "owner" | "relative" | "intruder", photo: Blob) => {
    const form = new FormData();
    form.append("visitor", visitor);
    form.append("photo", photo, "sim-photo.jpg");
    return request<Run>(`/api/runs/${id}/simulate`, { method: "POST", body: form });
  },
  getRun: (id: string) => request<Run>(`/api/runs/${id}`),
  verify: (id: string, frames: Blob[]) => {
    const form = new FormData();
    frames.forEach((frame, i) => form.append("frames", frame, `frame-${i}.jpg`));
    return request<Run>(`/api/runs/${id}/verify`, { method: "POST", body: form });
  },
  persons: () => request<Person[]>("/api/persons"),
  addPerson: (name: string, role: Role) => request<Person>("/api/persons", json("POST", { name, role })),
  updatePerson: (id: string, role: Role) => request<Person>(`/api/persons/${id}`, json("PATCH", { role })),
  deletePerson: (id: string) => request<void>(`/api/persons/${id}`, { method: "DELETE" }),
  addPhoto: (personId: string, photo: Blob) => {
    const form = new FormData();
    form.append("photo", photo, "photo.jpg");
    return request<unknown>(`/api/persons/${personId}/photos`, { method: "POST", body: form });
  },
  deletePhoto: (id: string) => request<void>(`/api/photos/${id}`, { method: "DELETE" }),
  notifications: () => request<Notification[]>("/api/notifications"),
  clearNotifications: (source?: Source) =>
    request<{ removed: number }>(`/api/notifications${source ? `?source=${source}` : ""}`, { method: "DELETE" }),
  decide: (id: string, action: NoteAction) =>
    request<Notification>(`/api/notifications/${id}/decision`, json("POST", { action })),
  emergency: (id: string, action: EmergencyKind) =>
    request<Notification>(`/api/notifications/${id}/emergency`, json("POST", { action })),
  lockDoor: () => request<DoorStatus>("/api/door/lock", { method: "POST" }),
  events: (limit = 100, source?: Source) =>
    request<AccessEvent[]>(`/api/events?limit=${limit}${source ? `&source=${source}` : ""}`),
  clearEvents: (source?: Source) =>
    request<{ removed: number }>(`/api/events${source ? `?source=${source}` : ""}`, { method: "DELETE" }),
};

export const snapshotUrl = (id: string) => `/api/snapshots/${id}`;
export const notificationsExportUrl = (source?: Source) =>
  `/api/notifications/export.csv${source ? `?source=${source}` : ""}`;
export const exportUrl = (source?: Source) => `/api/events/export.csv${source ? `?source=${source}` : ""}`;
