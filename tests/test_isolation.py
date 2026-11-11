from tests.conftest import A, B


def all_post_ids(client, cid):
    from app import db
    return {p["post_id"] for p in db.get_posts(cid)}


def test_report_only_contains_its_own_clients_posts(client):
    report = client.post(f"/api/clients/{A}/reports").json()
    text = str(report["payload"])

    b_ids = all_post_ids(client, B)
    assert b_ids, "seed data should exist for client B"
    assert not any(pid in text for pid in b_ids)
    assert "Blue Coast" not in text


def test_cannot_read_or_approve_another_clients_report(client):
    rid = client.post(f"/api/clients/{A}/reports").json()["id"]

    assert client.get(f"/api/clients/{B}/reports/{rid}").status_code == 404
    r = client.post(f"/api/clients/{B}/reports/{rid}/approve", json={"reviewer": "Mallory"})
    assert r.status_code == 404
    assert client.get(f"/api/clients/{B}/reports").json() == []


def test_import_goes_to_the_client_in_the_url_only(client):
    before_b = all_post_ids(client, B)
    csv = (
        "post_id,date,platform,format,topic,impressions,reach,likes,comments,shares,saves,link_clicks\n"
        "NEW-0001,2026-10-31,instagram,reel,pool,1500,1000,80,5,5,10,9\n"
    )
    r = client.post(f"/api/clients/{A}/import", files={"file": ("new.csv", csv, "text/csv")})
    assert r.status_code == 200
    assert "NEW-0001" in all_post_ids(client, A)
    assert all_post_ids(client, B) == before_b


def test_invalid_import_saves_nothing(client):
    before = all_post_ids(client, A)
    csv = (
        "post_id,date,platform,format,topic,impressions,reach,likes,comments,shares,saves,link_clicks\n"
        "OK-1,2026-10-01,instagram,reel,pool,1500,1000,80,5,5,10,9\n"
        "BAD-1,not-a-date,myspace,reel,pool,-5,1000,80,5,5,10,9\n"
    )
    r = client.post(f"/api/clients/{A}/import", files={"file": ("bad.csv", csv, "text/csv")})
    assert r.status_code == 422
    assert all_post_ids(client, A) == before
