# circuit-tracks-companion

Companion tools and research for the [Novation Circuit Tracks](https://novationmusic.com/products/circuit-tracks), built on top of the [circuit-tracks-tools](https://github.com/novation/circuit-tracks-tools) Python library.

## What's here

| Tool | What it does |
|---|---|
| `tools/analyze_ncs.py` | Batch-analyse session snapshots -> JSON + markdown summary with step bitmaps, sound diffs, FX routing |
| `tools/build_ncs_project.py` | Merge patterns from multiple session snapshots into one NCS project with Song Mode |
| `tools/sysex_probe.py` | Enter Exchange Mode, list SD-card packs, probe raw SysEx commands |
| `tools/apply_windows_fix.py` | Patch circuit_tracks/midi.py to fix SysEx fragmentation on Windows |

Research docs in docs/:
- sd-pack-research.md -- SD pack SysEx reverse-engineering: what works, what doesn't, what's missing
- circuit-tracks-pack-structure.md -- how packs, projects, patches, and samples relate
- windows-sysex-fix.md -- the Windows MIDI driver SysEx fragmentation bug and the fix

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- circuit-tracks-tools[mcp] -- the library this builds on

```
uv sync
```

## Quick start

```sh
# Analyse a folder of NCS session snapshots
uv run tools/analyze_ncs.py my_sessions/ --out analysis/

# Build a merged NCS project from a config file
uv run tools/build_ncs_project.py examples/dnb_session_a.json --verify

# Probe the device for SD-card pack info (disconnect MCP server first)
uv run tools/sysex_probe.py

# Apply the Windows SysEx fix after installing or upgrading circuit-tracks-tools
uv run tools/apply_windows_fix.py
```

Config file templates are in examples/.

## Windows note

On Windows, large SysEx messages (>1 KB) are fragmented by the MIDI driver. This breaks read_project() silently. Run apply_windows_fix.py once after installing the library. See docs/windows-sysex-fix.md for details and a manual patching guide.

## License

MIT -- see [LICENSE](LICENSE).
Built on [circuit-tracks-tools](https://github.com/novation/circuit-tracks-tools) (also MIT).
