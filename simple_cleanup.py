#!/usr/bin/env python3
"""
Simple cleanup script for SMOKi database
Removes UNREAD license plates and test data
"""
import psycopg
import os
from datetime import datetime

# Database configuration from backend/.env
DB_CONFIG = {
    'host': 'dpg-d5mc48fgi27c739ffhcg-a.oregon-postgres.render.com',
    'database': 'smoki_db',
    'user': 'smoki_db_user',
    'password': 'HwlPtCgq1vW9KI45aHRuD1sbNwA03kFT',
    'port': 5432
}

def get_connection_string():
    """Get database connection string"""
    return f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

def simple_cleanup():
    """Simple cleanup focusing on UNREAD plates and test data"""
    try:
        print("🧹 SMOKi Simple Cleanup")
        print("=" * 40)
        
        # Connect to database
        with psycopg.connect(get_connection_string()) as conn:
            with conn.cursor() as cursor:
                print("🔗 Connected to database")
                
                # Check current vehicles with UNREAD plates
                print("\n📊 Checking UNREAD vehicles...")
                cursor.execute("SELECT COUNT(*) FROM vehicles WHERE license_plate LIKE 'UNREAD%'")
                unread_count = cursor.fetchone()[0]
                print(f"   Found {unread_count} UNREAD vehicles")
                
                if unread_count > 0:
                    # Show some examples
                    cursor.execute("SELECT license_plate, vehicle_type, total_violations FROM vehicles WHERE license_plate LIKE 'UNREAD%' LIMIT 5")
                    examples = cursor.fetchall()
                    print("   Examples:")
                    for plate, vtype, violations in examples:
                        print(f"     - {plate} ({vtype}) - {violations} violations")
                
                # Check violations
                cursor.execute("SELECT COUNT(*) FROM violations")
                violations_count = cursor.fetchone()[0]
                print(f"   Total violations: {violations_count}")
                
                # Check vehicle_detections
                cursor.execute("SELECT COUNT(*) FROM vehicle_detections")
                detections_count = cursor.fetchone()[0]
                print(f"   Total vehicle detections: {detections_count}")
                
                if unread_count == 0:
                    print("\n✅ No UNREAD vehicles found - database is clean!")
                    return
                
                print(f"\n⚠️  This will delete:")
                print(f"   - {unread_count} UNREAD vehicles")
                print(f"   - Associated violations and detections")
                
                confirm = input("\nProceed with cleanup? (y/N): ").lower().strip()
                
                if confirm != 'y':
                    print("❌ Cleanup cancelled")
                    return
                
                print("\n🔥 Cleaning up UNREAD data...")
                
                # Delete in proper order to respect foreign key constraints
                
                # 1. Delete vehicle_detections for UNREAD vehicles
                cursor.execute("""
                    DELETE FROM vehicle_detections 
                    WHERE vehicle_id IN (
                        SELECT id FROM vehicles WHERE license_plate LIKE 'UNREAD%'
                    )
                """)
                deleted_detections = cursor.rowcount
                print(f"   Deleted {deleted_detections} vehicle detections")
                
                # 2. Delete violations for UNREAD vehicles  
                cursor.execute("""
                    DELETE FROM violations 
                    WHERE vehicle_id IN (
                        SELECT id FROM vehicles WHERE license_plate LIKE 'UNREAD%'
                    )
                """)
                deleted_violations = cursor.rowcount
                print(f"   Deleted {deleted_violations} violations")
                
                # 3. Delete UNREAD vehicles
                cursor.execute("DELETE FROM vehicles WHERE license_plate LIKE 'UNREAD%'")
                deleted_vehicles = cursor.rowcount
                print(f"   Deleted {deleted_vehicles} UNREAD vehicles")
                
                # 4. Also clean up any test/laptop data
                cursor.execute("""
                    DELETE FROM vehicle_detections 
                    WHERE metadata::text LIKE '%laptop%' 
                    OR metadata::text LIKE '%test%'
                    OR location LIKE '%laptop%'
                    OR location LIKE '%test%'
                """)
                deleted_test_detections = cursor.rowcount
                print(f"   Deleted {deleted_test_detections} test detections")
                
                # Commit all changes
                conn.commit()
                
                print(f"\n✅ Cleanup completed successfully!")
                print(f"📊 Summary:")
                print(f"   - UNREAD vehicles: {deleted_vehicles}")
                print(f"   - Violations: {deleted_violations}")
                print(f"   - Vehicle detections: {deleted_detections}")
                print(f"   - Test detections: {deleted_test_detections}")
                
                # Show final counts
                print("\n📊 Final counts:")
                cursor.execute("SELECT COUNT(*) FROM vehicles")
                final_vehicles = cursor.fetchone()[0]
                print(f"   Vehicles: {final_vehicles}")
                
                cursor.execute("SELECT COUNT(*) FROM violations")
                final_violations = cursor.fetchone()[0]
                print(f"   Violations: {final_violations}")
                
                cursor.execute("SELECT COUNT(*) FROM vehicle_detections")
                final_detections = cursor.fetchone()[0]
                print(f"   Vehicle detections: {final_detections}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    simple_cleanup()