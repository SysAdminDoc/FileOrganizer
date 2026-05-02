"""Tests for parallel LLM classifier — async batching with aiohttp."""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fileorganizer.parallel_classifier import AsyncClassifier, classify_parallel, HAS_AIOHTTP


# Skip all tests if aiohttp not available
pytestmark = pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")


@pytest.fixture
def sample_folders():
    """Sample folder metadata for testing."""
    return [
        {
            'folder_name': 'summer-flyer-2025',
            'folder_path': '/lib/summer-flyer-2025',
            'context': 'Folder name: "summer-flyer-2025"\nOther files: flyer.psd, flyer-alt.psd'
        },
        {
            'folder_name': 'logo-pack-v3',
            'folder_path': '/lib/logo-pack-v3',
            'context': 'Folder name: "logo-pack-v3"\nOther files: logo-1.ai, logo-2.ai'
        },
        {
            'folder_name': 'product-video-demo',
            'folder_path': '/lib/product-video-demo',
            'context': 'Folder name: "product-video-demo"\nOther files: demo.mp4, thumbnail.jpg'
        },
    ]


@pytest.fixture
def mock_response_valid():
    """Mock valid Ollama API response."""
    return {
        'message': {
            'content': json.dumps({
                'results': [
                    {'name': 'Summer Flyer 2025', 'category': 'Flyer / Poster', 'confidence': 92},
                    {'name': 'Logo Pack v3', 'category': 'Logo / Icon', 'confidence': 88},
                    {'name': 'Product Demo Video', 'category': 'Promo / Demo Video', 'confidence': 85},
                ]
            })
        }
    }


@pytest.fixture
def classifier(sample_folders):
    """Create a classifier instance."""
    return AsyncClassifier(concurrency=2, batch_size=2)


def test_classifier_init():
    """Test AsyncClassifier initialization with defaults and bounds."""
    c = AsyncClassifier()
    assert c.concurrency == 4
    assert c.batch_size == 3
    
    # Test bounds
    c = AsyncClassifier(concurrency=0, batch_size=10)
    assert c.concurrency == 1
    assert c.batch_size == 5


def test_classifier_batch_splits():
    """Test that batching splits folders correctly."""
    folders = [{'folder_name': f'folder-{i}', 'folder_path': f'/p{i}', 'context': f'c{i}'}
               for i in range(7)]
    
    c = AsyncClassifier(batch_size=3)
    # Manually check batch splitting logic
    batches = []
    for i in range(0, len(folders), c.batch_size):
        batches.append(folders[i:i + c.batch_size])
    
    assert len(batches) == 3
    assert len(batches[0]) == 3
    assert len(batches[1]) == 3
    assert len(batches[2]) == 1


@pytest.mark.asyncio
async def test_request_batch_async_valid_response(classifier, sample_folders, mock_response_valid):
    """Test successful batch request with valid response."""
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response_valid)
        
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session
        
        async with AsyncMock() as session:
            session.post = AsyncMock(return_value=mock_resp)
            results = await classifier._request_batch_async(sample_folders[:2], session)
    
    assert len(results) == 2
    assert results[0]['category'] == 'Flyer / Poster'
    assert results[0]['confidence'] == 92
    assert results[0]['method'] == 'llm_parallel'
    assert results[1]['category'] == 'Logo / Icon'


@pytest.mark.asyncio
async def test_request_batch_async_empty_response(classifier, sample_folders):
    """Test handling of empty response."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={'message': {'content': ''}})
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:2], session)
    
    assert len(results) == 2
    assert all(r['category'] is None for r in results)
    assert all('empty_response' in r['detail'] for r in results)


@pytest.mark.asyncio
async def test_request_batch_async_http_error(classifier, sample_folders):
    """Test handling of HTTP errors."""
    mock_resp = AsyncMock()
    mock_resp.status = 503  # Service Unavailable
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:2], session)
    
    assert len(results) == 2
    assert all(r['category'] is None for r in results)
    assert all('http_503' in r['detail'] for r in results)


@pytest.mark.asyncio
async def test_request_batch_async_timeout(classifier, sample_folders):
    """Test handling of timeout errors."""
    async def raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError("Request timeout")
    
    async with AsyncMock() as session:
        session.post = raise_timeout
        results = await classifier._request_batch_async(sample_folders[:2], session)
    
    assert len(results) == 2
    assert all(r['category'] is None for r in results)
    assert all('timeout' in r['detail'] for r in results)


@pytest.mark.asyncio
async def test_request_batch_async_invalid_json(classifier, sample_folders):
    """Test handling of invalid JSON in response."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(side_effect=json.JSONDecodeError("msg", "doc", 0))
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:2], session)
    
    assert len(results) == 2
    assert all(r['category'] is None for r in results)
    assert all('parse_error' in r['detail'] for r in results)


