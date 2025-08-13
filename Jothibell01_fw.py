#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  Jothibell_v3.py
#  
#  Copyright 2025  <pi@raspberrypi>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  sudo apt install mpg123
#sudo pip install paho-mqtt --break-system-packages

import socket
from flask import Flask, render_template_string, request, redirect, url_for
import os
import json
import threading
import time
import datetime
import subprocess
from gtts import gTTS
import re
import paho.mqtt.client as mqtt
import requests 
import time
from datetime import datetime
import serial
import socket
import pyaudio
from flask import Flask
from flask_socketio import SocketIO


from flask import Flask, render_template, request

app = Flask(__name__)
socketio = SocketIO(app)

# PyAudio setup
p = pyaudio.PyAudio()
audio_stream = None
mic_process = None
current_process = None
app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
SCHEDULE_FILE = 'schedule.json'
ALLOWED_EXTENSIONS = {'wav', 'mp3'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MQTT_BROKER = "103.207.4.72"  # Or your broker IP
MQTT_PORT = 4000
MQTT_TOPIC = "schoolbell/schedule"
MQTT_TOPIC_PUBLISH = "schoolbell/status"



# UART setup (adjust device if needed)
ser = serial.Serial("/dev/serial0", baudrate=9600, timeout=1)
# Global relay state list
relay_states = [0] * 8
# Port number for communication
PORT = 5002

# Global variable to store current relay state
current_speaker_zone = "off"
current_label = ""
lock = threading.Lock()

# Create schedule file if not exists
if not os.path.exists(SCHEDULE_FILE):
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump([], f)



@socketio.on('connect')
def handle_connect():
    global audio_stream
    print("[âœ“] Mic client connected")
    if audio_stream is None:
        audio_stream = p.open(format=pyaudio.paInt16,
                              channels=1,
                              rate=48000,
                              output=True,
                              frames_per_buffer=1024)
        print("[âœ“] Audio output stream opened")

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    if audio_stream:
        audio_stream.write(data)

@socketio.on('stop_recording')
def handle_stop():
    print("[âœ“] Mic stream stopped")



def get_rpi_serial():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.strip().split(':')[1].strip()
    except Exception as e:
        print(f"âš ï¸ Failed to read RPi serial: {e}")
    return "0000000000000000"
        
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        print(f"?? Could not detect local IP: {e}")
        return "127.0.0.1"

def send_relay_command(speaker_zone, label=""):
    if isinstance(speaker_zone, str):
        zones = [z.strip().lower() for z in speaker_zone.split(",")]
    elif isinstance(speaker_zone, list):
        zones = [z.strip().lower() for z in speaker_zone]
    else:
        zones = []

    relay_states = [0] * 8
    print("Selected zones:", zones)

    zone_map = {
        "classroom1": 0,
        "classroom2": 1,
        "classroom3": 2,
        "classroom4": 3,
        "classroom5": 4,
        "classroom6": 5,
        "classroom7": 6,
        "classroom8": 7
    }

    for zone in zones:
        if zone == "all":
            relay_states = [1] * 8
            break
        elif zone == "off":
            relay_states = [0] * 8
            break
        elif zone in zone_map:
            relay_states[zone_map[zone]] = 1

    data = {
        "command": "relay",
        "relays": relay_states,
        "label": label,
        "ip": get_local_ip()
    }

    json_data = json.dumps(data)
    ser.write((json_data + "\n").encode())
    print("[UART SEND]", json_data)
    update_speaker_zone(",".join(zones), label)

# Background thread to send every 10 sec
def update_speaker_zone(zone, label):
    global current_speaker_zone, current_label
    with lock:
        current_speaker_zone = zone
        current_label = label

def auto_send_relay_command():
    global current_speaker_zone, current_label
    while True:
        try:
            with lock:
                zone = current_speaker_zone
                label = current_label
            send_relay_command(zone, label)
        except Exception as e:
            print("[Auto Relay Thread Error]", e)
        time.sleep(10)

# Start background thread
threading.Thread(target=auto_send_relay_command, daemon=True).start()

def on_connect(client, userdata, flags, rc):
    print(f"? MQTT Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    print(f"ðŸ“© MQTT Message received on {msg.topic}")
    global mic_process 
    try:
        payload = json.loads(msg.payload.decode())
        command = payload.get("command")
        data = payload.get("data", {})

        if command == "add":
            schedule = load_schedule()

            time_val = data.get("time")
            file_val = data.get("file")
            label = data.get("label", "")
            enabled = data.get("enabled", True)
            days = data.get("days", [])
            date = data.get("date", "")
            file_url = data.get("url", "")
            speaker = data.get("speaker", "default")  # âœ… Add speaker type

            if not time_val or not file_val:
                raise ValueError("Missing 'time' or 'file' in add command")

            file_path = os.path.join(UPLOAD_FOLDER, file_val)

            # Download the file if not exists
            if not os.path.exists(file_path):
                if file_url:
                    try:
                        response = requests.get(file_url)
                        response.raise_for_status()
                        with open(file_path, 'wb') as f:
                            f.write(response.content)
                        print(f"ðŸ“¥ Downloaded file from {file_url}")
                    except Exception as e:
                        raise Exception(f"Failed to download file: {e}")
                else:
                    raise Exception(f"File '{file_val}' not found and no download URL provided")

            # Add schedule entry
            schedule.append({
                "time": time_val,
                "file": file_val,
                "label": label,
                "enabled": enabled,
                "days": days,
                "date": date,
                "speaker": speaker  # âœ… Save speaker in schedule
            })
            save_schedule(schedule)

            print("âœ… Schedule added via MQTT")
            client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                "status": "success",
                "command": "add",
                "message": "Schedule added successfully"
            }))

        elif command == "delete":
            label = data.get("label", "").strip().lower()
            schedule = load_schedule()
            found = False

            for i, item in enumerate(schedule):
                if item.get("label", "").strip().lower() == label:
                    removed = schedule.pop(i)
                    save_schedule(schedule)
                    found = True
                    print(f"ðŸ—‘ï¸ Deleted schedule with label: {label}")
                    client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                        "status": "success",
                        "command": "delete",
                        "message": f"Deleted schedule with label: {label}"
                    }))
                    break

            if not found:
                print(f"âš ï¸ No schedule found with label: {label}")
                client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                    "status": "error",
                    "command": "delete",
                    "message": f"No schedule found with label: {label}"
                }))
   
   
        elif command == "speaker":
            try:
                print(f"?? Parsed MQTT data: {json.dumps(data, indent=2)}")

                # Flexible extraction: handle both "data.speaker" and "speakers"
                if "data" in data and "speaker" in data["data"]:
                    speaker_list = data["data"]["speaker"]
                elif "speakers" in data:
                    speaker_list = data["speakers"]
                else:
                    raise ValueError("Missing 'speaker' or 'speakers' value in speaker command")

                # Ensure it's a list
                if isinstance(speaker_list, str):
                    speaker_list = [speaker_list]
                elif not isinstance(speaker_list, list):
                    raise ValueError("Speaker value must be a string or list")

                # Save to file
                with open("current_speaker.txt", "w") as f:
                    f.write(",".join(speaker_list).lower())

                # Send to relay command
                send_relay_command(speaker_list, data.get('label', ''))

                print(f"? Default speaker(s) set to: {speaker_list}")
                client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                    "status": "success",
                    "command": "speaker",
                    "message": f"Default speaker(s) set to: {speaker_list}"
                }))
            except Exception as e:
                print(f"? Failed to set speaker(s): {e}")
                client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                    "status": "error",
                    "command": "speaker",
                    "message": f"Failed to set speaker(s): {str(e)}"
                }))

        elif command == "micstart":
            try:
                    # If already running, stop it first
                    if mic_process and mic_process.poll() is None:
                        print("?? micstart received, but process already running. Restarting...")
                        mic_process.terminate()

                    # Start the subprocess
                    mic_process = subprocess.Popen(
                        ["python3", "/home/satheesh/jothibell01/webplay.py"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    print("?? Microphone streaming started (webplay.py)")
            except Exception as e:
                print(f"? Failed to start mic streaming: {e}")

        elif command == "micstop":
            try:
                if mic_process and mic_process.poll() is None:
                    mic_process.terminate()
                    mic_process.wait()
                    mic_process = None
                    print("?? Microphone streaming stopped")
                else:
                    print("?? micstop received, but process not running")
            except Exception as e:
                print(f"? Failed to stop mic streaming: {e}")
                
               
        elif command == "stop":
            print("â¹ï¸ Stop command received via MQTT")
            stop_audio()  # This should stop current audio, make sure you implement it
            client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                "status": "success",
                "command": "stop",
                "message": "Audio playback stopped"
            }))

        elif command == "play":
            file_name = data.get("file")
            file_url = data.get("url", "")
            speaker = data.get("speaker", "default").lower()  # âœ… get speaker value

            if not file_name:
                raise ValueError("Missing 'file' in play command")

            file_path = os.path.join(UPLOAD_FOLDER, file_name)

            # ðŸ”½ Download the file if it doesn't exist
            if not os.path.exists(file_path):
                if file_url:
                    try:
                        response = requests.get(file_url)
                        response.raise_for_status()
                        with open(file_path, 'wb') as f:
                            f.write(response.content)
                        print(f"ðŸ“¥ Downloaded file from {file_url}")
                    except Exception as e:
                        raise Exception(f"Failed to download file: {e}")
                else:
                    raise Exception(f"File '{file_name}' not found and no download URL provided")

            # ðŸ”Š Handle speaker selection (example routing logic)
            print(f"ðŸ”Š Playing '{file_name}' on speaker: {speaker}")
            
            send_relay_command(data.get('speaker', 'indoor'), data.get('label', ''))
            play_audio(file_name)

            client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                "status": "success",
                "command": "play",
                "message": f"Playing {file_name} on speaker: {speaker}"
            }))

    except Exception as e:
        print(f"? Failed to process MQTT message: {e}")
        client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
            "status": "error",
            "message": f"Exception: {str(e)}"
        }))
        
