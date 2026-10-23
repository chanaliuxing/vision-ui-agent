#!/usr/bin/env python3
"""
Complete YOLO+LLM+Chrome Extension Workflow Test
Tests the entire vision-first automation stack for xiaohongshu.com
"""

import subprocess
import sys
import time
import json
import os
from pathlib import Path

# Configuration
WORKFLOW_PATH = "./flows/xhs_lulu_girl_complete.json"
VISION_API_ENDPOINT = "http://127.0.0.1:8000"
CHROME_EXTENSION_READY = True

def check_services():
    """Check if all required services are running"""
    print("🔍 Checking service availability...")
    
    services = [
        ("Vision API", "http://127.0.0.1:8000/health"),
        ("Backend API", "http://127.0.0.1:8787/health"),
        ("Orchestrator", "http://127.0.0.1:8788/health")
    ]
    
    for name, url in services:
        try:
            result = subprocess.run([
                "curl", "-s", "-f", url
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                print(f"✅ {name} is healthy")
            else:
                print(f"❌ {name} is not responding")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"❌ {name} timeout")
            return False
        except Exception as e:
            print(f"❌ {name} error: {e}")
            return False
    
    return True

def run_workflow():
    """Execute the complete workflow using the main workflow runner"""
    print("🚀 Starting YOLO+LLM+Chrome Extension workflow...")
    
    # Use the main workflow runner from the parent directory
    cmd = [
        "python", "../run_workflow.py",
        "--workflow", WORKFLOW_PATH,
        "--endpoint", VISION_API_ENDPOINT,
        "--provider", "gemini",
        "--model", "gemini-1.5-flash",
        "--verbose"
    ]
    
    print(f"📝 Command: {' '.join(cmd)}")
    print("⏳ Executing workflow (this may take 2-3 minutes)...")
    
    try:
        # Run the workflow
        result = subprocess.run(cmd, cwd="./getcontent", 
                              capture_output=True, text=True, timeout=300)
        
        print("📊 Workflow execution completed!")
        print(f"📤 Return code: {result.returncode}")
        
        if result.stdout:
            print("📝 STDOUT:")
            print(result.stdout)
            
        if result.stderr:
            print("⚠️  STDERR:")  
            print(result.stderr)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("⏰ Workflow execution timed out (5 minutes)")
        return False
    except Exception as e:
        print(f"💥 Workflow execution failed: {e}")
        return False

def verify_artifacts():
    """Verify that expected artifacts were created"""
    print("🔎 Verifying generated artifacts...")
    
    expected_files = [
        "out/screens/overlay.png",
        "out/logs/yolo.json", 
        "out/reports/report.html",
        "xhs/lulu_girl_third_creator_info.txt",
        "xhs/lulu_girl_creator_data.json"
    ]
    
    found_files = []
    missing_files = []
    
    for file_path in expected_files:
        full_path = Path(file_path)
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"✅ {file_path} ({size} bytes)")
            found_files.append(file_path)
        else:
            print(f"❌ {file_path} (missing)")
            missing_files.append(file_path)
    
    # Check for any files in xhs/ directory
    xhs_dir = Path("xhs")
    if xhs_dir.exists():
        print(f"📁 Files in xhs/ directory:")
        for file in xhs_dir.iterdir():
            if file.is_file():
                print(f"   📄 {file.name} ({file.stat().st_size} bytes)")
    
    return len(found_files), len(missing_files)

def show_results():
    """Display key results from the workflow execution"""
    print("📋 Workflow Results Summary:")
    
    # Check for creator info file
    creator_file = Path("xhs/lulu_girl_third_creator_info.txt")
    if creator_file.exists():
        print("👤 Creator Information Found:")
        content = creator_file.read_text()
        print(content[:500] + "..." if len(content) > 500 else content)
    
    # Check for JSON data
    json_file = Path("xhs/lulu_girl_creator_data.json")  
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text())
            print("📊 Structured Data:")
            if "creator_name" in data:
                print(f"   Creator Name: {data['creator_name']}")
            if "profile_url" in data:
                print(f"   Profile URL: {data['profile_url']}")
        except Exception as e:
            print(f"⚠️  Could not parse JSON: {e}")
    
    # Check YOLO results
    yolo_file = Path("out/logs/yolo.json")
    if yolo_file.exists():
        try:
            yolo_data = json.loads(yolo_file.read_text())
            if "detections" in yolo_data:
                detection_count = len(yolo_data["detections"])
                print(f"🎯 YOLO Detections: {detection_count} objects detected")
        except Exception as e:
            print(f"⚠️  Could not parse YOLO data: {e}")

def main():
    print("🧪 YOLO+LLM+Chrome Extension Complete Workflow Test")
    print("=" * 60)
    
    # Step 1: Check services
    if not check_services():
        print("❌ Required services are not running. Please start:")
        print("   - uvicorn app:app --port 8000 (YOLO Vision API)")
        print("   - Backend services")
        print("   - Chrome extension")
        sys.exit(1)
    
    # Step 2: Confirm Chrome extension is ready
    if CHROME_EXTENSION_READY:
        print("✅ Chrome extension is ready")
    else:
        print("⚠️  Make sure Chrome extension is loaded and daemon is started")
        response = input("Press Enter when ready, or 'q' to quit: ")
        if response.lower() == 'q':
            sys.exit(0)
    
    # Step 3: Run the workflow
    success = run_workflow()
    
    # Step 4: Verify artifacts
    found_count, missing_count = verify_artifacts()
    
    # Step 5: Show results
    show_results()
    
    # Final summary
    print("\n" + "=" * 60)
    if success:
        print("🎉 Workflow Test COMPLETED")
        print(f"📁 Artifacts: {found_count} found, {missing_count} missing")
        
        if missing_count == 0:
            print("✅ All expected artifacts were generated!")
        else:
            print("⚠️  Some artifacts are missing, but workflow completed")
    else:
        print("❌ Workflow Test FAILED")
        print("Check the logs above for error details")
    
    print("🔚 Test finished")

if __name__ == "__main__":
    main()