"""FastAPI app: REST + WebSocket API for the React dashboards, and the built SPA."""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from backend.config import Settings
from backend.db import utc_now
from backend.events import EventHub
from backend.face_engine import FaceError
from backend.service import AccessService, Conflict, NotFound

log = logging.getLogger(__name__)


Source = Literal["live", "simulation"] | None


def csv_download(body: str, what: str, source: str | None) -> Response:
    """CSV with a BOM so Excel detects UTF-8; filename carries the filter and a timestamp."""
    name = f"edgevision-{what}{'-' + source if source else ''}-{datetime.now():%Y%m%d-%H%M%S}.csv"
    return Response(content="\ufeff" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


class PersonIn(BaseModel):
    name: str
    role: Literal["owner", "relative"]


class PersonUpdate(BaseModel):
    role: Literal["owner", "relative"]


class NotificationDecision(BaseModel):
    action: Literal["allow", "deny", "dismiss", "block"]


class EmergencyAction(BaseModel):
    action: Literal["police", "siren"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        settings.prepare_directories()
        hub = EventHub(asyncio.get_running_loop())
        service = await run_in_threadpool(AccessService, settings, hub.publish)
        await run_in_threadpool(service.start)
        application.state.hub, application.state.service = hub, service
        try:
            yield
        finally:
            hub.close()
            await run_in_threadpool(service.close)

    application = FastAPI(title="EdgeVision Access Control", version="3.0.0", lifespan=lifespan,
                          description="Face verification, access decisions and owner notifications.")

    def svc() -> AccessService:
        return application.state.service

    def authorize(x_api_key: str | None = Header(default=None)) -> None:
        if settings.admin_api_key and not hmac.compare_digest(x_api_key or "", settings.admin_api_key):
            raise HTTPException(status_code=401, detail="A valid X-API-Key is required")

    @application.exception_handler(FaceError)
    async def face_error(_: Request, exc: FaceError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.middleware("http")
    async def guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
            # Same-origin only (the Vite dev proxy rewrites Host to match).
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
        length = request.headers.get("content-length")
        limit = settings.max_upload_bytes * settings.max_frames + 65536
        if length and length.isdecimal() and int(length) > limit:
            return JSONResponse(status_code=413, content={"detail": "Upload too large"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    async def read_upload(upload: UploadFile) -> bytes:
        contents = await upload.read(settings.max_upload_bytes + 1)
        if len(contents) > settings.max_upload_bytes:
            raise FaceError("Image exceeds the upload size limit")
        return contents

    api = Depends(authorize)

    # ---- status ------------------------------------------------------------------------
    @application.get("/api/status", dependencies=[api])
    async def status():
        return await run_in_threadpool(svc().status)

    # ---- test-mode runs ----------------------------------------------------------------
    @application.post("/api/runs", status_code=201, dependencies=[api])
    async def create_run(source: Literal["live", "simulation"] = "live"):
        return await run_in_threadpool(svc().create_run, source)

    @application.post("/api/runs/{run_id}/simulate", dependencies=[api])
    async def simulate(run_id: str, visitor: Literal["owner", "relative", "intruder"] = Form(...),
                       photo: UploadFile = File(...)):
        contents = await read_upload(photo)
        return await run_in_threadpool(svc().simulate, run_id, visitor, contents)

    @application.get("/api/runs/{run_id}", dependencies=[api])
    async def get_run(run_id: str):
        return await run_in_threadpool(svc().get_run, run_id)

    @application.post("/api/runs/{run_id}/verify", dependencies=[api])
    async def verify(run_id: str, frames: list[UploadFile] = File(...)):
        if len(frames) > settings.max_frames:
            raise FaceError(f"Send at most {settings.max_frames} frames")
        contents = [await read_upload(frame) for frame in frames]
        return await run_in_threadpool(svc().verify, run_id, contents)

    # ---- people & photos ---------------------------------------------------------------
    @application.get("/api/persons", dependencies=[api])
    async def persons():
        return await run_in_threadpool(svc().list_persons)

    @application.post("/api/persons", status_code=201, dependencies=[api])
    async def add_person(body: PersonIn):
        return await run_in_threadpool(svc().add_person, body.name, body.role)

    @application.patch("/api/persons/{person_id}", dependencies=[api])
    async def update_person(person_id: str, body: PersonUpdate):
        return await run_in_threadpool(svc().update_person, person_id, body.role)

    @application.delete("/api/persons/{person_id}", status_code=204, dependencies=[api])
    async def delete_person(person_id: str):
        await run_in_threadpool(svc().delete_person, person_id)

    @application.post("/api/persons/{person_id}/photos", status_code=201, dependencies=[api])
    async def add_photo(person_id: str, photo: UploadFile = File(...)):
        contents = await read_upload(photo)
        return await run_in_threadpool(svc().add_photo, person_id, contents)

    @application.get("/api/photos/{photo_id}/image", dependencies=[api], include_in_schema=False)
    async def photo_image(photo_id: str):
        return FileResponse(await run_in_threadpool(svc().photo_path, photo_id), media_type="image/jpeg")

    @application.delete("/api/photos/{photo_id}", status_code=204, dependencies=[api])
    async def delete_photo(photo_id: str):
        await run_in_threadpool(svc().delete_photo, photo_id)

    # ---- owner inbox, door, history ------------------------------------------------------
    @application.get("/api/notifications", dependencies=[api])
    async def notifications():
        return await run_in_threadpool(svc().list_notifications)

    @application.delete("/api/notifications", dependencies=[api])
    async def clear_notifications(source: Source = None):
        return {"removed": await run_in_threadpool(svc().clear_notifications, source)}

    @application.get("/api/notifications/export.csv", dependencies=[api])
    async def export_notifications(source: Source = None):
        body = await run_in_threadpool(svc().notifications_csv, source)
        return csv_download(body, "notifications", source)

    @application.post("/api/notifications/{notification_id}/decision", dependencies=[api])
    async def decide(notification_id: str, body: NotificationDecision):
        return await run_in_threadpool(svc().decide_notification, notification_id, body.action)

    @application.post("/api/notifications/{notification_id}/emergency", dependencies=[api])
    async def emergency(notification_id: str, body: EmergencyAction):
        return await run_in_threadpool(svc().emergency, notification_id, body.action)

    @application.post("/api/door/lock", dependencies=[api])
    async def lock_door():
        return await run_in_threadpool(svc().lock_door)

    @application.get("/api/events", dependencies=[api])
    async def events(limit: int = Query(default=100, ge=1, le=500), source: Source = None):
        return await run_in_threadpool(svc().list_events, limit, source)

    @application.delete("/api/events", dependencies=[api])
    async def clear_events(source: Source = None):
        return {"removed": await run_in_threadpool(svc().clear_events, source)}

    @application.get("/api/events/export.csv", dependencies=[api])
    async def export_events(source: Source = None):
        body = await run_in_threadpool(svc().events_csv, source)
        return csv_download(body, "log", source)

    @application.get("/api/snapshots/{snapshot_id}", dependencies=[api], include_in_schema=False)
    async def snapshot(snapshot_id: str):
        return FileResponse(await run_in_threadpool(svc().snapshot_path, snapshot_id), media_type="image/jpeg")

    # ---- live events ---------------------------------------------------------------------
    @application.websocket("/ws")
    async def websocket_events(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        if origin and urlsplit(origin).netloc != websocket.headers.get("host"):
            await websocket.close(code=1008)
            return
        if settings.admin_api_key and not hmac.compare_digest(
                websocket.query_params.get("key", ""), settings.admin_api_key):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        hub: EventHub = application.state.hub
        subscriber = hub.subscribe()

        async def sender():
            await websocket.send_json({"type": "status", "status": await run_in_threadpool(svc().status)})
            while True:
                try:
                    event = await asyncio.wait_for(subscriber.get(), timeout=15)
                except asyncio.TimeoutError:
                    event = {"type": "heartbeat", "ts": utc_now()}
                await websocket.send_json(event)

        async def receiver():
            while True:
                await websocket.receive_text()

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            hub.unsubscribe(subscriber)

    # ---- React build (production) -------------------------------------------------------------
    dist = settings.frontend_dist
    if (dist / "index.html").is_file():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @application.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            candidate = (dist / path).resolve()
            if path and dist.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            if path.startswith(("api/", "ws")):
                raise HTTPException(status_code=404)
            return FileResponse(dist / "index.html")
    else:
        @application.get("/", include_in_schema=False)
        async def no_build():
            return JSONResponse({"detail": "Frontend not built. Run `npm run dev` in frontend/ "
                                           "(http://localhost:5173) or `npm run build`."})

    return application
