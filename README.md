# docsis-active

`docsis-active.py` is a small Linux monitor for passively observing **active DOCSIS upstream data SIDs** from downstream MAP messages.

It tunes a DOCSIS 3.0 downstream channel with `dvbv5-zap`, pipes the MPEG transport stream into `tshark`, decodes DOCSIS MAP messages, and counts unique SIDs that received data grants during a rolling time window.

## What it measures

By default the monitor counts SIDs seen with these Interval Usage Codes (IUCs):

- IUC 5 — Short Data Grant
- IUC 6 — Long Data Grant
- IUC 9 — Advanced PHY Short Data Grant
- IUC 10 — Advanced PHY Long Data Grant

A result such as:

```text
22:31:25 active data SIDs: 354  IUC5=134  IUC6=125  IUC9=50  IUC10=45
```

means that **354 distinct SIDs received at least one upstream data grant during the configured rolling window**.

### Important limitation

An active SID is **not necessarily one physical cable modem or one subscriber**. DOCSIS uses SIDs for upstream service flows and scheduling. A modem can have more than one service flow/SID, and SID assignments are temporary. Therefore this tool should be used as a **segment activity indicator**, not as an exact subscriber counter.

The tool also does **not** identify subscribers, decode payload data, or calculate exact per-modem throughput.

## Requirements

- Linux DVB-C tuner supported by the kernel
- Python 3
- `dvbv5-zap` from `dvb-tools`
- `tshark` / Wireshark with DOCSIS dissectors

On Debian/Ubuntu:

```bash
sudo apt install python3 dvb-tools tshark
```

The user running the monitor needs permission to access the DVB adapter, typically through membership in the appropriate device group.

## Quick start

Copy the example tuning file and adjust it for your network:

```bash
cp docsis-all.conf.example ~/docsis-all.conf
```

Then run:

```bash
./docsis-active.py --config ~/docsis-all.conf --channel DOCSIS570
```

Default settings:

- rolling window: 30 seconds
- output interval: 5 seconds
- data IUCs: 5,6,9,10

Example with a 60-second window:

```bash
./docsis-active.py --config ~/docsis-all.conf --channel DOCSIS570 --window 60
```

## Example output

```text
DOCSIS Active Data SID Monitor
==============================
Channel: DOCSIS570
Window: 30 s
Data IUCs: 5,6,9,10

22:31:15 active data SIDs: 318  IUC5=121  IUC6=110  IUC9=46  IUC10=41
22:31:20 active data SIDs: 342  IUC5=128  IUC6=121  IUC9=49  IUC10=44
22:31:25 active data SIDs: 354  IUC5=134  IUC6=125  IUC9=50  IUC10=45
```

## How it works

The processing chain is:

```text
DVB-C tuner
   |
   v
dvbv5-zap
   |
   | MPEG-TS
   v
tshark DOCSIS dissector
   |
   | DOCSIS MAP: SID + IUC
   v
rolling unique-SID counter
```

`dvbv5-zap` is used as the transport-stream reader rather than directly reading `/dev/dvb/adapter*/dvr0` with `cat`. This is more robust on systems where direct reads can terminate with DVB buffer-overrun errors such as `Value too large for defined data type`.

## Tuning configuration

The included `docsis-all.conf.example` contains an example EuroDOCSIS 3.0 256-QAM / 6.952 MSym/s channel set. Frequencies are network-specific; verify the downstream frequencies for your own cable segment.

DOCSIS 3.1 OFDM blocks cannot normally be demodulated by a conventional DVB-C tuner. This tool relies on DOCSIS MAP messages carried on a demodulatable DOCSIS 3.0 SC-QAM downstream.

## Privacy and scope

The monitor intentionally keeps only transient SID timestamps in memory. It does not store cable-modem MAC addresses, customer identities, or user payloads.

## License

MIT License. See [LICENSE](LICENSE).
