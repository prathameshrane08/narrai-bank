"""Bank statement import: detect the format and parse it into StatementEntry rows."""

from importers import camt053, csv_export, mt940
from importers.base import ParsedStatement, StatementEntry, StatementError

MAX_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 50_000

__all__ = ["ParsedStatement", "StatementEntry", "StatementError", "parse_statement"]


def detect_format(data: bytes) -> str:
    head = data[:4096].lstrip(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"<"):
        return "camt.053"
    if b":20:" in head or b":61:" in head or head.startswith(b"{1:"):
        return "MT940"
    return "CSV"


def parse_statement(data: bytes) -> ParsedStatement:
    if len(data) > MAX_BYTES:
        raise StatementError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not data.strip():
        raise StatementError("File is empty.")

    parser = {"camt.053": camt053.parse, "MT940": mt940.parse, "CSV": csv_export.parse}[detect_format(data)]
    parsed = parser(data)
    if len(parsed.entries) > MAX_ENTRIES:
        raise StatementError(f"File has more than {MAX_ENTRIES} entries.")
    return parsed
