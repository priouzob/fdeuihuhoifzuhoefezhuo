"""
Web Server Local Synchronisé pour WikiMasters Auto-Claimer.
Fournit une interface Web locale (http://localhost:5050) ultra-moderne, fluide et interactive.
Synchronisation bidirectionnelle 100% thread-safe avec l'application PySide6 via Qt Signals.
"""

import os
import sys
import time
import json
import queue
import logging
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, Response, request, jsonify, send_from_directory
from PySide6.QtCore import QObject, Signal

import engine
import guild
import transfer

# Supprimer les logs verbeux de Werkzeug dans la console
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

BASE_DIR = Path(__file__).parent.resolve()
WEB_DIR = BASE_DIR / "web"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

app = Flask(__name__, static_folder=str(WEB_DIR))
app.config['JSON_AS_ASCII'] = False

# ─── Pont Qt Thread-Safe ────────────────────────────────────────────────────

class WebBridge(QObject):
    claim_requested = Signal(list)
    refresh_requested = Signal(str)
    toggle_pause_requested = Signal()
    sync_friends_requested = Signal()
    setup_requested = Signal(str, str)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)
    set_main_requested = Signal(str)
    add_account_requested = Signal(str, str)

_web_bridge = None
_main_window_ref = None
_sse_queues = []
_sse_lock = threading.Lock()
_recent_logs = []
_recent_logs_lock = threading.Lock()

def set_bridge(bridge, main_window):
    global _web_bridge, _main_window_ref
    _web_bridge = bridge
    _main_window_ref = main_window

def broadcast_log(time_str, message, level="info"):
    entry = {
        "time": time_str,
        "message": message,
        "level": level,
        "timestamp": time.time()
    }
    with _recent_logs_lock:
        _recent_logs.append(entry)
        if len(_recent_logs) > 300:
            _recent_logs.pop(0)

    broadcast_event("log", entry)

def broadcast_event(event_type, data):
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    msg = f"event: {event_type}\ndata: {payload}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for d in dead:
            if d in _sse_queues:
                _sse_queues.remove(d)

# ─── Routes Web ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")

@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    return send_from_directory(str(SCREENSHOTS_DIR), filename)

@app.route("/api/events")
def sse_events():
    def event_stream():
        q = queue.Queue(maxsize=100)
        with _sse_lock:
            _sse_queues.append(q)
        try:
            # Message initial de connexion
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    # Heartbeat pour garder la connexion active
                    yield ": ping\n\n"
        except GeneratorExit:
            with _sse_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/state")
def get_state():
    accounts_data = []
    config_accs = engine.get_accounts()
    main_acc_id = engine.get_main_account_id()
    lifetime = engine.load_lifetime_stats()
    col_stats = engine.load_collection_stats()
    best_cards_data = engine.load_best_cards()

    mw = _main_window_ref

    for acc in config_accs:
        aid = acc.get("id")
        name = acc.get("name", aid)
        b_type = acc.get("browser_type", "chrome")

        card = mw.account_cards.get(aid) if mw and hasattr(mw, "account_cards") else None

        if card:
            is_connected = getattr(card, "is_connected", False)
            status_text = card.status_badge.text() if hasattr(card, "status_badge") else "● Prêt"
            remaining_seconds = getattr(card, "remaining_seconds", 0)
            sub_lbl = card.sub_lbl.text() if hasattr(card, "sub_lbl") else ""
            is_captcha_blocked = getattr(card, "is_captcha_blocked", False)
            is_reconnect_needed = getattr(card, "is_reconnect_needed", False)
            is_claiming = getattr(card, "is_claiming", False)
            last_cards = getattr(card, "last_pulled_cards", [])
            last_stock = getattr(card, "last_pack_stock", None)
        else:
            is_connected = engine.is_account_configured(aid)
            status_text = "✅ Prêt" if is_connected else "● Non connecté"
            remaining_seconds = 0
            sub_lbl = "Synchronisé"
            is_captcha_blocked = False
            is_reconnect_needed = False
            is_claiming = False
            last_cards = []
            last_stock = None

        acc_lifetime = lifetime.get(aid, {})
        acc_col = col_stats.get(aid, {})

        accounts_data.append({
            "id": aid,
            "name": name,
            "browser_type": b_type,
            "is_main": (aid == main_acc_id),
            "is_connected": is_connected,
            "status_text": status_text,
            "sub_lbl": sub_lbl,
            "remaining_seconds": remaining_seconds,
            "is_captcha_blocked": is_captcha_blocked,
            "is_reconnect_needed": is_reconnect_needed,
            "is_claiming": is_claiming,
            "stock_data": last_stock,
            "total_packs": acc_lifetime.get("total_packs", 0),
            "cards_count": acc_lifetime.get("total_cards", 0),
            "rarity_counts": {
                "L": acc_lifetime.get("L", 0),
                "UR": acc_lifetime.get("UR", 0),
                "SR": acc_lifetime.get("SR", 0),
                "R": acc_lifetime.get("R", 0),
                "PC": acc_lifetime.get("PC", 0),
                "C": acc_lifetime.get("C", 0),
            },
            "last_cards": last_cards or acc_col.get("recent_cards", []),
            "best_cards": best_cards_data.get(aid, [])[:10],
            "has_vault": engine.has_saved_session_vault(aid),
            "vault_info": engine.get_session_vault_info(aid)
        })

    with _recent_logs_lock:
        logs_copy = list(_recent_logs[-100:])

    total_packs_all = sum(a["total_packs"] for a in accounts_data)
    total_cards_all = sum(a["cards_count"] for a in accounts_data)

    version_str = "2.6.8"
    try:
        vf = BASE_DIR / "version.json"
        if vf.exists():
            with open(vf, "r", encoding="utf-8") as f:
                version_str = json.load(f).get("version", version_str)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "is_running": getattr(mw, "is_running", True) if mw else True,
        "version": version_str,
        "accounts": accounts_data,
        "stats": {
            "total_packs": total_packs_all,
            "total_cards": total_cards_all,
            "accounts_count": len(accounts_data)
        },
        "logs": logs_copy
    })

