from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import os
import time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return "pong!!"

port = int(os.environ.get("PORT", 5000))
socketio = SocketIO(app, cors_allowed_origins="*")

viewers = {f"oneevent{i}": set() for i in range(1, 11)} 
viewers["one"] = set() 

daily_unique_ips = set() 
current_unique_ips = set() 
ip_to_sid = {}  
last_reset_date = datetime.now().date()

matches = []
match_id_counter = 1

matches = []
match_id_counter = 1

ADMIN_PASSWORD = "onemediamodkit123"
authorized_admins = set()

def reset_daily_stats_if_needed():
    """Сбрасывает статистику за день в полночь"""
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

@socketio.on("get_matches")
def handle_get_matches():
    """Получить список всех матчей"""
    emit("matches_list", {"matches": matches})

@socketio.on("add_match")
def handle_add_match(data):
    """Добавить новый матч"""
    global match_id_counter
    sid = request.sid
    
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match = {
        "id": match_id_counter,
        "sport": data.get("sport", "Футбол"),
        "league": data.get("league", ""),
        "team1_name": data.get("team1_name", ""),
        "team1_logo": data.get("team1_logo", ""),
        "team2_name": data.get("team2_name", ""),
        "team2_logo": data.get("team2_logo", ""),
        "datetime": data.get("datetime", ""),
        "player_url": data.get("player_url", ""),
        "description": data.get("description", "")
    }
    
    matches.append(match)
    match_id_counter += 1
    
    print(f"[+] Добавлен матч: {match['team1_name']} vs {match['team2_name']}")
    
    socketio.emit("matches_list", {"matches": matches}, room="admin")
    socketio.emit("matches_update", {"matches": matches})

@socketio.on("delete_match")
def handle_delete_match(data):
    """Удалить матч"""
    global matches
    sid = request.sid
    
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match_id = data.get("match_id")
    matches = [m for m in matches if m["id"] != match_id]
    
    print(f"[-] Удален матч ID: {match_id}")
    
    socketio.emit("matches_list", {"matches": matches}, room="admin")
    socketio.emit("matches_update", {"matches": matches})

@socketio.on("edit_match")
def handle_edit_match(data):
    """Редактировать матч"""
    global matches
    sid = request.sid
    
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match_id = data.get("match_id")
    
    for match in matches:
        if match["id"] == match_id:
            match["sport"] = data.get("sport", match["sport"])
            match["league"] = data.get("league", match["league"])
            match["team1_name"] = data.get("team1_name", match["team1_name"])
            match["team1_logo"] = data.get("team1_logo", match["team1_logo"])
            match["team2_name"] = data.get("team2_name", match["team2_name"])
            match["team2_logo"] = data.get("team2_logo", match["team2_logo"])
            match["datetime"] = data.get("datetime", match["datetime"])
            match["player_url"] = data.get("player_url", match["player_url"])
            match["description"] = data.get("description", match["description"])
            
            print(f"[✎] Изменен матч ID: {match_id}")
            break
    
    socketio.emit("matches_list", {"matches": matches}, room="admin")
    socketio.emit("matches_update", {"matches": matches})

def update_admin():
    """Отправляет статистику админам"""
    reset_daily_stats_if_needed()
    
    stats = {ch: len(viewers[ch]) for ch in viewers}
    
    stats["daily_unique"] = len(daily_unique_ips)
    stats["current_unique"] = len(current_unique_ips)
    
    socketio.emit("update_stats", stats, room="admin")

@socketio.on("get_matches")
def handle_get_matches():
    """Отправляет список всех матчей"""
    emit("matches_data", matches)

@socketio.on("add_match")
def handle_add_match(data):
    """Добавляет новый матч"""
    global match_id_counter
    sid = request.sid
    
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match = {
        "id": match_id_counter,
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
        "watchPage": f"miniapp_watch{match_id_counter}.html"
    }
    
    matches.append(match)
    match_id_counter += 1
    
    emit("match_added", {"success": True})
    socketio.emit("matches_data", matches, broadcast=True)
    
    print(f"[+] Добавлен матч: {match['team1']} - {match['team2']}")

@socketio.on("delete_match")
def handle_delete_match(data):
    """Удаляет матч"""
    sid = request.sid
    
    if sid not in authorized_admins:
        emit("error", {"message": "Не авторизован"})
        return
    
    match_id = data.get("matchId")
    global matches
    matches = [m for m in matches if m["id"] != match_id]
    
    emit("match_deleted", {"success": True})
    socketio.emit("matches_data", matches, broadcast=True)
    
    print(f"[-] Удален матч ID: {match_id}")

@socketio.on("get_match_details")
def handle_get_match_details(data):
    """Отправляет детали конкретного матча"""
    match_id = int(data.get("matchId", 1))
    match = next((m for m in matches if m["id"] == match_id), None)
    emit("match_details", match)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
