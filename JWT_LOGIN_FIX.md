# JWT Login Fix Summary

## Issues Fixed

### 1. Password Hash Format Issue
**Problem**: The hashed passwords in `USERS_DB` were stored as byte strings (with `b` prefix), which caused bcrypt verification to fail.

**Solution**: Changed password hashes from bytes to strings:
- Updated `USERS_DB` to use string hashes instead of byte strings
- Modified `verify_password()` to encode the string hash before comparison
- Updated `get_password_hash()` to return decoded string instead of bytes
- Changed `UserInDB.hashed_password` type from `bytes` to `str`

### 2. Test Credentials
The following credentials are now working:

**Admin Account:**
- Username: `admin`
- Password: `1234`
- Role: admin

**Superadmin Account:**
- Username: `superadmin`
- Password: `superadmin123`
- Role: superadmin

## Testing
Run `python backend/test_auth.py` to verify password hashing is working correctly.

## How to Use
1. Start the backend server: `uvicorn main:app --reload` (from backend directory)
2. Start the frontend: `npm run dev` (from frontend directory)
3. Login with either admin or superadmin credentials
4. JWT token will be stored in localStorage and used for authenticated requests

## API Endpoints
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user info (requires JWT)
- `GET /api/sensors/data` - Get sensor data (requires admin or superadmin)
- `POST /api/sensors/data` - Add sensor data (requires superadmin only)
