#!/usr/bin/env python3
"""
Check current database state
"""
import psycopg

DB_CONFIG = {
    'host': 'dpg-d5mc48fgi27c739ffhcg-a.oregon-postgres.render.com',
    'database': 'smoki_db',
    'user': 'smoki_db_user',
    'password': 'HwlPtCgq1vW9KI45aHRuD1sbNwA03kFT',
    'port': 5432
}

def get_connection_string():
    return f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

def check_database():
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cursor:
            # Check UNREAD vehicles
            cursor.execute("SELECT COUNT(*) FROM vehicles WHERE license_plate LIKE 'UNREAD%'")
            unread_count = cursor.fetchone()[0]
            print(f"UNREAD vehicles: {unread_count}")
            
            # Check total violations
            cursor.execute("SELECT COUNT(*) FROM violations")
            violations_count = cursor.fetchone()[0]
            print(f"Total violations: {violations_count}")
            
            # Check recent vehicles
            cursor.execute("SELECT license_plate, vehicle_type, total_violations FROM vehicles ORDER BY created_at DESC LIMIT 5")
            recent = cursor.fetchall()
            print("Recent vehicles:")
            for plate, vtype, violations in recent:
                print(f"  {plate} ({vtype}) - {violations} violations")
            
            # Check recent violations
            cursor.execute("""
                SELECT v.id, veh.license_plate, v.violation_type, v.status, v.created_at 
                FROM violations v 
                JOIN vehicles veh ON v.vehicle_id = veh.id 
                ORDER BY v.created_at DESC LIMIT 5
            """)
            recent_violations = cursor.fetchall()
            print("Recent violations:")
            for vid, plate, vtype, status, created in recent_violations:
                print(f"  {vid}: {plate} ({vtype}) - {status} - {created}")

if __name__ == "__main__":
    check_database()