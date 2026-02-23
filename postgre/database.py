import psycopg
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection string
def get_connection_string():
    """Get database connection string"""
    return (f"host={os.getenv('DB_HOST', 'localhost')} "
            f"dbname={os.getenv('DB_NAME', 'smoki_db')} "
            f"user={os.getenv('DB_USER', 'postgres')} "
            f"password={os.getenv('DB_PASSWORD', 'password')} "
            f"port={os.getenv('DB_PORT', '5432')}")

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
                
                # Create violations table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS violations (
                        id SERIAL PRIMARY KEY,
                        vehicle_id INT REFERENCES vehicles(id) ON DELETE CASCADE,
                        detection_id INT REFERENCES vehicle_detections(id) ON DELETE CASCADE,
                        violation_type VARCHAR(50),
                        severity VARCHAR(20),
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        description TEXT,
                        resolved BOOLEAN DEFAULT FALSE,
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
                
                # Create indexes for faster queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
                    ON sensor_data(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_users_username 
                    ON users(username);
                """)
                
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
                    CREATE INDEX IF NOT EXISTS idx_violations_vehicle_id 
                    ON violations(vehicle_id);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_violations_timestamp 
                    ON violations(timestamp);
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
                
                conn.commit()
                print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
            conn.rollback()

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
    """Get top violating vehicles"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT v.id, v.license_plate, v.vehicle_type, v.total_violations,
                           v.last_detected, vd.emission_level, vd.smoke_detected
                    FROM vehicles v
                    LEFT JOIN vehicle_detections vd ON v.id = vd.vehicle_id
                    WHERE v.status = 'active'
                    ORDER BY v.total_violations DESC, v.last_detected DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'license_plate', 'vehicle_type', 'violations', 
                           'last_detected', 'emission_level', 'smoke_detected']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching top violators: {e}")
            return []

def get_vehicle_ranking():
    """Get all vehicles ranked by violations"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
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

