from __future__ import annotations

from app.services import rendering


def test_dispatch_render_jobs_submits_rq_job(monkeypatch):
    enqueued = []

    class FakeRedis:
        @staticmethod
        def from_url(url):
            assert url == rendering.settings.redis_url
            return "redis-connection"

    class FakeQueue:
        def __init__(self, name, connection):
            assert name == "renders"
            assert connection == "redis-connection"

        def enqueue_call(self, **kwargs):
            enqueued.append(kwargs)

    monkeypatch.setattr(rendering.settings, "render_queue_backend", "rq")
    monkeypatch.setattr(rendering, "Redis", FakeRedis)
    monkeypatch.setattr(rendering, "Queue", FakeQueue)

    rendering.dispatch_render_jobs([rendering.RenderQueueItem(render_job_id="job-1", plan_json={"variant": "youtube_16x9"})])

    assert enqueued == [
        {
            "func": "app.jobs.render_timeline_job",
            "args": ("job-1", {"variant": "youtube_16x9"}),
            "kwargs": {"trace_context": {}, "sources": {}},
            "timeout": 1800,
            "result_ttl": 86400,
            "failure_ttl": 86400,
        }
    ]
