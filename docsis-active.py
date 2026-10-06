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
            "Estimate active DOCSIS cable modems by counting unique SIDs "
            "seen in Ranging Response messages during a rolling time window."
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
        help="Rolling ranging-SID window in seconds (default: 30)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Output interval in seconds (default: 5)",
    )
    return parser.parse_args()


def require_command(name):
    path = shutil.which(name)
    if not path:
        print(f"Fehler: benötigtes Programm nicht gefunden: {name}", file=sys.stderr)
        sys.exit(2)
    return path


def main():
    args = parse_args()
    config = os.path.expanduser(args.config)

    if args.window <= 0 or args.interval <= 0:
        print("Fehler: --window und --interval müssen > 0 sein", file=sys.stderr)
        return 2

    if not os.path.isfile(config):
        print(f"Fehler: Konfigurationsdatei nicht gefunden: {config}", file=sys.stderr)
        return 2

    dvbv5_zap = require_command("dvbv5-zap")
    tshark_bin = require_command("tshark")

    last_seen = {}
    lock = threading.Lock()

    # Tune the selected DOCSIS downstream channel and write the full MPEG-TS
    # to stdout. Using dvbv5-zap as reader is more robust than `cat dvr0`
    # on DVB devices that may report EOVERFLOW/buffer overruns.
    zap = subprocess.Popen(
        [dvbv5_zap, "-c", config, "-P", "-r", "-o", "-", args.channel],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    # Decode DOCSIS Ranging Response messages. A SID is recorded whenever
    # tshark exposes docsis_rngrsp.sid in the downstream transport stream.
    tshark = subprocess.Popen(
        [
            tshark_bin,
            "-l",
            "-r",
            "-",
            "-Y",
            "docsis_rngrsp.sid",
            "-T",
            "fields",
            "-E",
            "aggregator=,",
            "-E",
            "occurrence=a",
            "-e",
            "docsis_rngrsp.sid",
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
            now = time.monotonic()

            for sid_text in line.strip().split(","):
                sid_text = sid_text.strip()
                if not sid_text:
                    continue

                try:
                    sid = int(sid_text, 0)
                except ValueError:
                    continue

                # Ignore reserved/special values if they appear.
                if sid <= 0 or sid == 0x3FFF:
                    continue

                with lock:
                    last_seen[sid] = now

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    print("DOCSIS Segment Monitor")
    print("======================")
    print(f"Kanal: {args.channel}")
    print(f"Fenster: {args.window:g} Sekunden")
    print()

    try:
        while True:
            time.sleep(args.interval)

            if zap.poll() is not None:
                print("Fehler: dvbv5-zap wurde unerwartet beendet.", file=sys.stderr)
                return 1

            if tshark.poll() is not None:
                print("Fehler: tshark wurde unerwartet beendet.", file=sys.stderr)
                if tshark.stderr is not None:
                    error_text = tshark.stderr.read().strip()
                    if error_text:
                        print(error_text, file=sys.stderr)
                return 1

            now = time.monotonic()
            cutoff = now - args.window

            with lock:
                stale = [sid for sid, ts in last_seen.items() if ts < cutoff]
                for sid in stale:
                    del last_seen[sid]
                count = len(last_seen)

            print(
                time.strftime("%H:%M:%S"),
                f"aktive Ranging-SIDs ≈ {count}",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\nBeendet.")
        return 0
    finally:
        for process in (tshark, zap):
            if process.poll() is None:
                process.terminate()
        for process in (tshark, zap):
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())
