"""Tests for parser registry dispatch."""
from pathlib import Path

import pytest

from parsers import detect_institution, get_parser, parse_pdf
from parsers.chime_parser import ChimeParser
from parsers.cashapp_parser import CashAppParser


class TestDetectInstitution:
    """Tests for institution detection from paths."""

    def test_detect_chime_from_parent_dir(self, tmp_path: Path) -> None:
        """Path with 'Chime' parent directory → 'chime'."""
        chime_dir = tmp_path / "Chime"
        chime_dir.mkdir()
        pdf_path = chime_dir / "statement.pdf"
        assert detect_institution(pdf_path) == "chime"

    def test_detect_chime_case_insensitive(self, tmp_path: Path) -> None:
        """Case-insensitive detection: 'chime', 'CHIME', 'Chime' all work."""
        for name in ["chime", "CHIME", "Chime", "Chime-Statements"]:
            test_dir = tmp_path / name
            test_dir.mkdir(exist_ok=True)
            assert detect_institution(test_dir / "file.pdf") == "chime"

    def test_detect_cashapp_from_parent_dir(self, tmp_path: Path) -> None:
        """Path with 'CashApp' parent directory → 'cashapp'."""
        cashapp_dir = tmp_path / "CashApp"
        cashapp_dir.mkdir()
        pdf_path = cashapp_dir / "statement.pdf"
        assert detect_institution(pdf_path) == "cashapp"

    def test_detect_cashapp_cash_variant(self, tmp_path: Path) -> None:
        """Path with 'Cash' in name → 'cashapp'."""
        cash_dir = tmp_path / "Cash"
        cash_dir.mkdir()
        assert detect_institution(cash_dir / "file.pdf") == "cashapp"

    def test_detect_unknown_raises(self, tmp_path: Path) -> None:
        """Unknown parent directory → raises ValueError."""
        unknown_dir = tmp_path / "UnknownBank"
        unknown_dir.mkdir()
        with pytest.raises(ValueError, match="Cannot detect institution"):
            detect_institution(unknown_dir / "file.pdf")


class TestGetParser:
    """Tests for parser registry lookup."""

    def test_get_parser_chime(self) -> None:
        """Returns ChimeParser instance."""
        parser = get_parser("chime")
        assert isinstance(parser, ChimeParser)

    def test_get_parser_cashapp(self) -> None:
        """Returns CashAppParser instance."""
        parser = get_parser("cashapp")
        assert isinstance(parser, CashAppParser)

    def test_get_parser_unknown_raises(self) -> None:
        """Unknown institution → raises ValueError."""
        with pytest.raises(ValueError, match="Unknown institution: unknown"):
            get_parser("unknown")


class TestParsePdfDispatch:
    """Integration tests for registry dispatch via parse_pdf."""

    def test_parse_pdf_dispatches_to_chime(self, tmp_path: Path) -> None:
        """parse_pdf with Chime path uses ChimeParser."""
        chime_dir = tmp_path / "Chime"
        chime_dir.mkdir()
        pdf_path = chime_dir / "nonexistent.pdf"

        # Should fail at file check, not at dispatch
        with pytest.raises(FileNotFoundError):
            parse_pdf(pdf_path)

    def test_parse_pdf_dispatches_to_cashapp(self, tmp_path: Path) -> None:
        """parse_pdf with CashApp path uses CashAppParser."""
        cashapp_dir = tmp_path / "CashApp"
        cashapp_dir.mkdir()
        pdf_path = cashapp_dir / "nonexistent.pdf"

        # Should fail at file check, not at dispatch
        with pytest.raises(FileNotFoundError):
            parse_pdf(pdf_path)

    def test_parse_pdf_fails_on_unknown_institution(self, tmp_path: Path) -> None:
        """parse_pdf with unknown path raises ValueError before file check."""
        unknown_dir = tmp_path / "Unknown"
        unknown_dir.mkdir()
        pdf_path = unknown_dir / "file.pdf"

        # Should fail at institution detection
        with pytest.raises(ValueError, match="Cannot detect institution"):
            parse_pdf(pdf_path)
