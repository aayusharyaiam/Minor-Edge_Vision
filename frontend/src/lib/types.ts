export type Role = "owner" | "relative";
export type Identity = "owner" | "relative" | "intruder";
export type DecisionKind = "GRANTED" | "PENDING" | "DENIED";
export type Stage = "motion" | "camera" | "detecting" | "identity" | "door" | "notified";

export interface DoorStatus {
  state: "LOCKED" | "UNLOCKED";
  unlocked: boolean;
  opened_by: string | null;
  seconds_remaining: number;
}

export interface Photo {
  id: string;
  created_at: string;
  image_url: string;
}

export interface Person {
  id: string;
  name: string;
  role: Role;
  created_at: string;
  photos: Photo[];
}

export type Source = "live" | "simulation";

export interface AccessEvent {
  id: number;
  ts: string;
  run_id: string | null;
  source: Source;
  stage: string;
  message: string;
  name: string | null;
  role: string | null;
  score: number | null;
  decision: DecisionKind | null;
  snapshot_id: string | null;
}

export interface Notification {
  id: string;
  ts: string;
  run_id: string | null;
  kind: "intruder" | "approval" | "info";
  status: "new" | "pending" | "approved" | "denied" | "expired" | "read" | "blocked";
  emergency?: string | null;
  title: string;
  body: string;
  name: string | null;
  role: string | null;
  score: number | null;
  snapshot_id: string | null;
  expires_at: string | null;
  decided_at: string | null;
  source: Source;
}

export interface VerifyResult {
  face_found: boolean;
  frames: number;
  frames_with_face: number;
  box: [number, number, number, number];
  image_size: [number, number];
  name: string;
  role: string;
  score: number;
  threshold: number;
  snapshot_id: string;
  snapshot_url: string;
  registered_faces: number;
}

export interface Run {
  id: string;
  created_at: string;
  stage: Stage;
  decision: DecisionKind | null;
  identity: Identity | null;
  reason?: string;
  result: VerifyResult | null;
  notification: Notification | null;
  door: DoorStatus;
  attempts: number;
  error: string | null;
  source?: Source;
  events?: AccessEvent[];
}

export interface Status {
  door: DoorStatus;
  pir_active: boolean;
  pir_triggers: number;
  registry: { owners: number; relatives: number; photos: number };
  threshold: number;
  stats: { granted: number; denied: number; pending: number; visits: number };
  engine: string;
  camera: string;
  pending_approvals: number;
}

export type LiveMessage =
  | { type: "status"; status: Status }
  | { type: "door"; door: DoorStatus }
  | { type: "run.update"; run: Run }
  | { type: "event"; event: AccessEvent }
  | { type: "notification.new"; notification: Notification }
  | { type: "notification.updated"; notification: Notification }
  | { type: "registry" }
  | { type: "events.cleared"; source: Source | null }
  | { type: "notifications.cleared"; source: Source | null }
  | { type: "siren"; notification_id: string }
  | { type: "heartbeat"; ts: string };
