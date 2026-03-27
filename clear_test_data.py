#!/usr/bin/env python3
"""
Clear test detection data from database
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('postgre/.env')

sys.path.insert(0, 'postgre')

from database import get_connection_string
import psycopg
import json

def clear_test_detections():
    """Clear test detection data from the database"""
    print("🧹 Clearing Test Detection Data")
    print("=" * 40)
    
    try:
        print(f"Connecting to database...")
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                # First, let's see what tables exist
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                tables = cursor.fetchall()
                print(f"📋 Available tables: {[t[0] for t in tables]}")
                
                # Clear vehicle_detections with test data
                cursor.execute("""
                    DELETE FROM vehicle_detections 
                    WHERE location IN ('Test_Location', 'Main Camera')
                    OR metadata::text LIKE '%test%'
                    OR metadata::text LIKE '%fake%'
                """)
                deleted_vehicle_detections = cursor.rowcount
                print(f"🗑️  Deleted {deleted_vehicle_detections} test vehicle detections")
                
                # Clear violations associated with test data
                cursor.execute("""
                    DELETE FROM violations 
                    WHERE description LIKE '%test%'
                    OR description LIKE '%fake%'
                """)
                deleted_violations = cursor.rowcount
                print(f"🗑️  Deleted {deleted_violations} test violations")
                
                # Clear test vehicles
                cursor.execute("""
                    DELETE FROM vehicles 
                    WHERE license_plate LIKE 'ABC-%'
                    OR license_plate LIKE 'PUV-%'
                    OR license_plate LIKE 'SVC-%'
                    OR license_plate LIKE 'MC-%'
                    OR license_plate LIKE 'VEH-%'
                    OR license_plate LIKE 'NCR-%'
                    OR license_plate LIKE 'UVW-%'
                """)
                deleted_vehicles = cursor.rowcount
                print(f"🗑️  Deleted {deleted_vehicles} test vehicles")
                
                # Clear test images
                cursor.execute("""
                    DELETE FROM images 
                    WHERE timestamp < NOW() - INTERVAL '1 day'
                """)
                deleted_images = cursor.rowcount
                print(f"🗑️  Deleted {deleted_images} old images")
                
                conn.commit()
                print(f"\n✅ Successfully cleared all test data!")
                return True
                
    except Exception as e:
        print(f"❌ Error clearing test data: {e}")
        return False

if __name__ == '__main__':
    clear_test_detections()