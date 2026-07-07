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

        def enqueue(self, function_name, *args, **kwargs):
            enqueued.append({"function_name": function_name, "args": args, "kwargs": kwargs})

    monkeypatch.setattr(rendering.settings, "render_queue_backend", "rq")
    monkeypatch.setattr(rendering, "Redis", FakeRedis)
    monkeypatch.setattr(rendering, "Queue", FakeQueue)

    rendering.dispatch_render_jobs([rendering.RenderQueueItem(render_job_id="job-1", plan_json={"variant": "youtube_16x9"})])

    assert enqueued == [
        {
            "function_name": "app.jobs.render_timeline_job",
            "args": ("job-1", {"variant": "youtube_16x9"}),
            "kwargs": {"job_timeout": 1800, "result_ttl": 86400, "failure_ttl": 86400},
        }
    ]
