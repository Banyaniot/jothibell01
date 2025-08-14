import websocket
import subprocess
from pydub import AudioSegment
import io

SERVER_URL = "wss://bellapi.jothiengg.com/audio"

# Start aplay in stdin mode (16-bit, 16kHz, mono example - adjust if needed)
aplay_proc = subprocess.Popen(["aplay", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1"], stdin=subprocess.PIPE)

def normalize_audio(wav_bytes, target_dBFS=-20.0):
    """Normalize audio volume to target dBFS."""
    try:
        audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        change_in_dBFS = target_dBFS - audio.dBFS
        normalized_audio = audio.apply_gain(change_in_dBFS)
        return normalized_audio.raw_data
    except Exception as e:
        print(f"[Normalize Error] {e}")
        return wav_bytes  # fallback to original if normalization fails

def on_message(ws, message):
    """Handle incoming audio data."""
    if isinstance(message, str):
        print("[Server Text]", message)
        return

    try:
        # Normalize volume
        normalized_data = normalize_audio(message)

        # Send to aplay
        aplay_proc.stdin.write(normalized_data)
        aplay_proc.stdin.flush()
    except Exception as e:
        print(f"[Error] {e}")

def on_open(ws):
    print("Connected to audio server, waiting for stream...")

def on_close(ws, close_status_code, close_msg):
    print("Disconnected from server")
    try:
        aplay_proc.stdin.close()
        aplay_proc.wait()
    except:
        pass

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