# ─── Actions REST ───────────────────────────────────────────────────────────

@app.route("/api/claim", methods=["POST"])
def api_claim():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id", "all")
    if _web_bridge:
        if account_id == "all":
            acc_ids = [a["id"] for a in engine.get_accounts()]
            _web_bridge.claim_requested.emit(acc_ids)
        else:
            _web_bridge.claim_requested.emit([account_id])
        return jsonify({"success": True, "message": f"Tirage lancé pour {account_id}"})
    return jsonify({"success": False, "message": "Pont non initialisé"}), 500

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    if account_id and _web_bridge:
        _web_bridge.refresh_requested.emit(account_id)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/toggle_pause", methods=["POST"])
def api_toggle_pause():
    if _web_bridge:
        _web_bridge.toggle_pause_requested.emit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 500

@app.route("/api/sync_friends", methods=["POST"])
def api_sync_friends():
    if _web_bridge:
        _web_bridge.sync_friends_requested.emit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 500

@app.route("/api/open_browser", methods=["POST"])
def api_open_browser():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    start_url = data.get("start_url", "https://wiki-masters.com/pulls")
    browser_type = data.get("browser_type")
    if account_id:
        acc = engine.get_account_info(account_id)
        name = acc.get("name", account_id)
        broadcast_log(f"🌐 Lancement du navigateur pour '{name}'...", "info")
        import threading
        def _launch():
            try:
                ok, msg = engine.open_account_browser(account_id, url=start_url, browser_type=browser_type)
                print(f"[API_OPEN_BROWSER] result: {ok}, {msg}", flush=True)
                if ok:
                    broadcast_log(f"✓ {msg}", "success")
                else:
                    broadcast_log(f"✗ {msg}", "error")
            except Exception as e:
                import traceback
                print(f"[API_OPEN_BROWSER ERROR] {e}\n{traceback.format_exc()}", flush=True)
        threading.Thread(target=_launch, daemon=True).start()
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/rename", methods=["POST"])
def api_rename():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    new_name = data.get("new_name", "").strip()
    if account_id and new_name and _web_bridge:
        _web_bridge.rename_requested.emit(account_id, new_name)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/set_main", methods=["POST"])
def api_set_main():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    if account_id and _web_bridge:
        _web_bridge.set_main_requested.emit(account_id)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/add_account", methods=["POST"])
def api_add_account():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    b_type = data.get("browser_type", "chrome")
    if name and _web_bridge:
        _web_bridge.add_account_requested.emit(name, b_type)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/delete_account", methods=["POST"])