def mqtt_publish_loop(client):
    rpi_id = get_rpi_serial()

    while True:
        try:
            version = datetime.now().isoformat()  # Current timestamp
            payload = {
                "imei": rpi_id,
                "version": version
            }

            client.publish(MQTT_TOPIC_PUBLISH, json.dumps(payload))
            print(f"?? Published: {payload}")

        except Exception as e:
            print(f"?? Error publishing MQTT: {e}")

        time.sleep(10)  # Repeat every 10 seconds


        
def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    # Start the publishing thread
    threading.Thread(target=mqtt_publish_loop, args=(client,), daemon=True).start()
    client.loop_forever()

# Start MQTT thread
threading.Thread(target=start_mqtt, daemon=True).start()


def load_schedule():
    with open(SCHEDULE_FILE) as f:
        return json.load(f)

def save_schedule(data):
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def play_audio(filename):
    global current_process
    stop_audio()
    path = os.path.join(UPLOAD_FOLDER, filename)
    if filename.endswith('.wav'):
        current_process = subprocess.Popen(['aplay', path])
    elif filename.endswith('.mp3'):
        current_process = subprocess.Popen(['mpg123', path])

def stop_audio():
    global current_process
    if current_process and current_process.poll() is None:
        current_process.terminate()
        current_process = None

