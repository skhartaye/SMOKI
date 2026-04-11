import psycopg
from datetime import datetime
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Database connection string
def get_connection_string():
    """Get database connection string"""
    return (f"host={os.getenv('DB_HOST', 'localhost')} "
            f"dbname={os.getenv('DB_NAME', 'smoki_db')} "
            f"user={os.getenv('DB_USER', 'postgres')} "
            f"password={os.getenv('DB_PASSWORD', 'password')} "
            f"port={os.getenv('DB_PORT', '5432')} "
            f"sslmode=require")

def init_db_pool():
    """Initialize database (create tables)"""
    try:
        print("Initializing database...")
        print(f"Connecting to: {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}")
        create_tables()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        print("WARNING: Database initialization failed. Some features may not work.")
        # Don't raise - allow app to start anyway

def create_tables():
    """Create necessary tables if they don't exist"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                print("[DB] Creating users table...")
                # Create users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        hashed_password VARCHAR(255) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        full_name VARCHAR(100),
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                print("[DB] Creating sensor_data table...")
                # Create sensor_data table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_data (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        temperature FLOAT,
                        humidity FLOAT,
                        pressure FLOAT,
                        vocs FLOAT,
                        nitrogen_dioxide FLOAT,
                        carbon_monoxide FLOAT,
                        pm25 FLOAT,
                        pm10 FLOAT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Add pressure column if it doesn't exist (for existing databases)
                cursor.execute("""
                    ALTER TABLE sensor_data
                    ADD COLUMN IF NOT EXISTS pressure FLOAT;
                """)
                
                print("[DB] Creating detections table...")
                # NEW SCHEMA: Create detections table (every snapshot - runs every 3 seconds always)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS detections (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        camera_id TEXT NOT NULL,
                        location TEXT,
                        smoke_count INT DEFAULT 0,
                        vehicle_count INT DEFAULT 0,
                        plate_count INT DEFAULT 0,
                        face_count INT DEFAULT 0,
                        is_violation BOOLEAN DEFAULT FALSE,
                        inference_ms INT,
                        upload_ms INT,
                        detections_json JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                print("[DB] Creating smoke_events table...")
                # NEW SCHEMA: Create smoke_events table (one row per smoke detection)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS smoke_events (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        camera_id TEXT NOT NULL,
                        location TEXT,
                        smoke_type TEXT,
                        opacity_level TEXT,
                        opacity_score FLOAT,
                        confidence FLOAT,
                        bbox JSONB,
                        bbox_area_px INT,
                        inference_ms INT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                print("[DB] Creating plate_events table...")
                # NEW SCHEMA: Create plate_events table (one row per plate OCR result)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plate_events (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        camera_id TEXT NOT NULL,
                        location TEXT,
                        plate_text TEXT,
                        ocr_confidence FLOAT,
                        bbox JSONB,
                        inference_ms INT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                print("[DB] Creating violations table...")
                # NEW SCHEMA: Create violations table (one row per violation - smoke + vehicle in same frame)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS violations (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        camera_id TEXT NOT NULL,
                        location TEXT,
                        smoke_count INT DEFAULT 0,
                        vehicle_count INT DEFAULT 0,
                        plate_texts TEXT[],
                        opacity_levels TEXT[],
                        detections_json JSONB,
                        inference_ms INT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                print("[DB] Creating legacy tables...")
                # Keep legacy tables for backward compatibility
                # Create vehicles table for SMOKI (RPi camera detection)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vehicles (
                        id SERIAL PRIMARY KEY,
                        license_plate VARCHAR(50) UNIQUE NOT NULL,
                        vehicle_type VARCHAR(50),
                        first_detected TIMESTAMPTZ DEFAULT NOW(),
                        last_detected TIMESTAMPTZ DEFAULT NOW(),
                        total_violations INT DEFAULT 0,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create vehicle_detections table for individual detections
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS vehicle_detections (
                        id SERIAL PRIMARY KEY,
                        vehicle_id INT REFERENCES vehicles(id) ON DELETE CASCADE,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        location VARCHAR(255),
                        confidence FLOAT,
                        smoke_detected BOOLEAN DEFAULT FALSE,
                        emission_level VARCHAR(20),
                        image_path VARCHAR(255),
                        metadata JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create notifications table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        violation_id INT REFERENCES violations(id) ON DELETE CASCADE,
                        title VARCHAR(255),
                        message TEXT,
                        notification_type VARCHAR(50),
                        is_read BOOLEAN DEFAULT FALSE,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create images table for storing image data
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS images (
                        id SERIAL PRIMARY KEY,
                        vehicle_detection_id INT REFERENCES vehicle_detections(id) ON DELETE CASCADE,
                        violation_id INT REFERENCES violations(id) ON DELETE SET NULL,
                        image_data BYTEA NOT NULL,
                        image_format VARCHAR(20),
                        file_size INT,
                        width INT,
                        height INT,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # Create image_metadata table for storing image metadata
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS image_metadata (
                        id SERIAL PRIMARY KEY,
                        image_id INT REFERENCES images(id) ON DELETE CASCADE,
                        camera_id VARCHAR(100),
                        camera_location VARCHAR(255),
                        exposure_time FLOAT,
                        iso_speed INT,
                        focal_length FLOAT,
                        aperture FLOAT,
                        white_balance VARCHAR(50),
                        flash_used BOOLEAN,
                        gps_latitude FLOAT,
                        gps_longitude FLOAT,
                        gps_altitude FLOAT,
                        device_model VARCHAR(255),
                        software_version VARCHAR(100),
                        processing_time_ms INT,
                        quality_score FLOAT,
                        additional_data JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                print("[DB] Creating indexes...")
                # Create indexes for faster queries
                try:
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
                        ON sensor_data(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_users_username 
                        ON users(username);
                    """)
                    
                    # NEW SCHEMA INDEXES - with error handling
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_detections_timestamp 
                        ON detections(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_detections_camera_id 
                        ON detections(camera_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_smoke_events_timestamp 
                        ON smoke_events(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_smoke_events_camera_id 
                        ON smoke_events(camera_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_plate_events_timestamp 
                        ON plate_events(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_plate_events_camera_id 
                        ON plate_events(camera_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_violations_timestamp 
                        ON violations(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_violations_camera_id 
                        ON violations(camera_id);
                    """)
                    
                    # Legacy indexes
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_vehicles_license_plate 
                        ON vehicles(license_plate);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_vehicle_detections_timestamp 
                        ON vehicle_detections(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_vehicle_detections_vehicle_id 
                        ON vehicle_detections(vehicle_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_notifications_timestamp 
                        ON notifications(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_images_vehicle_detection_id 
                        ON images(vehicle_detection_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_images_violation_id 
                        ON images(violation_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_images_timestamp 
                        ON images(timestamp);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_image_metadata_image_id 
                        ON image_metadata(image_id);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_image_metadata_camera_id 
                        ON image_metadata(camera_id);
                    """)
                    
                except Exception as idx_error:
                    print(f"[DB] Index creation error (non-fatal): {idx_error}")
                    # Continue anyway - indexes are not critical for basic functionality
                
                conn.commit()
                print("[DB] Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            raise  # Re-raise to see the full error

# ============ SENSOR DATA FUNCTIONS ============

def insert_sensor_data(temperature=None, humidity=None, pressure=None, vocs=None, 
                       nitrogen_dioxide=None, carbon_monoxide=None, 
                       pm25=None, pm10=None):
    """Insert sensor data into database"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO sensor_data 
                    (temperature, humidity, pressure, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (temperature, humidity, pressure, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error inserting sensor data: {e}")
            conn.rollback()
            return None

def get_latest_sensor_data(limit=10):
    """Get latest sensor readings"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, temperature, humidity, pressure, vocs, 
                           nitrogen_dioxide, carbon_monoxide, pm25, pm10
                    FROM sensor_data
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'timestamp', 'temperature', 'humidity', 'pressure', 'vocs', 
                           'nitrogen_dioxide', 'carbon_monoxide', 'pm25', 'pm10']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching sensor data: {e}")
            return []

def get_sensor_data_by_timerange(start_time, end_time):
    """Get sensor data within a time range"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, temperature, humidity, pressure, vocs, 
                           nitrogen_dioxide, carbon_monoxide, pm25, pm10
                    FROM sensor_data
                    WHERE timestamp BETWEEN %s AND %s
                    ORDER BY timestamp DESC;
                """, (start_time, end_time))
                
                columns = ['id', 'timestamp', 'temperature', 'humidity', 'pressure', 'vocs', 
                           'nitrogen_dioxide', 'carbon_monoxide', 'pm25', 'pm10']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching sensor data by time range: {e}")
            return []

def update_sensor_data(record_id, temperature=None, humidity=None, pressure=None, vocs=None, 
                       nitrogen_dioxide=None, carbon_monoxide=None, 
                       pm25=None, pm10=None):
    """Update sensor data record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE sensor_data
                    SET temperature = %s,
                        humidity = %s,
                        pressure = %s,
                        vocs = %s,
                        nitrogen_dioxide = %s,
                        carbon_monoxide = %s,
                        pm25 = %s,
                        pm10 = %s
                    WHERE id = %s
                    RETURNING id, timestamp;
                """, (temperature, humidity, pressure, vocs, nitrogen_dioxide, carbon_monoxide, 
                      pm25, pm10, record_id))
                
                result = cursor.fetchone()
                if result:
                    conn.commit()
                    return {"id": result[0], "timestamp": result[1]}
                else:
                    return None
        except Exception as e:
            print(f"Error updating sensor data: {e}")
            conn.rollback()
            return None

def delete_sensor_data(record_id):
    """Delete sensor data record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM sensor_data
                    WHERE id = %s
                    RETURNING id;
                """, (record_id,))
                
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error deleting sensor data: {e}")
            conn.rollback()
            return False

def delete_invalid_sensor_data():
    """Delete sensor data records with all NULL values"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Delete records where all sensor values are NULL
                cursor.execute("""
                    DELETE FROM sensor_data
                    WHERE temperature IS NULL 
                    AND humidity IS NULL 
                    AND pressure IS NULL 
                    AND vocs IS NULL 
                    AND nitrogen_dioxide IS NULL 
                    AND carbon_monoxide IS NULL 
                    AND pm25 IS NULL 
                    AND pm10 IS NULL
                    RETURNING id;
                """)
                
                deleted_ids = cursor.fetchall()
                conn.commit()
                return len(deleted_ids)
        except Exception as e:
            print(f"Error deleting invalid sensor data: {e}")
            conn.rollback()
            return 0

def delete_sensor_data_by_date_range(start_date, end_date):
    """Delete sensor data records within a date range"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM sensor_data
                    WHERE timestamp BETWEEN %s AND %s
                    RETURNING id;
                """, (start_date, end_date))
                
                deleted_ids = cursor.fetchall()
                conn.commit()
                return len(deleted_ids)
        except Exception as e:
            print(f"Error deleting sensor data by date range: {e}")
            conn.rollback()
            return 0

# ============ VEHICLE FUNCTIONS ============

def register_vehicle(license_plate, vehicle_type="unknown"):
    """Register a new vehicle"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO vehicles (license_plate, vehicle_type)
                    VALUES (%s, %s)
                    ON CONFLICT (license_plate) DO UPDATE
                    SET last_detected = NOW(), updated_at = NOW()
                    RETURNING id, license_plate, total_violations;
                """, (license_plate, vehicle_type))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "license_plate": result[1], "violations": result[2]}
        except Exception as e:
            print(f"Error registering vehicle: {e}")
            conn.rollback()
            return None

def get_top_violators(limit=5):
    """Get top violating vehicles from detection data"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Get vehicles with violations from detection metadata
                cursor.execute("""
                    SELECT 
                        v.license_plate,
                        v.vehicle_type,
                        v.total_violations,
                        v.last_detected,
                        'high' as emission_level,
                        true as smoke_detected,
                        v.id
                    FROM vehicles v
                    WHERE v.status = 'active' AND v.total_violations > 0
                    ORDER BY v.total_violations DESC, v.last_detected DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['license_plate', 'vehicle_type', 'violations', 
                           'last_detected', 'emission_level', 'smoke_detected', 'id']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                # If no registered vehicles with violations, return empty results
                # Real system should only show actual registered vehicles with violations
                
                return results
        except Exception as e:
            print(f"Error fetching top violators: {e}")
            return []

def get_vehicle_ranking():
    """Get all vehicles ranked by violations from detection data"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Get registered vehicles first
                cursor.execute("""
                    SELECT v.id, v.license_plate, v.vehicle_type, v.total_violations,
                           v.last_detected, v.status
                    FROM vehicles v
                    ORDER BY v.total_violations DESC, v.last_detected DESC;
                """)
                
                columns = ['id', 'license_plate', 'vehicle_type', 'violations', 
                           'last_detected', 'status']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                # If no registered vehicles, create ranking from recent detections
                if not results:
                    cursor.execute("""
                        SELECT id, metadata, timestamp, smoke_detected, location
                        FROM vehicle_detections 
                        ORDER BY timestamp DESC
                        LIMIT 10;
                    """)
                    
                    detection_rows = cursor.fetchall()
                    vehicle_counts = {}
                    
                    for row in detection_rows:
                        metadata = json.loads(row[1]) if row[1] else {}
                        detections = metadata.get('detections', [])
                        
                        # Count vehicles in this detection
                        for detection in detections:
                            class_name = detection.get('class_name', '')
                            if class_name in ['passenger', 'puv', 'services', 'two_wheel']:
                                # Generate consistent license plate for this vehicle type and location
                                timestamp = row[2]
                                location = row[4] or 'Unknown'
                                plate_key = f"{class_name}_{location}_{timestamp.hour}"
                                
                                if plate_key not in vehicle_counts:
                                    plate_suffix = f"{timestamp.hour:02d}{timestamp.minute:02d}"
                                    if class_name == 'passenger':
                                        license_plate = f"ABC-{plate_suffix}"
                                    elif class_name == 'puv':
                                        license_plate = f"PUV-{plate_suffix}"
                                    elif class_name == 'services':
                                        license_plate = f"SVC-{plate_suffix}"
                                    else:
                                        license_plate = f"MC-{plate_suffix}"
                                    
                                    vehicle_counts[plate_key] = {
                                        'license_plate': license_plate,
                                        'vehicle_type': class_name,
                                        'violations': 1 if row[3] else 0,  # smoke_detected
                                        'last_detected': timestamp,
                                        'status': 'active'
                                    }
                                else:
                                    vehicle_counts[plate_key]['violations'] += 1 if row[3] else 0
                                    if timestamp > vehicle_counts[plate_key]['last_detected']:
                                        vehicle_counts[plate_key]['last_detected'] = timestamp
                    
                    # Convert to list and add IDs
                    for i, (key, vehicle) in enumerate(vehicle_counts.items()):
                        vehicle['id'] = f"detected_{i+1}"
                        results.append(vehicle)
                    
                    # Sort by violations
                    results.sort(key=lambda x: x['violations'], reverse=True)
                
                return results
        except Exception as e:
            print(f"Error fetching vehicle ranking: {e}")
            return []

# ============ DETECTION FUNCTIONS ============

def insert_vehicle_detection(vehicle_id, location, confidence, smoke_detected=False, 
                            emission_level="normal", image_path=None, metadata=None):
    """Insert a vehicle detection record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO vehicle_detections 
                    (vehicle_id, location, confidence, smoke_detected, emission_level, image_path, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (vehicle_id, location, confidence, smoke_detected, emission_level, image_path, metadata))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error inserting vehicle detection: {e}")
            conn.rollback()
            return None

# ============ VIOLATION FUNCTIONS ============

def create_violation(vehicle_id, detection_id, violation_type, severity, description=None):
    """Create a violation record"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Insert violation
                cursor.execute("""
                    INSERT INTO violations 
                    (vehicle_id, detection_id, violation_type, severity, description)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                """, (vehicle_id, detection_id, violation_type, severity, description))
                
                violation_id = cursor.fetchone()[0]
                
                # Update vehicle violation count
                cursor.execute("""
                    UPDATE vehicles
                    SET total_violations = total_violations + 1,
                        last_detected = NOW(),
                        updated_at = NOW()
                    WHERE id = %s;
                """, (vehicle_id,))
                
                conn.commit()
                return {"id": violation_id}
        except Exception as e:
            print(f"Error creating violation: {e}")
            conn.rollback()
            return None

def get_recent_violations(limit=10):
    """Get recent violations"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT v.id, v.vehicle_id, v.violation_type, v.severity,
                           v.timestamp, v.description, veh.license_plate
                    FROM violations v
                    JOIN vehicles veh ON v.vehicle_id = veh.id
                    ORDER BY v.timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'vehicle_id', 'violation_type', 'severity', 
                           'timestamp', 'description', 'license_plate']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching violations: {e}")
            return []

# ============ NOTIFICATION FUNCTIONS ============

def create_notification(violation_id, title, message, notification_type="violation"):
    """Create a notification"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO notifications 
                    (violation_id, title, message, notification_type)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (violation_id, title, message, notification_type))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error creating notification: {e}")
            conn.rollback()
            return None

def get_unread_notifications(limit=10):
    """Get unread notifications"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT n.id, n.title, n.message, n.notification_type,
                           n.timestamp, v.severity, veh.license_plate
                    FROM notifications n
                    LEFT JOIN violations v ON n.violation_id = v.id
                    LEFT JOIN vehicles veh ON v.vehicle_id = veh.id
                    WHERE n.is_read = FALSE
                    ORDER BY n.timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'title', 'message', 'notification_type', 
                           'timestamp', 'severity', 'license_plate']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            return []

def mark_notification_read(notification_id):
    """Mark notification as read"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE notifications
                    SET is_read = TRUE
                    WHERE id = %s
                    RETURNING id;
                """, (notification_id,))
                
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error marking notification as read: {e}")
            conn.rollback()
            return False

def close_db_pool():
    """Close database connections"""
    print("Database connections closed")

# ============ USER MANAGEMENT ============

def create_default_users():
    """Create default admin and superadmin users if they don't exist"""
    from backend.auth import get_password_hash
    
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Check if admin exists
                cursor.execute("SELECT id FROM users WHERE username = %s", ("admin1234",))
                if not cursor.fetchone():
                    admin_hash = get_password_hash("superadmin")
                    cursor.execute("""
                        INSERT INTO users (username, hashed_password, role, full_name)
                        VALUES (%s, %s, %s, %s)
                    """, ("admin1234", admin_hash, "admin", "Admin User"))
                    print("✓ Created admin user: admin1234")
                
                # Check if superadmin exists
                cursor.execute("SELECT id FROM users WHERE username = %s", ("superadmin",))
                if not cursor.fetchone():
                    superadmin_hash = get_password_hash("superadmin123")
                    cursor.execute("""
                        INSERT INTO users (username, hashed_password, role, full_name)
                        VALUES (%s, %s, %s, %s)
                    """, ("superadmin", superadmin_hash, "superadmin", "Superadmin User"))
                    print("✓ Created superadmin user: superadmin")
                
                conn.commit()
        except Exception as e:
            print(f"Error creating default users: {e}")
            conn.rollback()

# ============ IMAGE FUNCTIONS ============

def insert_image(vehicle_detection_id, image_data, image_format="jpeg", 
                 file_size=None, width=None, height=None, violation_id=None):
    """Insert an image into the database"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO images 
                    (vehicle_detection_id, violation_id, image_data, image_format, file_size, width, height)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (vehicle_detection_id, violation_id, image_data, image_format, file_size, width, height))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0], "timestamp": result[1]}
        except Exception as e:
            print(f"Error inserting image: {e}")
            conn.rollback()
            return None

def get_image(image_id):
    """Retrieve image data by ID"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, image_data, image_format, file_size, width, height, timestamp
                    FROM images
                    WHERE id = %s;
                """, (image_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "id": result[0],
                        "image_data": result[1],
                        "image_format": result[2],
                        "file_size": result[3],
                        "width": result[4],
                        "height": result[5],
                        "timestamp": result[6]
                    }
                return None
        except Exception as e:
            print(f"Error retrieving image: {e}")
            return None

def get_images_by_detection(vehicle_detection_id):
    """Get all images for a vehicle detection"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, image_format, file_size, width, height, timestamp
                    FROM images
                    WHERE vehicle_detection_id = %s
                    ORDER BY timestamp DESC;
                """, (vehicle_detection_id,))
                
                columns = ['id', 'image_format', 'file_size', 'width', 'height', 'timestamp']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching images by detection: {e}")
            return []

def get_images_by_violation(violation_id):
    """Get all images for a violation"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, image_format, file_size, width, height, timestamp
                    FROM images
                    WHERE violation_id = %s
                    ORDER BY timestamp DESC;
                """, (violation_id,))
                
                columns = ['id', 'image_format', 'file_size', 'width', 'height', 'timestamp']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching images by violation: {e}")
            return []

def delete_image(image_id):
    """Delete an image"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM images
                    WHERE id = %s
                    RETURNING id;
                """, (image_id,))
                
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error deleting image: {e}")
            conn.rollback()
            return False

# ============ IMAGE METADATA FUNCTIONS ============

def insert_image_metadata(image_id, camera_id=None, camera_location=None, 
                         exposure_time=None, iso_speed=None, focal_length=None,
                         aperture=None, white_balance=None, flash_used=None,
                         gps_latitude=None, gps_longitude=None, gps_altitude=None,
                         device_model=None, software_version=None, 
                         processing_time_ms=None, quality_score=None, additional_data=None):
    """Insert image metadata"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO image_metadata 
                    (image_id, camera_id, camera_location, exposure_time, iso_speed, focal_length,
                     aperture, white_balance, flash_used, gps_latitude, gps_longitude, gps_altitude,
                     device_model, software_version, processing_time_ms, quality_score, additional_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (image_id, camera_id, camera_location, exposure_time, iso_speed, focal_length,
                      aperture, white_balance, flash_used, gps_latitude, gps_longitude, gps_altitude,
                      device_model, software_version, processing_time_ms, quality_score, additional_data))
                
                result = cursor.fetchone()
                conn.commit()
                return {"id": result[0]}
        except Exception as e:
            print(f"Error inserting image metadata: {e}")
            conn.rollback()
            return None

def get_image_metadata(image_id):
    """Get metadata for an image"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, camera_id, camera_location, exposure_time, iso_speed, focal_length,
                           aperture, white_balance, flash_used, gps_latitude, gps_longitude, gps_altitude,
                           device_model, software_version, processing_time_ms, quality_score, additional_data
                    FROM image_metadata
                    WHERE image_id = %s;
                """, (image_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "id": result[0],
                        "camera_id": result[1],
                        "camera_location": result[2],
                        "exposure_time": result[3],
                        "iso_speed": result[4],
                        "focal_length": result[5],
                        "aperture": result[6],
                        "white_balance": result[7],
                        "flash_used": result[8],
                        "gps_latitude": result[9],
                        "gps_longitude": result[10],
                        "gps_altitude": result[11],
                        "device_model": result[12],
                        "software_version": result[13],
                        "processing_time_ms": result[14],
                        "quality_score": result[15],
                        "additional_data": result[16]
                    }
                return None
        except Exception as e:
            print(f"Error fetching image metadata: {e}")
            return None

def update_image_metadata(metadata_id, **kwargs):
    """Update image metadata fields"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Build dynamic update query
                set_clauses = []
                values = []
                for key, value in kwargs.items():
                    set_clauses.append(f"{key} = %s")
                    values.append(value)
                
                values.append(metadata_id)
                
                query = f"""
                    UPDATE image_metadata
                    SET {', '.join(set_clauses)}
                    WHERE id = %s
                    RETURNING id;
                """
                
                cursor.execute(query, values)
                result = cursor.fetchone()
                conn.commit()
                return result is not None
        except Exception as e:
            print(f"Error updating image metadata: {e}")
            conn.rollback()
            return False

def get_metadata_by_camera(camera_id, limit=50):
    """Get all metadata for a specific camera"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT im.id, im.image_id, im.camera_location, im.processing_time_ms, 
                           im.quality_score, im.created_at
                    FROM image_metadata im
                    WHERE im.camera_id = %s
                    ORDER BY im.created_at DESC
                    LIMIT %s;
                """, (camera_id, limit))
                
                columns = ['id', 'image_id', 'camera_location', 'processing_time_ms', 
                           'quality_score', 'created_at']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching metadata by camera: {e}")
            return []

def insert_smoke_detection(timestamp, confidence, smoke_type, bounding_box=None, 
                          camera_id="rpi_camera", location="unknown", metadata=None,
                          detections=None, screenshots=None, license_plate=None):
    """Insert a smoke detection record from RPi camera with all model detections"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Prepare comprehensive metadata JSON
                detection_metadata = {
                    "smoke_type": smoke_type,
                    "bounding_box": bounding_box,
                    "camera_id": camera_id,
                    "detection_source": "rpi_camera",
                    "all_detections": []
                }
                
                # Add all model detections to metadata
                if detections:
                    for det in detections:
                        detection_metadata["all_detections"].append({
                            "model": det.get("model_name") if isinstance(det, dict) else det.model_name,
                            "class": det.get("class_name") if isinstance(det, dict) else det.class_name,
                            "confidence": det.get("confidence") if isinstance(det, dict) else det.confidence,
                            "bounding_box": det.get("bounding_box") if isinstance(det, dict) else det.bounding_box
                        })
                
                # Add screenshots info
                if screenshots:
                    detection_metadata["screenshots"] = screenshots
                
                # Add license plate
                if license_plate:
                    detection_metadata["license_plate"] = license_plate
                
                # Merge with additional metadata
                if metadata:
                    detection_metadata.update(metadata)
                
                cursor.execute("""
                    INSERT INTO vehicle_detections 
                    (timestamp, location, confidence, smoke_detected, emission_level, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (timestamp, location, confidence, True, smoke_type, detection_metadata))
                
                result = cursor.fetchone()
                conn.commit()
                
                if result:
                    return {
                        "id": result[0],
                        "timestamp": result[1],
                        "confidence": confidence,
                        "smoke_type": smoke_type,
                        "detections_count": len(detections) if detections else 0
                    }
                return None
        except Exception as e:
            print(f"Error inserting smoke detection: {e}")
            return None


def get_smoke_detections(limit=50, hours=24):
    """Get recent smoke detections"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, location, confidence, metadata
                    FROM vehicle_detections
                    WHERE smoke_detected = TRUE 
                    AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (hours, limit))
                
                columns = ['id', 'timestamp', 'location', 'confidence', 'metadata']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching smoke detections: {e}")
            return []


def insert_vehicle_detection_from_rpi(timestamp, camera_id, location, detections, frame_data, metadata=None):
    """Insert vehicle detection from RPi with frame and metadata"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Store frame image first
                cursor.execute("""
                    INSERT INTO images (vehicle_detection_id, image_data, image_format, file_size, width, height, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (None, frame_data, 'jpeg', len(frame_data), None, None, timestamp))
                
                image_id = cursor.fetchone()[0]
                
                # Store detection metadata with detections included
                full_metadata = metadata or {}
                full_metadata['detections'] = detections
                full_metadata['camera_id'] = camera_id
                full_metadata['location'] = location
                metadata_json = json.dumps(full_metadata)
                
                # Calculate average confidence from detections
                avg_confidence = 0.0
                if detections:
                    confidences = [d.get('confidence', 0.0) for d in detections if isinstance(d.get('confidence'), (int, float))]
                    if confidences:
                        avg_confidence = sum(confidences) / len(confidences)
                
                # Check if smoke was detected
                smoke_detected = any('smoke' in d.get('class_name', '').lower() for d in detections)
                
                cursor.execute("""
                    INSERT INTO vehicle_detections 
                    (vehicle_id, timestamp, location, confidence, smoke_detected, emission_level, image_path, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (None, timestamp, location, avg_confidence, smoke_detected, 'normal', str(image_id), metadata_json))
                
                result = cursor.fetchone()
                
                # Update the image to link back to the detection
                cursor.execute("""
                    UPDATE images SET vehicle_detection_id = %s WHERE id = %s;
                """, (result[0], image_id))
                
                conn.commit()
                
                print(f"[DB] Stored vehicle detection: id={result[0]}, detections={len(detections)}, smoke={smoke_detected}")
                
                return {
                    "id": result[0],
                    "timestamp": result[1],
                    "image_id": image_id,
                    "detections_count": len(detections) if detections else 0,
                    "smoke_detected": smoke_detected
                }
        except Exception as e:
            print(f"Error inserting vehicle detection from RPi: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return None


def get_recent_vehicle_detections(limit=10):
    """Get recent vehicle detections with metadata"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, location, confidence, metadata, image_path
                    FROM vehicle_detections
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                detections = []
                
                for row in rows:
                    try:
                        # Handle both string and dict metadata
                        metadata = row[4]
                        if isinstance(metadata, str):
                            metadata = json.loads(metadata)
                        elif metadata is None:
                            metadata = {}
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                    
                    detections.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "location": row[2],
                        "confidence": row[3],
                        "metadata": metadata,
                        "image_id": row[5]
                    })
                
                return detections
        except Exception as e:
            print(f"Error getting recent vehicle detections: {e}")
            return []


def insert_detection_summary(timestamp, camera_id, location, detection_count, smoke_count, vehicle_count, mode, metadata=None):
    """Insert detection summary metadata (lightweight, no frame data)"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS detection_summaries (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE,
                        camera_id VARCHAR(255),
                        location VARCHAR(255),
                        detection_count INT,
                        smoke_count INT,
                        vehicle_count INT,
                        mode VARCHAR(50),
                        metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                cursor.execute("""
                    INSERT INTO detection_summaries 
                    (timestamp, camera_id, location, detection_count, smoke_count, vehicle_count, mode, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    timestamp,
                    camera_id,
                    location,
                    detection_count,
                    smoke_count,
                    vehicle_count,
                    mode,
                    json.dumps(metadata) if metadata else None
                ))
                
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            print(f"Error inserting detection summary: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return None


def get_recent_detection_summaries(limit=50):
    """Get recent detection summaries"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, detection_count, smoke_count, vehicle_count, mode, metadata
                    FROM detection_summaries
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                summaries = []
                
                for row in rows:
                    metadata = json.loads(row[8]) if row[8] else {}
                    summaries.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "detection_count": row[4],
                        "smoke_count": row[5],
                        "vehicle_count": row[6],
                        "mode": row[7],
                        "metadata": metadata
                    })
                
                return summaries
        except Exception as e:
            print(f"Error getting recent detection summaries: {e}")
            return []

# ============ NEW SCHEMA FUNCTIONS ============

def insert_detection(timestamp, camera_id, location=None, smoke_count=0, vehicle_count=0, 
                    plate_count=0, face_count=0, is_violation=False, inference_ms=None, 
                    upload_ms=None, detections_json=None):
    """Insert detection snapshot (runs every 3 seconds)"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Ensure the detections table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS detections (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        camera_id TEXT NOT NULL,
                        location TEXT,
                        smoke_count INT DEFAULT 0,
                        vehicle_count INT DEFAULT 0,
                        plate_count INT DEFAULT 0,
                        face_count INT DEFAULT 0,
                        is_violation BOOLEAN DEFAULT FALSE,
                        inference_ms INT,
                        upload_ms INT,
                        detections_json JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                cursor.execute("""
                    INSERT INTO detections 
                    (timestamp, camera_id, location, smoke_count, vehicle_count, plate_count, 
                     face_count, is_violation, inference_ms, upload_ms, detections_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    timestamp, camera_id, location, smoke_count, vehicle_count, plate_count,
                    face_count, is_violation, inference_ms, upload_ms, 
                    json.dumps(detections_json) if detections_json else None
                ))
                
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            print(f"Error inserting detection: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return None


def insert_smoke_event(timestamp, camera_id, location=None, smoke_type=None, 
                      opacity_level=None, opacity_score=None, confidence=None, 
                      bbox=None, bbox_area_px=None, inference_ms=None):
    """Insert smoke detection event"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO smoke_events 
                    (timestamp, camera_id, location, smoke_type, opacity_level, opacity_score, 
                     confidence, bbox, bbox_area_px, inference_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    timestamp, camera_id, location, smoke_type, opacity_level, opacity_score,
                    confidence, json.dumps(bbox) if bbox else None, bbox_area_px, inference_ms
                ))
                
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            print(f"Error inserting smoke event: {e}")
            conn.rollback()
            return None


def insert_plate_event(timestamp, camera_id, location=None, plate_text=None, 
                      ocr_confidence=None, bbox=None, inference_ms=None):
    """Insert license plate OCR event"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO plate_events 
                    (timestamp, camera_id, location, plate_text, ocr_confidence, bbox, inference_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    timestamp, camera_id, location, plate_text, ocr_confidence,
                    json.dumps(bbox) if bbox else None, inference_ms
                ))
                
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            print(f"Error inserting plate event: {e}")
            conn.rollback()
            return None


def insert_violation_event(timestamp, camera_id, location=None, smoke_count=0, 
                          vehicle_count=0, plate_texts=None, opacity_levels=None, 
                          detections_json=None, inference_ms=None):
    """Insert violation event (smoke + vehicle in same frame) - REVERTED TO OLD SCHEMA"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Create vehicle records for each plate detected
                vehicle_ids = []
                if plate_texts:
                    for plate in plate_texts:
                        if plate and plate.strip():
                            # Register/get vehicle
                            vehicle = register_vehicle(plate.strip(), "unknown")
                            if vehicle:
                                vehicle_ids.append(vehicle['id'])
                                
                                # Create violation record in old schema
                                cursor.execute("""
                                    INSERT INTO violations 
                                    (vehicle_id, violation_type, severity, timestamp, description, camera_id)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    RETURNING id;
                                """, (
                                    vehicle['id'], 
                                    "smoke_emission", 
                                    "high" if "dense" in (opacity_levels or []) else "medium",
                                    timestamp,
                                    f"Smoke detected at {location or 'unknown location'} with {smoke_count} smoke sources and {vehicle_count} vehicles",
                                    camera_id
                                ))
                                
                                violation_result = cursor.fetchone()
                                if violation_result:
                                    print(f"Created violation {violation_result[0]} for vehicle {vehicle['id']} plate {plate}")
                
                conn.commit()
                # Return the first violation ID or a generated one
                return violation_result[0] if 'violation_result' in locals() and violation_result else len(vehicle_ids)
                
        except Exception as e:
            print(f"Error inserting violation event: {e}")
            conn.rollback()
            return None


def get_all_detections(limit=50):
    """Get all detection snapshots with timestamps"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, smoke_count, vehicle_count, 
                           plate_count, face_count, is_violation, inference_ms, upload_ms, 
                           detections_json
                    FROM detections
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                detections = []
                
                for row in rows:
                    detections_json = json.loads(row[11]) if row[11] else {}
                    detections.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "smoke_count": row[4],
                        "vehicle_count": row[5],
                        "plate_count": row[6],
                        "face_count": row[7],
                        "is_violation": row[8],
                        "inference_ms": row[9],
                        "upload_ms": row[10],
                        "detections_json": detections_json
                    })
                
                return detections
        except Exception as e:
            print(f"Error getting all detections: {e}")
            return []


def get_smoke_events(limit=50):
    """Get smoke detection events"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, smoke_type, opacity_level, 
                           opacity_score, confidence, bbox, bbox_area_px, inference_ms
                    FROM smoke_events
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                events = []
                
                for row in rows:
                    bbox = json.loads(row[8]) if row[8] else {}
                    events.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "smoke_type": row[4],
                        "opacity_level": row[5],
                        "opacity_score": row[6],
                        "confidence": row[7],
                        "bbox": bbox,
                        "bbox_area_px": row[9],
                        "inference_ms": row[10]
                    })
                
                return events
        except Exception as e:
            print(f"Error getting smoke events: {e}")
            return []


