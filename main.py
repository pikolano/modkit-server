from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Конфигурация
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
port = int(os.environ.get("PORT", 5000))

# Инициализация SocketIO
socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    logger=True,
                    engineio_logger=True,
                    async_mode='gevent')

# Хранилище данных
class StreamData:
    def __init__(self):
        self.viewers = {f"oneevent{i}": set() for i in range(1, 9)}
        self.authorized_admins = set()
        self.chat_messages = {f"oneevent{i}": [] for i in range(1, 9)}

    def add_viewer(self, channel, sid):
        if channel in self.viewers:
            self.viewers[channel].add(sid)

    def remove_viewer(self, sid):
        for channel in self.viewers:
            if sid in self.viewers[channel]:
                self.viewers[channel].remove(sid)
                return channel
        return None

    def get_viewers_count(self, channel):
        return len(self.viewers.get(channel, set()))

    def add_chat_message(self, channel, username, message):
        if channel in self.chat_messages:
            self.chat_messages[channel].append((username, message))
            if len(self.chat_messages[channel]) > 100:
                self.chat_messages[channel] = self.chat_messages[channel][-100:]

data = StreamData()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "onemediamodkit123")

@app.route("/")
def index():
    return "Stream Server is Running"

@app.route("/stats")
def get_stats():
    return {ch: data.get_viewers_count(ch) for ch in data.viewers}

# ========== Socket.IO ==========

@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    channel = data.remove_viewer(sid)
    if channel:
        emit("viewer_count", {"count": data.get_viewers_count(channel)}, room=channel)
    if sid in data.authorized_admins:
        data.authorized_admins.remove(sid)
    logger.info(f"Client disconnected: {sid}")

@socketio.on("join")
def handle_join(payload):
    try:
        channel = payload.get("channel")
        if not channel or channel not in data.viewers:
            emit("error", {"message": "Invalid channel"})
            return

        sid = request.sid
        data.add_viewer(channel, sid)
        join_room(channel)

        emit("viewer_count", {
            "count": data.get_viewers_count(channel)
        }, room=channel)

        for username, message in data.chat_messages.get(channel, []):
            emit("chat_message", {
                "username": username,
                "message": message
            }, room=sid)

        logger.info(f"User {sid} joined channel {channel}")
    except Exception as e:
        logger.error(f"Join error: {str(e)}")
        emit("error", {"message": "Internal server error"})

@socketio.on("auth")
def handle_auth(payload):
    try:
        password = payload.get("password")
        if password == ADMIN_PASSWORD:
            data.authorized_admins.add(request.sid)
            emit("auth_result", {"success": True})
            logger.info(f"Admin authenticated: {request.sid}")
        else:
            emit("auth_result", {"success": False})
            logger.warning(f"Failed auth attempt from: {request.sid}")
    except Exception as e:
        logger.error(f"Auth error: {str(e)}")
        emit("error", {"message": "Internal server error"})

@socketio.on("chat_message")
def handle_chat_message(payload):
    try:
        channel = payload.get("channel")
        username = payload.get("username")
        message = payload.get("message")

        if not all([channel, username, message]):
            emit("error", {"message": "Invalid message data"})
            return

        if len(message) > 500:
            emit("error", {"message": "Message too long"})
            return

        data.add_chat_message(channel, username, message)

        emit("chat_message", {
            "username": username,
            "message": message
        }, room=channel)

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        emit("error", {"message": "Internal server error"})

@socketio.on("redirect")
def handle_redirect(payload):
    try:
        if request.sid not in data.authorized_admins:
            emit("error", {"message": "Not authorized"})
            return

        channel = payload.get("channel")
        url = payload.get("url")

        if not all([channel, url]):
            emit("error", {"message": "Invalid redirect data"})
            return

        if channel not in data.viewers:
            emit("error", {"message": "Invalid channel"})
            return

        emit("redirect", {"url": url}, room=channel)
        logger.info(f"Redirecting {channel} to {url}")

    except Exception as e:
        logger.error(f"Redirect error: {str(e)}")
        emit("error", {"message": "Internal server error"})

if __name__ == "__main__":
    logger.info(f"Starting server on port {port}")
    socketio.run(app,
                 host="0.0.0.0",
                 port=port,
                 debug=False,
                 allow_unsafe_werkzeug=True,
                 use_reloader=False)
