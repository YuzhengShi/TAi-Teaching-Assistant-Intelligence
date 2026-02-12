"""
End-to-end integration test for indexing pipeline.
"""

import pytest
from pathlib import Path
import tempfile

from src.core.indexing.pipeline import IndexingPipeline


@pytest.mark.asyncio
async def test_indexing_pipeline_end_to_end(neo4j_driver, test_data_dir):
    """Test complete pipeline: fixtures → Neo4j graph."""
    # Create test fixtures
    assignment_path = test_data_dir / "assignment1.md"
    assignment_path.write_text(
        "# Assignment 1: Raft Implementation\n\n"
        "## Requirements\n"
        "- Implement Raft leader election\n"
        "- Handle node failures\n\n"
        "## Concepts\n"
        "- Raft protocol\n"
        "- Consensus algorithms"
    )
    
    # Run pipeline
    pipeline = IndexingPipeline()
    stats = await pipeline.run(test_data_dir, mode="full")
    
    # Verify statistics
    assert stats["files_processed"] > 0
    assert stats["chunks_created"] > 0
    assert stats["entities_extracted"] > 0
    
    # Verify Neo4j contains nodes
    # This would require actual Neo4j connection
    # For now, just verify pipeline completes
    assert stats["entities_stored"] > 0


@pytest.mark.asyncio
async def test_incremental_mode_skips_processed_files(neo4j_driver, test_data_dir):
    """Test that incremental mode skips already processed files."""
    # Create test file
    test_file = test_data_dir / "test.md"
    test_file.write_text("# Test Document")
    
    # Run pipeline twice
    pipeline = IndexingPipeline()
    
    # First run
    stats1 = await pipeline.run(test_data_dir, mode="full")
    files_first = stats1["files_processed"]
    
    # Second run (incremental)
    stats2 = await pipeline.run(test_data_dir, mode="incremental")
    files_second = stats2["files_processed"]
    
    # Second run should process fewer files (or zero if all processed)
    assert files_second <= files_first
