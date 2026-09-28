"""Byte windows that also fit the terminal's bounded visual-row buffer."""
from pathlib import Path


def terminal_window(path: Path, start: int, end: int, columns: int = 80,
                    direction: str = "tail", hit: int | None = None) -> dict[str, int]:
    columns = min(1000, max(2, columns))
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return {"start": 0, "end": 0}
    end = min(max(0, end), size)
    start = min(end, max(0, start, end - 4 * 1024 * 1024))
    if hit is not None:
        start = max(start, min(end, hit) - 1024)
    with path.open("rb") as stream:
        stream.seek(start)
        data = stream.read(end - start)

    def cost(value: bytes) -> int:
        # A UTF-8 byte bounds a printable cell; tabs need up to eight.
        # Add one row per LF plus the total possible wrapping. Counting
        # escape bytes as cells deliberately overestimates ordinary ANSI.
        return value.count(b"\n") + (len(value) + 7 * value.count(b"\t") + columns - 1) // columns

    low, high = 0, len(data)
    forward = direction in {"later", "hit"}
    while low < high:
        middle = (low + high + 1) // 2
        part = data[:middle] if forward else data[len(data) - middle:]
        if cost(part) <= 4000:
            low = middle
        else:
            high = middle - 1
    if forward:
        end = start + low
        # Do not terminate a replay in the middle of a UTF-8 sequence.
        candidate = end
        while (end > start and candidate - end < 3 and end - start < len(data)
               and data[end - start] & 0xC0 == 0x80):
            end -= 1
        if end == start or (end - start < len(data) and data[end - start] & 0xC0 == 0x80):
            end = candidate  # Malformed runs have no valid boundary to align.
    else:
        start = end - low
        candidate = start
        while (start < end and start - candidate < 3
               and data[start - (end - len(data))] & 0xC0 == 0x80):
            start += 1
        if start == end or data[start - (end - len(data))] & 0xC0 == 0x80:
            start = candidate
    return {"start": start, "end": end}
