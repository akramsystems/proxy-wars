"""
Test suite for classification_server.py
"""
import pytest
import httpx
import asyncio
from fastapi.testclient import TestClient
from classification_server import app

client = TestClient(app)

def test_classify_single_sequence():
    """Test classification with a single sequence"""
    response = client.post("/classify", json={"sequences": ["def foo(): pass"]})
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0] == "code"

def test_classify_multiple_sequences():
    """Test classification with multiple sequences"""
    sequences = ["def foo(): pass", "hello world", "class Bar:", "just text", "{code}"]
    response = client.post("/classify", json={"sequences": sequences})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 5
    expected = ["code", "not code", "code", "not code", "code"]
    assert data["results"] == expected

def test_classify_empty_list():
    """Test classification with empty sequences list - should return 400"""
    response = client.post("/classify", json={"sequences": []})
    assert response.status_code == 400
    assert "Need 1 - 5 sequences" in response.text

def test_classify_too_many_sequences():
    """Test classification with too many sequences - should return 400"""
    sequences = ["text"] * 6  # More than 5
    response = client.post("/classify", json={"sequences": sequences})
    assert response.status_code == 400
    assert "Need 1 - 5 sequences" in response.text

def test_code_detection():
    """Test the code detection logic"""
    from classification_server import _is_code
    
    # Should be detected as code
    assert _is_code("def function(): pass")
    assert _is_code("class MyClass:")
    assert _is_code("if True { print('hello'); }")
    assert _is_code("let obj = {key: value};")
    
    # Should not be detected as code
    assert not _is_code("hello world")
    assert not _is_code("just some text")
    assert not _is_code("no special tokens here")

def test_invalid_request_format():
    """Test with invalid request format"""
    response = client.post("/classify", json={"wrong_field": ["test"]})
    assert response.status_code == 422  # Validation error

def test_latency_simulation():
    """Test that longer sequences take more time (basic timing test)"""
    import time
    
    # Short sequence
    start = time.time()
    response = client.post("/classify", json={"sequences": ["hi"]})
    short_time = time.time() - start
    assert response.status_code == 200
    
    # Long sequence
    long_text = "x" * 100
    start = time.time()
    response = client.post("/classify", json={"sequences": [long_text]})
    long_time = time.time() - start
    assert response.status_code == 200
    
    # Longer sequence should take more time
    assert long_time > short_time

if __name__ == "__main__":
    pytest.main([__file__]) 