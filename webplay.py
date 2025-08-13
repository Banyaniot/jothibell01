import websocket
import subprocess
import tempfile
import os

# --------------------------
# CONFIG
# --------------------------
SERVER_URL = "wss://bellapi.jothiengg.com/audio"

def on_message(ws, message):
    """Handle incoming audio data."""
    if isinstance(message, str):
        # Server sent text message instead of binary audio
        print("[Server Text]", message)
        return

    try:
        # Save chunk to a temporary WAV file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(message)
            tmp_path = tmp.name

        # Play audio (blocking until finished)
        subprocess.run(["aplay", "-q", tmp_path])

        # Delete file after playback
        os.remove(tmp_path)

    except Exception as e:
        print(f"[Error] {e}")

def on_open(ws):
    print("? Connected to audio server, waiting for stream...")

def on_close(ws, close_status_code, close_msg):
    print("? Disconnected from server")

def on_error(ws, error):
    print(f"[WebSocket Error] {error}")

if __name__ == "__main__":
    ws = websocket.WebSocketApp(
        SERVER_URL,
        on_message=on_message,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error
    )
    ws.run_forever()
