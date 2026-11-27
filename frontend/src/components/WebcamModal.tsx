import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CameraIcon, XIcon } from "./Icons";

interface Props {
  open: boolean;
  title: string;
  subtitle?: string;
  /** "burst" captures several frames after a countdown; "single" takes one photo on click. */
  mode: "burst" | "single";
  frames?: number;
  onCapture: (frames: Blob[]) => void;
  onClose: () => void;
}

type Phase = "starting" | "ready" | "countdown" | "capturing" | "error";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function WebcamModal({ open, title, subtitle, mode, frames = 5, onCapture, onClose }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<Phase>("starting");
  const [count, setCount] = useState(3);
  const [shots, setShots] = useState(0);
  const [error, setError] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");

  const stop = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPhase("starting");
    setShots(0);
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("This browser cannot access the camera. Use Chrome/Firefox on http://localhost.");
        }
        stop();
        const media = await navigator.mediaDevices.getUserMedia({
          video: deviceId ? { deviceId: { exact: deviceId }, width: 640, height: 480 }
            : { width: 640, height: 480, facingMode: "user" },
          audio: false,
        });
        if (cancelled) {
          media.getTracks().forEach((t) => t.stop());
          return;
        }
        stream.current = media;
        if (video.current) {
          video.current.srcObject = media;
          await video.current.play().catch(() => undefined);
        }
        const all = await navigator.mediaDevices.enumerateDevices();
        setDevices(all.filter((d) => d.kind === "videoinput"));
        setPhase("ready");
      } catch (err) {
        const name = (err as DOMException)?.name;
        setError(name === "NotAllowedError" ? "Camera permission was denied. Allow camera access in the browser's address bar and retry."
          : name === "NotFoundError" ? "No camera was found on this laptop."
          : name === "NotReadableError" ? "The camera is busy in another app (Zoom, Meet, OBS...). Close it and retry."
          : (err as Error).message || "Could not start the camera.");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
      stop();
    };
  }, [open, deviceId, stop]);

  const grab = useCallback(async (): Promise<Blob | null> => {
    const v = video.current;
    if (!v || !v.videoWidth) return null;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  }, []);

  const capture = useCallback(async () => {
    const blobs: Blob[] = [];
    if (mode === "burst") {
      setPhase("countdown");
      for (let n = 3; n > 0; n--) {
        setCount(n);
        await sleep(700);
      }
      setPhase("capturing");
      for (let i = 0; i < frames; i++) {
        const blob = await grab();
        if (blob) blobs.push(blob);
        setShots(i + 1);
        await sleep(220);
      }
    } else {
      setPhase("capturing");
      const blob = await grab();
      if (blob) blobs.push(blob);
      await sleep(250);
    }
    stop();
    if (blobs.length) onCapture(blobs);
    else {
      setError("Could not read a frame from the camera.");
      setPhase("error");
    }
  }, [frames, grab, mode, onCapture, stop]);

  // Burst mode starts on its own once the preview is live: the popup opens, detects, closes.
  useEffect(() => {
    if (open && mode === "burst" && phase === "ready") {
      const t = setTimeout(capture, 900);
      return () => clearTimeout(t);
    }
  }, [open, mode, phase, capture]);

  const close = () => {
    stop();
    onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={(e) => e.target === e.currentTarget && phase !== "capturing" && close()}>
          <motion.div className="modal webcam" role="dialog" aria-modal="true" aria-label={title}
            initial={{ scale: 0.92, y: 24, opacity: 0 }} animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.95, y: 12, opacity: 0 }} transition={{ type: "spring", stiffness: 320, damping: 28 }}>
            <header className="modal-head">
              <div className="modal-title"><CameraIcon size={18} /> {title}</div>
              <button className="icon-btn" onClick={close} aria-label="Close camera"><XIcon size={18} /></button>
            </header>
            {subtitle && <p className="modal-sub">{subtitle}</p>}
            <div className={`viewfinder ph-${phase}`}>
              <video ref={video} muted playsInline />
              <div className="guide-oval" />
              <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
              <div className="rec"><span className="rec-dot" /> ESP32-CAM EMULATION · 640×480</div>
              {phase === "starting" && <div className="vf-overlay">Starting camera…</div>}
              {phase === "countdown" && (
                <motion.div key={count} className="countdown" initial={{ scale: 1.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
                  {count}
                </motion.div>
              )}
              {phase === "capturing" && <div className="flash" />}
              {phase === "capturing" && mode === "burst" && (
                <div className="vf-overlay bottom">Capturing frame {shots}/{frames}</div>
              )}
              {phase === "error" && <div className="vf-overlay error">{error}</div>}
            </div>
            <footer className="modal-foot">
              {devices.length > 1 ? (
                <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} aria-label="Camera">
                  <option value="">Default camera</option>
                  {devices.map((d, i) => (<option key={d.deviceId} value={d.deviceId}>{d.label || `Camera ${i + 1}`}</option>))}
                </select>
              ) : <span className="hint">Keep your face inside the oval, in good light.</span>}
              {phase === "error" ? (
                <button className="btn" onClick={close}>Close</button>
              ) : mode === "single" ? (
                <button className="btn primary" disabled={phase !== "ready"} onClick={capture}><CameraIcon size={16} /> Take photo</button>
              ) : (
                <span className="hint mono">{phase === "ready" ? "Auto-capture in a moment…" : phase === "countdown" ? "Hold still" : ""}</span>
              )}
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
