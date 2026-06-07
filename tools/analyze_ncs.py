"""Batch-analyse a folder of NCS session files.

Writes one JSON per file and a markdown summary with step bitmaps,
drum levels, FX routing, and sound-diffs between adjacent files.

Usage:
    uv run tools/analyze_ncs.py sessionsA sessionsB sessionsC
    uv run tools/analyze_ncs.py sessionsA --out analysis/
"""

import argparse
import json
import os
import re

from circuit_tracks.ncs_parser import parse_ncs
from circuit_tracks.song import ncs_to_song, _song_data_to_dict

TRACKS = ["synth1", "synth2", "drum1", "drum2", "drum3", "drum4"]


def natural_sort_key(fname):
    m = re.search(r'\((\d+)\)', fname)
    return int(m.group(1)) if m else 0


def step_bitmap(steps, length):
    return "".join("X" if str(i) in steps else "." for i in range(length))


def load_session(folder):
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".ncs")],
        key=natural_sort_key,
    )
    entries = []
    for fname in files:
        path = os.path.join(folder, fname)
        try:
            song = _song_data_to_dict(ncs_to_song(parse_ncs(path)))
            entries.append((fname, song))
        except (OSError, ValueError, KeyError) as exc:
            print(f"  SKIP {fname}: {exc}")
            entries.append((fname, None))
    return entries


def sound_diff(prev, curr):
    changes = []
    for synth_key in ("synth1", "synth2"):
        prev_s = prev.get("sounds", {}).get(synth_key, {})
        curr_s = curr.get("sounds", {}).get(synth_key, {})
        if prev_s.get("name") != curr_s.get("name"):
            changes.append(f"{synth_key}: {prev_s.get('name')!r} -> {curr_s.get('name')!r}")
        prev_p = prev_s.get("params", {})
        curr_p = curr_s.get("params", {})
        for param in set(list(prev_p) + list(curr_p)):
            if prev_p.get(param) != curr_p.get(param):
                changes.append(f"{synth_key}.{param}: {prev_p.get(param)} -> {curr_p.get(param)}")
    for drum_key in ("drum1", "drum2", "drum3", "drum4"):
        prev_d = prev.get("sounds", {}).get(drum_key, {})
        curr_d = curr.get("sounds", {}).get(drum_key, {})
        for field in ("sample", "level", "pitch", "decay", "distortion", "eq", "pan"):
            if prev_d.get(field) != curr_d.get(field):
                changes.append(f"{drum_key}.{field}: {prev_d.get(field)} -> {curr_d.get(field)}")
    return changes


def _format_drums(sounds):
    parts = []
    for drum_key in ("drum1", "drum2", "drum3", "drum4"):
        drum = sounds.get(drum_key, {})
        if drum:
            parts.append(
                f"{drum_key}: smp={drum.get('sample')} lvl={drum.get('level')} "
                f"pit={drum.get('pitch')} dist={drum.get('distortion')}"
            )
    return "Drums: " + " | ".join(parts) if parts else ""


def _format_fx(fx):
    lines = []
    sc = fx.get("sidechain", {})
    sc_synth1 = sc.get("synth1", {})
    sc_synth2 = sc.get("synth2", {})
    if sc_synth1.get("depth") or sc_synth2.get("depth"):
        lines.append(
            f"Sidechain: synth1.depth={sc_synth1.get('depth')} synth2.depth={sc_synth2.get('depth')}"
        )
    delay = fx.get("delay_sends", {})
    reverb = fx.get("reverb_sends", {})
    if delay:
        lines.append("Delay: " + " ".join(f"{k}={v}" for k, v in delay.items()))
    if reverb:
        lines.append("Reverb: " + " ".join(f"{k}={v}" for k, v in reverb.items()))
    return lines


def _format_patterns(patterns):
    lines = []
    for pat_name, pat in sorted(patterns.items()):
        length = pat.get("length", 16)
        active = [t for t in TRACKS if pat.get("tracks", {}).get(t, {}).get("steps")]
        lines.append(f"\n**{pat_name}** ({length} steps) — {', '.join(active)}")
        lines.append("```")
        for track in TRACKS:
            steps = pat.get("tracks", {}).get(track, {}).get("steps", {})
            if steps:
                lines.append(f"  {track:8s}: {step_bitmap(steps, length)}")
        lines.append("```")
    return lines


