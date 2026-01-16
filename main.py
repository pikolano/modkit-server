from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return "pong!!"

port = int(os.environ.get("PORT", 5000))
socketio = SocketIO(app, cors_allowed_origins="*")

# Каналы и зрители
viewers = {f"oneevent{i}": set() for i in range(1, 11)}
viewers["one"] = set()

# Отслеживание уникальных IP
daily_unique_ips = set()
current_unique_ips = set()
ip_to_sid = {}
last_reset_date = datetime.now().date()

matches = [None, None, None, None, None]  # 5 слотов для матчей

ADMIN_PASSWORD = "onemediamodkit123"
authorized_admins = set()

def reset_daily_stats_if_needed():
    global daily_unique_ips, last_reset_date
    current_date = datetime.now().date()
    if current_date > last_reset_date:
        print(f"[!] Новый день! Сброс дневной статистики")
        daily_unique_ips.clear()
        last_reset_date = current_date

@socketio.on("join")
def handle_join(data):
    sid = request.sid
    room = data["channel"]
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    
    viewers[room].add(sid)
    join_room(room)
    
    reset_daily_stats_if_needed()
    daily_unique_ips.add(ip)
    current_unique_ips.add(ip)
    
    if ip not in ip_to_sid:
        ip_to_sid[ip] = set()
    ip_to_sid[ip].add(sid)
    
    print(f"[+] Зритель подключился: {sid} (IP: {ip}) в канал {room}")
    update_admin()

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    ip_to_remove = None
    for ip, sids in ip_to_sid.items():
        if sid in sids:
            sids.discard(sid)
            if len(sids) == 0:
                ip_to_remove = ip
            break
    
    if ip_to_remove:
        current_unique_ips.discard(ip_to_remove)
        del ip_to_sid[ip_to_remove]
    
    for room in viewers:
        if sid in viewers[room]:
            viewers[room].remove(sid)
            leave_room(room)
            break
    
    authorized_admins.discard(sid)
    print(f"[-] Зритель отключился: {sid}")
    update_admin()

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

@socketio.on("admin_join")
def handle_admin_join():
    sid = request.sid
    if sid in authorized_admins:
        join_room("admin")
        update_admin()
    else:
        emit("error", {"message": "Не авторизован"})

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

def update_admin():
    reset_daily_stats_if_needed()
    stats = {ch: len(viewers[ch]) for ch in viewers}
    stats["daily_unique"] = len(daily_unique_ips)
    stats["current_unique"] = len(current_unique_ips)
    socketio.emit("update_stats", stats, room="admin")

# ============ MINI APP HANDLERS ============

@socketio.on("get_matches")
def handle_get_matches():
    """Отправляет список всех матчей"""
    active_matches = []
    for i, match in enumerate(matches):
        if match is not None:
            match_copy = match.copy()
            match_copy["id"] = i + 1
            match_copy["watchPage"] = f"miniapp_watch{i+1}.html"
            active_matches.append(match_copy)
    emit("matches_data", active_matches)

@socketio.on("get_match_by_id")
def handle_get_match_by_id(data):
    """Получить матч по ID"""
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match_id = data.get("matchId")
    slot_index = match_id - 1
    
    if 0 <= slot_index < len(matches) and matches[slot_index] is not None:
        emit("match_data", matches[slot_index])
    else:
        emit("match_data", None)

@socketio.on("add_match")
def handle_add_match(data):
    """Добавляет новый матч в первый свободный слот"""
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    # Ищем первый пустой слот
    slot_index = None
    for i in range(len(matches)):
        if matches[i] is None:
            slot_index = i
            break
    
    if slot_index is None:
        emit("match_added", {"success": False, "error": "Все слоты заняты (максимум 5 матчей)"})
        return
    
    match = {
        "id": slot_index + 1,
        "team1": data.get("team1"),
        "team2": data.get("team2"),
        "team1Logo": data.get("team1Logo", ""),
        "team2Logo": data.get("team2Logo", ""),
        "league": data.get("league"),
        "category": data.get("category", "other"),
        "date": data.get("date"),
        "time": data.get("time"),
        "playerUrl": data.get("playerUrl"),
        "description": data.get("description", ""),
        "watchPage": f"miniapp_watch{slot_index + 1}.html"
    }
    
    matches[slot_index] = match
    emit("match_added", {"success": True})
    socketio.emit("matches_data", [m for m in matches if m], broadcast=True)
    print(f"[+] Добавлен матч в слот {slot_index + 1}: {match['team1']} - {match['team2']}")

@socketio.on("edit_match")
def handle_edit_match(data):
    """Редактирует существующий матч"""
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match_id = data.get("id")
    slot_index = match_id - 1
    
    if not (0 <= slot_index < len(matches) and matches[slot_index] is not None):
        emit("match_updated", {"success": False, "error": "Матч не найден"})
        return
    
    match = {
        "id": match_id,
        "team1": data.get("team1"),
        "team2": data.get("team2"),
        "team1Logo": data.get("team1Logo", ""),
        "team2Logo": data.get("team2Logo", ""),
        "league": data.get("league"),
        "category": data.get("category", "other"),
        "date": data.get("date"),
        "time": data.get("time"),
        "playerUrl": data.get("playerUrl"),
        "description": data.get("description", ""),
        "watchPage": f"miniapp_watch{match_id}.html"
    }
    
    matches[slot_index] = match
    emit("match_updated", {"success": True})
    socketio.emit("matches_data", [m for m in matches if m], broadcast=True)
    print(f"[✏️] Обновлен матч в слоте {match_id}: {match['team1']} - {match['team2']}")

@socketio.on("delete_match")
def handle_delete_match(data):
    """Удаляет матч из слота, НЕ СДВИГАЯ остальные"""
    sid = request.sid
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match_id = data.get("matchId")
    slot_index = match_id - 1
    
    if 0 <= slot_index < len(matches):
        matches[slot_index] = None
        emit("match_deleted", {"success": True})
        socketio.emit("matches_data", [m for m in matches if m], broadcast=True)
        print(f"[-] Удален матч из слота {match_id}")
    else:
        emit("match_deleted", {"success": False})

@socketio.on("get_match_by_number")
def handle_get_match_by_number(data):
    """Получить матч по номеру страницы"""
    match_number = data.get("matchNumber", 1)
    slot_index = match_number - 1
    
    if 0 <= slot_index < len(matches) and matches[slot_index] is not None:
        emit("match_data_by_number", matches[slot_index])
    else:
        emit("match_data_by_number", None)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
