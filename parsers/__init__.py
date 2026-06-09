"""Parser registry — routes PDFs to institution-specific parsers."""
from pathlib import Path
from typing import Protocol

from chime_ingestor.models import ChimeTransaction


class PDFParser(Protocol):
    """Protocol for PDF parsers."""

    def parse(self, path: Path) -> list[ChimeTransaction]:
        """Parse a PDF and return normalized transactions."""
        ...


def get_parser(institution: str) -> PDFParser:
    """Get the appropriate parser for an institution.

    Args:
        institution: Institution name ("chime", "cashapp")

    Returns:
        Parser instance implementing PDFParser protocol

    Raises:
        ValueError: If institution is unknown
    """
    if institution == "chime":
        from parsers.chime_parser import ChimeParser

        return ChimeParser()
    if institution == "cashapp":
        from parsers.cashapp_parser import CashAppParser

        return CashAppParser()
    raise ValueError(f"Unknown institution: {institution}")


def detect_institution(path: Path) -> str:
    """Detect institution from parent directory name.

    Args:
        path: Path to the PDF file

    Returns:
        Institution name ("chime", "cashapp")

    Raises:
        ValueError: If institution cannot be detected

    Note:
        Institution detection is directory-based only.
        Never inspect PDF content to detect institution.
    """
    parent = path.parent.name.lower()
    if "chime" in parent:
        return "chime"
    if "cashapp" in parent or "cash" in parent:
        return "cashapp"
    raise ValueError(f"Cannot detect institution from path: {path}")


def parse_pdf(path: Path) -> list[ChimeTransaction]:
    """Parse any supported PDF using registry dispatch.

    Args:
        path: Path to the PDF file

    Returns:
        List of normalized transactions
    """
    institution = detect_institution(path)
    parser = get_parser(institution)
    return parser.parse(path)
