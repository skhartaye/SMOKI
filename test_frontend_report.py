#!/usr/bin/env python3
"""
Test the frontend report workflow
"""
import requests
import json

API_URL = 'https://smoki-backend-rpi.onrender.com'

def test_frontend_report_workflow():
    """Test the complete frontend report workflow"""
    print("🧪 Testing Frontend Report Workflow")
    print("=" * 40)
    
    try:
        # Step 1: Generate report (what frontend does)
        print("📄 Step 1: Generating report...")
        response = requests.post(
            f"{API_URL}/api/stream/generate-report",
            headers={'Content-Type': 'application/json'},
            json={'report_type': 'detection_snapshot'},
            timeout=30
        )
        
        print(f"Generate Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Report generated successfully!")
            print(f"   Report ID: {result.get('report_id', 'N/A')}")
            
            if result.get('success') and result.get('report_id'):
                report_id = result['report_id']
                
                # Step 2: Download report (what frontend should do instead of viewing)
                print(f"\n💾 Step 2: Downloading report for user...")
                download_url = f"{API_URL}/api/stream/reports/{report_id}/download"
                print(f"Download URL: {download_url}")
                
                download_response = requests.get(download_url, timeout=10)
                print(f"Download Response Status: {download_response.status_code}")
                
                if download_response.status_code == 200:
                    html_content = download_response.text
                    print(f"✅ Report downloaded successfully ({len(html_content)} characters)")
                    
                    # Check for email links in the downloaded content
                    if 'mailto:' in html_content:
                        print("❌ WARNING: Found mailto links in downloaded HTML!")
                        import re
                        mailto_links = re.findall(r'mailto:[^"\']*', html_content)
                        for link in mailto_links:
                            print(f"   Found: {link}")
                    else:
                        print("✅ No mailto links found in downloaded HTML")
                    
                    # Check for Gmail links
                    if 'gmail.com' in html_content:
                        print("❌ WARNING: Found Gmail links in downloaded HTML!")
                    else:
                        print("✅ No Gmail links found in downloaded HTML")
                    
                    # Check for action buttons
                    if 'action-buttons' in html_content:
                        print("✅ Action buttons found in HTML")
                    else:
                        print("❌ No action buttons found")
                    
                    # Save the downloaded report locally for testing
                    local_filename = f"downloaded_report_{report_id}.html"
                    with open(local_filename, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print(f"📁 Report saved locally as: {local_filename}")
                    
                    # Check headers
                    headers = download_response.headers
                    content_disposition = headers.get('Content-Disposition', '')
                    print(f"Content-Disposition: {content_disposition}")
                    
                    if 'attachment' in content_disposition:
                        print("✅ Proper download headers - will trigger browser download")
                    else:
                        print("❌ Download headers not set properly")
                    
                    print("\n🎉 Frontend workflow test completed successfully!")
                    print("   The frontend should:")
                    print("   1. Call /api/stream/generate-report")
                    print("   2. Show success message with report details")
                    print("   3. Provide download button that calls /api/stream/reports/{id}/download")
                    print("   4. Browser will automatically download the HTML file")
                    
                else:
                    print(f"❌ Download failed: {download_response.status_code}")
                    print(f"   Response: {download_response.text}")
            
        else:
            print(f"❌ Report generation failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_frontend_report_workflow()