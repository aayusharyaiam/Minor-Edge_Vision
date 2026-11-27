import { useEffect, useRef, useState } from "react";
import type { LiveMessage } from "./types";

type Listener = (message: LiveMessage) => void;

const listeners = new Set<Listener>();
const connectionListeners = new Set<(connected: boolean) => void>();
let socket: WebSocket | null = null;
let connected = false;
let retry = 0;

function setConnected(value: boolean) {
  connected = value;
  connectionListeners.forEach((fn) => fn(value));
}

function connect() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.host}/ws`);
  socket.onopen = () => {
    retry = 0;
    setConnected(true);
  };
  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data) as LiveMessage;
      listeners.forEach((fn) => fn(message));
    } catch {
      /* ignore malformed frames */
    }
  };
  socket.onclose = () => {
    setConnected(false);
    socket = null;
    if (listeners.size || connectionListeners.size) {
      setTimeout(connect, Math.min(5000, 500 * 2 ** retry++));
    }
  };
}

function ensure() {
  if (!socket) connect();
}

/** Subscribe to the shared live-events WebSocket. Handler may change between renders. */
export function useLive(handler: Listener): boolean {
  const ref = useRef(handler);
  ref.current = handler;
  const [isConnected, setIsConnected] = useState(connected);
  useEffect(() => {
    const listener: Listener = (message) => ref.current(message);
    listeners.add(listener);
    connectionListeners.add(setIsConnected);
    ensure();
    setIsConnected(connected);
    return () => {
      listeners.delete(listener);
      connectionListeners.delete(setIsConnected);
    };
  }, []);
  return isConnected;
}

export function beep(kind: "alert" | "soft" = "soft") {
  try {
    const ctx = new AudioContext();
    const tones = kind === "alert" ? [880, 660, 880] : [660, 880];
    tones.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      osc.type = kind === "alert" ? "square" : "sine";
      gain.gain.setValueAtTime(0.08, ctx.currentTime + i * 0.16);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.16 + 0.15);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.16);
      osc.stop(ctx.currentTime + i * 0.16 + 0.16);
    });
    setTimeout(() => ctx.close(), 1200);
  } catch {
    /* audio not available */
  }
}

export const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** Two-tone police-style siren for a few seconds (Web Audio, no audio files needed). */
export function siren(seconds = 4) {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sawtooth";
    gain.gain.value = 0.05;
    for (let t = 0; t < seconds; t += 0.5) {
      osc.frequency.setValueAtTime(t % 1 === 0 ? 960 : 640, ctx.currentTime + t);
    }
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + seconds);
    setTimeout(() => ctx.close(), seconds * 1000 + 300);
  } catch {
    /* audio not available */
  }
}

const secondsUntil = (iso: string | null) =>
  iso ? Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 1000)) : 0;

/** Seconds left until an ISO timestamp, ticking every second while active. */
export function useCountdown(expires: string | null, active: boolean) {
  const [left, setLeft] = useState(() => secondsUntil(expires));
  useEffect(() => {
    if (!expires || !active) return;
    const tick = () => setLeft(secondsUntil(expires));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [expires, active]);
  return left;
}
