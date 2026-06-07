# Circuit Tracks: Pack and Project Structure

## What is a pack?

A **pack** is the top-level container on the Circuit Tracks. It holds everything:

| Contents      | Count        |
|---------------|--------------|
| Projects      | up to 64 (slots 0–63) |
| Drum samples  | 64           |
| Synth presets | 128          |

The device has **internal Flash** for exactly **one pack**. Whatever is loaded into
Flash occupies all 64 project slots at once. A **microSD card** can hold
any number of additional packs.

## Pack vs. project

| Term        | What it is |
|-------------|------------|
| **Pack**    | Container: 64 projects + 64 samples + 128 patches. Loaded via Novation Components. |
| **Project** | A single song/groove in one of the 64 slots. Has its own BPM, patterns, patch settings. |
| **Patch**   | A synth sound (340 bytes). 128 per pack, shared across all projects in that pack. |
| **Sample**  | A drum sample (WAV). 64 per pack. |

## BPM and packs

Each of the 64 projects in a pack can technically have its **own BPM** — this is not
a hardware constraint.

Commercial packs typically set all projects to the genre's standard BPM (e.g. ~170 for
DnB, ~128 for house). This is a convention of pack creators, not a technical requirement.

## The active pack owns all 64 slots

read_project(slot=0) through read_project(slot=63) always read from whichever pack
is currently loaded into Flash. There is no way to address a specific microSD pack
via the MIDI API. Switching packs requires the hardware UI or Novation Components.

## Switching packs

1. **Hardware**: Shift + Projects button → pack selection on device
2. **Novation Components**: load a pack from your computer

When a new pack is loaded, all 64 new projects replace the old ones in Flash.
Previous data is gone unless backed up to microSD.

## Identifying the active pack

The MCP server has no direct "which pack is loaded?" query. Indirect identification:
read a few slots with read_project() and compare project names or BPMs to known packs.

## SD card pack list

Use tools/sysex_probe.py to enumerate all packs on the SD card via Exchange Mode.
The tool sends CMD_GET_ALL_PACKS and prints the response -- one line per pack showing
the pack index and name. See docs/sd-pack-research.md for the SysEx details.

## Relationship to read_project

`read_project(slot)` reads from **internal Flash only**. SD packs load into RAM without
modifying Flash. So `read_project` always returns Flash data even when an SD pack is
actively playing.

Writing (set_synth_params, set_drum_params, CC/NRPN) targets the live RAM state.
This works regardless of whether a Flash or SD pack is active.

The SysEx command for reading directly from SD packs is unknown.
Research status and next steps: docs/sd-pack-research.md.
