FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /worker
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ffmpeg tini \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin worker \
    && mkdir -p /tmp/ai-video-editor \
    && chown -R worker:worker /worker /tmp/ai-video-editor \
    && rm -rf /var/lib/apt/lists/*
COPY apps/worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/worker/app ./app
COPY packages/shared /packages/shared
ENV PYTHONPATH=/worker:/packages/shared/python

USER 10001:10001
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "app.worker_main"]
