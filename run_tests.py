#!/usr/bin/env python3
"""
Test runner for proxy-wars project
Runs all tests and provides clear output
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and print results"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*60)
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print("STDOUT:")
        print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Exit code: {result.returncode}")
    return result.returncode == 0

def main():
    """Main test runner"""
    print("Proxy Wars Test Suite")
    print("====================")
    
    # Change to project directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Install dependencies if needed
    print("\nInstalling dependencies...")
    run_command("pip install -r requirements.txt", "Installing requirements")
    
    all_passed = True
    
    # Run unit tests (these don't require servers)
    print("\n" + "="*60)
    print("UNIT TESTS (no servers required)")
    print("="*60)
    
    success = run_command("python -m pytest tests/test_classification_server.py -v", 
                         "Classification server unit tests")
    all_passed = all_passed and success
    
    success = run_command("python -m pytest tests/test_proxy.py::TestProxyBasics -v", 
                         "Proxy server unit tests")
    all_passed = all_passed and success
    
    # Integration tests (require servers)
    print("\n" + "="*60)
    print("INTEGRATION TESTS (require servers to be running)")
    print("="*60)
    print("NOTE: Start servers first:")
    print("Terminal 1: uvicorn classification_server:app --host 0.0.0.0 --port 8001")
    print("Terminal 2: uvicorn proxy:app --host 0.0.0.0 --port 8000")
    print("="*60)
    
    success = run_command("python -m pytest tests/test_integration.py -v", 
                         "Integration tests (requires running servers)")
    # Don't fail overall if integration tests fail (servers might not be running)
    if not success:
        print("Integration tests failed - make sure both servers are running!")
    
    success = run_command("python -m pytest tests/test_proxy.py::TestProxyIntegration -v", 
                         "Proxy integration tests (requires running servers)")
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    if all_passed:
        print("✅ All unit tests PASSED!")
    else:
        print("❌ Some unit tests FAILED!")
    
    print("\nTo run integration tests:")
    print("1. Start servers in separate terminals:")
    print("   Terminal 1: uvicorn classification_server:app --host 0.0.0.0 --port 8001 --reload")
    print("   Terminal 2: uvicorn proxy:app --host 0.0.0.0 --port 8000 --reload")
    print("2. Run: python -m pytest tests/test_integration.py -v")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main()) 