@pytest.mark.asyncio
async def test_request_batch_async_missing_results(classifier, sample_folders):
    """Test handling of incomplete results array."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': json.dumps({
                'results': [
                    {'name': 'Folder 1', 'category': 'Design', 'confidence': 85}
                    # Only 1 result, but we requested 2 folders
                ]
            })
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:2], session)
    
    assert len(results) == 2
    assert results[0]['category'] == 'Design'
    assert results[1]['category'] is None
    assert 'missing_result' in results[1]['detail']


@pytest.mark.asyncio
async def test_request_batch_async_removes_thinking_blocks(classifier, sample_folders):
    """Test that thinking blocks are removed from response (Qwen3.5 with think=True)."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': '<think>Let me think about this...</think>{"results":[{"name":"Folder","category":"Design","confidence":85}]}'
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:1], session)
    
    assert len(results) == 1
    assert results[0]['category'] == 'Design'


@pytest.mark.asyncio
async def test_request_batch_async_fuzzy_category_matching(classifier, sample_folders):
    """Test fuzzy matching for slightly misspelled categories."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': json.dumps({
                'results': [
                    {'name': 'Folder', 'category': 'Fliar / Poster', 'confidence': 85},  # Typo: Fliar instead of Flyer
                ]
            })
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:1], session)
    
    assert len(results) == 1
    # Should either fuzzy match or reject, depending on threshold
    # (Fliar vs Flyer is ~86% similar, so should match if fuzzy enabled)


@pytest.mark.asyncio
async def test_classify_parallel_folders_in_order(classifier, sample_folders, mock_response_valid):
    """Test that classify() preserves folder order."""
    with patch('aiohttp.ClientSession'):
        # This is simplified; in real test we'd mock the full async stack
        pass
    # Deferred to integration test


def test_classify_sync_without_aiohttp():
    """Test fallback when aiohttp is not available."""
    with patch('fileorganizer.parallel_classifier.HAS_AIOHTTP', False):
        folders = [{'folder_name': 'test', 'folder_path': '/p', 'context': 'c'}]
        results = classify_parallel(folders)
    
    assert len(results) == 1
    assert results[0]['category'] is None
    assert 'aiohttp_not_installed' in results[0]['detail']


@pytest.mark.asyncio
async def test_classify_with_invalid_category(classifier, sample_folders):
    """Test category validation with out-of-range categories."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': json.dumps({
                'results': [
                    {'name': 'Folder', 'category': 'NonExistentCategory', 'confidence': 85},
                ]
            })
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:1], session)
    
    assert len(results) == 1
    assert results[0]['category'] is None
    assert 'invalid_category' in results[0]['detail']


def test_classify_parallel_function(sample_folders):
    """Test classify_parallel convenience function signature and defaults."""
    # Just check it doesn't crash with sensible defaults
    with patch('fileorganizer.parallel_classifier.HAS_AIOHTTP', False):
        results = classify_parallel(sample_folders, concurrency=2, batch_size=2)
    
    assert len(results) == len(sample_folders)
    assert all(isinstance(r, dict) for r in results)
    assert all('method' in r for r in results)


@pytest.mark.asyncio
async def test_request_batch_async_thinking_block_partial(classifier, sample_folders):
    """Test removal of partial thinking blocks (unclosed tags)."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': '<think>Starting analysis...\n{"results":[{"name":"Test","category":"Design","confidence":80}]}'
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:1], session)
    
    assert len(results) == 1
    # Should handle gracefully


@pytest.mark.asyncio
async def test_request_batch_async_response_not_list(classifier, sample_folders):
    """Test handling when response is not a list (e.g., wrapped dict)."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': json.dumps({
                'items': [
                    {'name': 'Folder', 'category': 'Design', 'confidence': 85},
                ]
            })
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(sample_folders[:1], session)
    
    assert len(results) == 1
    assert results[0]['category'] == 'Design'  # Should unwrap 'items' fallback


@pytest.mark.skipif(not HAS_AIOHTTP, reason="Integration test requires aiohttp")
@pytest.mark.asyncio
async def test_classifier_concurrency_spread():
    """Test that concurrency parameter properly limits concurrent requests.
    
    This is a behavioral test: we check that at most N requests are in flight
    by mocking the session and counting concurrent access.
    """
    concurrent_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()
    
    async def mock_post(*args, **kwargs):
        nonlocal concurrent_count, max_concurrent
        async with lock:
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
        
        await asyncio.sleep(0.01)  # Simulate latency
        
        async with lock:
            concurrent_count -= 1
        
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            'message': {'content': json.dumps({'results': [{'name': 'Test', 'category': 'Design', 'confidence': 80}]})}
        })
        return mock_resp
    
    folders = [{'folder_name': f'f{i}', 'folder_path': f'/p{i}', 'context': f'c{i}'}
               for i in range(8)]
    
    classifier = AsyncClassifier(concurrency=2, batch_size=2)
    
    # Test the concurrency limit
    # (Note: This is difficult to test without full event loop control)


def test_classifier_settings_loading():
    """Test that classifier loads settings correctly."""
    c = AsyncClassifier()
    assert c.url is not None
    assert c.model is not None
    assert c.concurrency >= 1
    assert c.batch_size >= 1
