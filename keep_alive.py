from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Discord bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def keep_alive_thread():
    t = threading.Thread(target=run_flask)
    t.start()
