"""Bounded scans of complete simulator logs, independent of terminal windows."""
from __future__ import annotations

import codecs
import os
import re
from collections.abc import Iterable
from pathlib import Path

from .log_files import output_integrity

_EVENT = re.compile(
    r"(?P<header>UVM Report Summary)|UVM_(?P<name>INFO|WARNING|ERROR|FATAL)\s*:\s*(?P<count>\d+)",
    re.IGNORECASE,
)
_FATAL = re.compile(r"^\s*(?:Fatal(?:-|\s*:\s*)|Error-\[NOA\]|\*F,)", re.IGNORECASE)
_ERROR = re.compile(r"^\s*(?:Error(?:-|\s*:\s*)|\*E,)", re.IGNORECASE)


class _SummaryScan:
    def __init__(self) -> None:
        self.pending = ""
        self.counts: dict[str, int] = {}
        self.reports = 0

    def feed(self, text: str, *, final: bool = False) -> None:
        # Whitespace runs have no cardinality in this grammar. Compact them
        # before buffering, including runs spanning arbitrarily long lines.
        text = re.sub(r"\s+", " ", self.pending + re.sub(r"\s+", " ", text))
        boundary = len(text) if final else max(0, len(text) - 128)
        for match in _EVENT.finditer(text):
            if not final and match.group("count") and match.end() == len(text):
                boundary = min(boundary, match.start())
                break
            if match.group("header"):
                self.counts.clear()
                self.reports += 1
            else:
                self.counts[match.group("name").upper()] = int(match.group("count"))
            boundary = max(boundary, match.end())
        self.pending = text[boundary:]
        if len(self.pending) > 4096:
            raise ValueError("UVM summary count exceeds supported integer size")


def evaluate_vcs_chunks(chunks: Iterable[str]) -> tuple[str, int]:
    """Use the last report in one log and retain later VCS diagnostics."""
    summary = _SummaryScan()
    fatal = error = 0
    prefix = ""
    last_reports = 0

    def consume(segment: str, end_line: bool) -> None:
        nonlocal prefix, fatal, error, last_reports
        summary.feed(segment + ("\n" if end_line else ""))
        if summary.reports != last_reports:
            fatal = error = 0
            last_reports = summary.reports
        # Only an anchored diagnostic prefix is needed. Leading whitespace is
        # unbounded and semantically irrelevant; preserve no giant line.
        prefix = re.sub(r"\s+", " ", prefix + re.sub(r"\s+", " ", segment)).lstrip()[:128]
        if end_line:
            fatal += bool(_FATAL.match(prefix))
            error += bool(_ERROR.match(prefix))
            prefix = ""

    for chunk in chunks:
        parts = chunk.split("\n")
        for segment in parts[:-1]:
            consume(segment, True)
        consume(parts[-1], False)
    consume("", True)
    summary.feed("", final=True)
    if summary.counts.get("FATAL", 0) or fatal:
        return "fatal", summary.counts.get("FATAL", 0) + fatal
    if summary.counts.get("ERROR", 0) or error:
        return "error", summary.counts.get("ERROR", 0) + error
    if (summary.reports or summary.counts) and not {"ERROR", "FATAL"} <= summary.counts.keys():
        raise ValueError("final UVM report is incomplete: ERROR and FATAL counts are required")
    return "passed", 0


def evaluate_vcs_logs(paths: Iterable[Path]) -> tuple[str, int]:
    """Scan each declared file separately; one failing file defeats success."""
    result, count = "passed", 0
    severity = {"passed": 0, "error": 1, "fatal": 2}
    for path in paths:
        health = output_integrity(path)
        if health.get("complete") is False or health.get("reason") == "metadata_unreadable":
            raise ValueError(f"result log is incomplete: {path}")
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size == 0:
                raise ValueError(f"result log is empty: {path}")
            def chunks(size=before.st_size, source=path):
                decoder = codecs.getincrementaldecoder("utf-8")("replace")
                remaining = size
                while remaining:
                    raw = stream.read(min(65536, remaining))
                    if not raw:
                        raise ValueError(f"result log was shortened during evaluation: {source}")
                    remaining -= len(raw)
                    yield decoder.decode(raw)
                yield decoder.decode(b"", final=True)

            status, current = evaluate_vcs_chunks(chunks())
            after = os.fstat(stream.fileno())
            current_path = path.stat()
            def signature(stat):
                return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
            if signature(before) != signature(after) or signature(before) != signature(current_path):
                raise ValueError(f"result log changed during evaluation: {path}")
        if severity[status] > severity[result]:
            result, count = status, current
        elif status == result:
            count += current
    return result, count


def evaluate_vcs_text(text: str) -> tuple[str, int]:
    return evaluate_vcs_chunks(text[index:index + 65536] for index in range(0, len(text), 65536))
