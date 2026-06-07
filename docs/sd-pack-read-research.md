# Circuit Tracks: Reading SD-Pack Projects via SysEx

## Background

read_project(slot) always reads from the device's internal Flash. SD-card packs load
into RAM -- the Flash is not modified. So read_project always returns Flash data,
regardless of which SD pack is currently active.

## What works

### 1. List all packs on the SD card

```
Enter Exchange Mode:   F0 00 20 29 01 64 03 40 F7
Get All Packs Info:    F0 00 20 29 01 64 03 0B 02 F7
```

The device responds with one SysEx message per pack. Each message contains a 1-byte
pack index and a null-terminated ASCII name.

Example output (your SD card contents will differ):

| ID   | Name                  |
|------|-----------------------|
| 0x00 | MyFirstPack           |
| 0x01 | SomeDnbPack           |
| 0x02 | HousePack             |
| ...  | ...                   |

Use tools/sysex_probe.py to enumerate your packs.

### 2. Query the active pack ID

```
F0 00 20 29 01 64 49 F7
```

The device responds with ~22 bytes. Byte 8 (0-indexed) contains the pack ID of the
currently active pack. The meaning of the remaining bytes is not fully decoded.

### 3. Data transfer: 160,780 bytes confirmed

The standard NCS transfer (WRITE_INIT with flag `0x02`) reliably transfers 160,780 bytes.
The QUERY_INFO command with a pack-ID parameter answers from the device, but does
**not** change the read pointer. It still reads internal Flash.

## What does NOT work

### Hypothesis: QUERY_INFO as pack pointer

Tested: sending `F0 00 20 29 01 64 03 09 01 <pack_id> F7` before WRITE_INIT.  
Result: device responds and transfers 160,780 bytes — but the content is still
internal Flash, not the SD pack.

QUERY_INFO echoes the pack ID back but does not switch the read source.

## Missing piece: sniffing Novation Components

To find the exact SysEx sequence Components sends when downloading a project from
an SD pack, intercept the WebMIDI traffic.

### Chrome DevTools WebMIDI hook

1. Open Novation Components in Chrome
2. Connect the Circuit Tracks
3. Open DevTools (F12) → Console
4. Paste and run:

```javascript
(function() {
    const origSend = MIDIOutput.prototype.send;
    MIDIOutput.prototype.send = function(data, timestamp) {
        const arr = Array.from(data instanceof Uint8Array ? data : new Uint8Array(data));
        if (arr[0] === 0xF0) {
            console.log('%cSysEx TX [' + arr.length + ']', 'color:lime',
                arr.map(b => b.toString(16).padStart(2,'0').toUpperCase()).join(' '));
        }
        return origSend.call(this, data, timestamp);
    };
    console.log('%cWebMIDI TX hook active', 'color:orange; font-weight:bold');
})();
```

5. In Components: download a project slot from an SD pack
6. Copy all SysEx output from the console

### What to look for

The sequence between `03 40` (Enter Exchange Mode) and the first `03 01` (WRITE_INIT).
Specifically: any command with format `03 XX YY <pack_id>` that precedes the read.

Known Exchange Mode sub-commands seen in the community:
- `03 09 01 00` — tested, does not function as pack selector
- `03 0B 01` — unknown meaning
- Additional unknown sub-commands

## Technical background

From community research:

> SD card packs are not copied into internal Flash. The firmware loads data directly
> into volatile RAM. The SysEx dump command reads Flash, not RAM. Without an explicit
> SD-slot pointer in the read command, storage always falls back to the internal pack.

> Components most likely sends an unknown request (e.g. `03 09 01 <pack_id>` or
> similar) before WRITE_INIT to redirect the read head to the SD pack.
