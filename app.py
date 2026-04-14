from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import threading, time, random, math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'drone-gcs-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# ── Drone State ──────────────────────────────────────────────────────────────
drone_state = {
    "mode": "AUTO",
    "lat": 28.6139, "lon": 77.2090,
    "altitude": 0.0, "speed": 0.0,
    "heading": 47.0, "battery": 100.0,
    "waypoint_index": 0, "total_waypoints": 6,
    "status": "Takeoff", "obstacle": "Clear",
    "ai_decision": "Initialising...",
}

# ── Waypoints (Delhi area) ───────────────────────────────────────────────────
WAYPOINTS = [
    {"lat": 28.6139, "lon": 77.2090, "alt": 50,  "name": "Home"},
    {"lat": 28.6155, "lon": 77.2110, "alt": 100, "name": "WP1"},
    {"lat": 28.6170, "lon": 77.2145, "alt": 120, "name": "WP2"},
    {"lat": 28.6185, "lon": 77.2170, "alt": 140, "name": "WP3"},
    {"lat": 28.6200, "lon": 77.2190, "alt": 130, "name": "WP4"},
    {"lat": 28.6215, "lon": 77.2210, "alt": 100, "name": "WP5 (Target)"},
]

AI_DECISIONS = [
    "Path clear. Maintaining current heading.",
    "Wind speed increased. Adjusting altitude by +10m.",
    "Obstacle detected at 35m range. Climbing to avoid.",
    "Battery optimal. Continuing mission.",
    "GPS accuracy high. Refining position fix.",
    "Thermal updraft detected. Compensating attitude.",
    "Camera active. Terrain mapping in progress.",
    "Recalculating optimal route to next waypoint.",
    "Return-to-home reserve battery threshold check: OK",
]

log_buffer = []

def add_log(msg, level="INFO"):
    entry = {"time": time.strftime("%H:%M:%S"), "level": level, "msg": msg}
    log_buffer.insert(0, entry)
    if len(log_buffer) > 50:
        log_buffer.pop()
    return entry

add_log("System initialized. Autonomous mission loaded.", "INFO")
add_log("GPS lock acquired — 12 satellites.", "INFO")
add_log("Pre-arm checks passed. Motors armed.", "SUCCESS")

# ── Autonomous flight loop ────────────────────────────────────────────────────
def flight_loop():
    wp_idx = 0
    t = 0
    while True:
        time.sleep(1)
        t += 1
        state = drone_state
        target = WAYPOINTS[wp_idx]

        dlat = target["lat"] - state["lat"]
        dlon = target["lon"] - state["lon"]
        dist = math.sqrt(dlat**2 + dlon**2)

        if dist < 0.0002:
            log = add_log(f"Waypoint {target['name']} reached.", "SUCCESS")
            wp_idx = (wp_idx + 1) % len(WAYPOINTS)
            state["waypoint_index"] = wp_idx
            socketio.emit("log", log)

        step = 0.00004
        if dist > 0:
            state["lat"] += (dlat / dist) * step
            state["lon"] += (dlon / dist) * step

        alt_diff = target["alt"] - state["altitude"]
        state["altitude"] = round(state["altitude"] + alt_diff * 0.05 + random.uniform(-0.5, 0.5), 1)

        if abs(dlat) + abs(dlon) > 0.00001:
            angle = math.degrees(math.atan2(dlon, dlat))
            state["heading"] = round((angle + 360) % 360, 1)

        state["speed"]    = round(random.uniform(15, 22), 1)
        state["battery"]  = round(max(0, state["battery"] - 0.03), 1)
        state["signal"]   = random.choice(["Strong", "Strong", "Strong", "Good"])
        state["obstacle"] = random.choice(["Clear", "Clear", "Clear", "Detected (avoiding)"])
        state["status"]   = "Returning Home" if wp_idx == 0 else f"Navigating to {WAYPOINTS[wp_idx]['name']}"

        if t % 7 == 0:
            decision = random.choice(AI_DECISIONS)
            state["ai_decision"] = decision
            socketio.emit("log", add_log(f"AI: {decision}", "AI"))

        if t % 13 == 0:
            msg, lvl = random.choice([
                ("Terrain scan complete.", "INFO"),
                ("Photo captured at current GPS coords.", "INFO"),
                ("Wind compensation applied.", "INFO"),
                ("Barometer reading stable.", "INFO"),
            ])
            socketio.emit("log", add_log(msg, lvl))

        socketio.emit("telemetry", {
            "lat": round(state["lat"], 6),
            "lon": round(state["lon"], 6),
            "altitude": state["altitude"],
            "speed": state["speed"],
            "heading": state["heading"],
            "battery": state["battery"],
            "waypoint_index": state["waypoint_index"],
            "total_waypoints": state["total_waypoints"],
            "status": state["status"],
            "signal": state.get("signal", "Strong"),
            "obstacle": state["obstacle"],
            "mode": state["mode"],
            "ai_decision": state["ai_decision"],
            "waypoints": WAYPOINTS,
        })

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/logs")
def get_logs():
    return jsonify(log_buffer)

@socketio.on("connect")
def on_connect():
    emit("telemetry", {
        "lat": drone_state["lat"], "lon": drone_state["lon"],
        "altitude": drone_state["altitude"], "speed": drone_state["speed"],
        "heading": drone_state["heading"], "battery": drone_state["battery"],
        "waypoint_index": drone_state["waypoint_index"],
        "total_waypoints": drone_state["total_waypoints"],
        "status": drone_state["status"], "signal": "Strong",
        "obstacle": drone_state["obstacle"], "mode": drone_state["mode"],
        "ai_decision": "Connected to GCS. Mission active.",
        "waypoints": WAYPOINTS,
    })
    for log in log_buffer[:10]:
        emit("log", log)

if __name__ == "__main__":
    threading.Thread(target=flight_loop, daemon=True).start()
    print("\n  Drone GCS running → http://localhost:5000\n")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)

