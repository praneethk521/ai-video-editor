CREATE TABLE IF NOT EXISTS teams (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS team_members (
  id VARCHAR(64) PRIMARY KEY,
  team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
  user_id VARCHAR(64) NOT NULL REFERENCES users(id),
  role VARCHAR(32) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_members (
  id VARCHAR(64) PRIMARY KEY,
  project_id VARCHAR(64) NOT NULL REFERENCES projects(id),
  user_id VARCHAR(64) REFERENCES users(id),
  team_id VARCHAR(64) REFERENCES teams(id),
  role VARCHAR(32) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (user_id IS NOT NULL AND team_id IS NULL) OR
    (user_id IS NULL AND team_id IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS service_tokens (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  token_hash VARCHAR(128) UNIQUE NOT NULL,
  scope VARCHAR(64) NOT NULL DEFAULT 'worker',
  role VARCHAR(32) NOT NULL DEFAULT 'worker',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  project_id VARCHAR(64) REFERENCES projects(id),
  expires_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_team_user ON team_members(team_id, user_id);
CREATE INDEX IF NOT EXISTS idx_team_members_user_id ON team_members(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_members_project_user
  ON project_members(project_id, user_id)
  WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_members_project_team
  ON project_members(project_id, team_id)
  WHERE team_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_team_id ON project_members(team_id);
CREATE INDEX IF NOT EXISTS idx_service_tokens_project_id ON service_tokens(project_id);
