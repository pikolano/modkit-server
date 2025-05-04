from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# Добавляем маршрут по умолчанию
@app.route("/")
def index():
    return "Я живой!"

# Устанавливаем порт из переменной окружения или по умолчанию 5000
port = int(os.environ.get("PORT", 5000))

socketio = SocketIO(app, cors_allowed_origins="*")

# Счётчик зрителей
viewers = {f"oneevent{i}": set() for i in range(1, 9)}

# Авторизация
ADMIN_PASSWORD = "onemediamodkit123"
authorized_admins = set()  # по sid

# Пользователь зашёл на канал
@socketio.on("join")
def handle_join(data):
    sid = request.sid
    room = data["channel"]
    viewers[room].add(sid)
    join_room(room)
    update_admin()

# Отключился
@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    for room in viewers:
        if sid in viewers[room]:
            viewers[room].remove(sid)
            leave_room(room)
            break
    authorized_admins.discard(sid)
    update_admin()

# Авторизация админа
@socketio.on("auth")
def handle_auth(data):
    sid = request.sid
    if data.get("password") == ADMIN_PASSWORD:
        authorized_admins.add(sid)
        emit("auth_result", {"success": True})
        print(f"[+] Админ авторизован: {sid}")
    else:
        emit("auth_result", {"success": False})
        print(f"[-] Неверный пароль от: {sid}")

# Только авторизованные могут попасть в админку
@socketio.on("admin_join")
def handle_admin_join():
    sid = request.sid
    if sid in authorized_admins:
        join_room("admin")
        update_admin()
    else:
        emit("error", {"message": "Не авторизован"})

# Редирект — только если авторизован
@socketio.on("redirect")
def handle_redirect(data):
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    channel = data["channel"]
    url = data["url"]
    socketio.emit("redirect", {"url": url}, room=channel)
    print(f"[↪] Перенаправление: {channel} → {url}")

# Обновить админку
def update_admin():
    stats = {ch: len(viewers[ch]) for ch in viewers}
    socketio.emit("update_stats", stats, room="admin")

if __name__ == "__main__":
    # Запускаем с allow_unsafe_werkzeug=True для работы в продакшн
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
