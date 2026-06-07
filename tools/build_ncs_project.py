"""Merge patterns from multiple NCS session snapshots into one NCS project.

Each snapshot is a Circuit Tracks project saved at a moment in time.
This tool selects specific patterns from specific snapshots, optionally
upgrades 16-step patterns to 32-step (by doubling), assigns a Song Mode
sequence, and writes a single NCS binary ready to transfer to the device.

The project is described by a JSON config file. See examples/ for templates.

Usage:
    uv run tools/build_ncs_project.py config.json
    uv run tools/build_ncs_project.py config.json --out my_project.ncs
    uv run tools/build_ncs_project.py config.json --verify

Config format:
    {
      "name": "My Project",
      "session_folder": "path/to/session/",
      "master_index": 5,
      "patterns": [
        {"id": "intro",   "file_index": 0, "pattern": "pattern_0"},
        {"id": "main",    "file_index": 3, "pattern": "pattern_0"},
        {"id": "fill",    "file_index": 3, "pattern": "pattern_1"}
      ],
      "song": ["intro", "intro", "main", "fill", "main"],
      "force_32_step": true
    }

    session_folder: path containing 'User Session.ncs', 'User Session (1).ncs', ...
    master_index:   which file's sounds/BPM/scale to use as the project base
    patterns:       which pattern to pull from which file
    song:           Song Mode sequence (list of pattern IDs, max 16 entries)
    force_32_step:  double 16-step patterns to 32-step (default true)
"""

import argparse
import copy
import json
import os
import re

from circuit_tracks.ncs_parser import parse_ncs
from circuit_tracks.song import ncs_to_song, _song_data_to_dict, song_to_ncs, parse_song


def natural_sort_key(fname):
    # no number in filename = index 0, (N) = index N
    m = re.search(r'\((\d+)\)', fname)
    return int(m.group(1)) if m else 0


def load_session(folder):
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".ncs")],
        key=natural_sort_key,
    )
    entries = []
    for fname in files:
        path = os.path.join(folder, fname)
        song = _song_data_to_dict(ncs_to_song(parse_ncs(path)))
        entries.append((fname, song))
        print(f"  [{natural_sort_key(fname):2d}] {fname}  bpm={song['bpm']}  "
              f"s1={song['sounds']['synth1']['name']!r}")
    return entries


def double_steps(steps):
    doubled = {}
    for key, val in steps.items():
        idx = int(key)
        doubled[str(idx)]      = copy.deepcopy(val)
        doubled[str(idx + 16)] = copy.deepcopy(val)
    return doubled


def upgrade_to_32(pattern):
    if pattern.get("length", 16) == 32:
        return copy.deepcopy(pattern)
    upgraded = copy.deepcopy(pattern)
    upgraded["length"] = 32
    for track_data in upgraded.get("tracks", {}).values():
        if "steps" in track_data:
            track_data["steps"] = double_steps(track_data["steps"])
    return upgraded


def get_pattern(entries, file_index, pattern_name, force_32):
    fname, song = entries[file_index]
    pat = song["patterns"].get(pattern_name)
    if pat is None:
        available = list(song["patterns"].keys())
        raise KeyError(f"Pattern '{pattern_name}' not in {fname}. Available: {available}")
    return upgrade_to_32(pat) if force_32 else copy.deepcopy(pat)


def build_project(config, base_dir="."):
    folder = os.path.join(base_dir, config["session_folder"])
    force_32 = config.get("force_32_step", True)

    print(f"\nLoading session: {folder}")
    entries = load_session(folder)

    patterns = {}
    for spec in config["patterns"]:
        pat_id = spec["id"]
        patterns[pat_id] = get_pattern(entries, spec["file_index"], spec["pattern"], force_32)
        print(f"  pattern '{pat_id}' <- file[{spec['file_index']}] {spec['pattern']}")

    master_fname, master = entries[config["master_index"]]
    print(f"  master sounds <- file[{config['master_index']}] {master_fname}")

    song_dict = {
        "name":     config["name"],
        "bpm":      config.get("bpm", master["bpm"]),
        "swing":    master["swing"],
        "color":    master.get("color", 7),
        "scale":    master["scale"],
        "sounds":   master["sounds"],
        "fx":       master.get("fx", {}),
        "mixer":    master.get("mixer", {}),
        "patterns": patterns,
        "song":     config["song"],
    }
    return song_dict


def write_ncs(song_dict, out_path):
    ncs_bytes = song_to_ncs(parse_song(song_dict))
    with open(out_path, "wb") as fh:
        fh.write(ncs_bytes)
    size = os.path.getsize(out_path)
    print(f"  -> {out_path}  ({size:,} bytes)")
    return size


def verify_roundtrip(path):
    song = _song_data_to_dict(ncs_to_song(parse_ncs(path)))
    pats = list(song["patterns"].keys())
    lengths = sorted({p["length"] for p in song["patterns"].values()})
    print(f"  verify: name={song['name']!r}  bpm={song['bpm']}  "
          f"scale={song['scale']['root']} {song['scale']['type']}  "
          f"patterns={pats}  lengths={lengths}  song_len={len(song['song'])}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("config", help="JSON config file describing the project")
    parser.add_argument("--out", metavar="FILE",
                        help="Output .ncs path (default: <config_name>.ncs in current dir)")
    parser.add_argument("--base-dir", default=".", metavar="DIR",
                        help="Base directory for resolving session_folder (default: .)")
    parser.add_argument("--verify", action="store_true",
                        help="Re-parse output file and print summary")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)

    out_path = args.out or os.path.splitext(os.path.basename(args.config))[0] + ".ncs"

    song_dict = build_project(config, base_dir=args.base_dir)
    write_ncs(song_dict, out_path)

    if args.verify:
        verify_roundtrip(out_path)


if __name__ == "__main__":
    main()
