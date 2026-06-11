import os, json, time, threading, websocket, requests, random
from flask import Flask

app = Flask('')
@app.route('/')
def home(): return "Sentinel XP-Lock: Active"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

GUILD = int(os.getenv("GUILD"))
CHANNEL = int(os.getenv("CHANNEL"))

tokens = {
    "Sentinel 1": os.getenv("TOKEN_ONE"),
    "Sentinel 2": os.getenv("TOKEN_TWO"),
    "Sentinel XP": os.getenv("TOKEN_XP")
}


def send_periodic_msg(token, name):
    while True:
        if token:
            url = f"https://discord.com/api/v9/channels/{CHANNEL}/messages"
            headers = {"Authorization": token.strip(), "Content-Type": "application/json"}
            payload = {"content": ""}
            try:
                res = requests.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    print(f"Message sent by {name}.")
                else:
                    print(f"{name} failed: {res.status_code}")
            except Exception as e:
                print(f"{name} message error: {e}")
        time.sleep(3600)


def vc_locker(token, name, is_xp_token=False):
    if not token:
        print(f"{name} token missing.")
        return

    while True:
        try:
            ws = websocket.WebSocket()
            ws.connect('wss://gateway.discord.gg/?v=9&encoding=json')

            hello = json.loads(ws.recv())
            heartbeat_interval = hello['d']['heartbeat_interval'] / 1000.0
            print(f"[{name}] Connected, heartbeat={heartbeat_interval}s")

            ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": token.strip(),
                    "properties": {"$os": "windows", "$browser": "Discord Client", "$device": "desktop"},
                }
            }))
            print(f"[{name}] IDENTIFY sent")

            time.sleep(0.5)

            ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": GUILD,
                    "channel_id": CHANNEL,
                    "self_mute": False,
                    "self_deaf": False,
                    "self_stream": True,
                    "self_video": True
                }
            }))
            print(f"[{name}] JOIN sent (stream=True, video=True)")

            time.sleep(1)

            ws.send(json.dumps({
                "op": 18,
                "d": {
                    "type": "guild",
                    "guild_id": GUILD,
                    "channel_id": CHANNEL,
                    "preferred_region": "singapore"
                }
            }))
            print(f"[{name}] LOBBY sent")

            time.sleep(2)
            print(f"[{name}] Streaming! Starting leave/rejoin loop...")

            while True:
                time.sleep(1)

                ws.send(json.dumps({
                    "op": 4,
                    "d": {
                        "guild_id": GUILD,
                        "channel_id": None,
                        "self_mute": False,
                        "self_deaf": False,
                        "self_stream": True,
                        "self_video": True
                    }
                }))

                time.sleep(1)

                ws.send(json.dumps({
                    "op": 4,
                    "d": {
                        "guild_id": GUILD,
                        "channel_id": CHANNEL,
                        "self_mute": False,
                        "self_deaf": False,
                        "self_stream": True,
                        "self_video": True
                    }
                }))

        except Exception as e:
            print(f"[{name}] ERROR: {e}")
            time.sleep(10)


if __name__ == "__main__":
    print(f"Guild: {GUILD}, Channel: {CHANNEL}")
    threading.Thread(target=run_web, daemon=True).start()

    threads = []
    for name, token in tokens.items():
        if token:
            is_xp = (name == "Sentinel XP")
            vt = threading.Thread(target=vc_locker, args=(token, name, is_xp))
            vt.start()
            threads.append(vt)
            mt = threading.Thread(target=send_periodic_msg, args=(token, name), daemon=True)
            mt.start()
            time.sleep(5)

    for t in threads:
        t.join()
