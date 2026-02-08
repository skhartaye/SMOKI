# SMOKI Authentication Guide

## 🔐 JWT Authentication System

SMOKI now uses JWT (JSON Web Token) authentication with role-based access control.

## 👥 User Roles

### 1. Admin (Read-Only)
- **Username**: `admin`
- **Password**: `1234`
- **Permissions**:
  - ✅ View dashboard
  - ✅ View sensor data
  - ✅ View records
  - ✅ View graphs
  - ❌ Cannot add/update/delete sensor data

### 2. Super Admin (Full Access)
- **Username**: `superadmin`
- **Password**: `superadmin123`
- **Permissions**:
  - ✅ View dashboard
  - ✅ View sensor data
  - ✅ View records
  - ✅ View graphs
  - ✅ Add sensor data
  - ✅ Update sensor data
  - ✅ Delete sensor data

## 🚀 Setup Instructions

### 1. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

New packages added:
- `python-jose[cryptography]` - JWT token handling
- `passlib[bcrypt]` - Password hashing
- `python-multipart` - Form data handling

### 2. Start Backend Server

```bash
cd backend
python -m uvicorn main:app --reload
```

### 3. Start Frontend

```bash
cd frontend
npm run dev
```

## 🔑 API Endpoints

### Authentication

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "1234"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "admin",
  "username": "admin"
}
```

#### Get Current User
```http
GET /api/auth/me
Authorization: Bearer <token>
```

**Response:**
```json
{
  "username": "admin",
  "role": "admin",
  "full_name": "Admin User"
}
```

### Protected Endpoints

All sensor endpoints now require authentication:

#### Get Sensor Data (Admin & Superadmin)
```http
GET /api/sensors/data?limit=50
Authorization: Bearer <token>
```

#### Get Latest Reading (Admin & Superadmin)
```http
GET /api/sensors/latest
Authorization: Bearer <token>
```

#### Add Sensor Data (Superadmin Only)
```http
POST /api/sensors/data
Authorization: Bearer <token>
Content-Type: application/json

{
  "temperature": 25.5,
  "humidity": 60.2,
  "vocs": 150.0,
  "nitrogen_dioxide": 0.05,
  "carbon_monoxide": 0.8,
  "pm25": 12.5,
  "pm10": 18.3
}
```

## 🔒 Security Features

### Token Expiration
- Tokens expire after **24 hours**
- Users must log in again after expiration
- Expired tokens are automatically rejected

### Password Hashing
- Passwords are hashed using **bcrypt**
- Plain passwords are never stored
- Secure password verification

### Role-Based Access Control
- Endpoints check user roles before allowing access
- Unauthorized access returns `403 Forbidden`
- Invalid tokens return `401 Unauthorized`

## 🛠️ Frontend Integration

### Storing Token
```javascript
// After successful login
localStorage.setItem('token', data.access_token);
localStorage.setItem('role', data.role);
localStorage.setItem('username', data.username);
```

### Making Authenticated Requests
```javascript
const token = localStorage.getItem('token');
const response = await fetch(`${API_URL}/api/sensors/data`, {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

### Handling Token Expiration
```javascript
if (response.status === 401) {
  // Token expired or invalid
  localStorage.clear();
  navigate('/');
}
```

## 🔐 Production Security Checklist

Before deploying to production:

- [ ] Change `SECRET_KEY` in `backend/auth.py`
- [ ] Use environment variable for `SECRET_KEY`
- [ ] Change default passwords
- [ ] Store users in a database (not in-memory)
- [ ] Enable HTTPS
- [ ] Set secure CORS origins
- [ ] Implement rate limiting
- [ ] Add password complexity requirements
- [ ] Implement password reset functionality
- [ ] Add account lockout after failed attempts
- [ ] Enable audit logging

## 📝 Adding New Users

To add new users, update `USERS_DB` in `backend/auth.py`:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Generate password hash
hashed_password = pwd_context.hash("your_password")

# Add to USERS_DB
USERS_DB["newuser"] = {
    "username": "newuser",
    "hashed_password": hashed_password,
    "role": "admin",  # or "superadmin"
    "full_name": "New User"
}
```

## 🐛 Troubleshooting

### "Could not validate credentials"
- Check if token is being sent in Authorization header
- Verify token hasn't expired
- Ensure SECRET_KEY matches between token creation and validation

### "Not enough permissions"
- Verify user role is correct
- Check if endpoint requires superadmin access
- Confirm token contains role information

### "Connection error"
- Verify backend server is running
- Check API_URL in frontend .env file
- Ensure CORS is properly configured

## 📚 Testing with cURL

### Login
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"1234"}'
```

### Get Sensor Data
```bash
TOKEN="your_token_here"
curl -X GET http://127.0.0.1:8000/api/sensors/data?limit=10 \
  -H "Authorization: Bearer $TOKEN"
```

### Add Sensor Data (Superadmin)
```bash
TOKEN="superadmin_token_here"
curl -X POST http://127.0.0.1:8000/api/sensors/data \
  -H "Authorization: Bearer $TOKEN" \
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
```

## 🔄 Token Refresh (Future Enhancement)

Currently, tokens expire after 24 hours. Future enhancements could include:
- Refresh tokens for extended sessions
- Sliding expiration windows
- Remember me functionality

---

**Note**: This authentication system is suitable for development and small deployments. For production use with many users, consider implementing a proper user management system with a database.
