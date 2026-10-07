#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Estimate active DOCSIS ranging/maintenance SIDs by counting unique "
            "SIDs in MAP IUC 3/4 entries during a rolling time window and mark "
            "SIDs which also receive allocations on an OFDMA upstream channel."
        )
    )
    parser.add_argument(
        "--config",
        default="~/docsis-all.conf",
        help="dvbv5-zap channel configuration file (default: ~/docsis-all.conf)",
    )
    parser.add_argument(
        "--channel",
        default="DOCSIS570",
        help="Channel name from the dvbv5-zap config (default: DOCSIS570)",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=30.0,
        help="Rolling SID window in seconds (default: 30)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Output interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--ofdma-ucid",
        type=int,
        default=43,
        help="OFDMA upstream channel ID to track (default: 43)",
    )
    return parser.parse_args()


def require_command(name):
    path = shutil.which(name)
    if not path:
        print(f"Fehler: benötigtes Programm nicht gefunden: {name}", file=sys.stderr)
        sys.exit(2)
    return path


def parse_int_list(text):
    values = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.append(int(item))
        except ValueError:
            pass
    return values


def main():
    args = parse_args()
    config = os.path.expanduser(args.config)

    if args.window <= 0 or args.interval <= 0:
        print("Fehler: --window und --interval müssen > 0 sein", file=sys.stderr)
        return 2

    if args.ofdma_ucid < 0:
        print("Fehler: --ofdma-ucid muss >= 0 sein", file=sys.stderr)
        return 2

    if not os.path.isfile(config):
        print(f"Fehler: Konfigurationsdatei nicht gefunden: {config}", file=sys.stderr)
        return 2

    dvbv5_zap = require_command("dvbv5-zap")
    tshark_bin = require_command("tshark")

    ranging_last_seen = {}
    ofdma_last_seen = {}
    lock = threading.Lock()

    # DVB-C tunen und kompletten Transportstream nach stdout ausgeben.
    # dvbv5-zap ist hier robuster als ein direktes `cat` auf dvr0, weil
    # DVB-Pufferüberläufe den Reader sonst beenden können.
    zap = subprocess.Popen(
        [
            dvbv5_zap,
            "-c", config,
            "-P",
            "-r",
            "-o", "-",
            args.channel,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    # DOCSIS MAPs aus dem MPEG-TS dekodieren.
    # docsis_mgmt.upchid liefert bei der hier verwendeten Wireshark-Version
    # die Upstream Channel ID (UCID).
    tshark = subprocess.Popen(
        [
            tshark_bin,
            "-l",
            "-r", "-",
            "-Y", "docsis_map",
            "-T", "fields",
            "-E", "separator=;",
            "-E", "aggregator=,",
            "-E", "occurrence=a",
            "-e", "docsis_mgmt.upchid",
            "-e", "docsis_map.sid",
            "-e", "docsis_map.iuc",
        ],
        stdin=zap.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    if zap.stdout is not None:
        zap.stdout.close()

    def reader():
        if tshark.stdout is None:
            return

        for line in tshark.stdout:
            fields = line.strip().split(";")

            if len(fields) != 3:
                continue

            upchids = parse_int_list(fields[0])
            sids = parse_int_list(fields[1])
            iucs = parse_int_list(fields[2])
            now = time.monotonic()

            # Eine MAP-Zeile kann in tshark mehrere UCID-Vorkommen enthalten.
            # Für die OFDMA-Zuordnung verwenden wir nur eindeutig einem UCID
            # zuordenbare Zeilen, um SIDs nicht fälschlich UCID 43 zuzuordnen.
            unique_upchids = set(upchids)
            unambiguous_ucid = next(iter(unique_upchids)) if len(unique_upchids) == 1 else None

            with lock:
                for sid, iuc in zip(sids, iucs):
                    # Reservierte/broadcast SIDs ignorieren.
                    if sid <= 0 or sid == 16383:
                        continue

                    # Ranging / Maintenance opportunities.
                    if iuc in (3, 4):
                        ranging_last_seen[sid] = now

                    # Jede reale MAP-Zuteilung auf dem OFDMA-UCID zeigt, dass
                    # diese SID auf dem DOCSIS-3.1-Upstream verwendet wird.
                    if unambiguous_ucid == args.ofdma_ucid:
                        ofdma_last_seen[sid] = now

    threading.Thread(target=reader, daemon=True).start()

    print("DOCSIS Segment Monitor")
    print("======================")
    print(f"Kanal: {args.channel}")
    print(f"Fenster: {args.window:g} Sekunden")
    print(f"OFDMA-UCID: {args.ofdma_ucid}")
    print()

    try:
        while True:
            time.sleep(args.interval)

            if tshark.poll() is not None:
                print("tshark wurde beendet:")
                if tshark.stderr is not None:
                    print(tshark.stderr.read())
                return 1

            if zap.poll() is not None:
                print("dvbv5-zap wurde beendet.")
                return 1

            now = time.monotonic()

            with lock:
                for table in (ranging_last_seen, ofdma_last_seen):
                    stale = [
                        sid
                        for sid, ts in table.items()
                        if now - ts > args.window
                    ]
                    for sid in stale:
                        del table[sid]

                ranging_sids = set(ranging_last_seen)
                ofdma_sids = set(ofdma_last_seen)
                docsis31_sids = ranging_sids & ofdma_sids
                docsis30_only = ranging_sids - docsis31_sids

                total = len(ranging_sids)
                d31 = len(docsis31_sids)
                d30 = len(docsis30_only)
                d31_percent = (100.0 * d31 / total) if total else 0.0

            print(
                time.strftime("%H:%M:%S"),
                f"aktive Ranging-SIDs ≈ {total} | "
                f"OFDMA/UCID {args.ofdma_ucid} ≈ {d31} ({d31_percent:.1f} %) | "
                f"ohne OFDMA-Zuteilung ≈ {d30}",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\nBeendet.")
        return 0

    finally:
        for process in (tshark, zap):
            if process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    sys.exit(main())
