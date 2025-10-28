#!/usr/bin/env python3
r"""
Simple automated WebSocket test for the basic_chatbot project.

What it does:
- Connects to the backend WebSocket endpoint (default ws://localhost:8080/ws/chat)
- Sends a start message with a generated requestId and user message
- Receives streaming chunks (handles both SSE-style 'data: {...}' frames and plain JSON)
- Optionally cancels after N chunks or waits until 'done' received

Usage (PowerShell on Windows):
  cd "c:\Users\Admin\Desktop\Tuan\Demo project\basic_chatbot"
  python -m pip install websocket-client
  python scripts\ws_test.py --message "Hello from test" --cancel-after 3

Arguments:
  --url            WebSocket URL (default ws://localhost:8080/ws/chat)
  --message        Message text to ask the bot
  --timeout        Timeout seconds to wait for completion (default 30)
  --cancel-after   Number of chunks after which the script will send a cancel (optional)

Exit code: 0 on success (received done or cancelled), 2 on timeout, 1 on error
"""

import argparse
import json
import re
import threading
import time
import uuid
import sys

try:
    import websocket
except Exception as e:
    print("Missing dependency 'websocket-client'. Install with: python -m pip install websocket-client")
    raise


def parse_sse_text(text):
    """Extract JSON objects from SSE-like text blocks. Returns list of parsed dicts or raw strings."""
    out = []
    # SSE events are separated by blank lines
    parts = re.split(r"\r?\n\r?\n", text)
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = re.search(r"data:\s*(\{.*\})", p, flags=re.S)
        if m:
            try:
                out.append(json.loads(m.group(1)))
            except Exception:
                out.append(p)
        else:
            # try raw json fallback
            try:
                out.append(json.loads(p))
            except Exception:
                out.append(p)
    return out


def run_test(url, message_text, timeout, cancel_after):
    request_id = "r-" + str(int(time.time() * 1000))
    received_chunks = []
    done_event = threading.Event()
    ws_error = [None]

    def on_message(ws, evt):
        payload = evt
        # evt may be a string; websocket-client delivers text as str
        # Try SSE parsing first
        objs = []
        if isinstance(payload, str) and "data:" in payload:
            objs = parse_sse_text(payload)
        else:
            # try direct json
            try:
                objs = [json.loads(payload)]
            except Exception:
                objs = [payload]

        for o in objs:
            if isinstance(o, dict):
                # chunk style
                if 'chunk' in o or 'request_id' in o:
                    # normalize
                    rid = o.get('request_id') or o.get('requestId') or request_id
                    chunk = o.get('chunk')
                    if chunk is not None:
                        received_chunks.append((rid, chunk))
                        print(f"CHUNK [{rid}]: {chunk}")
                        # maybe auto cancel
                        if cancel_after and len(received_chunks) >= cancel_after and not done_event.is_set():
                            print("Auto-canceling (test) after", cancel_after, "chunks")
                            ws.send(json.dumps({"requestId": request_id, "cancel": True}))
                    if o.get('done') or o.get('status') == 'done':
                        print(f"DONE [{rid}]")
                        done_event.set()
                elif o.get('cancelled'):
                    print(f"CANCELLED [{o.get('request_id') or o.get('requestId')}]")
                    done_event.set()
                else:
                    print("MSG:", o)
            else:
                print("RAW:", o)

    def on_error(ws, err):
        print('WS ERROR:', err)
        ws_error[0] = err
        done_event.set()

    def on_close(ws, code, reason):
        print('WS CLOSED', code, reason)
        done_event.set()

    def on_open(ws):
        print('WS OPEN — sending start message, request_id=', request_id)
        msg = {"requestId": request_id, "message": message_text}
        ws.send(json.dumps(msg))

    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(url,
                                on_open=lambda w: on_open(w),
                                on_message=lambda w, m: on_message(w, m),
                                on_error=lambda w, e: on_error(w, e),
                                on_close=lambda w, c, r: on_close(w, c, r))

    # run socket in thread
    thr = threading.Thread(target=ws.run_forever, kwargs={})
    thr.daemon = True
    thr.start()

    finished = done_event.wait(timeout)
    if not finished:
        print('TEST TIMEOUT after', timeout, 'seconds')
        return 2
    if ws_error[0]:
        return 1
    print('Test finished — received', len(received_chunks), 'chunks')
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='ws://localhost:8080/ws/chat')
    p.add_argument('--message', default='Hello from automated test')
    p.add_argument('--timeout', type=int, default=30)
    p.add_argument('--cancel-after', type=int, default=0,
                   help='If >0, auto-sends cancel after this many chunks')
    args = p.parse_args()

    code = run_test(args.url, args.message, args.timeout, args.cancel_after if args.cancel_after > 0 else None)
    sys.exit(code)


if __name__ == '__main__':
    main()