def format_entry_md(label, index, fname, song, prev_song):
    scale = song.get("scale", {})
    sounds = song.get("sounds", {})
    patterns = song.get("patterns", {})
    pat_lengths = sorted({p.get("length", 16) for p in patterns.values()})

    lines = [
        f"### {label}_{index:02d} — `{fname}`",
        f"BPM={song['bpm']}  Scale={scale.get('root')} {scale.get('type')}  "
        f"Patterns={len(patterns)}  Steps={pat_lengths}  Song={len(song.get('song', []))} scenes",
        f"Synth1={sounds.get('synth1', {}).get('name')!r}  "
        f"Synth2={sounds.get('synth2', {}).get('name')!r}",
    ]

    drums_line = _format_drums(sounds)
    if drums_line:
        lines.append(drums_line)

    lines.extend(_format_fx(song.get("fx", {})))
    lines.extend(_format_patterns(patterns))

    if prev_song is not None:
        diffs = sound_diff(prev_song, song)
        if diffs:
            lines.append("\nSound changes vs. predecessor:")
            lines.extend(f"  - {d}" for d in diffs[:20])
            if len(diffs) > 20:
                lines.append(f"  - ... ({len(diffs) - 20} more)")
        else:
            lines.append("\nSound changes: none")

    lines.append("")
    return "\n".join(lines)


def count_active_steps(song):
    return sum(
        len(track.get("steps", {}))
        for pat in song.get("patterns", {}).values()
        for track in pat.get("tracks", {}).values()
    )


def write_jsons(label, entries, out_dir):
    for i, (_, song) in enumerate(entries):
        if song is None:
            continue
        path = os.path.join(out_dir, f"{label}_{i:02d}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(song, fh, indent=2, ensure_ascii=False)


def build_summary_md(all_sessions):
    lines = ["# NCS Session Analysis", "", "## Overview", ""]
    lines.append("| Session | Files | Key | BPM | Step lengths | Active steps (last) |")
    lines.append("|---|---|---|---|---|---|")

    for label, entries in all_sessions.items():
        valid = [(f, s) for f, s in entries if s is not None]
        if not valid:
            continue
        last = valid[-1][1]
        scale = last.get("scale", {})
        all_lengths = sorted(
            {p.get("length", 16) for _, s in valid for p in s.get("patterns", {}).values()}
        )
        lines.append(
            f"| {label} | {len(valid)} | {scale.get('root')} {scale.get('type')} | "
            f"{last['bpm']} | {all_lengths} | {count_active_steps(last)} |"
        )

    lines += ["", "---", "## Step density progression", ""]
    for label, entries in all_sessions.items():
        valid = [(f, s) for f, s in entries if s is not None]
        density = "  ".join(f"{i}={count_active_steps(s)}" for i, (_, s) in enumerate(valid))
        lines += [f"**{label}:** {density}", ""]

    lines.append("---")
    for label, entries in all_sessions.items():
        valid = [(f, s) for f, s in entries if s is not None]
        lines.append(f"\n## Session {label} ({len(valid)} files)\n")
        prev = None
        for i, (fname, song) in enumerate(valid):
            lines.append(format_entry_md(label, i, fname, song, prev))
            prev = song

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sessions", nargs="+", metavar="FOLDER",
                        help="Session folder(s) to analyse (each gets a label A, B, C...)")
    parser.add_argument("--out", default="analysis", metavar="DIR",
                        help="Output directory for JSON files and summary.md (default: analysis/)")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    labels = [chr(ord("A") + i) for i in range(len(args.sessions))]
    all_sessions = {}

    for label, folder in zip(labels, args.sessions):
        print(f"Loading {label}: {folder}")
        entries = load_session(folder)
        all_sessions[label] = entries
        write_jsons(label, entries, args.out)
        print(f"  {len(entries)} files written to {args.out}/")

    summary_path = os.path.join(args.out, "summary.md")
    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write(build_summary_md(all_sessions))
    print(f"\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
