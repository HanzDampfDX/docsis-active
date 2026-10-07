# docsis-active

`docsis-active.py` is a small Linux monitor for estimating DOCSIS segment activity by observing **ranging/maintenance SIDs in downstream MAP messages**.

It tunes a DOCSIS 3.0 downstream channel with `dvbv5-zap`, pipes the MPEG transport stream into `tshark`, extracts DOCSIS MAP information, and counts unique non-reserved SIDs seen with **IUC 3 or IUC 4** during a rolling time window.

The monitor can additionally track which of those ranging/maintenance SIDs also receive MAP allocations on a configured **OFDMA Upstream Channel ID (UCID)**. This provides an estimate of the DOCSIS 3.1/OFDMA-capable subset of the observed modems.

## Credits and related work

Background material, related projects and acknowledgements used while developing this monitor are collected in the separate **[docsis-credits](https://github.com/HanzDampfDX/docsis-credits)** repository.

## Example output

```text
DOCSIS Segment Monitor
======================
Kanal: DOCSIS570
Fenster: 30 Sekunden
OFDMA-UCID: 43

22:31:05 aktive Ranging-SIDs ≈ 114 | OFDMA/UCID 43 ≈ 88 (77.2 %) | ohne OFDMA-Zuteilung ≈ 26
22:31:10 aktive Ranging-SIDs ≈ 226 | OFDMA/UCID 43 ≈ 182 (80.5 %) | ohne OFDMA-Zuteilung ≈ 44
22:31:15 aktive Ranging-SIDs ≈ 318 | OFDMA/UCID 43 ≈ 263 (82.7 %) | ohne OFDMA-Zuteilung ≈ 55
22:31:20 aktive Ranging-SIDs ≈ 364 | OFDMA/UCID 43 ≈ 301 (82.7 %) | ohne OFDMA-Zuteilung ≈ 63
```

During the first observation window after startup the counters normally rise as the rolling window fills. Afterwards they fluctuate as SIDs enter and leave the window.

## What it measures

The monitor inspects DOCSIS MAP messages and records the timestamp of SIDs attached to maintenance/ranging entries:

- IUC 3 — Initial Maintenance
- IUC 4 — Station Maintenance

SID 0 and the broadcast SID `0x3fff` are ignored. A SID remains active until it has not been seen for the configured rolling window, 30 seconds by default.

In parallel, the monitor observes MAP allocations on the configured OFDMA UCID. If an active ranging SID also receives an allocation on that UCID during the same rolling window, it is included in the OFDMA/DOCSIS 3.1 subset.

For example, with:

```text
--ofdma-ucid 43
```

a ranging SID that also appears in an unambiguously UCID-43 MAP is counted as an OFDMA SID.

The implementation deliberately uses only MAP rows that can be assigned to exactly one UCID. Rows containing multiple UCID occurrences are not used for OFDMA attribution, reducing the risk of associating a SID with the wrong upstream channel.

The `≈` symbol is deliberate. The result is an **estimate based on observed MAP SIDs and allocations**, not a guaranteed exact inventory of physical cable modems or subscribers. Packet loss, CMTS implementation, channel bonding and the selected observation window can influence the result.

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
channel:     DOCSIS570
window:      30 seconds
interval:    5 seconds
ofdma-ucid:  43
```

Use a different OFDMA upstream channel ID with:

```bash
python3 docsis-active.py --config ~/docsis-all.conf --channel DOCSIS570 --ofdma-ucid 41
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
   | docsis_mgmt.upchid
   | docsis_map.sid
   | docsis_map.iuc
   v
+-----------------------------+
| IUC 3/4 -> ranging SIDs     |
| target UCID -> OFDMA SIDs   |
+-----------------------------+
   |
   v
rolling unique-SID counters
```

The relevant tshark operation is conceptually equivalent to:

```bash
tshark -l -r - -Y 'docsis_map' -T fields -E separator=';' -E aggregator=',' -E occurrence=a -e docsis_mgmt.upchid -e docsis_map.sid -e docsis_map.iuc
```

`dvbv5-zap` is used as the DVB DVR reader rather than `cat /dev/dvb/adapter0/dvr0`. On some DVB devices direct reads can terminate on a kernel DVB buffer overrun with an error such as:

```text
Value too large for defined data type
```

`dvbv5-zap` is generally better suited to keeping the transport-stream pipeline running.

## Tuning configuration

The included `docsis-all.conf.example` contains example EuroDOCSIS 3.0 256-QAM channels using 6.952 MSym/s. Frequencies are network-specific and must be adjusted to the local cable network.

A conventional DVB-C tuner can demodulate DOCSIS 3.0 SC-QAM downstreams. It cannot normally demodulate a DOCSIS 3.1 OFDM block directly, but DOCSIS management traffic visible on the selected SC-QAM channel can still be useful for segment observation.

## Privacy

The program keeps only SID timestamps in memory. It does not store modem MAC addresses, customer identities or payloads.

## License

MIT License. See [LICENSE](LICENSE).
