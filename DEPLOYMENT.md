# SMOKI Deployment Guide

## 🚀 Deployment Options

### Option 1: Netlify (Recommended for Frontend)

#### Prerequisites
- GitHub account
- Netlify account (free tier available)

#### Steps

1. **Push to GitHub** (if not already done)
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push origin main
   ```

2. **Deploy to Netlify**
   - Go to [Netlify](https://app.netlify.com/)
   - Click "Add new site" → "Import an existing project"
   - Connect your GitHub repository
   - Configure build settings:
     - **Base directory**: `frontend`
     - **Build command**: `npm run build`
     - **Publish directory**: `dist`
   - Click "Deploy site"

3. **Configure Environment Variables**
   - Go to Site settings → Environment variables
   - Add: `VITE_API_URL` = `your-backend-url`

4. **Custom Domain (Optional)**
   - Go to Domain settings
   - Add custom domain: `smoki.yourdomain.com`

### Option 2: Vercel (Alternative for Frontend)

1. **Install Vercel CLI**
   ```bash
   npm install -g vercel
   ```

2. **Deploy**
   ```bash
   cd frontend
   vercel
   ```

3. **Follow prompts** and configure:
   - Set root directory to `frontend`
   - Build command: `npm run build`
   - Output directory: `dist`

### Option 3: Backend Deployment (Render/Railway)

#### Deploy Backend to Render

1. **Create Render Account**
   - Go to [Render](https://render.com/)

2. **Create Web Service**
   - Click "New" → "Web Service"
   - Connect GitHub repository
   - Configure:
     - **Root Directory**: `backend`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
     - **Environment**: Python 3

3. **Add Environment Variables**
   ```
   DB_HOST=your-postgres-host
   DB_NAME=smoki_db
   DB_USER=your-db-user
   DB_PASSWORD=your-db-password
   DB_PORT=5432
   ```

4. **Create PostgreSQL Database**
   - In Render dashboard, create a new PostgreSQL database
   - Copy connection details to environment variables

### Option 4: Full Stack on Railway

1. **Install Railway CLI**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login and Initialize**
   ```bash
   railway login
   railway init
   ```

3. **Deploy Backend**
   ```bash
   cd backend
   railway up
   ```

4. **Deploy Frontend**
   ```bash
   cd frontend
   railway up
   ```

5. **Add PostgreSQL**
   - In Railway dashboard, add PostgreSQL plugin
   - Environment variables will be auto-configured

## 🔧 Post-Deployment Configuration

### Update Frontend API URL

1. **Create `.env.production` in frontend folder**
   ```env
   VITE_API_URL=https://your-backend-url.com
   ```

2. **Rebuild frontend**
   ```bash
   cd frontend
   npm run build
   ```

### Database Migration

1. **Connect to production database**
   ```bash
   psql -h your-db-host -U your-db-user -d smoki_db
   ```

2. **Run schema creation**
   ```sql
   CREATE TABLE IF NOT EXISTS sensor_data (
       id SERIAL PRIMARY KEY,
       temperature FLOAT,
       humidity FLOAT,
       vocs FLOAT,
       nitrogen_dioxide FLOAT,
       carbon_monoxide FLOAT,
       pm25 FLOAT,
       pm10 FLOAT,
       timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
   );
   ```

### CORS Configuration

Update `backend/main.py` with your frontend URL:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-frontend-url.netlify.app",
        "http://localhost:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🔒 Security Checklist

- [ ] Change default login credentials in production
- [ ] Enable HTTPS for both frontend and backend
- [ ] Set secure environment variables
- [ ] Configure proper CORS origins
- [ ] Enable database SSL connection
- [ ] Set up rate limiting on API endpoints
- [ ] Implement proper authentication (JWT/OAuth)
- [ ] Regular database backups

## 📊 Monitoring

### Frontend Monitoring
- Netlify Analytics (built-in)
- Google Analytics (optional)

### Backend Monitoring
- Render/Railway built-in metrics
- Sentry for error tracking
- Uptime monitoring (UptimeRobot)

## 🐛 Troubleshooting

### Build Fails
```bash
# Clear cache and rebuild
cd frontend
rm -rf node_modules dist
npm install
npm run build
```

### API Connection Issues
- Check CORS configuration
- Verify API URL in environment variables
- Check backend logs for errors

### Database Connection Issues
- Verify database credentials
- Check if database allows external connections
- Ensure SSL is configured if required

## 📝 Quick Deploy Commands

### Netlify CLI
```bash
cd frontend
npm install -g netlify-cli
netlify login
netlify deploy --prod
```

### Manual Deploy
```bash
# Build frontend
cd frontend
npm run build

# Upload dist folder to your hosting service
```

## 🎯 Production URLs

After deployment, update these in your documentation:

- **Frontend**: https://smoki.netlify.app (or your custom domain)
- **Backend API**: https://smoki-api.render.com
- **Database**: Managed by hosting provider

## 📞 Support

For deployment issues:
- Check hosting provider documentation
- Review build logs
- Contact support if needed

---

**Note**: Always test in a staging environment before deploying to production!
