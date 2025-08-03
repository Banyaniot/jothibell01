# jothibell01

raspberry pi

git config --global user.name "Banyaniot"
git config --global user.email "satheeshsst@outlook.com"

git clone https://github.com/Banyaniot/jothibell01.git
git add .

git commit -m "First commit"

git push origin main
git pull
git fetch origin && git reset --hard origin/main && git clean -fd

Tested comment

sample_data = {
 "command": "add",
    "data": {
    "time": "09:00",
    "file": "JanaGanman.mp3",
    "label": "Assembly Bell2",
     "enabled": True,
     "days": ["Monday", "Wednesday"],
     "speaker": "indoor",
     "url": "http://103.207.4.72:3040/files/JanaGanman.mp3"
    }

"command": "delete",
"data": {
 "label": "Assembly Bell"
 }
"command": "play",
"data": {
"file": "JanaGanman.mp3",
"url": "http://103.207.4.72:3040/files/JanaGanman.mp3",
"speaker": "outdoor"
}

"command": "stop"

"command": "speaker",
"data": {
 "speaker": "outdoor"
 }
 
}
