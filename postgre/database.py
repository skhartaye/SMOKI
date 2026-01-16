import psycopg2
from psycopg2 import pool
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection pool
connection_pool = None

def init_db_pool():
    """Initialize database connection pool"""
    global connection_pool
    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'smoki_db'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'password'),
            port=os.getenv('DB_PORT', '5432')
        )
        print("Database connection pool created successfully")
        create_tables()
    except Exception as e:
        print(f"Error creating connection pool: {e}")

def get_connection():
    """Get a connection from the pool"""
    return connection_pool.getconn()

def release_connection(conn):
    """Release connection back to the pool"""
    connection_pool.putconn(conn)

def create_tables():
    """Create necessary tables if they don't exist"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Create sensor_data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                temperature FLOAT,
                humidity FLOAT,
                vocs FLOAT,
                nitrogen_dioxide FLOAT,
                carbon_monoxide FLOAT,
                pm25 FLOAT,
                pm10 FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create index on timestamp for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
            ON sensor_data(timestamp);
        """)
        
        conn.commit()
        print("Tables created successfully")
    except Exception as e:
        print(f"Error creating tables: {e}")
        conn.rollback()
    finally:
        cursor.close()
        release_connection(conn)

def insert_sensor_data(temperature=None, humidity=None, vocs=None, 
                       nitrogen_dioxide=None, carbon_monoxide=None, 
                       pm25=None, pm10=None):
    """Insert sensor data into database"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
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
    finally:
        cursor.close()
        release_connection(conn)

def get_latest_sensor_data(limit=10):
    """Get latest sensor readings"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
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
    finally:
        cursor.close()
        release_connection(conn)

def get_sensor_data_by_timerange(start_time, end_time):
    """Get sensor data within a time range"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
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
    finally:
        cursor.close()
        release_connection(conn)

def close_db_pool():
    """Close all database connections"""
    if connection_pool:
        connection_pool.closeall()
        print("Database connection pool closed")
