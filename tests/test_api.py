def register(client, name, role, photo):
    person = client.post("/api/persons", json={"name": name, "role": role}).json()
    response = client.post(f"/api/persons/{person['id']}/photos",
                           files={"photo": ("p.jpg", photo, "image/jpeg")})
    assert response.status_code == 201, response.text
    return person


def visit(client, frames):
    run = client.post("/api/runs").json()
    assert run["stage"] == "camera"
    files = [("frames", (f"f{i}.jpg", frame, "image/jpeg")) for i, frame in enumerate(frames)]
    return client.post(f"/api/runs/{run['id']}/verify", files=files)


def test_owner_is_granted_and_door_opens(client, hopper_jpg, hopper_flipped_jpg):
    register(client, "Grace", "owner", hopper_jpg)
    result = visit(client, [hopper_flipped_jpg] * 3).json()
    assert result["decision"] == "GRANTED" and result["identity"] == "owner"
    assert result["door"]["unlocked"] is True
    assert result["notification"]["kind"] == "info"
    assert client.get(result["result"]["snapshot_url"]).status_code == 200
    stages = [e["stage"] for e in result["events"]]
    assert stages[0] == "motion" and "notified" in stages


def test_intruder_is_denied_with_alert(client, hopper_jpg, astronaut_jpg):
    register(client, "Grace", "owner", hopper_jpg)
    result = visit(client, [astronaut_jpg] * 3).json()
    assert result["decision"] == "DENIED" and result["identity"] == "intruder"
    assert result["door"]["unlocked"] is False
    inbox = client.get("/api/notifications").json()
    assert inbox[0]["kind"] == "intruder" and inbox[0]["snapshot_id"]


def test_relative_waits_for_owner_then_allowed(client, hopper_jpg, hopper_flipped_jpg):
    register(client, "Grace", "relative", hopper_jpg)
    result = visit(client, [hopper_flipped_jpg] * 3).json()
    assert result["decision"] == "PENDING" and result["stage"] == "door"
    note = result["notification"]
    assert note["kind"] == "approval" and note["status"] == "pending"
    decided = client.post(f"/api/notifications/{note['id']}/decision", json={"action": "allow"})
    assert decided.json()["status"] == "approved"
    run = client.get(f"/api/runs/{result['id']}").json()
    assert run["decision"] == "GRANTED" and run["door"]["unlocked"] is True
    again = client.post(f"/api/notifications/{note['id']}/decision", json={"action": "deny"})
    assert again.status_code == 409


def test_no_face_returns_422_and_allows_retry(client, blank_jpg, hopper_jpg):
    register(client, "Grace", "owner", hopper_jpg)
    run = client.post("/api/runs").json()
    bad = client.post(f"/api/runs/{run['id']}/verify", files=[("frames", ("a.jpg", blank_jpg, "image/jpeg"))])
    assert bad.status_code == 422
    good = client.post(f"/api/runs/{run['id']}/verify", files=[("frames", ("a.jpg", hopper_jpg, "image/jpeg"))])
    assert good.json()["decision"] == "GRANTED"


def test_person_management_and_validation(client, hopper_jpg, blank_jpg):
    person = register(client, "Grace", "owner", hopper_jpg)
    assert client.post("/api/persons", json={"name": "grace", "role": "owner"}).status_code == 422
    assert client.post("/api/persons", json={"name": "Intruder", "role": "owner"}).status_code == 422
    noface = client.post(f"/api/persons/{person['id']}/photos", files={"photo": ("b.jpg", blank_jpg, "image/jpeg")})
    assert noface.status_code == 422
    listed = client.get("/api/persons").json()
    assert listed[0]["photos"] and client.get(listed[0]["photos"][0]["image_url"]).status_code == 200
    assert client.patch(f"/api/persons/{person['id']}", json={"role": "relative"}).json()["role"] == "relative"
    assert client.delete(f"/api/persons/{person['id']}").status_code == 204
    assert client.get("/api/persons").json() == []


