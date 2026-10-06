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
        description="Monitor active DOCSIS upstream data SIDs from downstream MAP messages."
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
        help="Rolling activity window in seconds (default: 30)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Output interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--iucs",
        default="5,6,9,10",
        help="Comma-separated IUCs counted as data grants (default: 5,6,9,10)",
    )
    return parser.parse_args()


def require_command(name):
    path = shutil.which(name)
    if not path:
        print(f"error: required command not found: {name}", file=sys.stderr)
        sys.exit(2)
    return path


def main():
    args = parse_args()
    config = os.path.expanduser(args.config)

    if args.window <= 0 or args.interval <= 0:
        print("error: --window and --interval must be > 0", file=sys.stderr)
        return 2

    try:
        data_iucs = {int(x.strip(), 0) for x in args.iucs.split(",") if x.strip()}
    except ValueError:
        print("error: invalid --iucs value", file=sys.stderr)
        return 2

    dvbv5_zap = require_command("dvbv5-zap")
    tshark_bin = require_command("tshark")

    last_seen = {}
    last_iuc = {}
    lock = threading.Lock()

    zap = subprocess.Popen(
        [dvbv5_zap, "-c", config, "-P", "-r", "-o", "-", args.channel],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    tshark = subprocess.Popen(
        [
            tshark_bin,
            "-l",
            "-r",
            "-",
            "-Y",
            "docsis_map",
            "-T",
            "fields",
            "-E",
            "separator=;",
            "-E",
            "aggregator=,",
            "-E",
            "occurrence=a",
            "-e",
            "docsis_map.sid",
            "-e",
            "docsis_map.iuc",
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
            fields = line.rstrip("\n").split(";")
            if len(fields) != 2:
                continue

            sids = fields[0].split(",")
            iucs = fields[1].split(",")
            now = time.monotonic()

            for sid_text, iuc_text in zip(sids, iucs):
                try:
                    sid = int(sid_text, 0)
                    iuc = int(iuc_text, 0)
                except ValueError:
                    continue

                if iuc not in data_iucs:
                    continue

                if sid <= 0 or sid == 0x3FFF:
                    continue

                with lock:
                    last_seen[sid] = now
                    last_iuc[sid] = iuc

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    print("DOCSIS Active Data SID Monitor")
    print("==============================")
    print(f"Channel: {args.channel}")
    print(f"Window: {args.window:g} s")
    print("Data IUCs: " + ",".join(str(x) for x in sorted(data_iucs)))
    print()

    try:
        while True:
            time.sleep(args.interval)

            if zap.poll() is not None:
                print("error: dvbv5-zap terminated unexpectedly", file=sys.stderr)
                return 1

            if tshark.poll() is not None:
                print("error: tshark terminated unexpectedly", file=sys.stderr)
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
                    last_seen.pop(sid, None)
                    last_iuc.pop(sid, None)

                total = len(last_seen)
                counts = {iuc: 0 for iuc in data_iucs}
                for sid in last_seen:
                    counts[last_iuc[sid]] = counts.get(last_iuc[sid], 0) + 1

            detail = "  ".join(
                f"IUC{iuc}={counts.get(iuc, 0)}" for iuc in sorted(data_iucs)
            )
            print(
                time.strftime("%H:%M:%S"),
                f"active data SIDs: {total:4d}",
                detail,
                flush=True,
            )

    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        tshark.terminate()
        zap.terminate()


if __name__ == "__main__":
    sys.exit(main())
