from app.models.entities import MediaAsset, PlanStatus, TimelinePlan


def add_review_fixture(client, auth_headers, db_session):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Review"}).json()["id"]
    assets = [
        MediaAsset(
            project_id=project_id,
            original_filename=name,
            sanitized_filename=name,
            mime_type=mime_type,
            size_bytes=100,
            duration_seconds=duration,
            orientation="landscape",
            private_locator=f"file://private/sources/{project_id}/{index}",
            malware_scan_status="clean",
            metadata_json={"relative_path": f"{project_id}/{index}"},
        )
        for index, (name, mime_type, duration) in enumerate(
            [("view.jpg", "image/jpeg", 3), ("walk.mp4", "video/mp4", 10)]
        )
    ]
    db_session.add_all(assets)
    db_session.flush()
    decisions = [
        {"asset_id": asset.id, "status": "selected", "reasons": ["quality_representative"],
         "score": 0.9, "start": 0, "duration": 3}
        for asset in assets
    ]
    plan = TimelinePlan(
        project_id=project_id,
        variant="youtube_16x9",
        status=PlanStatus.approved,
        confidence_score=0.8,
        plan_json={
            "project_id": project_id,
            "variant": "youtube_16x9",
            "version": 1,
            "confidence_score": 0.8,
            "strategy": {"hook": "Review"},
            "tracks": [{"type": "video", "clips": [
                {"asset_id": asset.id, "start": 0, "end": 3, "timeline_start": index * 3,
                 "effect": "cut", "caption": "", "crop_strategy": "center"}
                for index, asset in enumerate(assets)
            ]}],
            "export": {"width": 1920, "height": 1080, "fps": 30, "format": "mp4",
                       "max_duration_seconds": 20},
            "selection": {"method": "local_semantic_curation_v1", "target_seconds": 20,
                          "duration_seconds": 6, "decisions": decisions, "limitations": []},
        },
    )
    db_session.add(plan)
    db_session.commit()
    return project_id, assets, plan


def test_owner_review_rebuilds_timeline_and_invalidates_approval(client, auth_headers, db_session):
    project_id, assets, plan = add_review_fixture(client, auth_headers, db_session)
    response = client.patch(
        f"/projects/{project_id}/plans/{plan.id}",
        headers=auth_headers,
        json={
            "notes": "Keep the walking clip.",
            "decisions": [
                {"asset_id": assets[0].id, "selected": False, "start": 0, "duration": 3},
                {"asset_id": assets[1].id, "selected": True, "pinned": True, "start": 2, "duration": 4},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["plan"]["version"] == 2
    assert body["plan"]["selection"]["method"] == "owner_reviewed_v1"
    assert body["plan"]["selection"]["duration_seconds"] == 4
    assert body["plan"]["strategy"]["hook"].startswith("Owner-reviewed local selection")
    assert body["plan"]["tracks"][0]["clips"] == [{
        "asset_id": assets[1].id,
        "start": 2.0,
        "end": 6.0,
        "timeline_start": 0.0,
        "effect": "cut",
        "caption": "",
        "crop_strategy": "center",
    }]
    decisions = {item["asset_id"]: item for item in body["plan"]["selection"]["decisions"]}
    assert decisions[assets[0].id]["status"] == "excluded"
    assert "owner_excluded" in decisions[assets[0].id]["reasons"]
    assert decisions[assets[1].id]["pinned"] is True
    assert "owner_pinned" in decisions[assets[1].id]["reasons"]


def test_owner_review_rejects_incomplete_or_invalid_trims(client, auth_headers, db_session):
    project_id, assets, plan = add_review_fixture(client, auth_headers, db_session)
    incomplete = client.patch(
        f"/projects/{project_id}/plans/{plan.id}",
        headers=auth_headers,
        json={"decisions": [{"asset_id": assets[0].id, "selected": True}]},
    )
    assert incomplete.status_code == 422

    overflow = client.patch(
        f"/projects/{project_id}/plans/{plan.id}",
        headers=auth_headers,
        json={"decisions": [
            {"asset_id": assets[0].id, "selected": False},
            {"asset_id": assets[1].id, "selected": True, "start": 8, "duration": 4},
        ]},
    )
    assert overflow.status_code == 422
    assert "trim exceeds source duration" in overflow.json()["detail"]


def test_media_list_and_thumbnail_are_project_scoped(client, auth_headers, db_session, monkeypatch):
    project_id, assets, _ = add_review_fixture(client, auth_headers, db_session)
    listing = client.get(f"/projects/{project_id}/media", headers=auth_headers)
    assert listing.status_code == 200
    assert [item["filename"] for item in listing.json()["media"]] == ["view.jpg", "walk.mp4"]

    monkeypatch.setattr("app.api.projects.media_thumbnail", lambda asset: b"\xff\xd8thumbnail")
    thumbnail = client.get(
        f"/projects/{project_id}/media/{assets[0].id}/thumbnail",
        headers=auth_headers,
    )
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/jpeg"
    assert thumbnail.content == b"\xff\xd8thumbnail"

    other_project = client.post("/projects", headers=auth_headers, json={"name": "Other"}).json()["id"]
    assert client.get(
        f"/projects/{other_project}/media/{assets[0].id}/thumbnail",
        headers=auth_headers,
    ).status_code == 404