def api_delete_account():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    if account_id and _web_bridge:
        _web_bridge.delete_requested.emit(account_id)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/api/import_session", methods=["POST"])
def api_import_session():
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    raw_data = data.get("session_data", "")
    if not account_id or not raw_data:
        return jsonify({"success": False, "message": "Paramètres manquants."}), 400
    success, msg = engine.import_manual_session(account_id, raw_data)
    if success and _main_window_ref:
        card = _main_window_ref.account_cards.get(account_id)
        if card:
            card.is_connected = True
            card.set_reconnect_needed(False)
            card.set_status("🛡️  Protégé", "#14532d", "#86efac")
            card.sub_lbl.setText("Session coffre-fort active")
            card.login_fail_count = 0
    return jsonify({"success": success, "message": msg})

@app.route("/api/vault_status")
def api_vault_status():
    config_accs = engine.get_accounts()
    res = {}
    for acc in config_accs:
        aid = acc.get("id")
        res[aid] = engine.get_session_vault_info(aid)
    return jsonify(res)

@app.route("/api/best_cards")
def api_best_cards():
    return jsonify(engine.load_best_cards())

@app.route("/api/fleet_stats")
def api_fleet_stats():
    lifetime = engine.load_lifetime_stats()
    col_stats = engine.load_collection_stats()
    history = engine.load_history()
    return jsonify({
        "lifetime": lifetime,
        "collection": col_stats,
        "history": history[-50:]
    })

@app.route("/api/discord", methods=["GET", "POST"])
def api_discord():
    if request.method == "GET":
        return jsonify(engine.get_discord_settings())
    data = request.get_json(silent=True) or {}
    url = data.get("webhook_url", "")
    rare_only = data.get("notify_rare_only", True)
    errors = data.get("notify_errors", True)
    engine.set_discord_settings(url, rare_only, errors)
    return jsonify({"success": True})

@app.route("/api/discord_test", methods=["POST"])
def api_discord_test():
    ok, msg = engine.test_discord_webhook()
    return jsonify({"success": ok, "message": msg})

@app.route("/api/transfer", methods=["POST"])
def api_transfer():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "centralize")
    target_name = data.get("target_name", "").strip()
    rarities = data.get("rarities", ["C", "PC"])
    keep_duplicates = data.get("keep_duplicates", False)
    source_ids = data.get("source_ids", [])

    if not target_name:
        return jsonify({"success": False, "message": "Nom du compte cible requis"}), 400

    def run_bg():
        def cb(msg, level="info"):
            now = datetime.now().strftime("%H:%M:%S")
            broadcast_log(now, msg, level)

        if mode == "centralize":
            transfer.execute_bulk_donation(
                source_ids or [a["id"] for a in engine.get_accounts()],
                target_name,
                rarities,
                keep_duplicates_only=keep_duplicates,
                status_callback=cb
            )
        else:
            source_id = data.get("source_id")
            if source_id:
                transfer.execute_card_transfer(
                    source_id,
                    target_name,
                    rarities,
                    keep_duplicates_only=keep_duplicates,
                    status_callback=cb
                )

    threading.Thread(target=run_bg, daemon=True).start()
    return jsonify({"success": True, "message": "Transfert démarré en arrière-plan"})

@app.route("/api/guild_sync", methods=["POST"])
def api_guild_sync():
    def run_bg():
        def cb(msg, level="info"):
            now = datetime.now().strftime("%H:%M:%S")
            broadcast_log(now, msg, level)
        engine.sync_guild(status_callback=cb)
    threading.Thread(target=run_bg, daemon=True).start()
    return jsonify({"success": True, "message": "Synchronisation de guilde lancée en arrière-plan"})

# ─── Démarrage Serveur ──────────────────────────────────────────────────────

_server_thread = None
_actual_port = 5050

def start_web_server(main_window=None, port=5050):
    global _server_thread, _actual_port, _main_window_ref
    _main_window_ref = main_window

    import socket
    # Trouver un port disponible à partir de port
    for p in range(port, port + 10):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('127.0.0.1', p))
            s.close()
            _actual_port = p
            break
        except Exception:
            s.close()
            continue

    def run():
        app.run(host="127.0.0.1", port=_actual_port, threaded=True, debug=False, use_reloader=False)

    _server_thread = threading.Thread(target=run, name="WikiMastersWebServer", daemon=True)
    _server_thread.start()
    return _actual_port
