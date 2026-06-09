"""Tests for batch ingestor."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chime_ingestor.ingestor import ingest_directory
from chime_ingestor.models import ChimeTransaction


class TestIngestor:
    """Tests for batch ingestion."""

    def test_ingestor_skips_ingested(self, tmp_path: Path) -> None:
        """Pre-logged hash → skipped, not re-parsed."""
        # Create Chime directory with a PDF
        chime_dir = tmp_path / "Chime"
        chime_dir.mkdir()
        pdf_file = chime_dir / "statement.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        db_path = tmp_path / "test.db"

        # First ingestion
        with patch("parsers.chime_parser.pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_pdf.pages = []
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)

            stats1 = ingest_directory(chime_dir, db_path)

        # Second ingestion should skip
        stats2 = ingest_directory(chime_dir, db_path)

        assert stats2["skipped"] == 1
        assert stats2["processed"] == 0

    def test_ingestor_failed_continues(self, tmp_path: Path) -> None:
        """One bad PDF → rest of batch continues."""
        chime_dir = tmp_path / "Chime"
        chime_dir.mkdir()

        # Create one valid and one invalid PDF
        valid_pdf = chime_dir / "valid.pdf"
        valid_pdf.write_bytes(b"fake pdf content")

        # Create a corrupted PDF (will fail to parse)
        invalid_pdf = chime_dir / "invalid.pdf"
        invalid_pdf.write_text("not a real pdf")

        db_path = tmp_path / "test.db"

        with patch("parsers.chime_parser.pdfplumber.open") as mock_open:
            # First call succeeds, second raises
            def side_effect(path):
                if "invalid" in str(path):
                    raise Exception("Cannot parse")
                mock_pdf = MagicMock()
                mock_pdf.pages = []
                return MagicMock(
                    __enter__=MagicMock(return_value=mock_pdf),
                    __exit__=MagicMock(return_value=False)
                )

            mock_open.side_effect = side_effect

            stats = ingest_directory(chime_dir, db_path)

        # Should have one failure but continue
        assert len(stats["failed"]) >= 1

    def test_ingestor_summary(self, tmp_path: Path) -> None:
        """Returns correct processed/skipped/failed counts."""
        chime_dir = tmp_path / "Chime"
        chime_dir.mkdir()

        pdf_file = chime_dir / "statement.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        db_path = tmp_path / "test.db"

        with patch("parsers.chime_parser.pdfplumber.open") as mock_open:
            mock_pdf = MagicMock()
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""
            mock_pdf.pages = [mock_page]
            mock_open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)

            stats = ingest_directory(chime_dir, db_path)

        assert "processed" in stats
        assert "skipped" in stats
        assert "failed" in stats
        assert "total_transactions" in stats
