# docsis-active

`docsis-active.py` is a small Linux monitor for estimating DOCSIS segment activity by observing **ranging/maintenance SIDs in downstream MAP messages**.

It tunes a DOCSIS 3.0 downstream channel with `dvbv5-zap`, pipes the MPEG transport stream into `tshark`, extracts `docsis_map.sid` together with `docsis_map.iuc`, and counts unique non-reserved SIDs seen with **IUC 3 or IUC 4** during a rolling time window.

## Example output

```text
DOCSIS Segment Monitor
======================
Kanal: DOCSIS570
Fenster: 30 Sekunden

22:31:05 aktive Ranging-SIDs ≈ 114
22:31:10 aktive Ranging-SIDs ≈ 226
22:31:15 aktive Ranging-SIDs ≈ 318
22:31:20 aktive Ranging-SIDs ≈ 364
22:31:25 aktive Ranging-SIDs ≈ 381
22:31:30 aktive Ranging-SIDs ≈ 387
```

During the first 30 seconds after startup the counter normally rises as the rolling window fills. Afterwards it fluctuates as SIDs enter and leave the observation window.

## What it measures

The monitor inspects DOCSIS MAP messages and records the timestamp of SIDs attached to maintenance/ranging entries:

- IUC 3 — Initial Maintenance
- IUC 4 — Station Maintenance

SID 0 and the broadcast SID `0x3fff` are ignored. A SID remains active until it has not been seen for the configured rolling window, 30 seconds by default.

This approach usually produces a broader segment activity estimate than counting only actual Ranging Response (`RNG-RSP`) messages, because it observes maintenance opportunities announced by the CMTS scheduler.

The `≈` symbol is deliberate. The result is an **estimate based on observed MAP SIDs**, not a guaranteed exact number of physical cable modems or subscribers. CMTS implementation, DOCSIS version, channel bonding, packet loss and the selected observation window can influence the result.

The tool does not decode customer payload data and does not attempt to associate SIDs with subscriber identities.

## Requirements

- Linux DVB-C tuner supported by the kernel
- Python 3
- `dvbv5-zap` from `dvb-tools`
- `tshark` / Wireshark with DOCSIS dissectors

Debian/Ubuntu:

```bash
sudo apt install python3 dvb-tools tshark
```

The user running the program also needs permission to access the DVB adapter.

## Quick start

Copy and adapt the example tuning configuration:

```bash
cp docsis-all.conf.example ~/docsis-all.conf
```

Run the monitor:

```bash
python3 docsis-active.py --config ~/docsis-all.conf --channel DOCSIS570
```

Defaults:

```text
channel:  DOCSIS570
window:   30 seconds
interval: 5 seconds
```

A different observation window can be selected with:

```bash
python3 docsis-active.py --config ~/docsis-all.conf --channel DOCSIS570 --window 60
```

## How it works

```text
DVB-C tuner
   |
   v
dvbv5-zap
   |
   | MPEG transport stream
   v
tshark DOCSIS dissector
   |
   | docsis_map.sid + docsis_map.iuc
   | keep IUC 3/4
   v
rolling unique-SID counter
```

The relevant tshark operation is conceptually equivalent to:

```bash
tshark -l -r - -Y 'docsis_map' -T fields -E separator=';' -E aggregator=',' -E occurrence=a -e docsis_map.sid -e docsis_map.iuc
```

`dvbv5-zap` is used as the DVB DVR reader rather than `cat /dev/dvb/adapter0/dvr0`. On some DVB devices direct reads can terminate on a kernel DVB buffer overrun with an error such as:

```text
Value too large for defined data type
```

`dvbv5-zap` is generally better suited to keeping the transport-stream pipeline running.

## Tuning configuration

The included `docsis-all.conf.example` contains example EuroDOCSIS 3.0 256-QAM channels using 6.952 MSym/s. Frequencies are network-specific and must be adjusted to the local cable network.

A conventional DVB-C tuner can demodulate DOCSIS 3.0 SC-QAM downstreams. It cannot normally demodulate a DOCSIS 3.1 OFDM block directly, but DOCSIS management traffic visible on the selected SC-QAM channel can still be useful for segment observation.

## Credits and related work

Background material, related projects and acknowledgements used while developing this monitor are collected in the separate **[docsis-credits](https://github.com/HanzDampfDX/docsis-credits)** repository.

## Privacy

The program keeps only SID timestamps in memory. It does not store modem MAC addresses, customer identities or payloads.

## License

MIT License. See [LICENSE](LICENSE).