def bell_scheduler():
    triggered = set()
    while True:
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M")
        today = now.strftime("%A")
        schedules = load_schedule()

        for item in schedules:
            if not item.get('enabled', False):
                continue

            if 'date' in item and item['date']:
                # Check for specific date
                if item['date'] != now.strftime("%Y-%m-%d"):
                    continue
            else:
                # Otherwise check for day match
                allowed_days = item.get('days', [])
                if allowed_days and today not in allowed_days:
                    continue

            key = (time_str, item['file'])
            if item['time'] == time_str and key not in triggered:
                print(f"?? Bell ringing at {time_str} on {today} or {item.get('date', '')}")
                # Speaker relay ON
                send_relay_command(item.get('speaker', 'indoor'), item.get('label', ''))

                play_audio(item['file'])
                triggered.add(key)

        if time_str == "00:00":
            triggered.clear()

        time.sleep(30)

HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jothi Smart School Bell System</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      padding: 20px;
      margin: auto;
      background-color: #f7f9fc;
      transition: background-color 0.3s, color 0.3s;
    }
    
    h1 {
      background-color: #4CAF50;
      color: white;
      padding: 15px;
      border-radius: 8px;
      text-align: center;
      margin-bottom: 30px;
    }
    form, table {
      margin-bottom: 30px;
      width: 100%;
      max-width: 1000px;
      margin-left: auto;
      margin-right: auto;
    }
    label, input, select, button {
      display: block;
      width: 100%;
      margin-top: 10px;
    }
    input, select, button {
      padding: 10px;
      font-size: 16px;
      border-radius: 5px;
      border: 1px solid #ccc;
    }
    button {
      background-color: #4CAF50;
      color: white;
      cursor: pointer;
      margin-top: 15px;
    }
    button:hover {
      background-color: #45a049;
    }
      .days-container {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 5px;
      }
    .days-container label {
      display: flex;
      align-items: center;
      font-weight: normal;
      }

    .table-container {
      overflow-y: auto;
      max-height: 500px;
    }
    .toggle-container {
      display: flex;
      align-items: left;
      gap: 10px;
      margin-top: 10px;
      margin-bottom: 10px;
    }

    .toggle-label {
      font-weight: 500;
      font-size: 16px;
      margin-right: 5px;
    }

    .switch {
      position: relative;
      display: inline-block;
      width: 50px;
      height: 24px;
    }

    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: #ccc;
      transition: 0.4s;
      border-radius: 24px;
    }

    .slider:before {
      position: absolute;
      content: "";
      height: 18px;
      width: 18px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: 0.4s;
      border-radius: 50%;
    }

    input:checked + .slider {
      background-color: #4CAF50;
    }

    input:checked + .slider:before {
      transform: translateX(26px);
    }
    .toggle-state {
      font-size: 14px;
      color: #555;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      background-color: #fff;
    }
    th, td {
      border: 1px solid #ccc;
      padding: 10px;
      text-align: center;
    }
    th {
      background-color: #4CAF50;
      color: white;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    .actions form {
      display: inline-block;
      margin: 0 2px;
    }
    .toast {
      visibility: hidden;
      min-width: 250px;
      background-color: #4CAF50;
      color: white;
      text-align: center;
      border-radius: 8px;
      padding: 12px;
      position: fixed;
      z-index: 1000;
      bottom: 30px;
      left: 50%;
      transform: translateX(-50%);
      box-shadow: 0px 2px 6px rgba(0,0,0,0.2);
    }
    .toast.show {
      visibility: visible;
      animation: fadein 0.5s, fadeout 0.5s 2.5s;
    }
    @keyframes fadein { from { bottom: 0; opacity: 0; } to { bottom: 30px; opacity: 1; } }
    @keyframes fadeout { from { bottom: 30px; opacity: 1; } to { bottom: 0; opacity: 0; } }

    body.dark {
      background-color: #121212;
      color: #eee;
    }
    body.dark input, body.dark select, body.dark table, body.dark button {
      background-color: #1e1e1e;
      color: #fff;
      border-color: #444;
    }
    body.dark th {
      background-color: #333;
    }
    body.dark h1 {
      background-color: #333;
    }
    body.dark button:hover {
      background-color: #555;
    }
  </style>
</head>
<body>
  <h1>
    Jothi Smart School Bell Scheduler
    <label style="float:right; font-size:14px;">
      <input type="checkbox" id="darkToggle"> Dark Mode
    </label>
  </h1>
 
       
  <form action="/upload" method="post" enctype="multipart/form-data">
    <label>Upload New Audio File:</label>
    <input type="file" name="file" required>
    <button type="submit">Upload</button>
  </form>
 <form action="/speak" method="post">
  <label>Text to Speak:</label>
  <input type="text" name="tts_text" placeholder="Enter text to speak..." required>
  <button type="submit">Speak</button>
 </form>
  <form action="/add" method="post">
    <label>Time:</label>
    <input type="time" name="time" required>
    <label>Date (Optional):</label>
    <input type="date" name="date">

    <label>Audio File:</label>
    <select name="file">
      {% for f in files %}
        <option value="{{ f }}">{{ f }}</option>
      {% endfor %}
    </select>

    <label>Label:</label>
    <input type="text" name="label" placeholder="Label (e.g., Morning Bell)">
    <label>Speaker:</label>
    <select name="speaker" required>
      <option value="default">Default</option>
      <option value="indoor">Indoor</option>
      <option value="outdoor">Outdoor</option>
    </select>
    <div style="display: flex; gap: 20px; white-space: nowrap; align-items: center;">
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Monday" style="margin-right: 5px;">Monday</label>
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Tuesday" style="margin-right: 5px;">Tuesday</label>
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Wednesday" style="margin-right: 5px;">Wednesday</label>
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Thursday" style="margin-right: 5px;">Thursday</label>
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Friday" style="margin-right: 5px;">Friday</label>
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Saturday" style="margin-right: 5px;">Saturday</label>
      <label style="display: flex; align-items: center;"><input type="checkbox" name="days" value="Sunday" style="margin-right: 5px;">Sunday</label>
    </div>

    <div class="toggle-container">
      <label class="toggle-label" for="alarmToggle">Alarm:</label>
      <label class="switch">
        <input type="checkbox"id="alarmToggle" name="enabled" checked>
        <span class="slider"></span>
      </label>
    </div>

    <a href="/mic" target="_blank" style="color: yellow;">ðŸŽ¤ Mic Stream</a>
    
   <div style="text-align: left; margin: 10px 20px;">
    <a href="{{ url_for('speaker_selection') }}">Manual Speaker Zone Control</a>
   </div>
   
    <button type="submit">Add Schedule</button>
  </form>

  <div class="table-container">
    <table>
      <tr><th>Date</th><th>Time</th><th>Sound</th><th>Label</th><th>Speaker</th><th>Days</th><th>Status</th><th>Actions</th></tr>
      {% for s in schedule %}
      <tr>
        <td>{{ s.date if s.date else "-" }}</td>
        <td>{{ s.time }}</td>
        <td>{{ s.file }}</td>
        <td>{{ s.label }}</td>
        <td>{{ s.speaker if s.speaker else "default" }}</td>
        <td>{{ ", ".join(s.days) if s.days else "Daily" }}</td>
        <td>{{ 'Enabled' if s.enabled else 'Disabled' }}</td>
        <td class="actions">
          <form action="/toggle/{{ loop.index0 }}" method="post">
            <button type="submit">{{ 'Disable' if s.enabled else 'Enable' }}</button>
          </form>
          <form action="/edit/{{ loop.index0 }}" method="get">
            <button type="submit">Edit</button>
          </form>
          <form action="/delete/{{ loop.index0 }}" method="post">
            <button type="submit">Delete</button>
          </form>
          <form action="/playnow/{{ s.file }}" method="post">
            <button type="submit">Test</button>
          </form>
          <form action="/stop" method="post">
            <button type="submit" style="background-color: #f44336;">Stop</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div id="toast" class="toast">Schedule Saved Successfully!</div>

  <script>
    const toggle = document.getElementById('darkToggle');
    toggle.addEventListener('change', () => {
      document.body.classList.toggle('dark');
      localStorage.setItem('dark', document.body.classList.contains('dark'));
    });
    if (localStorage.getItem('dark') === 'true') {
      document.body.classList.add('dark');
      toggle.checked = true;
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get("saved")) {
      const toast = document.getElementById("toast");
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 3000);
    }
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    schedule = load_schedule()
    files = os.listdir(UPLOAD_FOLDER)
    return render_template_string(HTML, schedule=schedule, files=files)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files['file']
    if file and allowed_file(file.filename):
        file.save(os.path.join(UPLOAD_FOLDER, file.filename))
    return redirect(url_for('index'))

