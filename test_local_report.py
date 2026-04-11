#!/usr/bin/env python3
"""
Test report generation locally
"""
import sys
import os
sys.path.append('backend')

from report_generator import SMOKiReportGenerator

def test_local_report_generation():
    """Test generating a report locally"""
    print("🧪 Testing Local Report Generation")
    print("=" * 40)
    
    try:
        # Initialize report generator
        generator = SMOKiReportGenerator()
        
        # Generate report
        result = generator.generate_report("detection_snapshot")
        
        if result['success']:
            print(f"✅ Report generated successfully!")
            print(f"   Report ID: {result.get('report_id', 'N/A')}")
            print(f"   Report Path: {result.get('report_path', 'N/A')}")
            
            # Check if file exists
            report_path = result.get('report_path')
            if report_path and os.path.exists(report_path):
                print(f"✅ Report file exists: {report_path}")
                
                # Read and check content
                with open(report_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                print(f"📄 Report size: {len(content)} characters")
                
                # Check for email links
                if 'mailto:' in content:
                    print("❌ WARNING: Found mailto links in HTML content!")
                    import re
                    mailto_links = re.findall(r'mailto:[^"\']*', content)
                    for link in mailto_links:
                        print(f"   Found: {link}")
                else:
                    print("✅ No mailto links found in HTML content")
                
                # Check for Gmail links
                if 'gmail.com' in content:
                    print("❌ WARNING: Found Gmail links in HTML content!")
                else:
                    print("✅ No Gmail links found in HTML content")
                
                # Check for action buttons
                if 'action-buttons' in content:
                    print("✅ Action buttons found in HTML")
                else:
                    print("❌ No action buttons found")
                
                print(f"📁 Report saved to: {report_path}")
                
            else:
                print(f"❌ Report file not found: {report_path}")
        else:
            print(f"❌ Report generation failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_local_report_generation()