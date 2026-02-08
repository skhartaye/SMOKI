# API Permissions Summary

## User Roles

### Admin
- Can READ sensor data
- Cannot CREATE, UPDATE, or DELETE

### Superadmin
- Can CREATE sensor data
- Can READ sensor data
- Can UPDATE sensor data
- Can DELETE sensor data

## API Endpoints

### Authentication (Public)
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user info (requires any valid token)

### Sensor Data

#### READ (Admin + Superadmin)
- `GET /api/sensors/data?limit=10` - Get latest sensor readings
- `GET /api/sensors/latest` - Get most recent reading

#### CREATE (Superadmin Only)
- `POST /api/sensors/data` - Add new sensor reading
  ```json
  {
    "temperature": 25.5,
    "humidity": 60.0,
    "vocs": 150.0,
    "nitrogen_dioxide": 0.05,
    "carbon_monoxide": 0.02,
    "pm25": 12.5,
    "pm10": 20.0
  }
  ```

#### UPDATE (Superadmin Only)
- `PUT /api/sensors/data/{record_id}` - Update existing record
  ```json
  {
    "temperature": 26.0,
    "humidity": 65.0
  }
  ```

#### DELETE (Superadmin Only)
- `DELETE /api/sensors/data/{record_id}` - Delete record

## Testing Permissions

### Test as Admin (should fail for CUD operations)
```bash
# Login as admin
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"1234"}'

# Try to delete (should get 403 Forbidden)
curl -X DELETE http://127.0.0.1:8000/api/sensors/data/1 \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Test as Superadmin (should succeed)
```bash
# Login as superadmin
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"superadmin","password":"superadmin123"}'

# Delete record (should succeed)
curl -X DELETE http://127.0.0.1:8000/api/sensors/data/1 \
  -H "Authorization: Bearer YOUR_SUPERADMIN_TOKEN"
```

## Security Notes

✅ All endpoints require JWT authentication
✅ Role-based access control enforced on backend
✅ Admin cannot escalate privileges
✅ Frontend modifications won't bypass backend checks
