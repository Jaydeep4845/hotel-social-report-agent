from tests.conftest import A


def new_report(client):
    return client.post(f"/api/clients/{A}/reports").json()["id"]


def test_draft_cannot_be_exported(client):
    rid = new_report(client)
    r = client.get(f"/api/clients/{A}/reports/{rid}/export?fmt=md")
    assert r.status_code == 409


def test_approve_then_export_with_reviewer_edits(client):
    rid = new_report(client)
    report = client.get(f"/api/clients/{A}/reports/{rid}").json()
    drop = report["payload"]["insights"][0]["id"]

    r = client.post(f"/api/clients/{A}/reports/{rid}/approve", json={
        "reviewer": "Jaydeep", "summary": "Edited summary.", "excluded_insights": [drop],
    })
    assert r.status_code == 200
    approved = r.json()
    assert approved["status"] == "approved"
    assert approved["payload"]["summary"] == "Edited summary."
    assert drop not in [i["id"] for i in approved["payload"]["insights"]]
    assert [a["action"] for a in approved["audit"]] == ["report_generated", "approved"]

    md = client.get(f"/api/clients/{A}/reports/{rid}/export?fmt=md")
    assert md.status_code == 200
    assert "APPROVED" in md.text and "Edited summary." in md.text
    assert client.get(f"/api/clients/{A}/reports/{rid}/export?fmt=csv").status_code == 200


def test_decision_is_final_and_reject_needs_a_note(client):
    rid = new_report(client)
    assert client.post(f"/api/clients/{A}/reports/{rid}/reject", json={"reviewer": "Jaydeep", "note": ""}).status_code == 422
    assert client.post(f"/api/clients/{A}/reports/{rid}/reject",
                       json={"reviewer": "Jaydeep", "note": "Too vague"}).status_code == 200
    assert client.post(f"/api/clients/{A}/reports/{rid}/approve", json={"reviewer": "Jaydeep"}).status_code == 409
    assert client.get(f"/api/clients/{A}/reports/{rid}/export").status_code == 409
