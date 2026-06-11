import os, json, time, threading, websocket, requests, random, struct, socket, subprocess
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
        if token and CHANNEL:
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


def voice_heartbeat(voice_ws, interval, name):
    while True:
        try:
            time.sleep(interval)
            voice_ws.send(json.dumps({"op": 1, "d": None}))
        except Exception:
            break


def do_voice_stream(endpoint, v_token, guild_id, user_id, session_id, bot_name, main_ws):
    from nacl.secret import SecretBox

    while True:
        try:
            voice_ws = websocket.WebSocket()
            voice_ws.connect(f"wss://{endpoint}/?v=4", timeout=None)

            vhello = json.loads(voice_ws.recv())
            v_heartbeat_interval = vhello['d']['heartbeat_interval'] / 1000.0

            voice_ws.send(json.dumps({
                "op": 0,
                "d": {
                    "server_id": guild_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "token": v_token
                }
            }))

            ssrc = None
            voice_ip = None
            voice_port = None

            while True:
                vdata = json.loads(voice_ws.recv())
                if vdata.get('op') == 1:
                    voice_ws.send(json.dumps({"op": 11, "d": None}))
                if vdata.get('op') == 2:
                    ssrc = vdata['d']['ssrc']
                    voice_ip = vdata['d']['ip']
                    voice_port = vdata['d']['port']
                    print(f"[{bot_name}] Voice READY: {voice_ip}:{voice_port} ssrc={ssrc}")
                    break
                if vdata.get('op') in (7, 9):
                    voice_ws.close()
                    raise Exception("Voice disconnected during handshake")

            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.bind(('0.0.0.0', 0))
            udp.settimeout(5)

            ip_packet = bytearray(70)
            struct.pack_into('!HHI', ip_packet, 0, 1, 70, ssrc)
            udp.sendto(bytes(ip_packet), (voice_ip, voice_port))

            try:
                resp, _ = udp.recvfrom(70)
                pub_ip = resp[8:72].rstrip(b'\x00').decode()
                pub_port = struct.unpack('!H', resp[72:74])[0]
            except Exception:
                pub_ip = "0.0.0.0"
                pub_port = udp.getsockname()[1]

            print(f"[{bot_name}] UDP: {pub_ip}:{pub_port}")

            voice_ws.send(json.dumps({
                "op": 1,
                "d": {
                    "protocol": "udp",
                    "data": {
                        "address": pub_ip,
                        "port": pub_port,
                        "mode": "xsalsa20_poly1305"
                    }
                }
            }))

            secret_key = None
            while True:
                vdata = json.loads(voice_ws.recv())
                if vdata.get('op') == 1:
                    voice_ws.send(json.dumps({"op": 11, "d": None}))
                if vdata.get('op') == 4:
                    secret_key = bytes(vdata['d']['secret_key'])
                    print(f"[{bot_name}] Got secret key, streaming video...")
                    break
                if vdata.get('op') in (7, 9):
                    udp.close()
                    voice_ws.close()
                    raise Exception("Voice disconnected during protocol")

            hb = threading.Thread(target=voice_heartbeat, args=(voice_ws, v_heartbeat_interval, bot_name), daemon=True)
            hb.start()

            box = SecretBox(secret_key)

            ffmpeg = subprocess.Popen([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=0x2f3136:s=1280x720:r=30',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                '-pix_fmt', 'yuv420p',
                '-f', 'h264', 'pipe:1'
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            seq = 0
            ts = 0

            while True:
                chunk = ffmpeg.stdout.read(4000)
                if not chunk:
                    ffmpeg.wait()
                    break

                rtp = struct.pack('!BBHII', 0x80, 96, seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc)
                nonce = os.urandom(24)
                enc = box.encrypt(chunk, nonce)

                udp.sendto(rtp + nonce + enc.ciphertext, (voice_ip, voice_port))

                seq = (seq + 1) & 0xFFFF
                ts = (ts + 1500) & 0xFFFFFFFF
                time.sleep(0.033)

            ffmpeg.terminate()
            udp.close()
            voice_ws.close()
            print(f"[{bot_name}] FFmpeg ended, restarting in 2s...")
            time.sleep(2)

        except Exception as e:
            print(f"[{bot_name}] Voice error: {e}, reconnecting in 3s...")
            time.sleep(3)


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

            ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": token.strip(),
                    "properties": {"$os": "windows", "$browser": "Discord Client", "$device": "desktop"},
                }
            }))

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

            time.sleep(2)
            print(f"[{name}] Joined voice + lobby sent")

            user_id = None
            session_id = None
            last_heartbeat = time.time()
            last_dice_roll = time.time()
            voice_started = False

            while True:
                try:
                    msg = ws.recv()
                except Exception:
                    break

                if not msg:
                    break

                data = json.loads(msg)

                if data.get('op') == 1:
                    ws.send(json.dumps({"op": 11, "d": data.get('s')}))

                if time.time() - last_heartbeat > heartbeat_interval:
                    ws.send(json.dumps({"op": 1, "d": None}))
                    last_heartbeat = time.time()

                if data.get('t') == "READY":
                    user_id = data['d']['user']['id']
                    print(f"[{name}] READY user={user_id}")

                if data.get('t') == "VOICE_STATE_UPDATE":
                    d = data['d']
                    if d.get('user_id') == user_id:
                        session_id = d.get('session_id')

                if data.get('t') == "VOICE_SERVER_UPDATE":
                    d = data['d']
                    if d.get('guild_id') == GUILD and session_id and not voice_started:
                        voice_started = True
                        ep = d['endpoint']
                        vt = d['token']
                        print(f"[{name}] VOICE_SERVER, starting voice stream...")

                        def start_voice(ep=ep, vt=vt, sid=session_id, uid=user_id):
                            nonlocal voice_started
                            try:
                                do_voice_stream(ep, vt, GUILD, uid, sid, name, ws)
                            except Exception as e:
                                print(f"[{name}] Voice error: {e}")
                            voice_started = False

                        threading.Thread(target=start_voice, daemon=True).start()

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