def test_cross_origin_writes_rejected(client):
    response = client.post("/api/runs", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403


def test_websocket_receives_status(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "status"


def simulate(client, visitor, photo):
    run = client.post("/api/runs?source=simulation").json()
    response = client.post(f"/api/runs/{run['id']}/simulate", data={"visitor": visitor},
                           files={"photo": ("sim.jpg", photo, "image/jpeg")})
    assert response.status_code == 200, response.text
    return response.json()


def test_simulation_visits_follow_the_same_rules(client, blank_jpg):
    owner = simulate(client, "owner", blank_jpg)
    assert owner["decision"] == "GRANTED" and owner["door"]["unlocked"] is True
    assert {e["source"] for e in owner["events"]} == {"simulation"}
    relative = simulate(client, "relative", blank_jpg)
    assert relative["decision"] == "PENDING" and relative["notification"]["source"] == "simulation"
    intruder = simulate(client, "intruder", blank_jpg)
    assert intruder["decision"] == "DENIED" and intruder["notification"]["kind"] == "intruder"
    assert client.get(intruder["result"]["snapshot_url"]).status_code == 200


def test_live_runs_cannot_be_simulated(client, blank_jpg):
    run = client.post("/api/runs").json()
    response = client.post(f"/api/runs/{run['id']}/simulate", data={"visitor": "owner"},
                           files={"photo": ("sim.jpg", blank_jpg, "image/jpeg")})
    assert response.status_code == 409


def test_export_and_clear_log(client, blank_jpg):
    simulate(client, "intruder", blank_jpg)
    client.post("/api/runs")  # one live motion event
    export = client.get("/api/events/export.csv")
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    lines = export.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("id,time_local,ts,source,run_id,stage,message")
    assert any(",simulation," in line for line in lines) and any(",live," in line for line in lines)
    only_sim = client.get("/api/events/export.csv?source=simulation").text
    assert ",live," not in only_sim
    assert client.delete("/api/events?source=simulation").json()["removed"] > 0
    assert {e["source"] for e in client.get("/api/events").json()} == {"live"}
    client.delete("/api/events")
    assert client.get("/api/events").json() == []


def test_clear_notifications_denies_pending_approvals(client, blank_jpg):
    simulate(client, "intruder", blank_jpg)
    pending = simulate(client, "relative", blank_jpg)
    assert len(client.get("/api/notifications").json()) == 2
    assert client.delete("/api/notifications").json()["removed"] == 2
    assert client.get("/api/notifications").json() == []
    run = client.get(f"/api/runs/{pending['id']}").json()
    assert run["decision"] == "DENIED" and run["door"]["unlocked"] is False
    assert client.get("/api/status").json()["pending_approvals"] == 0


def test_notifications_export_and_clear_by_source(client, blank_jpg, hopper_jpg, astronaut_jpg):
    register(client, "Grace", "owner", hopper_jpg)
    simulate(client, "intruder", blank_jpg)
    visit(client, [astronaut_jpg])  # live intruder
    export = client.get("/api/notifications/export.csv?source=simulation")
    assert "edgevision-notifications-simulation" in export.headers["content-disposition"]
    lines = export.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("id,time_local,ts,source,kind,status,title") and len(lines) == 2
    assert client.delete("/api/notifications?source=simulation").json()["removed"] == 1
    assert [n["source"] for n in client.get("/api/notifications").json()] == ["live"]


def test_block_intruder_then_call_police(client, blank_jpg):
    intruder = simulate(client, "intruder", blank_jpg)
    note = intruder["notification"]
    blocked = client.post(f"/api/notifications/{note['id']}/decision", json={"action": "block"}).json()
    assert blocked["status"] == "blocked"
    assert client.get("/api/status").json()["door"]["unlocked"] is False
    called = client.post(f"/api/notifications/{note['id']}/emergency", json={"action": "police"}).json()
    assert called["emergency"] == "police"
    both = client.post(f"/api/notifications/{note['id']}/emergency", json={"action": "siren"}).json()
    assert both["emergency"] == "police,siren"
    stages = [e["stage"] for e in client.get(f"/api/runs/{intruder['id']}").json()["events"]]
    assert stages.count("emergency") == 2 and "door" in stages
    # Blocking is intruder-only; emergency actions too.
    relative = simulate(client, "relative", blank_jpg)["notification"]
    assert client.post(f"/api/notifications/{relative['id']}/decision", json={"action": "block"}).status_code == 409
    assert client.post(f"/api/notifications/{relative['id']}/emergency", json={"action": "police"}).status_code == 409
