"""
CLI entry point for indexing pipeline.
"""

import asyncio
import argparse
from pathlib import Path

from src.core.indexing.pipeline import IndexingPipeline
from src.shared.config import settings
from src.shared.logging import setup_logging


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="TAi indexing pipeline")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental", "staging"],
        default="staging",
        help="Indexing mode"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(settings.indexing.data_dir),
        help="Data directory path"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    # Run pipeline
    pipeline = IndexingPipeline()
    stats = await pipeline.run(args.data_dir, mode=args.mode)
    
    # Print summary
    print("\n" + "=" * 50)
    print("Indexing Pipeline Summary")
    print("=" * 50)
    print(f"Files processed: {stats['files_processed']}")
    print(f"Chunks created: {stats['chunks_created']}")
    print(f"Entities extracted: {stats['entities_extracted']}")
    print(f"Relationships extracted: {stats['relationships_extracted']}")
    print(f"Entities merged: {stats['entities_merged']}")
    print(f"Entities stored: {stats['entities_stored']}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
