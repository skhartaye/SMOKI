-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    full_name VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Insert default users
INSERT INTO users (username, hashed_password, role, full_name) 
VALUES 
    ('admin', '$2b$12$MFlbL7pZ9DAcX2WhtiqTY.7aGS6XcSpfK2ezzpGhoRo0lUVTPU5Gu', 'admin', 'Admin User'),
    ('superadmin', '$2b$12$fDaAQyBWz8Qjmh.MwY7Yz.muNfhED1z81LTL6Aow3SZzHFsC25LwK', 'superadmin', 'Super Admin')
ON CONFLICT (username) DO NOTHING;
