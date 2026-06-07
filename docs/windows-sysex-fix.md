# Windows SysEx Fragmentation Fix for circuit-tracks-tools

## Problem

`read_project()` fails on Windows with:

```
CRC32 mismatch: computed 0x00000000, received 0x4D551660
```

`computed 0x00000000` is the CRC32 of empty bytes. **No data was received**, despite the device successfully sending the file.

## Root Cause

The NCS project transfer protocol (reverse-engineered from Novation Components WebMIDI traffic) works as follows:

1. Host sends READ request (WRITE_INIT with flag `0x02`)
2. Device responds with READ_INIT (file size: 160,780 bytes) ✅
3. Device streams ~20× WRITE_DATA blocks of ~9,400 bytes each ❌
4. Device sends WRITE_FINISH with CRC32 ✅

Steps 2 and 4 succeed because those messages are small (~26-30 bytes). Step 3 fails silently because **Windows MIDI drivers (WinMM) fragment SysEx messages larger than ~1KB** into multiple chunks. The mido polling-based input receives each fragment as a separate incomplete message. Since each fragment lacks the expected SysEx header (`F0 00 20 29 01 64 03`), the matching code in receive_ncs_project() skips all of them, and raw_data stays empty.

## Fix

Replace mido.open_input() in MidiConnection.connect() with a callback-based _RtMidiInput class that:

1. Uses rtmidi's callback mode (runs in a separate thread)
2. Accumulates raw bytes one at a time: F0 -> start buffer, F7 -> complete message -> queue
3. Reassembles fragmented SysEx before the caller ever sees it

See `tools/apply_windows_fix.py` for automated patching.

## Files Changed

| File | Change |
|---|---|
| `circuit_tracks/midi.py` (in your venv) | Added `_RtMidiInput` class; replaced `mido.open_input()` in `connect()` |
| `.mcp.json` | Changed from `uvx` to local `.venv` executable (required so edits persist) |

## Re-applying After Package Updates

If you upgrade `circuit-tracks-tools` via:

```powershell
uv pip install --upgrade circuit-tracks-tools
```

...the midi.py edit will be overwritten. Run this to reapply:

```powershell
uv run tools\apply_windows_fix.py
```

## MCP Server Config Note

`.mcp.json` now uses the local venv directly:

```json
{
  "mcpServers": {
    "circuit-tracks": {
      "command": "path/to/your/project/.venv/Scripts/circuit-tracks-mcp.exe",
      "args": []
    }
  }
}
```

Previously it used `uvx --from circuit-tracks-tools[mcp] circuit-tracks-mcp`, which runs from a cached environment -- not editable.

## Upstream

The fix should ideally be contributed upstream to circuit-tracks-tools. The relevant file is circuit_tracks/midi.py, specifically the connect() method and the input port handling. The _RtMidiInput class in tools/apply_windows_fix.py is the proposed patch.
