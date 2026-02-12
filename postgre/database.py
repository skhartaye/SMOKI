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
        create_tables()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")

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
                        vocs FLOAT,
                        nitrogen_dioxide FLOAT,
                        carbon_monoxide FLOAT,
                        pm25 FLOAT,
                        pm10 FLOAT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
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
                
                conn.commit()
                print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
            conn.rollback()

# ============ SENSOR DATA FUNCTIONS ============

def insert_sensor_data(temperature=None, humidity=None, vocs=None, 
                       nitrogen_dioxide=None, carbon_monoxide=None, 
                       pm25=None, pm10=None):
    """Insert sensor data into database"""
    with psycopg.connect(get_connection_string()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO sensor_data 
                    (temperature, humidity, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, timestamp;
                """, (temperature, humidity, vocs, nitrogen_dioxide, carbon_monoxide, pm25, pm10))
                
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
                    SELECT id, timestamp, temperature, humidity, vocs, 
                           nitrogen_dioxide, carbon_monoxide, pm25, pm10
                    FROM sensor_data
                    ORDER BY timestamp DESC
                    LIMIT %s;
                """, (limit,))
                
                columns = ['id', 'timestamp', 'temperature', 'humidity', 'vocs', 
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
                    SELECT id, timestamp, temperature, humidity, vocs, 
                           nitrogen_dioxide, carbon_monoxide, pm25, pm10
                    FROM sensor_data
                    WHERE timestamp BETWEEN %s AND %s
                    ORDER BY timestamp DESC;
                """, (start_time, end_time))
                
                columns = ['id', 'timestamp', 'temperature', 'humidity', 'vocs', 
                           'nitrogen_dioxide', 'carbon_monoxide', 'pm25', 'pm10']
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
        except Exception as e:
            print(f"Error fetching sensor data by time range: {e}")
            return []

def update_sensor_data(record_id, temperature=None, humidity=None, vocs=None, 
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
                        vocs = %s,
                        nitrogen_dioxide = %s,
                        carbon_monoxide = %s,
                        pm25 = %s,
                        pm10 = %s
                    WHERE id = %s
                    RETURNING id, timestamp;
                """, (temperature, humidity, vocs, nitrogen_dioxide, carbon_monoxide, 
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
