CREATE TABLE IF NOT EXISTS photos_connections (
  project_id VARCHAR(64) PRIMARY KEY REFERENCES projects(id),
  status VARCHAR(32) NOT NULL DEFAULT 'disconnected',
  encrypted_data TEXT NOT NULL,
  state_hash VARCHAR(128) UNIQUE,
  state_expires_at TIMESTAMPTZ,
  lease_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_photos_connections_status ON photos_connections(status);
