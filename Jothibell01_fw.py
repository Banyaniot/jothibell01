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

# Create schedule file if not exists
if not os.path.exists(SCHEDULE_FILE):
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump([], f)

def on_connect(client, userdata, flags, rc):
    print(f"? MQTT Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    print(f"📩 MQTT Message received on {msg.topic}")
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
            speaker = data.get("speaker", "default")  # ✅ Add speaker type

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
                        print(f"📥 Downloaded file from {file_url}")
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
                "speaker": speaker  # ✅ Save speaker in schedule
            })
            save_schedule(schedule)

            print("✅ Schedule added via MQTT")
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
                    print(f"🗑️ Deleted schedule with label: {label}")
                    client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                        "status": "success",
                        "command": "delete",
                        "message": f"Deleted schedule with label: {label}"
                    }))
                    break

            if not found:
                print(f"⚠️ No schedule found with label: {label}")
                client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                    "status": "error",
                    "command": "delete",
                    "message": f"No schedule found with label: {label}"
                }))

        elif command == "play":
            file_name = data.get("file")
            file_url = data.get("url", "")
            speaker = data.get("speaker", "default").lower()  # ✅ get speaker value

            if not file_name:
                raise ValueError("Missing 'file' in play command")

            file_path = os.path.join(UPLOAD_FOLDER, file_name)

            # 🔽 Download the file if it doesn't exist
            if not os.path.exists(file_path):
                if file_url:
                    try:
                        response = requests.get(file_url)
                        response.raise_for_status()
                        with open(file_path, 'wb') as f:
                            f.write(response.content)
                        print(f"📥 Downloaded file from {file_url}")
                    except Exception as e:
                        raise Exception(f"Failed to download file: {e}")
                else:
                    raise Exception(f"File '{file_name}' not found and no download URL provided")

            # 🔊 Handle speaker selection (example routing logic)
            print(f"🔊 Playing '{file_name}' on speaker: {speaker}")
            
            if speaker == "indoor":
                # Example: route to indoor amplifier or ALSA device
                print("➡️ Routing to indoor speaker")
                # os.system('aplay -D plughw:1,0 {}'.format(file_path))  # example
            elif speaker == "outdoor":
                print("➡️ Routing to outdoor speaker")
                # os.system('aplay -D plughw:2,0 {}'.format(file_path))  # example
            else:
                print("➡️ Routing to default speaker")
                # os.system('aplay {}'.format(file_path))  # example

            # ✅ Call your actual play logic (e.g., ALSA/gTTS/mpg123/etc.)
            play_audio(file_path)  # ← this should already handle your playback

            client.publish(MQTT_TOPIC_PUBLISH, json.dumps({
                "status": "success",
                "command": "play",
                "message": f"Playing {file_name} on speaker: {speaker}"
            }))

  
        
def mqtt_publish_loop(client):
    while True:
        try:
            schedule_data = load_schedule()
            payload =  "{\"imei\":\"schoolbell/status\",\"data\":\"123456\"}" #json.dumps(schedule_data)
            client.publish(MQTT_TOPIC_PUBLISH, payload)
            print(f"?? Published schedule to {MQTT_TOPIC_PUBLISH}")
        except Exception as e:
            print(f"? Error publishing MQTT: {e}")
        time.sleep(10)  # Publish every 10 seconds
        
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
    .table-container {
      overflow-y: auto;
      max-height: 500px;
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
    <label>Days:</label>
    <div style="margin-top: 10px;">
      {% for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] %}
        <label style="display:inline-block; margin-right: 12px;">
          <input type="checkbox" name="days" value="{{ day }}"> {{ day[:3] }}
        </label>
      {% endfor %}
    </div>

    <label><input type="checkbox" name="enabled" checked> Enabled</label>
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

    schedule = load_schedule()
    schedule.append({
        'time': time_val,
        'file': file_val,
        'label': label,
        'enabled': enabled,
        'days': days,
        'date': date
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

@app.route("/speak", methods=["POST"])
def speak_text():
    from gtts import gTTS
    text = request.form.get('tts_text', '').strip()
    if not text:
        return redirect(url_for('index'))

    # Sanitize text to create a safe filename
    safe_filename = re.sub(r'[^a-zA-Z0-9_]+', '_', text)[:30]  # Limit to 30 chars
    filename = f"{safe_filename}.mp3"
    tts_path = os.path.join(UPLOAD_FOLDER, filename)

    # Generate and save TTS
    tts = gTTS(text=text, lang='en')
    tts.save(tts_path)

    # Play the generated audio
    play_audio(filename)
    return redirect(url_for('index'))
    
# Start background scheduler
threading.Thread(target=bell_scheduler, daemon=True).start()

if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"?? Running on: http://{local_ip}:5000")
    app.run(host=local_ip, port=5002, debug=True)
