import os, json, time, threading, websocket, requests, random, struct
from flask import Flask

app = Flask('')
@app.route('/')
def home(): return "Sentinel XP-Lock: Active"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

GUILD_ID = os.getenv("GUILD")
CHANNEL_ID = os.getenv("CHANNEL")

tokens = {
    "Sentinel 1": os.getenv("TOKEN_ONE"),
    "Sentinel 2": os.getenv("TOKEN_TWO"),
    "Sentinel XP": os.getenv("TOKEN_XP")
}

SILENCE_FRAME = b'\xf8\xff\xfe'


def do_voice(endpoint, v_token, guild_id, user_id, session_id, bot_name):
    from nacl.secret import SecretBox
    print(f"[{bot_name}] Starting voice connection to {endpoint}")

    voice_ws = websocket.WebSocket()
    voice_ws.connect(f"wss://{endpoint}/?v=4", timeout=15)
    print(f"[{bot_name}] Connected to voice gateway")

    vhello = json.loads(voice_ws.recv())
    v_heartbeat_interval = vhello['d']['heartbeat_interval'] / 1000.0
    print(f"[{bot_name}] Voice HELLO received, heartbeat={v_heartbeat_interval}s")

    voice_ws.send(json.dumps({
        "op": 0,
        "d": {
            "server_id": guild_id,
            "user_id": user_id,
            "session_id": session_id,
            "token": v_token
        }
    }))
    print(f"[{bot_name}] Voice IDENTIFY sent")

    v_heartbeat = time.time()
    ssrc = None
    secret_key = None

    while True:
        vmsg = voice_ws.recv()
        if not vmsg:
            print(f"[{bot_name}] Voice WS closed")
            voice_ws.close()
            return
        vdata = json.loads(vmsg)
        op = vdata.get('op')
        print(f"[{bot_name}] Voice op={op}")

        if op == 1:
            voice_ws.send(json.dumps({"op": 11, "d": None}))

        if time.time() - v_heartbeat > v_heartbeat_interval:
            voice_ws.send(json.dumps({"op": 1, "d": None}))
            v_heartbeat = time.time()

        if op == 2:
            ssrc = vdata['d']['ssrc']
            print(f"[{bot_name}] Voice READY, ssrc={ssrc}")

            voice_ws.send(json.dumps({
                "op": 1,
                "d": {
                    "protocol": "udp",
                    "data": {
                        "address": "0.0.0.0",
                        "port": 0,
                        "mode": "xsalsa20_poly1305"
                    }
                }
            }))
            print(f"[{bot_name}] SELECT_PROTOCOL sent")

        if op == 4:
            secret_key = vdata['d']['secret_key']
            print(f"[{bot_name}] SESSION_DESCRIPTION received, key={len(secret_key)} bytes")
            break

        if op in (7, 9):
            print(f"[{bot_name}] Voice disconnected op={op}")
            voice_ws.close()
            return

    box = SecretBox(bytes(secret_key))
    sequence = 0
    timestamp = 0
    print(f"[{bot_name}] Starting to send silence frames...")

    while True:
        try:
            header = struct.pack('!BBHII',
                0x80, 0x78,
                sequence & 0xFFFF,
                timestamp & 0xFFFFFFFF,
                ssrc
            )
            nonce = os.urandom(24)
            encrypted = box.encrypt(SILENCE_FRAME, nonce)

            voice_ws.send(header + nonce + encrypted.ciphertext, opcode=2)

            sequence = (sequence + 1) & 0xFFFF
            timestamp = (timestamp + 960) & 0xFFFFFFFF
            time.sleep(0.02)
        except Exception as e:
            print(f"[{bot_name}] Voice send error: {e}")
            break

    voice_ws.close()
    print(f"[{bot_name}] Voice connection closed")


def send_periodic_msg(token, name):
    while True:
        if token:
            url = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/messages"
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
            print(f"[{name}] Connecting to gateway...")
            ws = websocket.WebSocket()
            ws.connect('wss://gateway.discord.gg/?v=9&encoding=json', timeout=15)

            hello = json.loads(ws.recv())
            heartbeat_interval = hello['d']['heartbeat_interval'] / 1000.0

            ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": token.strip(),
                    "properties": {"$os": "windows", "$browser": "Chrome", "$device": ""},
                    "presence": {"status": "online", "afk": False}
                }
            }))

            user_id = None
            session_id = None
            last_heartbeat = time.time()
            last_dice_roll = time.time()
            voice_thread = None

            while True:
                try:
                    msg = ws.recv()
                except:
                    break

                if not msg: break
                data = json.loads(msg)

                if data.get('op') == 1:
                    ws.send(json.dumps({"op": 11, "d": data.get('s')}))

                if time.time() - last_heartbeat > heartbeat_interval:
                    ws.send(json.dumps({"op": 1, "d": None}))
                    last_heartbeat = time.time()

                if data.get('t') == "READY":
                    user_id = data['d']['user']['id']
                    print(f"[{name}] READY, user_id={user_id}")

                    print(f"[{name}] Sending: JOIN channel={CHANNEL_ID}")
                    ws.send(json.dumps({
                        "op": 4,
                        "d": {
                            "guild_id": GUILD_ID,
                            "channel_id": CHANNEL_ID,
                            "self_mute": False,
                            "self_deaf": False,
                            "self_stream": True,
                            "self_video": True
                        }
                    }))

                    time.sleep(0.5)

                    print(f"[{name}] Sending: LEAVE")
                    ws.send(json.dumps({
                        "op": 4,
                        "d": {
                            "guild_id": GUILD_ID,
                            "channel_id": None,
                            "self_mute": False,
                            "self_deaf": False,
                            "self_stream": True,
                            "self_video": True
                        }
                    }))

                    time.sleep(0.5)

                    print(f"[{name}] Sending: REJOIN channel={CHANNEL_ID}")
                    ws.send(json.dumps({
                        "op": 4,
                        "d": {
                            "guild_id": GUILD_ID,
                            "channel_id": CHANNEL_ID,
                            "self_mute": False,
                            "self_deaf": False,
                            "self_stream": True,
                            "self_video": True
                        }
                    }))

                if data.get('t') == "VOICE_STATE_UPDATE":
                    d = data['d']
                    if d.get('user_id') == user_id:
                        old_sid = session_id
                        session_id = d.get('session_id')
                        print(f"[{name}] VOICE_STATE_UPDATE: channel={d.get('channel_id')} session={session_id}")

                if data.get('t') == "VOICE_SERVER_UPDATE":
                    d = data['d']
                    if d.get('guild_id') == GUILD_ID and session_id:
                        endpoint = d['endpoint']
                        v_token = d['token']
                        print(f"[{name}] VOICE_SERVER_UPDATE: endpoint={endpoint}")

                        if voice_thread is None or not voice_thread.is_alive():
                            def run_voice(ep=endpoint, vt=v_token, sid=session_id, uid=user_id):
                                try:
                                    do_voice(ep, vt, GUILD_ID, uid, sid, name)
                                except Exception as e:
                                    print(f"[{name}] Voice thread error: {e}")

                            voice_thread = threading.Thread(target=run_voice, daemon=True)
                            voice_thread.start()

                if is_xp_token and (time.time() - last_dice_roll > 60):
                    if random.randint(1, 400) == 77:
                        print(f"{name}: Disconnecting for wavy line XP.")
                        break
                    last_dice_roll = time.time()

            ws.close()
            if is_xp_token:
                time.sleep(random.randint(400, 450))

        except Exception as e:
            print(f"{name} error: {e}")
            time.sleep(10)


if __name__ == "__main__":
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