def get_plate_events(limit=50):
    """Get license plate OCR events"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, camera_id, location, plate_text, ocr_confidence, 
                           bbox, inference_ms
                    FROM plate_events
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                events = []
                
                for row in rows:
                    bbox = json.loads(row[6]) if row[6] else {}
                    events.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": row[3],
                        "plate_text": row[4],
                        "ocr_confidence": row[5],
                        "bbox": bbox,
                        "inference_ms": row[7]
                    })
                
                return events
        except Exception as e:
            print(f"Error getting plate events: {e}")
            return []


def get_violation_events(limit=50):
    """Get violation events (smoke + vehicle in same frame) - REVERTED TO OLD SCHEMA"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT v.id, v.timestamp, v.camera_id, v.violation_type, v.severity, 
                           v.description, vh.license_plate, vh.vehicle_type
                    FROM violations v
                    LEFT JOIN vehicles vh ON v.vehicle_id = vh.id
                    ORDER BY v.timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                rows = cursor.fetchall()
                events = []
                
                for row in rows:
                    events.append({
                        "id": row[0],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "camera_id": row[2],
                        "location": "Unknown",  # Old schema doesn't have location
                        "smoke_count": 1,  # Assume 1 for old records
                        "vehicle_count": 1,  # Assume 1 for old records
                        "plate_texts": [row[6]] if row[6] else [],
                        "opacity_levels": [row[4]] if row[4] else [],  # Use severity as opacity
                        "detections_json": {"violation_type": row[3], "description": row[5]},
                        "inference_ms": None,
                        "violation_type": row[3],
                        "severity": row[4],
                        "description": row[5],
                        "license_plate": row[6],
                        "vehicle_type": row[7]
                    })
                
                return events
        except Exception as e:
            print(f"Error getting violation events: {e}")
            import traceback
            traceback.print_exc()
            return []

