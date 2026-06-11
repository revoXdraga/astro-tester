import os, json, time, threading, websocket, requests, random
from flask import Flask

# --- FLASK WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "🛰️ Sentinel XP-Lock: Active"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- CONFIG ---
GUILD_ID = os.getenv("GUILD")
CHANNEL_ID = os.getenv("CHANNEL")

# Added TOKEN_XP to the dictionary
tokens = {
    "Sentinel 1": os.getenv("TOKEN_ONE"),
    "Sentinel 2": os.getenv("TOKEN_TWO"),
    "Sentinel XP": os.getenv("TOKEN_XP") 
}

# --- 2-HOUR MESSAGE FUNCTION ---
def send_periodic_msg(token, name):
    while True:
        if token:
            url = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/messages"
            headers = {"Authorization": token.strip(), "Content-Type": "application/json"}
            payload = {"content": ""}
            try:
                res = requests.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    print(f"📅 Message 'd' sent by {name}.")
                else:
                    print(f"⚠️ {name} failed: {res.status_code}")
            except Exception as e:
                print(f"⚠️ {name} message error: {e}")
        
        # Original 11s/2h logic (Change to 7200 for 2 hours)
        time.sleep(3600) 

def vc_locker(token, name, is_xp_token=False):
    if not token:
        print(f"⚠️ {name} token missing.")
        return

    while True:
        try:
            ws = websocket.WebSocket()
            ws.connect('wss://gateway.discord.gg/?v=9&encoding=json', timeout=15)
            
            ws.send(json.dumps({
                "op": 2, 
                "d": {
                    "token": token.strip(), 
                    "properties": {"$os": "windows", "$browser": "Chrome", "$device": ""},
                    "presence": {"status": "online", "afk": False}
                }
            }))

            join_payload = {
                "op": 4, 
                "d": {
                    "guild_id": GUILD_ID, 
                    "channel_id": CHANNEL_ID,
                    "self_mute": False, "self_deaf": False,
                    "self_video": False, "self_stream": True
                }
            }

            last_heartbeat = 0
            user_id = None
            last_dice_roll = time.time()

            while True:
                msg = ws.recv()
                if not msg: break
                data = json.loads(msg)
                
                if data.get('op') == 10:
                    ws.send(json.dumps(join_payload))

                if data.get('t') == "READY":
                    user_id = data['d']['user']['id']
                    print(f"✅ {name} connected.")

                # --- THE WAVY XP LOGIC ---
                # Only runs if this is the TOKEN_XP slot
                if is_xp_token and (time.time() - last_dice_roll > 60):
                    if random.randint(1, 400) == 77:
                        print(f"📉 {name}: Disconnecting for wavy line XP.")
                        break # Break out to trigger the 7-min sleep
                    last_dice_roll = time.time()

                if data.get('t') == "VOICE_STATE_UPDATE":
                    if data['d'].get('user_id') == user_id:
                        if data['d'].get('channel_id') != CHANNEL_ID:
                            time.sleep(1)
                            ws.send(json.dumps(join_payload))

                if time.time() - last_heartbeat > 30:
                    ws.send(json.dumps({"op": 1, "d": data.get('s')}))
                    ws.send(json.dumps(join_payload)) 
                    last_heartbeat = time.time()

            ws.close()
            if is_xp_token:
                # Random 7 minute gap for the wavy line
                time.sleep(random.randint(400, 450))

        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    threads = []
    for name, token in tokens.items():
        if token:
            # Check if this is the XP token to apply the disconnect logic
            is_xp = (name == "Sentinel XP")
            
            vt = threading.Thread(target=vc_locker, args=(token, name, is_xp))
            vt.start()
            threads.append(vt)
            
            mt = threading.Thread(target=send_periodic_msg, args=(token, name), daemon=True)
            mt.start()
            
            time.sleep(5) 

    for t in threads:
        t.join()
        