#!/usr/bin/env python3
"""
Create test violations to populate the vehicle ranking
"""
import sys
import os
sys.path.append('postgre')

from database import register_vehicle, create_violation, approve_violation

def create_test_violations():
    """Create some test violations for vehicle ranking"""
    print("🧪 Creating Test Violations for Vehicle Ranking")
    print("=" * 50)
    
    # Test vehicles with different violation counts
    test_vehicles = [
        {"plate": "ABC123", "type": "passenger", "violations": 3},
        {"plate": "XYZ789", "type": "puv", "violations": 5},
        {"plate": "DEF456", "type": "two_wheel", "violations": 2},
        {"plate": "GHI789", "type": "services", "violations": 1},
        {"plate": "JKL012", "type": "passenger", "violations": 4},
    ]
    
    for vehicle_data in test_vehicles:
        print(f"\n📋 Creating violations for {vehicle_data['plate']} ({vehicle_data['type']})")
        
        # Register the vehicle
        vehicle = register_vehicle(vehicle_data['plate'], vehicle_data['type'])
        if not vehicle:
            print(f"❌ Failed to register vehicle {vehicle_data['plate']}")
            continue
            
        print(f"✅ Registered vehicle ID: {vehicle['id']}")
        
        # Create violations
        for i in range(vehicle_data['violations']):
            violation = create_violation(
                vehicle_id=vehicle['id'],
                detection_id=None,
                violation_type="smoke_emission",
                severity="warning" if i % 2 == 0 else "critical",
                description=f"Test smoke emission violation #{i+1} for {vehicle_data['plate']}",
                auto_approve=False  # Create as pending
            )
            
            if violation:
                print(f"  ✅ Created violation ID: {violation['id']}")
                
                # Approve the violation to make it count in ranking
                approval_result = approve_violation(violation['id'])
                if approval_result:
                    print(f"  ✅ Approved violation ID: {violation['id']}")
                else:
                    print(f"  ❌ Failed to approve violation ID: {violation['id']}")
            else:
                print(f"  ❌ Failed to create violation #{i+1}")
    
    print(f"\n🎉 Test violations created! Check the vehicle ranking now.")

if __name__ == "__main__":
    create_test_violations()