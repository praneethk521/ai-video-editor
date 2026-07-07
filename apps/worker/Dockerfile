FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /worker
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tini && rm -rf /var/lib/apt/lists/*
COPY apps/worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/worker/app ./app
COPY packages/shared /packages/shared
ENV PYTHONPATH=/worker:/packages/shared/python

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "app.worker_main"]
