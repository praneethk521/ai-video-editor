from __future__ import annotations

from redis import Redis
from rq import Worker

from app.config import settings


def main() -> None:
    connection = Redis.from_url(settings.redis_url)
    Worker(["renders"], connection=connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
