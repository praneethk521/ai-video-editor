ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user';

UPDATE users SET role = 'user' WHERE role = 'owner';
