"""
End-to-end test: index docs → ask question → get cited answer.
"""

import pytest

from src.core.pipeline import TAiPipeline
from src.core.indexing.pipeline import IndexingPipeline
from src.safety.consent import ConsentManager
from src.memory.store import SafeMemoryStore


@pytest.mark.asyncio
async def test_end_to_end_query_pipeline(neo4j_driver, test_data_dir):
    """Test complete pipeline: index → query → answer."""
    # Setup consent
    memory_store = SafeMemoryStore()
    consent_manager = ConsentManager(memory_store)
    
    # Grant consent for test student
    session_token = "test_token_123"
    consent_manager.grant_consent("test_student", "I CONSENT", session_token)
    
    # Index test documents
    indexing_pipeline = IndexingPipeline()
    await indexing_pipeline.run(test_data_dir, mode="full")
    
    # Ask question
    tai_pipeline = TAiPipeline()
    response = await tai_pipeline.ask(
        student_id="test_student",
        question="How does Raft handle leader failure?",
        context_type="lecture-raft"
    )
    
    # Verify response
    assert len(response.answer) > 0
    assert "Raft" in response.answer or "raft" in response.answer.lower()
    assert len(response.citations) > 0
    assert response.retrieval_strategy_used in ["local", "global", "hybrid"]
