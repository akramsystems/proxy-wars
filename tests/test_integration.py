"""
Integration tests for the complete proxy + classification system
Run these tests with both servers running
"""
import pytest
import requests
import time
import threading
import subprocess
import signal
import os
from contextlib import contextmanager

CLASSIFICATION_URL = "http://localhost:8001/classify"
PROXY_URL = "http://localhost:8000/proxy_classify"
STRATEGY_URL = "http://localhost:8000/strategy"

def test_servers_are_running():
    """Verify both servers are accessible"""
    try:
        # Test classification server
        response = requests.get("http://localhost:8001/docs", timeout=2)
        assert response.status_code == 200, "Classification server not running on port 8001"
        
        # Test proxy server
        response = requests.get("http://localhost:8000/docs", timeout=2)
        assert response.status_code == 200, "Proxy server not running on port 8000"
        
    except requests.exceptions.ConnectionError as e:
        pytest.skip(f"Servers not running: {e}")

def test_classification_server_direct():
    """Test classification server directly"""
    try:
        response = requests.post(
            CLASSIFICATION_URL,
            json={"sequences": ["def foo(): pass", "hello world"]},
            timeout=5
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0] == "code"
        assert data["results"][1] == "not code"
    except requests.exceptions.ConnectionError:
        pytest.skip("Classification server not running")

def test_proxy_server_end_to_end():
    """Test proxy server end-to-end"""
    try:
        response = requests.post(
            PROXY_URL,
            json={"sequences": ["def foo(): pass", "hello world"]},
            headers={"X-Customer-Id": "A"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "proxy_latency_ms" in data
        assert len(data["results"]) == 2
        assert isinstance(data["proxy_latency_ms"], int)
        assert data["proxy_latency_ms"] >= 0
    except requests.exceptions.ConnectionError:
        pytest.skip("Servers not running")

def test_proxy_batching_behavior():
    """Test that proxy properly batches requests"""
    try:
        # Send requests with different customer IDs
        sequences_a = ["def test_a()"]
        sequences_b = ["hello from B"]
        
        response_a = requests.post(
            PROXY_URL,
            json={"sequences": sequences_a},
            headers={"X-Customer-Id": "A"},
            timeout=10
        )
        
        response_b = requests.post(
            PROXY_URL,
            json={"sequences": sequences_b},
            headers={"X-Customer-Id": "B"},
            timeout=10
        )
        
        assert response_a.status_code == 200
        assert response_b.status_code == 200
        
        data_a = response_a.json()
        data_b = response_b.json()
        
        assert data_a["results"][0] == "code"
        assert data_b["results"][0] == "not code"
        
    except requests.exceptions.ConnectionError:
        pytest.skip("Servers not running")

def test_strategy_switching():
    """Test switching between different strategies"""
    try:
        strategies = ["sjf", "fair", "fcfs"]
        
        for strategy in strategies:
            # Change strategy - use query parameter format
            response = requests.post(
                f"{STRATEGY_URL}?new_strategy={strategy}",
                timeout=5
            )
            assert response.status_code == 200
            data = response.json()
            assert data["active_strategy"] == strategy
            
            # Test a request with this strategy
            response = requests.post(
                PROXY_URL,
                json={"sequences": ["test"]},
                headers={"X-Customer-Id": "A"},
                timeout=10
            )
            assert response.status_code == 200
            
    except requests.exceptions.ConnectionError:
        pytest.skip("Servers not running")

def test_concurrent_requests():
    """Test multiple concurrent requests to proxy"""
    try:
        import concurrent.futures
        import threading
        
        def make_request(customer_id, sequence):
            response = requests.post(
                PROXY_URL,
                json={"sequences": [sequence]},
                headers={"X-Customer-Id": customer_id},
                timeout=15
            )
            return response.status_code, response.json() if response.status_code == 200 else None
        
        # Create multiple concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i in range(8):
                customer = "A" if i % 2 == 0 else "B"
                sequence = f"def test_{i}(): pass" if i % 3 == 0 else f"hello {i}"
                futures.append(executor.submit(make_request, customer, sequence))
            
            results = [future.result() for future in futures]
        
        # All requests should succeed
        for status_code, data in results:
            assert status_code == 200
            assert data is not None
            assert "results" in data
            assert "proxy_latency_ms" in data
            
    except requests.exceptions.ConnectionError:
        pytest.skip("Servers not running")

def test_error_handling():
    """Test proxy error handling"""
    try:
        # Test with too many sequences (should be handled by proxy)
        response = requests.post(
            PROXY_URL,
            json={"sequences": ["test"] * 6},  # More than MAX_BATCH
            headers={"X-Customer-Id": "A"},
            timeout=5
        )
        assert response.status_code == 400
        assert "Need 1–5 sequences" in response.text
        
    except requests.exceptions.ConnectionError:
        pytest.skip("Servers not running")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"]) 