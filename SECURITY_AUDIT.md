# SMOKi Security Audit Report

## Critical Vulnerabilities

### 1. CORS Misconfiguration
**Severity**: CRITICAL
**Location**: `backend/main.py` line 20-27

**Current Code**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
```

**Fix**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://yourdomain.com"  # Add your production domain
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
    max_age=3600
)
```

### 2. Hardcoded Secret Key
**Severity**: CRITICAL
**Location**: `backend/auth.py` line 15

**Current Code**:
```python
SECRET_KEY = "your-secret-key-change-this-in-production"
```

**Fix**:
```python
import os
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
if SECRET_KEY == "change-this-in-production":
    raise ValueError("SECRET_KEY must be set in environment variables!")
```

### 3. Unauthenticated Sensor Endpoints
**Severity**: HIGH
**Location**: `backend/main.py` lines 95-130

**Current Code**:
```python
@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData):  # No auth
    """Add new sensor reading to database (No auth required for ESP32)"""
```

**Fix**:
```python
@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData, current_user: User = Depends(get_current_user)):
    """Add new sensor reading to database"""
    # For ESP32, use API key authentication instead
```

### 4. Missing Rate Limiting
**Severity**: HIGH

**Solution**:
```bash
pip install slowapi
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/auth/login")
@limiter.limit("5/minute")
def login(request: Request, login_data: LoginRequest):
    # Login endpoint limited to 5 attempts per minute
```

### 5. Information Disclosure in Error Messages
**Severity**: MEDIUM
**Location**: Multiple endpoints

**Current Code**:
```python
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

**Fix**:
```python
import logging

logger = logging.getLogger(__name__)

except Exception as e:
    logger.error(f"Database error: {e}")  # Log internally
    raise HTTPException(status_code=500, detail="Internal server error")
```

### 6. No Input Validation
**Severity**: MEDIUM

**Fix**:
```python
from pydantic import BaseModel, Field, validator

class SensorData(BaseModel):
    temperature: float | None = Field(None, ge=-50, le=150)
    humidity: float | None = Field(None, ge=0, le=100)
    vocs: float | None = Field(None, ge=0)
    nitrogen_dioxide: float | None = Field(None, ge=0)
    carbon_monoxide: float | None = Field(None, ge=0)
    pm25: float | None = Field(None, ge=0)
    pm10: float | None = Field(None, ge=0)
    
    @validator('*')
    def check_not_nan(cls, v):
        if v is not None and (v != v):  # NaN check
            raise ValueError('Value cannot be NaN')
        return v
```

### 7. Missing HTTPS Enforcement
**Severity**: MEDIUM

**Fix** (for production):
```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["yourdomain.com"])

# Use HTTPS in production
# Configure with reverse proxy (nginx, Apache) or cloud provider
```

### 8. No Logging/Monitoring
**Severity**: MEDIUM

**Fix**:
```python
import logging
from logging.handlers import RotatingFileHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/app.log', maxBytes=10485760, backupCount=10),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Log authentication attempts
logger.info(f"Login attempt for user: {login_data.username}")
logger.warning(f"Failed login attempt for user: {login_data.username}")
```

## Additional Recommendations

### 1. Implement API Key for ESP32
```python
# For IoT devices, use API keys instead of JWT
API_KEYS = {
    "esp32-device-1": "your-secure-api-key-here"
}

@app.post("/api/sensors/data")
def add_sensor_data(data: SensorData, api_key: str = Header(None)):
    if api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Process sensor data
```

### 2. Implement HTTPS
- Use Let's Encrypt for free SSL certificates
- Configure reverse proxy (nginx)
- Enforce HSTS headers

### 3. Database Security
- Use parameterized queries (already done with psycopg)
- Implement connection pooling with timeout
- Use strong database passwords
- Restrict database access to backend only

### 4. Frontend Security
- Implement CSRF tokens
- Use secure cookie flags (HttpOnly, Secure, SameSite)
- Sanitize user inputs
- Implement Content Security Policy (CSP)

### 5. Deployment Security
- Run backend in Docker container
- Use environment variables for secrets
- Implement secrets management (AWS Secrets Manager, HashiCorp Vault)
- Regular security updates and patches
- Web Application Firewall (WAF)

## Testing Recommendations

1. **Penetration Testing**: Hire professional penetration testers
2. **OWASP Top 10**: Test against OWASP Top 10 vulnerabilities
3. **Dependency Scanning**: Use `pip-audit` to check for vulnerable packages
4. **Static Code Analysis**: Use `bandit` for Python security issues

```bash
pip install bandit pip-audit
bandit -r backend/
pip-audit
```

## Compliance

- GDPR: Implement data retention policies
- CCPA: Implement data deletion mechanisms
- PCI DSS: If handling payment data
- HIPAA: If handling health data

## Priority Fix Order

1. ✅ Change SECRET_KEY (CRITICAL)
2. ✅ Fix CORS configuration (CRITICAL)
3. ✅ Add authentication to sensor endpoints (HIGH)
4. ✅ Implement rate limiting (HIGH)
5. ✅ Add input validation (MEDIUM)
6. ✅ Implement logging (MEDIUM)
7. ✅ Add error handling (MEDIUM)
8. ✅ Enforce HTTPS (MEDIUM)

---

**Report Generated**: 2025-02-19
**Status**: NEEDS IMMEDIATE ATTENTION
