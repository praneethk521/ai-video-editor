from app.models.entities import (
    AnalysisResult,
    MediaAsset,
    OutputVideo,
    PlanStatus,
    Project,
    RenderJob,
    RenderStatus,
    TimelinePlan,
)
from app.services.project_progress import derive_project_pipeline


def test_new_project_pipeline_starts_at_import(client, auth_headers, db_session):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Fresh trip"}).json()["id"]

    pipeline = derive_project_pipeline(db_session, project_id=project_id)

    assert pipeline["current_step"] == "import"
    assert pipeline["next_action"] == "Import photos and videos"
    assert [step["state"] for step in pipeline["steps"]] == [
        "current", "pending", "pending", "pending", "pending", "pending",
    ]


def test_successful_retry_pipeline_is_ready(client, auth_headers, db_session):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Finished trip"}).json()["id"]
    project = db_session.get(Project, project_id)
    asset = MediaAsset(
        project_id=project_id,
        original_filename="view.jpg",
        sanitized_filename="view.jpg",
        mime_type="image/jpeg",
        size_bytes=100,
        duration_seconds=3,
        orientation="landscape",
        private_locator=f"file://private/sources/{project_id}/view",
        malware_scan_status="clean",
        metadata_json={},
    )
    db_session.add(asset)
    db_session.add(AnalysisResult(project_id=project_id, provider="test", result_json={}))
    for variant in ("youtube_16x9", "shorts_9x16"):
        plan = TimelinePlan(
            project_id=project_id,
            variant=variant,
            status=PlanStatus.approved,
            confidence_score=0.9,
            plan_json={"selection": {"decisions": [{"asset_id": "view"}]}},
        )
        db_session.add(plan)
        db_session.flush()
        db_session.add(RenderJob(
            project_id=project_id,
            timeline_plan_id=plan.id,
            variant=variant,
            status=RenderStatus.failed,
        ))
        db_session.flush()
        retry = RenderJob(
            project_id=project_id,
            timeline_plan_id=plan.id,
            variant=variant,
            status=RenderStatus.succeeded,
        )
        db_session.add(retry)
        db_session.flush()
        db_session.add(OutputVideo(
            project_id=project_id,
            render_job_id=retry.id,
            variant=variant,
            private_locator=f"file://private/{project_id}/{variant}.mp4",
            width=1920 if variant == "youtube_16x9" else 1080,
            height=1080 if variant == "youtube_16x9" else 1920,
            duration_seconds=30,
            file_size_bytes=100,
            validation_json={"status": "passed"},
        ))
    db_session.flush()

    pipeline = derive_project_pipeline(db_session, project_id=project.id)

    assert pipeline["current_step"] == "ready"
    assert pipeline["next_action"] == "Preview or download the finished videos"
    assert all(step["state"] == "complete" for step in pipeline["steps"])
    assert pipeline["steps"][4]["detail"] == "2 formats rendered"


def test_latest_failed_render_is_actionable(client, auth_headers, db_session):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Retry trip"}).json()["id"]
    plan = TimelinePlan(
        project_id=project_id,
        variant="youtube_16x9",
        status=PlanStatus.approved,
        confidence_score=0.9,
        plan_json={"selection": {"decisions": []}},
    )
    db_session.add(plan)
    db_session.flush()
    db_session.add(RenderJob(
        project_id=project_id,
        timeline_plan_id=plan.id,
        variant="youtube_16x9",
        status=RenderStatus.failed,
    ))
    db_session.flush()

    pipeline = derive_project_pipeline(db_session, project_id=project_id)

    render = next(step for step in pipeline["steps"] if step["id"] == "render")
    assert render["state"] == "failed"
    assert pipeline["current_step"] == "render"
    assert pipeline["next_action"] == "Retry the failed render"
