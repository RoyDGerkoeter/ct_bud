"""Probe Circuit Tracks for SD-card pack information via raw SysEx.

Sends known Exchange-Mode SysEx commands and prints all responses.
Run while the MCP server is disconnected (no other process may hold the port).

The device display shows green/yellow arrows while in Exchange Mode.
The UI unfreezes automatically when the port is closed.

Usage:
    uv run tools/sysex_probe.py
    uv run tools/sysex_probe.py --port "Circuit Tracks"
"""

import argparse
import threading
import time

import rtmidi

DEFAULT_PORT = "Circuit Tracks"

CMD_CURRENT_PACK_ID = [0xF0, 0x00, 0x20, 0x29, 0x01, 0x64, 0x49, 0xF7]
CMD_ENTER_EXCHANGE  = [0xF0, 0x00, 0x20, 0x29, 0x01, 0x64, 0x03, 0x40, 0xF7]
CMD_GET_ALL_PACKS   = [0xF0, 0x00, 0x20, 0x29, 0x01, 0x64, 0x03, 0x0B, 0x02, 0xF7]

# not confirmed to work -- byte 9 is the pack id (0x00 = flash, 0x01+ = sd)
def cmd_set_pack_ptr(pack_id):
    return [0xF0, 0x00, 0x20, 0x29, 0x01, 0x64, 0x03, 0x09, 0x01, pack_id, 0xF7]


def find_port(ports, name):
    for idx, port_name in enumerate(ports):
        if name in port_name:
            return idx
    return None


def hex_str(data):
    return " ".join(f"{byte:02X}" for byte in data)


def ascii_str(data):
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in data)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--port", default=DEFAULT_PORT,
        help=f"MIDI port name fragment (default: {DEFAULT_PORT!r})",
    )
    args = parser.parse_args()

    midi_out = rtmidi.MidiOut()
    midi_in  = rtmidi.MidiIn()
    midi_in.ignore_types(sysex=False, timing=True, active_sense=True)

    out_ports = midi_out.get_ports()
    in_ports  = midi_in.get_ports()
    print("MIDI Out:", out_ports)
    print("MIDI In: ", in_ports)

    out_idx = find_port(out_ports, args.port)
    in_idx  = find_port(in_ports,  args.port)

    if out_idx is None or in_idx is None:
        print(f"\nERROR: '{args.port}' not found in port list.")
        print("Make sure the MCP server is disconnected and the device is plugged in.")
        return

    print(f"\nUsing Out[{out_idx}]: {out_ports[out_idx]}")
    print(f"Using In [{in_idx}]:  {in_ports[in_idx]}")

    responses = []
    sysex_buf = None
    lock = threading.Lock()

    def on_sysex(event, _data=None):
        nonlocal sysex_buf
        raw, _timestamp = event
        with lock:
            for byte in raw:
                if byte == 0xF0:
                    sysex_buf = []
                elif byte == 0xF7:
                    if sysex_buf is not None:
                        responses.append(bytes(sysex_buf))
                        print(f"  << SysEx ({len(sysex_buf)} bytes): {hex_str(sysex_buf)}")
                        print(f"     ASCII: {ascii_str(sysex_buf)}")
                    sysex_buf = None
                elif sysex_buf is not None:
                    sysex_buf.append(byte)

    midi_in.set_callback(on_sysex)
    midi_in.open_port(in_idx)
    midi_out.open_port(out_idx)

    def send(label, cmd, wait=1.5):
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"  >> {hex_str(cmd)}")
        before = len(responses)
        midi_out.send_message(cmd)
        time.sleep(wait)
        if len(responses) == before:
            print("  (no response)")

    send("Current Pack ID",          CMD_CURRENT_PACK_ID)
    send("Enter Exchange Mode",       CMD_ENTER_EXCHANGE,  wait=0.5)
    send("Get All Packs",             CMD_GET_ALL_PACKS,   wait=3.0)
    send("Set pack pointer -> SD 1",  cmd_set_pack_ptr(0x01), wait=1.0)
    send("Set pack pointer -> SD 2",  cmd_set_pack_ptr(0x02), wait=1.0)

    print(f"\n{'='*60}")
    print(f"Total responses: {len(responses)}")

    midi_in.cancel_callback()
    midi_in.close_port()
    midi_out.close_port()
    print("Ports closed. Device UI should be back to normal.")


if __name__ == "__main__":
    main()
