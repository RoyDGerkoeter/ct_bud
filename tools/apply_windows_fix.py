"""Re-apply the Windows SysEx fragmentation fix to circuit_tracks/midi.py.

Windows MIDI drivers split large SysEx messages (>1 KB) into fragments.
The polling-based mido input in circuit_tracks drops these silently, so
read_project() receives 0 bytes and fails with a CRC mismatch.

This script patches midi.py in-place to use an rtmidi callback accumulator
instead of mido polling. Run it after installing or upgrading circuit-tracks.

Usage:
    uv run tools/apply_windows_fix.py
    uv run tools/apply_windows_fix.py --midi-py path/to/circuit_tracks/midi.py
"""

import argparse
import sys
from pathlib import Path


MARKER = "_RtMidiInput"

PATCH_IMPORTS = """\
from __future__ import annotations

import queue as _queue
import threading as _threading
"""

PATCH_CLASS = '''

class _RtMidiInput:
    """rtmidi callback that reassembles sysex fragmented by winmm."""

    def __init__(self, port_name: str) -> None:
        import rtmidi  # type: ignore[import]

        self._queue: _queue.Queue[mido.Message] = _queue.Queue()
        self._sysex_buf: list[int] | None = None
        self._lock = _threading.Lock()
        self.name = port_name
        self._closed = False

        self._rt = rtmidi.MidiIn()
        self._rt.ignore_types(sysex=False, timing=True, active_sense=True)

        ports = self._rt.get_ports()
        idx = next(
            (i for i, n in enumerate(ports) if port_name in n or n in port_name),
            None,
        )
        if idx is None:
            raise RuntimeError(f"MIDI input port not found: {port_name!r}")

        self._rt.set_callback(self._callback)
        self._rt.open_port(idx)

    def _callback(self, event: tuple, data: object = None) -> None:
        raw_bytes, _ = event
        with self._lock:
            for byte in raw_bytes:
                if byte == 0xF0:
                    self._sysex_buf = []
                elif byte == 0xF7:
                    if self._sysex_buf is not None:
                        try:
                            self._queue.put_nowait(
                                mido.Message("sysex", data=self._sysex_buf)
                            )
                        except Exception:
                            pass
                    self._sysex_buf = None
                elif self._sysex_buf is not None:
                    self._sysex_buf.append(byte)

    @property
    def closed(self) -> bool:
        return self._closed

    def poll(self) -> mido.Message | None:
        try:
            return self._queue.get_nowait()
        except _queue.Empty:
            return None

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._rt.cancel_callback()
                self._rt.close_port()
            except Exception:
                pass

'''

OLD_CONNECT_INPUT = """\
        # Auto-open matching input port for bidirectional communication
        input_ports = mido.get_input_names()
        for ip in input_ports:
            if port_name in ip or ip in port_name:
                try:
                    self._input_port = mido.open_input(ip)
                    self._input_port_name = ip
                except Exception:
                    pass  # Input port not available, not critical
                break"""

NEW_CONNECT_INPUT = """\
        # open matching input port
        # rtmidi callback survives winmm sysex fragmentation; mido polling drops fragments
        input_ports = mido.get_input_names()
        for ip in input_ports:
            if port_name in ip or ip in port_name:
                try:
                    self._input_port = _RtMidiInput(ip)
                    self._input_port_name = ip
                except Exception:
                    try:
                        self._input_port = mido.open_input(ip)
                        self._input_port_name = ip
                    except Exception:
                        pass  # Input port not available, not critical
                break"""


def apply(midi_py: Path):
    if not midi_py.exists():
        print(f"ERROR: {midi_py} not found.")
        sys.exit(1)

    src = midi_py.read_text(encoding="utf-8")

    if MARKER in src:
        print("Fix already applied — nothing to do.")
        return

    if '"""MIDI connection management' in src:
        src = src.replace(
            '"""MIDI connection management for Novation Circuit Tracks."""\n\nimport time',
            '"""MIDI connection management for Novation Circuit Tracks."""\n\n'
            + PATCH_IMPORTS + "import time",
        )
    else:
        print("WARNING: Could not find docstring anchor — prepending imports.")
        src = PATCH_IMPORTS + src

    if "class MidiConnection:" not in src:
        print("ERROR: 'class MidiConnection:' not found in midi.py")
        sys.exit(1)
    src = src.replace("class MidiConnection:", PATCH_CLASS + "class MidiConnection:")

    if OLD_CONNECT_INPUT in src:
        src = src.replace(OLD_CONNECT_INPUT, NEW_CONNECT_INPUT)
    else:
        print("WARNING: connect() input block not found verbatim.")
        print("See docs/windows-sysex-fix.md for manual patching instructions.")

    midi_py.write_text(src, encoding="utf-8")
    print(f"Fix applied: {midi_py}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--midi-py",
        metavar="PATH",
        help="Path to circuit_tracks/midi.py (auto-detected from installed package if omitted)",
    )
    args = parser.parse_args()

    if args.midi_py:
        midi_py = Path(args.midi_py)
    else:
        import importlib.util
        spec = importlib.util.find_spec("circuit_tracks.midi")
        if spec is None or spec.origin is None:
            print("ERROR: circuit_tracks not found in current environment.")
            print("Activate the venv or use --midi-py to specify the path.")
            sys.exit(1)
        midi_py = Path(spec.origin)
        print(f"Auto-detected: {midi_py}")

    apply(midi_py)


if __name__ == "__main__":
    main()
