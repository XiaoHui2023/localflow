from __future__ import annotations

import importlib.util
import tracemalloc
from pathlib import Path

import pytest

from localflow.log_files import BoundedLogWriter
from localflow.results import evaluate_vcs_chunks, evaluate_vcs_logs, evaluate_vcs_text


@pytest.mark.parametrize("width", [1, 2, 7, 31, 128, 65536])
@pytest.mark.parametrize(("text", "expected"), [
    ("UVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\n", ("passed", 0)),
    ("UVM Report Summary\nUVM_ERROR : 1234\nUVM_FATAL : 0", ("error", 1234)),
    ("UVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\nFatal: late failure", ("fatal", 1)),
    ("Error-[OLD] prior\nUVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\n", ("passed", 0)),
    ("UVM Report Summary\nUVM_ERROR : 2\nUVM_FATAL : 1\nUVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\n", ("passed", 0)),
    ("ordinary\nError-[SYN] bad\n", ("error", 1)),
    ("uVm report summary\nuvm_error : 0\nuvm_fatal : 4", ("fatal", 4)),
])
def test_streaming_summary_is_independent_of_chunk_boundaries(text, expected, width) -> None:
    chunks = (text[i:i + width] for i in range(0, len(text), width))
    assert evaluate_vcs_chunks(chunks) == expected


def test_large_log_and_arbitrarily_long_lines_have_bounded_allocations(tmp_path: Path) -> None:
    path = tmp_path / "large.log"
    with path.open("wb") as stream:
        for _ in range(48):
            stream.write(b"x" * 1024 * 1024)
        stream.write(b"\n" + b" " * (1024 * 1024) + b"Fatal: final error\n")
    tracemalloc.start()
    try:
        assert evaluate_vcs_logs([path]) == ("fatal", 1)
        _, peak = tracemalloc.get_traced_memory()
        assert peak < 4 * 1024 * 1024
    finally:
        tracemalloc.stop()


def test_incomplete_final_report_never_becomes_pass() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_vcs_text("UVM Report Summary\nUVM_INFO : 100\n")


def test_each_result_file_retains_its_failure(tmp_path: Path) -> None:
    first, second = tmp_path / "bad.log", tmp_path / "clean.log"
    first.write_text("UVM Report Summary\nUVM_ERROR : 1\nUVM_FATAL : 0\n")
    second.write_text("UVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\n")
    assert evaluate_vcs_logs([first, second]) == ("error", 1)
    assert evaluate_vcs_logs([second, first]) == ("error", 1)


def test_legacy_regex_failure_wins_and_oversize_is_explicit(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "plugins/sim_run/log_result.py"
    spec = importlib.util.spec_from_file_location("legacy_log_result", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "legacy.log"
    path.write_text("PASS early\nFAIL final\n", encoding="utf-8")
    assert module.evaluate_log_result(path, pass_regex="PASS", fail_regex="FAIL")[0] == "FAIL"
    assert module.evaluate_log_result(path, pass_regex="PASS", fail_regex="[")[0] == "ERROR"
    assert module.evaluate_log_result(path, pass_regex="PASS", max_bytes=4)[0] == "ERROR"
    assert module.read_log_tail(path, max_chars=5) == "inal\n"
    assert module.read_log_tail(path, max_chars=0) == ""


@pytest.mark.parametrize("kind", ["empty", "capped"])
def test_known_incomplete_evidence_cannot_pass(tmp_path: Path, kind) -> None:
    path = tmp_path / "result.log"
    if kind == "empty":
        path.write_bytes(b"")
    else:
        with BoundedLogWriter(path, 128) as writer:
            writer.write(b"x" * 200)
    with pytest.raises(ValueError, match="empty|incomplete"):
        evaluate_vcs_logs([path])


def test_file_mutation_during_scan_is_rejected(tmp_path: Path, monkeypatch) -> None:
    from localflow import results
    path = tmp_path / "result.log"
    path.write_text("UVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\n")
    original = results.evaluate_vcs_chunks

    def mutate_after_scan(chunks):
        status = original(chunks)
        with path.open("ab") as stream:
            stream.write(b"Fatal: producer continued writing\n")
        return status

    monkeypatch.setattr(results, "evaluate_vcs_chunks", mutate_after_scan)
    with pytest.raises(ValueError, match="changed during"):
        evaluate_vcs_logs([path])
