from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import os
import time

app = Flask(__name__)
CORS(app)

# Добавляем маршрут по умолчанию
@app.route("/")
def index():
    return "pong!"

# Устанавливаем порт из переменной окружения или по умолчанию 5000
port = int(os.environ.get("PORT", 5000))

socketio = SocketIO(app, cors_allowed_origins="*")

# Счётчик зрителей
viewers = {f"oneevent{i}": set() for i in range(1, 9)}

# Авторизация
ADMIN_PASSWORD = "onemediamodkit123"
authorized_admins = set()  # по sid

# Хранилище рекламы и плашек
ad_storage = {
    'ad_playing': False,
    'ad_url': None,
    'banner_visible': False,
    'banner_position': 'bottom-right',  # или 'center'
    'banner_title': '',
    'banner_text': ''
}

# Пользователь зашёл на канал
@socketio.on("join")
def handle_join(data):
    sid = request.sid
    room = data["channel"]
    viewers[room].add(sid)
    join_room(room)
    
    # Отправляем текущее состояние рекламы новому зрителю
    if ad_storage['ad_playing']:
        emit("play_ad", {"url": ad_storage['ad_url']}, room=sid)
    
    if ad_storage['banner_visible']:
        emit("show_banner", {
            "position": ad_storage['banner_position'],
            "title": ad_storage['banner_title'],
            "text": ad_storage['banner_text']
        }, room=sid)
    
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

# Управление рекламой
@socketio.on("control_ad")
def handle_control_ad(data):
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    action = data.get("action")
    
    if action == "play":
        ad_storage['ad_playing'] = True
        ad_storage['ad_url'] = data.get("url")
        socketio.emit("play_ad", {"url": ad_storage['ad_url']}, skip_sid=sid)
        print(f"[▶] Включена реклама: {ad_storage['ad_url']}")
    
    elif action == "stop":
        ad_storage['ad_playing'] = False
        socketio.emit("stop_ad", {}, skip_sid=sid)
        print(f"[⏹] Реклама остановлена")
    
    update_admin()

# Управление плашкой
@socketio.on("control_banner")
def handle_control_banner(data):
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    action = data.get("action")
    
    if action == "show":
        ad_storage['banner_visible'] = True
        ad_storage['banner_position'] = data.get("position", "bottom-right")
        ad_storage['banner_title'] = data.get("title", "")
        ad_storage['banner_text'] = data.get("text", "")
        
        socketio.emit("show_banner", {
            "position": ad_storage['banner_position'],
            "title": ad_storage['banner_title'],
            "text": ad_storage['banner_text']
        }, skip_sid=sid)
        
        print(f"[ℹ] Показана плашка: {ad_storage['banner_title']}")
    
    elif action == "hide":
        ad_storage['banner_visible'] = False
        socketio.emit("hide_banner", {}, skip_sid=sid)
        print(f"[✖] Плашка скрыта")
    
    update_admin()

# Обновить админку
def update_admin():
    stats = {ch: len(viewers[ch]) for ch in viewers}
    stats.update({
        'ad_playing': ad_storage['ad_playing'],
        'ad_url': ad_storage['ad_url'],
        'banner_visible': ad_storage['banner_visible'],
        'banner_position': ad_storage['banner_position'],
        'banner_title': ad_storage['banner_title'],
        'banner_text': ad_storage['banner_text']
    })
    socketio.emit("update_stats", stats, room="admin")

if __name__ == "__main__":
    # Запускаем с allow_unsafe_werkzeug=True для работы в продакшн
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
