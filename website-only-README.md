# 💨 SMOKi - Air Quality Monitoring Web Dashboard

A web-based air quality monitoring dashboard that displays real-time environmental metrics through an interactive React interface with FastAPI backend.

**Repository**: [skhartaye/SMOKI](https://github.com/skhartaye/SMOKI)  
**Web Design**: [miiikunnn/SMOKi_web_design_3](https://github.com/miiikunnn/SMOKi_web_design_3)

## 🌟 Features

- **Real-time Data Dashboard**: Interactive React-based interface with live graphs and historical data
- **RESTful API**: FastAPI backend for data management and API endpoints
- **PostgreSQL Database**: Reliable data storage with timezone-aware timestamps
- **Responsive Design**: Mobile-friendly web interface
- **Data Visualization**: Charts and graphs for environmental metrics
- **User Authentication**: Secure login system

## 🏗️ Architecture

```
┌─────────────┐      HTTP      ┌──────────────┐      HTTP      ┌─────────────┐
│   Client    │ ──────────────> │   Backend    │ ──────────────> │  Database   │
│  (React)    │                 │  (FastAPI)   │                 │(PostgreSQL) │
└─────────────┘                 └──────────────┘                 └─────────────┘
```

## 📋 Prerequisites

- **Python 3.10+** (Backend)
- **Node.js 16+** (Frontend)
- **PostgreSQL 12+** (Database)
- **Docker & Docker Compose** (Optional, for containerized deployment)

## 🚀 Quick Start

### Option 1: Docker Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/skhartaye/SMOKI.git
cd SMOKI

# Start all services with Docker Compose
docker-compose up -d

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# Database: localhost:5432
```

### Option 2: Manual Setup

#### 1. Database Setup

```bash
# Install PostgreSQL (if not already installed)
# Windows: https://www.postgresql.org/download/windows/
# Linux: sudo apt install postgresql postgresql-contrib
# macOS: brew install postgresql

# Create database
psql -U postgres
CREATE DATABASE smoki_db;
\q

# Configure database credentials
cd postgre
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

#### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials

# Run backend server
python -m uvicorn main:app --reload
```

Backend will be available at: `http://127.0.0.1:8000`

#### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your backend URL

# Run development server
npm run dev
```

Frontend will be available at: `http://localhost:5173`

## 📁 Project Structure

```
smoki-website/
├── backend/              # FastAPI backend
│   ├── main.py          # API endpoints
│   ├── auth.py          # Authentication
│   ├── stream.py        # Data streaming
│   ├── vehicles.py      # Vehicle data management
│   ├── requirements.txt # Python dependencies
│   ├── Dockerfile       # Backend container
│   └── .env            # Backend configuration
├── frontend/            # React frontend
│   ├── src/
│   │   ├── App.jsx     # Login page
│   │   ├── Dashboard.jsx # Main dashboard
│   │   ├── component/  # React components
│   │   ├── styles/     # CSS files
│   │   └── utils/      # Utility functions
│   ├── package.json    # Node dependencies
│   ├── Dockerfile      # Frontend container
│   └── .env           # Frontend configuration
├── postgre/            # Database module
│   ├── database.py     # Database operations
│   └── .env           # Database configuration
├── docker-compose.yml  # Container orchestration
└── netlify.toml       # Netlify deployment config
```

## 🔌 API Endpoints

### Sensor Data
- `POST /api/sensors/data` - Add new sensor reading
- `GET /api/sensors/data?limit=N` - Get latest N readings
- `GET /api/sensors/latest` - Get most recent reading

### Violators (Detection Data)
- `POST /api/violators` - Submit detection metadata
- `GET /api/violators` - Get list of detected violations
- `GET /api/violators/{id}` - Get specific violation details
- `PUT /api/violators/{id}` - Update violation status
- `DELETE /api/violators/{id}` - Remove violation record

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/verify` - Verify authentication

### System
- `GET /api/hello` - Health check
- `GET /api/time` - Server time

### Example API Usage

```bash
# Health check
curl http://127.0.0.1:8000/api/hello

# Add sensor data
curl -X POST http://127.0.0.1:8000/api/sensors/data \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 25.5,
    "humidity": 60.2,
    "vocs": 150.0,
    "nitrogen_dioxide": 0.05,
    "carbon_monoxide": 0.8,
    "pm25": 12.5,
    "pm10": 18.3
  }'

# Get latest sensor data
curl http://127.0.0.1:8000/api/sensors/latest
```

## 🔧 Configuration

### Backend Environment (.env)
```env
# Database Configuration
DB_HOST=localhost
DB_NAME=smoki_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_PORT=5432

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true

# Authentication
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Frontend Environment (.env)
```env
# API Configuration
VITE_API_URL=http://localhost:8000

# App Configuration
VITE_APP_NAME=SMOKi Dashboard
VITE_APP_VERSION=1.0.0
```

### Production Environment (.env.production)
```env
# Production API URL
VITE_API_URL=https://your-backend-url.com

# Production settings
VITE_DEBUG=false
```

## 🚀 Deployment

### Netlify Deployment (Frontend)

The project includes `netlify.toml` for easy frontend deployment:

```bash
# Build the frontend
cd frontend
npm run build

# Deploy to Netlify (manual)
# Upload the dist/ folder to Netlify

# Or use Netlify CLI
npm install -g netlify-cli
netlify deploy --prod --dir=dist
```

### Backend Deployment

For backend deployment, you can use services like:
- **Heroku**: Includes `Procfile` for easy deployment
- **Railway**: Docker-based deployment
- **DigitalOcean App Platform**: Container deployment
- **AWS/GCP/Azure**: Cloud deployment

### Docker Production Deployment

```bash
# Production build
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale services
docker-compose up -d --scale backend=3
```

## 🐛 Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
# Windows: Check Services
# Linux: sudo systemctl status postgresql
# Mac: brew services list

# Test connection
psql -U postgres -d smoki_db

# Reset database
docker-compose down -v
docker-compose up -d postgres
```

### Frontend Build Issues

```bash
# Clear node modules and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm install

# Clear build cache
npm run build -- --force
```

### Backend Issues

```bash
# Check logs
docker-compose logs backend

# Restart backend service
docker-compose restart backend

# Check Python dependencies
cd backend
pip install -r requirements.txt
```

## 📊 Features Overview

### Dashboard Components
- **Real-time Metrics**: Live sensor data display
- **Historical Charts**: Time-series data visualization
- **Alert System**: Threshold-based notifications
- **Data Export**: CSV/JSON data export functionality
- **User Management**: Authentication and user roles

### API Features
- **RESTful Design**: Standard HTTP methods and status codes
- **Data Validation**: Pydantic models for request/response validation
- **Error Handling**: Comprehensive error responses
- **Documentation**: Auto-generated OpenAPI/Swagger docs at `/docs`
- **CORS Support**: Cross-origin resource sharing enabled

## 🔒 Security

- **Authentication**: JWT-based user authentication
- **Input Validation**: Server-side data validation
- **CORS Configuration**: Controlled cross-origin access
- **Environment Variables**: Sensitive data in environment files
- **SQL Injection Protection**: ORM-based database queries

## 📈 Performance

- **Database Indexing**: Optimized database queries
- **Caching**: Response caching for frequently accessed data
- **Compression**: Gzip compression for API responses
- **Lazy Loading**: Frontend component lazy loading
- **Bundle Optimization**: Webpack optimization for production builds

## 🧪 Testing

```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests
cd frontend
npm test

# Integration tests
npm run test:integration
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Contributors

- mercado - backend development
- miiikunnn - web design
- skhartaye - project coordination

## 🙏 Acknowledgments

- FastAPI for the excellent web framework
- React and Recharts for the frontend
- PostgreSQL for reliable data storage
- Docker for containerization

## 📞 Support

For issues and questions:
- Create an issue on GitHub
- Email: aerobandtech@gmail.com

---

**Note**: This is the website-only version of the SMOKi project, excluding ESP32 and Raspberry Pi components. For the complete IoT system, see the full repository.