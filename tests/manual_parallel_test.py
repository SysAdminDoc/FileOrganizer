"""Manual integration test for parallel LLM classifier — no pytest required."""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from fileorganizer.parallel_classifier import AsyncClassifier


async def test_parallel_classifier_basic():
    """Test basic async classification."""
    print("Test 1: Basic AsyncClassifier initialization")
    classifier = AsyncClassifier(concurrency=2, batch_size=2)
    assert classifier.concurrency == 2
    assert classifier.batch_size == 2
    assert classifier.model is not None
    print(f"  ✓ Created classifier: concurrency={classifier.concurrency}, batch_size={classifier.batch_size}")


async def test_batch_request():
    """Test batch request with mocked response."""
    print("\nTest 2: Mock batch request")
    classifier = AsyncClassifier(concurrency=2, batch_size=2)
    
    folders = [
        {
            'folder_name': 'summer-flyer',
            'folder_path': '/lib/summer-flyer',
            'context': 'Folder: summer-flyer\nFiles: flyer.psd'
        },
        {
            'folder_name': 'logo-pack',
            'folder_path': '/lib/logo-pack',
            'context': 'Folder: logo-pack\nFiles: logo.ai'
        }
    ]
    
    # Mock async session
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': json.dumps({
                'results': [
                    {'name': 'Summer Flyer 2025', 'category': 'Flyer / Poster', 'confidence': 92},
                    {'name': 'Logo Pack', 'category': 'Logo / Icon', 'confidence': 88}
                ]
            })
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(folders, session)
    
    assert len(results) == 2
    assert results[0]['category'] == 'Flyer / Poster'
    assert results[1]['category'] == 'Logo / Icon'
    assert all(r['method'] == 'llm_parallel' for r in results)
    print(f"  ✓ Batch request returned {len(results)} results")
    print(f"    - Result 0: {results[0]['name']} → {results[0]['category']} ({results[0]['confidence']}%)")
    print(f"    - Result 1: {results[1]['name']} → {results[1]['category']} ({results[1]['confidence']}%)")


async def test_error_handling():
    """Test error handling for failed requests."""
    print("\nTest 3: Error handling")
    classifier = AsyncClassifier(concurrency=2, batch_size=2)
    
    folders = [
        {'folder_name': 'test', 'folder_path': '/p', 'context': 'test'}
    ]
    
    # Test HTTP error
    mock_resp = AsyncMock()
    mock_resp.status = 503
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(folders, session)
    
    assert len(results) == 1
    assert results[0]['category'] is None
    assert 'http_503' in results[0]['detail']
    print(f"  ✓ HTTP error handled: {results[0]['detail']}")
    
    # Test timeout
    async def raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError("Request timeout")
    
    async with AsyncMock() as session:
        session.post = raise_timeout
        results = await classifier._request_batch_async(folders, session)
    
    assert results[0]['category'] is None
    assert 'timeout' in results[0]['detail']
    print(f"  ✓ Timeout handled: {results[0]['detail']}")


async def test_empty_response():
    """Test handling of empty response."""
    print("\nTest 4: Empty response handling")
    classifier = AsyncClassifier(concurrency=2, batch_size=2)
    
    folders = [
        {'folder_name': 'test', 'folder_path': '/p', 'context': 'test'}
    ]
    
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={'message': {'content': ''}})
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(folders, session)
    
    assert results[0]['category'] is None
    assert 'empty_response' in results[0]['detail']
    print(f"  ✓ Empty response handled: {results[0]['detail']}")


async def test_batch_split_logic():
    """Test folder batching logic."""
    print("\nTest 5: Batch splitting")
    
    folders = [{'folder_name': f'f{i}', 'folder_path': f'/p{i}', 'context': f'c{i}'}
               for i in range(7)]
    
    # Simulate batching with batch_size=3
    classifier = AsyncClassifier(batch_size=3)
    batches = []
    for i in range(0, len(folders), classifier.batch_size):
        batches.append(folders[i:i + classifier.batch_size])
    
    assert len(batches) == 3
    assert len(batches[0]) == 3
    assert len(batches[1]) == 3
    assert len(batches[2]) == 1
    print(f"  ✓ 7 folders split into {len(batches)} batches: {[len(b) for b in batches]}")


async def test_concurrency_bounds():
    """Test concurrency parameter bounds."""
    print("\nTest 6: Concurrency bounds")
    
    c1 = AsyncClassifier(concurrency=0)
    assert c1.concurrency == 1
    print(f"  ✓ concurrency=0 → 1 (min)")
    
    c2 = AsyncClassifier(concurrency=10)
    assert c2.concurrency == 8
    print(f"  ✓ concurrency=10 → 8 (max)")
    
    c3 = AsyncClassifier(concurrency=4)
    assert c3.concurrency == 4
    print(f"  ✓ concurrency=4 → 4 (in range)")


async def test_thinking_block_removal():
    """Test removal of thinking blocks from response."""
    print("\nTest 7: Thinking block removal (Qwen3.5)")
    
    classifier = AsyncClassifier(concurrency=2, batch_size=1)
    folders = [{'folder_name': 'test', 'folder_path': '/p', 'context': 'test'}]
    
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'message': {
            'content': '<think>Let me analyze this...</think>\n{"results":[{"name":"Test","category":"Design","confidence":85}]}'
        }
    })
    
    async with AsyncMock() as session:
        session.post = AsyncMock(return_value=mock_resp)
        results = await classifier._request_batch_async(folders, session)
    
    assert results[0]['category'] == 'Design'
    print(f"  ✓ Thinking block removed, parsed result: {results[0]['category']}")


async def main():
    """Run all tests."""
    print("=" * 70)
    print("FileOrganizer — Parallel LLM Classifier Tests")
    print("=" * 70)
    
    try:
        await test_parallel_classifier_basic()
        await test_batch_request()
        await test_error_handling()
        await test_empty_response()
        await test_batch_split_logic()
        await test_concurrency_bounds()
        await test_thinking_block_removal()
        
        print("\n" + "=" * 70)
        print("✓ All tests passed!")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(asyncio.run(main()))
