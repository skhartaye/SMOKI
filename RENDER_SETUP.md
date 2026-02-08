# Setup Users on Render PostgreSQL

## Option 1: Using Render Dashboard (Easiest)

1. Go to your Render Dashboard
2. Click on your PostgreSQL database
3. Click "Connect" → "External Connection" 
4. Copy the connection string (looks like: `postgresql://user:pass@host/db`)
5. Use a PostgreSQL client (like pgAdmin, DBeaver, or psql) to connect
6. Run the SQL from `postgre/create_users.sql`

## Option 2: Using psql Command Line

```bash
# Get your database external URL from Render dashboard
# It looks like: postgresql://smoki_db_user:password@dpg-xxxxx.oregon-postgres.render.com/smoki_db

# Connect to Render database
psql "postgresql://smoki_db_user:password@dpg-xxxxx.oregon-postgres.render.com/smoki_db"

# Then paste the SQL:
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    full_name VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

INSERT INTO users (username, hashed_password, role, full_name) 
VALUES 
    ('admin', '$2b$12$MFlbL7pZ9DAcX2WhtiqTY.7aGS6XcSpfK2ezzpGhoRo0lUVTPU5Gu', 'admin', 'Admin User'),
    ('superadmin', '$2b$12$fDaAQyBWz8Qjmh.MwY7Yz.muNfhED1z81LTL6Aow3SZzHFsC25LwK', 'superadmin', 'Super Admin')
ON CONFLICT (username) DO NOTHING;
```

## Option 3: Using Render Shell (If available)

1. Go to your backend service on Render
2. Click "Shell" tab
3. Run: `psql $DATABASE_URL -f postgre/create_users.sql`

## Deploy Updated Code

After adding users to the database:

```bash
# Commit and push your changes
git add .
git commit -m "Update auth to use PostgreSQL users table"
git push origin main
```

Render will automatically redeploy your backend with the new code.

## Verify Users Were Created

```sql
SELECT username, role, full_name FROM users;
```

Should show:
- admin (password: 1234)
- superadmin (password: superadmin123)
