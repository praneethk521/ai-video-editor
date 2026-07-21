CREATE TABLE IF NOT EXISTS project_usage_counters (
    id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL REFERENCES projects(id),
    metric VARCHAR(64) NOT NULL,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_seconds INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    "limit" INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_usage_window
    ON project_usage_counters(project_id, metric, window_start);

CREATE INDEX IF NOT EXISTS ix_project_usage_counters_project_id
    ON project_usage_counters(project_id);

CREATE INDEX IF NOT EXISTS ix_project_usage_counters_metric
    ON project_usage_counters(metric);

CREATE INDEX IF NOT EXISTS ix_project_usage_counters_window_start
    ON project_usage_counters(window_start);