def get_recent_images(limit=50, hours=24):
    """Get recent images within specified hours"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT i.id, i.image_format, i.file_size, i.width, i.height, i.timestamp,
                           i.vehicle_detection_id, i.violation_id,
                           im.camera_id, im.camera_location
                    FROM images i
                    LEFT JOIN image_metadata im ON i.id = im.image_id
                    WHERE i.timestamp >= NOW() - INTERVAL '%s hours'
                    ORDER BY i.timestamp DESC
                    LIMIT %s;
                """, (hours, limit))
                
                columns = ['id', 'image_format', 'file_size', 'width', 'height', 'timestamp',
                          'vehicle_detection_id', 'violation_id', 'camera_id', 'camera_location']
                results = []
                for row in cursor.fetchall():
                    image_data = dict(zip(columns, row))
                    # Convert timestamp to ISO format if it exists
                    if image_data['timestamp']:
                        image_data['timestamp'] = image_data['timestamp'].isoformat()
                    results.append(image_data)
                return results
        except Exception as e:
            print(f"Error fetching recent images: {e}")
            return []

def get_all_images_list(limit=100):
    """Get list of all images (metadata only, no image data)"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT i.id, i.image_format, i.file_size, i.width, i.height, i.timestamp,
                           i.vehicle_detection_id, i.violation_id,
                           im.camera_id, im.camera_location
                    FROM images i
                    LEFT JOIN image_metadata im ON i.id = im.image_id
                    ORDER BY i.timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'image_format', 'file_size', 'width', 'height', 'timestamp',
                          'vehicle_detection_id', 'violation_id', 'camera_id', 'camera_location']
                results = []
                for row in cursor.fetchall():
                    image_data = dict(zip(columns, row))
                    # Convert timestamp to ISO format if it exists
                    if image_data['timestamp']:
                        image_data['timestamp'] = image_data['timestamp'].isoformat()
                    results.append(image_data)
                return results
        except Exception as e:
            print(f"Error fetching images list: {e}")
            return []

def get_user_by_username(username):
    """Get user by username for authentication"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                # Get the requested user
                cursor.execute("""
                    SELECT id, username, hashed_password, role, created_at
                    FROM users
                    WHERE username = %s
                """, (username,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'username': row[1],
                        'password_hash': row[2],  # Note: using 'password_hash' key to match main.py expectations
                        'role': row[3],
                        'created_at': row[4]
                    }
                return None
                
        except Exception as e:
            print(f"Error getting user by username: {e}")
            return None