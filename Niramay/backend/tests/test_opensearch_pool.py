"""Test that OpenSearch client is configured with
sufficient connection pool size."""

def test_opensearch_client_has_sufficient_pool():
    """pool_maxsize should be at least 10 to handle
    concurrent writes from multiple async workers."""
    import inspect
    from app.ingestion import opensearch_client
    source = inspect.getsource(opensearch_client)
    assert "pool_maxsize" in source
    # Verify value is meaningful (at least 10)
    import re
    match = re.search(r"pool_maxsize\s*=\s*(\d+)", source)
    assert match is not None, "pool_maxsize not found"
    assert int(match.group(1)) >= 10, (
        f"pool_maxsize should be >= 10, got {match.group(1)}"
    )
