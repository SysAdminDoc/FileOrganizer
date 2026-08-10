import argparse
import json
import time


def emit(event):
    print(json.dumps(event, separators=(",", ":")), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.01)
    args = parser.parse_args()

    emit({
        "event": "handshake",
        "protocol_version": "1.0",
        "sequence": 0,
        "sidecar": "runner-fixture",
        "capabilities": {},
    })
    for index in range(args.count):
        time.sleep(args.delay)
        emit({
            "event": "item",
            "protocol_version": "1.0",
            "sequence": index + 1,
            "path": f"fixture-{index}",
        })
    emit({
        "event": "complete",
        "protocol_version": "1.0",
        "sequence": args.count + 1,
        "status": "ok",
        "total": args.count,
        "terminal": True,
    })


if __name__ == "__main__":
    main()
