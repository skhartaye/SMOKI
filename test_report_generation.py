#!/usr/bin/env python3
"""
Test report generation to see what's happening
"""
import requests
import json

API_URL = 'https://smoki-backend-rpi.onrender.com'

def test_report_generation():
    """Test generating a report"""
    print("🧪 Testing Report Generation")
    print("=" * 40)
    
    try:
        # Test report generation
        print("📄 Generating report...")
        response = requests.post(
            f"{API_URL}/api/stream/generate-report",
            headers={'Content-Type': 'application/json'},
            json={'report_type': 'detection_snapshot'},
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Report generated successfully!")
            print(f"   Report ID: {result.get('report_id', 'N/A')}")
            print(f"   Success: {result.get('success', False)}")
            
            if result.get('success') and result.get('report_id'):
                report_id = result['report_id']
                
                # Test viewing the report
                print(f"\n👁️ Testing report viewing...")
                view_url = f"{API_URL}/api/stream/reports/{report_id}"
                print(f"View URL: {view_url}")
                
                view_response = requests.get(view_url, timeout=10)
                print(f"View Response Status: {view_response.status_code}")
                
                if view_response.status_code == 200:
                    html_content = view_response.text
                    print(f"✅ Report content received ({len(html_content)} characters)")
                    
                    # Check for email links in the content
                    if 'mailto:' in html_content:
                        print("❌ WARNING: Found mailto links in HTML content!")
                        # Find the mailto links
                        import re
                        mailto_links = re.findall(r'mailto:[^"\']*', html_content)
                        for link in mailto_links:
                            print(f"   Found: {link}")
                    else:
                        print("✅ No mailto links found in HTML content")
                    
                    # Check for Gmail links
                    if 'gmail.com' in html_content:
                        print("❌ WARNING: Found Gmail links in HTML content!")
                    else:
                        print("✅ No Gmail links found in HTML content")
                    
                    # Save a sample of the HTML to check
                    with open('test_report_sample.html', 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print("📄 Saved sample HTML to test_report_sample.html")
                    
                else:
                    print(f"❌ Failed to view report: {view_response.status_code}")
                    print(f"   Response: {view_response.text}")
                
                # Test download endpoint
                print(f"\n💾 Testing report download...")
                download_url = f"{API_URL}/api/stream/reports/{report_id}/download"
                print(f"Download URL: {download_url}")
                
                download_response = requests.get(download_url, timeout=10)
                print(f"Download Response Status: {download_response.status_code}")
                
                if download_response.status_code == 200:
                    print("✅ Download endpoint working")
                    
                    # Check headers
                    headers = download_response.headers
                    content_disposition = headers.get('Content-Disposition', '')
                    print(f"Content-Disposition: {content_disposition}")
                    
                    if 'attachment' in content_disposition:
                        print("✅ Proper download headers set")
                    else:
                        print("❌ Download headers not set properly")
                else:
                    print(f"❌ Download endpoint failed: {download_response.status_code}")
            
        else:
            print(f"❌ Report generation failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_report_generation()