@app.route("/add", methods=["POST"])
def add_schedule():
    time_val = request.form['time']
    file_val = request.form['file']
    label = request.form.get('label', '')
    enabled = 'enabled' in request.form
    days = request.form.getlist('days')
    date = request.form.get('date', '')
    speaker = request.form.get('speaker', 'default')  # âœ… Get speaker

    schedule = load_schedule()
    schedule.append({
        'time': time_val,
        'file': file_val,
        'label': label,
        'enabled': enabled,
        'days': days,
        'date': date,
        'speaker': speaker  # âœ… Save speaker in the schedule
    })
    save_schedule(schedule)
    return redirect(url_for('index'))


@app.route("/delete/<int:index>", methods=["POST"])
def delete_schedule(index):
    schedule = load_schedule()
    if 0 <= index < len(schedule):
        schedule.pop(index)
        save_schedule(schedule)
    return redirect(url_for('index'))

@app.route("/toggle/<int:index>", methods=["POST"])
def toggle_schedule(index):
    schedule = load_schedule()
    if 0 <= index < len(schedule):
        schedule[index]['enabled'] = not schedule[index].get('enabled', True)
        save_schedule(schedule)
    return redirect(url_for('index'))

@app.route("/stop", methods=["POST"])
def stop_now():
    stop_audio()
    return redirect(url_for('index'))

@app.route("/playnow/<filename>", methods=["POST"])
def play_now(filename):
    play_audio(filename)
    return redirect(url_for('index'))

@app.route("/speaker", methods=["GET", "POST"])
def speaker_selection():
    global current_speaker_zone

    if request.method == "POST":
        selected_zones = request.form.getlist("speaker_zone")

        # Determine and apply command
        if "AllOff" in selected_zones:
            send_relay_command("off", "speaker_zone")
            current_speaker_zone = "AllOff"
        elif "AllOn" in selected_zones:
            send_relay_command("all", "speaker_zone")
            current_speaker_zone = "AllOn"
        else:
            for zone in selected_zones:
                send_relay_command(zone, "speaker_zone")
            current_speaker_zone = ", ".join(selected_zones)

        return redirect(url_for("speaker_selection"))

    return render_template("speaker.html", speaker_zone=current_speaker_zone)    
    
@app.route('/mic')
def mic_stream():
    return render_template('mic_stream.html')

# Start background scheduler
threading.Thread(target=bell_scheduler, daemon=True).start()

if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"?? Running on: http://{local_ip}:5002")
    #app.run(host=local_ip, port=5002, debug=True)
    socketio.run(app, host=local_ip, port=5002)
