from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.entities import MediaAsset, OutputVideo, RenderJob
from app.services import local_media
from app.services.malware import ClamAVScanner
from app.services.rendering import complete_render_job


@pytest.fixture
def upload_project(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "media_source_root", str(tmp_path))
    project = client.post("/projects", headers=auth_headers, json={"name": "Upload test"}).json()
    return project["id"], tmp_path


def test_upload_persists_scanned_probed_metadata(client, auth_headers, db_session, upload_project, monkeypatch):
    project_id, root = upload_project
    monkeypatch.setattr(ClamAVScanner, "scan_stream", lambda self, chunks: SimpleNamespace(status="clean") if b"".join(chunks) == b"fixture" else None)
    monkeypatch.setattr(local_media, "probe_media", lambda *args: {
        "mime_type": "image/png", "duration_seconds": 3, "orientation": "landscape", "width": 100, "height": 50, "has_audio": False,
    })
    response = client.post(f"/projects/{project_id}/upload", headers=auth_headers, files={"file": ("photo.png", b"fixture", "image/png")})
    assert response.status_code == 201
    asset = db_session.get(MediaAsset, response.json()["accepted_asset_ids"][0])
    assert asset.malware_scan_status == "clean"
    assert asset.metadata_json["source"] == "local_upload"
    assert (root / asset.metadata_json["relative_path"]).read_bytes() == b"fixture"


@pytest.mark.parametrize("failure", ["oversize", "infected", "corrupt"])
def test_failed_uploads_leave_no_asset_or_file(client, auth_headers, db_session, upload_project, monkeypatch, failure):
    project_id, root = upload_project
    monkeypatch.setattr(settings, "max_upload_bytes", 2 if failure == "oversize" else 100)
    monkeypatch.setattr(ClamAVScanner, "scan_stream", lambda *args: SimpleNamespace(status="infected" if failure == "infected" else "clean"))
    def bad_probe(*args):
        raise ValueError("corrupt input")
    monkeypatch.setattr(local_media, "probe_media", bad_probe)
    response = client.post(f"/projects/{project_id}/upload", headers=auth_headers, files={"file": ("bad.png", b"bad file", "image/png")})
    assert response.status_code == 422
    assert db_session.query(MediaAsset).count() == 0
    assert not [path for path in root.rglob("*") if path.is_file()]


def test_upload_requires_auth(client, upload_project):
    project_id, root = upload_project
    response = client.post(f"/projects/{project_id}/upload", files={"file": ("x.jpg", b"x")})
    assert response.status_code in {401, 403}
    assert not list(root.rglob("*"))


def test_clamav_nul_terminated_fragmented_reply(monkeypatch):
    class Socket:
        chunks = iter([b"stream:", b" OK\0"])
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def sendall(self, chunk):
            pass
        def recv(self, size):
            return next(self.chunks)
    monkeypatch.setattr("app.services.malware.socket.create_connection", lambda *args, **kwargs: Socket())
    assert ClamAVScanner("localhost", 3310).scan_stream([b"test"]).status == "clean"


def test_download_auth_project_and_validation_guards(client, auth_headers, db_session, upload_project, monkeypatch):
    project_id, root = upload_project
    monkeypatch.setattr(settings, "output_delivery_local_root", str(root))
    folder = root / project_id
    folder.mkdir()
    (folder / "video.mp4").write_bytes(b"private test bytes")
    output = OutputVideo(project_id=project_id, render_job_id="fixture-job", variant="youtube_16x9",
                         private_locator=f"file://private/{project_id}/video.mp4", width=1920, height=1080,
                         duration_seconds=3, file_size_bytes=18, validation_json={"status": "passed"})
    db_session.add(output)
    db_session.commit()
    url = f"/projects/{project_id}/outputs/{output.id}/download"
    assert client.get(url).status_code in {401, 403}
    response = client.get(url, headers=auth_headers)
    assert response.status_code == 200
    assert response.content == b"private test bytes"
    other = client.post("/projects", headers=auth_headers, json={"name": "Other"}).json()["id"]
    assert client.get(f"/projects/{other}/outputs/{output.id}/download", headers=auth_headers).status_code == 404
    output.private_locator = f"file://private/{other}/video.mp4"
    db_session.commit()
    assert client.get(url, headers=auth_headers).status_code == 404
    output.private_locator = f"file://private/{project_id}/video.mp4"
    output.validation_json = {"status": "skipped"}
    db_session.commit()
    assert client.get(url, headers=auth_headers).status_code == 404


@pytest.mark.parametrize("status", ["skipped", "failed", None])
def test_completion_rejects_unvalidated_outputs(db_session, status):
    job = RenderJob(project_id="project", timeline_plan_id="plan", variant="youtube_16x9")
    db_session.add(job)
    db_session.flush()
    with pytest.raises(ValueError, match="only validated"):
        complete_render_job(db_session, render_job_id=job.id, result=SimpleNamespace(validation={"status": status}))
