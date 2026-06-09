"""Command-line interface for chime-ingestor."""
import argparse
import sys
from pathlib import Path

from chime_ingestor.ingestor import ingest_directory


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="chime-ingestor",
        description="Ingest Chime and CashApp PDF statements into SQLite database",
    )
    parser.add_argument(
        "command",
        choices=["ingest"],
        help="Command to execute",
    )
    parser.add_argument(
        "data_dir",
        type=Path,
        help="Directory containing PDF files to ingest",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("finance.db"),
        help="Path to SQLite database (default: finance.db)",
    )

    args = parser.parse_args()

    if args.command == "ingest":
        if not args.data_dir.exists():
            print(f"Error: Data directory not found: {args.data_dir}", file=sys.stderr)
            return 1

        print(f"Ingesting PDFs from: {args.data_dir}")
        print(f"Database: {args.db}")
        print()

        stats = ingest_directory(args.data_dir, args.db)

        print(f"Processed: {stats['processed']} files")
        print(f"Skipped (already ingested): {stats['skipped']} files")
        print(f"Failed: {len(stats['failed'])} files")
        print(f"Total transactions inserted: {stats['total_transactions']}")

        if stats["failed"]:
            print("\nFailed files:")
            for failure in stats["failed"]:
                print(f"  - {failure}")

        return 0 if not stats["failed"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
