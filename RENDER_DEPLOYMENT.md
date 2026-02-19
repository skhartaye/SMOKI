# Deploying SMOKI to Render

This guide explains how to deploy the SMOKI application to Render.

## Prerequisites

- Render account (https://render.com)
- GitHub repository with SMOKI code
- PostgreSQL database (can use Render's PostgreSQL service)

## Environment Variables

Set the following environment variables in your Render service:

### Backend Environment Variables

1. **Database Configuration**
   - `DB_HOST`: Your PostgreSQL host (e.g., from Render PostgreSQL service)
   - `DB_NAME`: Database name (e.g., `smoki_db`)
   - `DB_USER`: Database user (e.g., `postgres`)
   - `DB_PASSWORD`: Database password
   - `DB_PORT`: Database port (default: `5432`)

2. **JWT Configuration**
   - `SECRET_KEY`: A secure random key for JWT token signing
   
   Generate a secure key with:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. **Frontend Configuration**
   - `VITE_API_URL`: Backend API URL (e.g., `https://your-backend.onrender.com`)

## Step-by-Step Deployment

### 1. Create PostgreSQL Database on Render

1. Go to Render Dashboard
2. Click "New +" → "PostgreSQL"
3. Fill in the details:
   - Name: `smoki-db`
   - Database: `smoki_db`
   - User: `postgres`
4. Create the database
5. Copy the connection details

### 2. Create Backend Service

1. Go to Render Dashboard
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Fill in the details:
   - Name: `smoki-backend`
   - Environment: `Python 3`
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add Environment Variables:
   - `DB_HOST`: From PostgreSQL service
   - `DB_NAME`: `smoki_db`
   - `DB_USER`: `postgres`
   - `DB_PASSWORD`: From PostgreSQL service
   - `DB_PORT`: `5432`
   - `SECRET_KEY`: Generated secure key
6. Deploy

### 3. Create Frontend Service

1. Go to Render Dashboard
2. Click "New +" → "Static Site"
3. Connect your GitHub repository
4. Fill in the details:
   - Name: `smoki-frontend`
   - Build Command: `cd frontend && npm install && npm run build`
   - Publish Directory: `frontend/dist`
5. Add Environment Variables:
   - `VITE_API_URL`: Your backend service URL (e.g., `https://smoki-backend.onrender.com`)
6. Deploy

### 4. Initialize Database

After backend deployment, run the database initialization:

1. Connect to your PostgreSQL database
2. Run the SQL scripts from `postgre/database.py` to create tables
3. Or use the backend's initialization endpoint if available

## Troubleshooting

### SECRET_KEY Error
If you see: `ValueError: SECRET_KEY environment variable is not set`

**Solution**: Add `SECRET_KEY` to your Render environment variables. The application will generate a temporary key if not set, but this is not recommended for production.

### Database Connection Error
If the backend can't connect to the database:

1. Verify all database environment variables are set correctly
2. Check that the PostgreSQL service is running
3. Ensure the database user has proper permissions

### Frontend API Connection Error
If the frontend can't reach the backend:

1. Verify `VITE_API_URL` is set to the correct backend URL
2. Check CORS settings in the backend
3. Ensure both services are deployed and running

## Monitoring

- Check logs in Render Dashboard for each service
- Monitor database connections and performance
- Set up alerts for service failures

## Security Notes

- Always use a strong, randomly generated `SECRET_KEY`
- Use HTTPS for all connections (Render provides this by default)
- Regularly update dependencies
- Keep sensitive information in environment variables, not in code
- Use strong database passwords
