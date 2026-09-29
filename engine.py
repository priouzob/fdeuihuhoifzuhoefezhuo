"""
Moteur d'automatisation ultra-léger et furtif pour WikiMasters.
Gère les sessions persistantes pour Chrome, Brave et Opera.
- Détection et calcul automatique des raretés des cartes (C, PC, R, SR, UR, L).
- Consommation minimale de ressources : le navigateur ne tourne QUE pendant l'ouverture (~15s) puis libère 100% de la RAM.
- Protection anti-détection maximale : courbes de Bézier, masquage WebGL/CDP et résolution discrète de Cloudflare Turnstile.
"""

import os
import sys
import json
import time
import re
import random
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from stealth import apply_stealth, human_delay, human_click, check_and_handle_turnstile, check_and_handle_verification_modal

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = BASE_DIR / "history.json"
STATS_FILE = BASE_DIR / "stats.json"
BEST_CARDS_FILE = BASE_DIR / "best_cards.json"
COLLECTION_STATS_FILE = BASE_DIR / "collection_stats.json"

_file_io_lock = threading.RLock()
_active_setup_proc = None

def clean_profile_locks(browser_key):
    """Nettoie les fichiers de verrouillage résiduels (SingletonLock, lockfile) du profil Chrome."""
    try:
        acc = get_account_info(browser_key)
        p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{browser_key}")
        if not p_dir.exists():
            return
        lock_names = ["lockfile", "SingletonLock", "SingletonSocket", "SingletonCookie"]
        for name in lock_names:
            f = p_dir / name
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

def kill_browser_processes(browser_key):
    """Ferme proprement et instantanément tout processus résiduel du navigateur pour ce profil avant réouverture."""
    try:
        import psutil
        target_key = str(browser_key).lower()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = " ".join(proc.info.get('cmdline') or []).lower()
                if f"profiles/{target_key}" in cmdline or f"profiles\\{target_key}" in cmdline:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.6)
                    except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception:
        pass
    clean_profile_locks(browser_key)
    time.sleep(0.05)

def load_collection_stats():
    """Charge le cache des statistiques de collection de chaque compte."""
    with _file_io_lock:
        if COLLECTION_STATS_FILE.exists():
            try:
                with open(COLLECTION_STATS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

def save_collection_stats(stats_dict):
    """Sauvegarde le cache des statistiques de collection."""
    with _file_io_lock:
        try:
            with open(COLLECTION_STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(stats_dict, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def get_account_collection_stats(account_id):
    """Récupère les statistiques de cartes pour un compte spécifique."""
    stats = load_collection_stats()
    return stats.get(account_id, None)

def extract_collection_stats(page, account_id):
    """Extrait en temps réel via l'API interne le total et la répartition des raretés de cartes."""
    try:
        data = page.evaluate("""async () => {
            try {
                const res = await fetch('/api/my-collection/stats?sort=rarity');
                if (res.ok) return await res.json();
            } catch(e) {}
            return null;
        }""")
        if data and "total" in data:
            with _file_io_lock:
                all_stats = load_collection_stats()
                all_stats[account_id] = {
                    "total": data.get("total", 0),
                    "rarityCounts": data.get("rarityCounts", {}),
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_collection_stats(all_stats)
            return all_stats[account_id]
    except Exception:
        pass
    return None

def load_lifetime_stats():
    with _file_io_lock:
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Initialisation depuis history.json si stats.json n'existe pas encore
        stats = {}
        try:
            history = load_history()
            for entry in history:
                b = entry.get("browser_key", "chrome")
                if b not in stats:
                    stats[b] = {"total_packs": 0}
                stats[b]["total_packs"] = stats[b].get("total_packs", 0) + entry.get("packs_count", 1)
        except Exception:
            pass
        return stats

def update_lifetime_stats(browser_key, count=1):
    with _file_io_lock:
        try:
            stats = load_lifetime_stats()
            if browser_key not in stats:
                stats[browser_key] = {"total_packs": 0}
            stats[browser_key]["total_packs"] = stats[browser_key].get("total_packs", 0) + count
            stats[browser_key]["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

# Dictionnaire et hiérarchie des raretés officielles WikiMasters
RARITY_RANKS = {
    "L": 6,
    "UR": 5,
    "SR": 4,
    "R": 3,
    "PC": 2,
    "C": 1
}

RARITY_MAP = {
    "C": {"singular": "commune", "plural": "communes", "name": "Commune", "color": "#94a3b8", "bg": "#1e293b", "badge": "⚪ C"},
    "PC": {"singular": "peu commune", "plural": "peu communes", "name": "Peu Commune", "color": "#38bdf8", "bg": "#0c4a6e", "badge": "🔷 PC"},
    "R": {"singular": "rare", "plural": "rares", "name": "Rare", "color": "#34d399", "bg": "#064e3b", "badge": "✨ R"},
    "SR": {"singular": "super rare", "plural": "super rares", "name": "Super Rare", "color": "#a855f7", "bg": "#4c1d95", "badge": "⭐ SR"},
    "UR": {"singular": "ultra rare", "plural": "ultra rares", "name": "Ultra Rare", "color": "#ec4899", "bg": "#701a75", "badge": "💎 UR"},
    "L": {"singular": "légendaire", "plural": "légendaires", "name": "Légendaire", "color": "#fbbf24", "bg": "#78350f", "badge": "👑 L"},
}

def safe_notify(callback, message, level="info"):
    """Appelle le callback d'état de manière 100% sécurisée sans risque d'erreur d'encodage."""
    if callback:
        try:
            callback(str(message), level)
        except Exception:
            pass

def format_rarity_summary(rarities_list):
    """
    Calcule et formate le bilan des raretés (ex: '3 communes, 1 rare, 1 super rare').
    Trie de la rareté la plus prestigieuse à la plus commune.
    """
    if not rarities_list:
        return ""
    counts = {}
    for r in rarities_list:
        code = str(r).upper().strip()
        if code in RARITY_MAP:
            counts[code] = counts.get(code, 0) + 1
        else:
            counts["C"] = counts.get("C", 0) + 1

    order = ["L", "UR", "SR", "R", "PC", "C"]
    parts = []
    for code in order:
        c = counts.get(code, 0)
        if c > 0:
            name = RARITY_MAP[code]["plural"] if c > 1 else RARITY_MAP[code]["singular"]
            parts.append(f"{c} {name}")

    return ", ".join(parts) if parts else "5 cartes"

def load_config():
    if not CONFIG_FILE.exists():
        example_cfg = BASE_DIR / "config.example.json"
        if example_cfg.exists():
            try:
                import shutil
                shutil.copy(example_cfg, CONFIG_FILE)
            except Exception:
                pass
        if not CONFIG_FILE.exists():
            default_cfg = {
                "target_url": "https://wiki-masters.com/pulls",
                "check_interval_seconds": 600,
                "random_jitter_seconds": 15,
                "headless": True,
                "chrome_executable": get_chrome_executable(),
                "accounts": []
            }
            save_config(default_cfg)
            return default_cfg
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_history():
    with _file_io_lock:
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

def save_history(entry):
    try:
        with _file_io_lock:
            history = []
            if HISTORY_FILE.exists():
                try:
                    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    pass
            history.insert(0, entry)
            history = history[:500]
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            
            b_key = entry.get("browser_key")
            packs = entry.get("packs_count", 1)
            if b_key:
                update_lifetime_stats(b_key, packs)
                if entry.get("card_objects"):
                    register_pulled_cards(b_key, entry["card_objects"])
                elif entry.get("cards") and entry.get("rarities"):
                    register_pulled_cards(
                        b_key,
                        entry["cards"],
                        entry["rarities"],
                        timestamp=entry.get("timestamp"),
                        screenshot=entry.get("screenshot")
                    )
    except Exception:
        pass

def load_best_cards():
    """
    Charge les 10 meilleures cartes enregistrées par compte.
    Initialise automatiquement depuis l'historique complet si le fichier n'existe pas.
    """
    with _file_io_lock:
        if BEST_CARDS_FILE.exists():
            try:
                with open(BEST_CARDS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Initialisation intelligente depuis history.json
        best_cards = {}
        try:
            history = load_history()
            # Parcourt du plus ancien au plus récent
            for entry in reversed(history):
                b_key = entry.get("browser_key")
                if not b_key:
                    continue
                cards = entry.get("cards", [])
                rarities = entry.get("rarities", [])
                ts = entry.get("timestamp", "")
                shot = entry.get("screenshot", "")
                if b_key not in best_cards:
                    best_cards[b_key] = []

                for c_title, r_code in zip(cards, rarities):
                    if not c_title:
                        continue
                    r_upper = str(r_code).upper().strip()
                    if r_upper not in RARITY_RANKS:
                        r_upper = "C"
                    best_cards[b_key].append({
                        "title": c_title,
                        "rarity": r_upper,
                        "timestamp": ts,
                        "screenshot": shot
                    })

            # Tri et conservation stricte des 10 meilleures cartes
            for b_key in list(best_cards.keys()):
                best_cards[b_key].sort(
                    key=lambda x: (RARITY_RANKS.get(x.get("rarity", "C"), 0), x.get("timestamp", "")),
                    reverse=True
                )
                # Suppression automatique au-delà de 10
                best_cards[b_key] = best_cards[b_key][:10]

            save_best_cards(best_cards)
        except Exception:
            pass

        return best_cards

def save_best_cards(data):
    with _file_io_lock:
        try:
            with open(BEST_CARDS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def get_account_best_cards(account_id):
    """Renvoie les 10 meilleures cartes pour le compte donné."""
    best_cards = load_best_cards()
    return best_cards.get(account_id, [])

def register_pulled_cards(account_id, cards_list, rarities_list=None, timestamp=None, screenshot=None):
    """
    Enregistre les nouvelles cartes tirées pour un compte.
    Ne conserve strictement que les 10 cartes les plus rares (L, UR, SR, R, PC, C).
    Dès qu'une nouvelle carte plus rare est tirée et qu'il y en a déjà 10,
    les cartes les moins rares sont automatiquement supprimées du classement.
    """
    with _file_io_lock:
        best_cards = load_best_cards()
        if account_id not in best_cards:
            best_cards[account_id] = []

        ts_default = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        blacklist = {"ouvrir un paquet", "ouvrir", "paquet", "continuer", "carte", ""}

        # Si cards_list contient déjà des dictionnaires complets avec screenshot individuel
        if cards_list and isinstance(cards_list[0], dict):
            for card_obj in cards_list:
                t = str(card_obj.get("title", "")).strip()
                if not t or len(t) < 3 or t.lower() in blacklist:
                    continue
                r = str(card_obj.get("rarity", "C")).upper().strip()
                if r not in RARITY_RANKS:
                    r = "C"
                best_cards[account_id].append({
                    "title": t,
                    "rarity": r,
                    "timestamp": card_obj.get("timestamp") or ts_default,
                    "screenshot": card_obj.get("screenshot") or ""
                })
        else:
            rarities_list = rarities_list or []
            for title, rarity in zip(cards_list, rarities_list):
                if not title or not isinstance(title, str):
                    continue
                t = title.strip()
                if not t or len(t) < 3 or t.lower() in blacklist:
                    continue
                r_code = str(rarity).upper().strip() if rarity else "C"
                if r_code not in RARITY_RANKS:
                    r_code = "C"
                best_cards[account_id].append({
                    "title": t,
                    "rarity": r_code,
                    "timestamp": ts_default,
                    "screenshot": screenshot or ""
                })

        # Dédoublonnage exact
        seen = set()
        unique = []
        for c in best_cards[account_id]:
            k = (c.get("title"), c.get("rarity"), c.get("timestamp"))
            if k not in seen:
                seen.add(k)
                unique.append(c)

        # Tri par rareté décroissante (L > UR > SR > R > PC > C), puis date décroissante
        unique.sort(
            key=lambda x: (RARITY_RANKS.get(x.get("rarity", "C"), 0), x.get("timestamp", "")),
            reverse=True
        )

        # Garde strictement le TOP 10 (suppression automatique au-delà de 10)
        best_cards[account_id] = unique[:10]
        save_best_cards(best_cards)
        return best_cards[account_id]

def delete_account_card(account_id, card_index):
    """Supprime manuellement une carte du Top 10."""
    with _file_io_lock:
        best_cards = load_best_cards()
        cards = best_cards.get(account_id, [])
        if 0 <= card_index < len(cards):
            deleted = cards.pop(card_index)
            save_best_cards(best_cards)
            return True, deleted
        return False, None

SUPPORTED_BROWSERS = {
    "chrome": {
        "name": "Google Chrome",
        "icon": "🌐",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
    },
    "brave": {
        "name": "Brave Browser",
        "icon": "🦁",
        "paths": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
        ]
    },
    "edge": {
        "name": "Microsoft Edge",
        "icon": "🌊",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
        ]
    },
    "opera": {
        "name": "Opera / Opera GX",
        "icon": "🔴",
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe"),
            r"C:\Program Files\Opera\launcher.exe"
        ]
    }
}

def find_browser_executable(b_type="chrome"):
    """Trouve le chemin de l'exécutable pour le type de navigateur donné."""
    info = SUPPORTED_BROWSERS.get(b_type.lower())
    if info:
        for p in info["paths"]:
            if os.path.exists(p):
                return p
    # Fallback vers un autre navigateur installé
    for other_key, other_info in SUPPORTED_BROWSERS.items():
        for p in other_info["paths"]:
            if os.path.exists(p):
                return p
    return r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def get_available_browsers():
    """Renvoie la liste des navigateurs supportés avec leur statut d'installation."""
    result = {}
    for b_key, b_info in SUPPORTED_BROWSERS.items():
        found_path = None
        for p in b_info["paths"]:
            if os.path.exists(p):
                found_path = p
                break
        result[b_key] = {
            "name": b_info["name"],
            "icon": b_info["icon"],
            "path": found_path,
            "installed": (found_path is not None)
        }
    return result

def get_chrome_executable():
    return find_browser_executable("chrome")

def get_browser_executable_for_account(account_id):
    acc = get_account_info(account_id)
    custom_exe = acc.get("browser_executable")
    if custom_exe and os.path.exists(custom_exe):
        return custom_exe
    b_type = acc.get("browser_type", "chrome")
    return find_browser_executable(b_type)

def get_accounts():
    config = load_config()
    if "accounts" in config and isinstance(config["accounts"], list):
        return config["accounts"]
    # Fallback si ancien format 'browsers'
    accounts = []
    for k, v in config.get("browsers", {}).items():
        accounts.append({
            "id": k,
            "name": v.get("name", k),
            "browser_type": v.get("browser_type", "chrome"),
            "profile_dir": v.get("profile_dir", f"profiles/{k}"),
            "enabled": v.get("enabled", True)
        })
    return accounts

def get_account_info(account_id):
    for acc in get_accounts():
        if acc.get("id") == account_id:
            return acc
    return {
        "id": account_id,
        "name": account_id.replace("_", " ").title(),
        "browser_type": "chrome",
        "profile_dir": f"profiles/{account_id}",
        "enabled": True
    }

def add_new_account(name=None, browser_type="chrome"):
    config = load_config()
    accounts = config.get("accounts", [])
    existing_nums = []
    for acc in accounts:
        m = re.search(r"compte_(\d+)", acc.get("id", ""))
        if m:
            existing_nums.append(int(m.group(1)))
    next_num = max(existing_nums, default=len(accounts)) + 1
    new_id = f"compte_{next_num}"
    new_name = name or f"Compte {next_num}"
    b_type = browser_type.lower() if browser_type else "chrome"
    exe_path = find_browser_executable(b_type)

    new_acc = {
        "id": new_id,
        "name": new_name,
        "browser_type": b_type,
        "browser_executable": exe_path,
        "profile_dir": f"profiles/{new_id}",
        "enabled": True
    }
    accounts.append(new_acc)
    config["accounts"] = accounts
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    (BASE_DIR / "profiles" / new_id).mkdir(parents=True, exist_ok=True)
    return new_acc

def delete_account(account_id, remove_files=True):
    close_active_setup()
    kill_browser_processes(account_id)
    config = load_config()
    accounts = config.get("accounts", [])
    config["accounts"] = [acc for acc in accounts if acc.get("id") != account_id]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    if remove_files:
        p_dir = BASE_DIR / "profiles" / account_id
        if p_dir.exists():
            try:
                import shutil
                shutil.rmtree(p_dir, ignore_errors=True)
            except Exception:
                pass
        try:
            bc = load_best_cards()
            if account_id in bc:
                del bc[account_id]
                save_best_cards(bc)
        except Exception:
            pass
    return True

def rename_account(account_id, new_name):
    """Modifie le nom d'un compte dans config.json et met à jour l'historique."""
    if not new_name or not new_name.strip():
        return False
    new_name = new_name.strip()
    try:
        config = load_config()
        accounts = config.get("accounts", [])
        found = False
        for acc in accounts:
            if acc.get("id") == account_id:
                acc["name"] = new_name
                found = True
                break
        if found:
            config["accounts"] = accounts
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # Mise à jour synchronisée dans l'historique pour l'affichage
            try:
                history = load_history()
                hist_updated = False
                for entry in history:
                    if entry.get("browser_key") == account_id:
                        entry["browser"] = new_name
                        hist_updated = True
                if hist_updated:
                    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                        json.dump(history, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False

def save_config(config):
    """Sauvegarde la configuration globale."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def set_account_option(account_id, option_key, value):
    """Met à jour une option modulaire pour un compte (ex: auto_achievements, auto_friends)."""
    try:
        config = load_config()
        for acc in config.get("accounts", []):
            if acc.get("id") == account_id:
                acc[option_key] = value
                save_config(config)
                return True
    except Exception:
        pass
    return False

def send_discord_notification(title, description, color=0x38bdf8, fields=None):
    """Envoie une notification Discord Webhook riche et asynchrone sans bloquer l'application."""
    config = load_config()
    webhook_url = config.get("discord_webhook", "").strip()
    if not webhook_url:
        return False

    import threading
    import urllib.request

    def _send():
        try:
            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {"text": "WikiMasters Auto-Claimer • Companion"}
            }
            if fields:
                embed["fields"] = fields

            payload = json.dumps({
                "username": "WikiMasters Companion",
                "embeds": [embed]
            })
            req = urllib.request.Request(
                webhook_url,
                data=payload.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WikiMasters-Companion"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                pass
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()
    return True

def test_discord_webhook(webhook_url):
    """Teste immédiatement un Webhook Discord avec un message d'essai."""
    if not webhook_url or not webhook_url.strip():
        return False, "URL du webhook vide."
    import urllib.request

    try:
        payload = json.dumps({
            "username": "WikiMasters Companion",
            "embeds": [{
                "title": "✅ Connexion Discord Réussie !",
                "description": "Le webhook WikiMasters Auto-Claimer est parfaitement configuré.\nVous recevrez désormais des alertes pour vos cartes rares et vos comptes !",
                "color": 0x22c55e,
                "fields": [
                    {"name": "Statut", "value": "🟢 Opérationnel", "inline": True},
                    {"name": "Mode", "value": "Multi-Comptes Furtif", "inline": True}
                ],
                "footer": {"text": "WikiMasters Auto-Claimer"}
            }]
        })
        req = urllib.request.Request(
            webhook_url.strip(),
            data=payload.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WikiMasters-Companion"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            if 200 <= response.status < 300:
                return True, "Message de test envoyé avec succès sur Discord !"
            return False, f"Code de réponse Discord : {response.status}"
    except Exception as e:
        return False, f"Erreur de connexion : {e}"

def get_discord_settings():
    """Récupère les paramètres actuels de Discord Webhook."""
    cfg = load_config()
    return {
        "webhook_url": cfg.get("discord_webhook", ""),
        "notify_rare_only": cfg.get("discord_notify_rare_only", True),
        "notify_errors": cfg.get("discord_notify_errors", True)
    }

def set_discord_settings(webhook_url, notify_rare_only=True, notify_errors=True):
    """Enregistre les paramètres Discord Webhook."""
    cfg = load_config()
    cfg["discord_webhook"] = webhook_url.strip() if webhook_url else ""
    cfg["discord_notify_rare_only"] = bool(notify_rare_only)
    cfg["discord_notify_errors"] = bool(notify_errors)
    save_config(cfg)
    return True

_LAST_ACHIEVEMENTS_CHECK = {}

def should_check_account_achievements(account_id, cooldown_seconds=600):
    last = _LAST_ACHIEVEMENTS_CHECK.get(account_id, 0)
    return (time.time() - last) > cooldown_seconds

def record_achievements_check(account_id):
    _LAST_ACHIEVEMENTS_CHECK[account_id] = time.time()

def claim_account_achievements(page, account_name, status_callback=None):
    """
    Réclame automatiquement tous les succès débloqués sur /achievements.
    Protégé contre les boucles infinies et délais excessifs.
    """
    try:
        safe_notify(status_callback, f"[{account_name}] 🏆 Vérification des succès...", "info")
        # 1. Déclencher la synchronisation des succès via API
        page.evaluate("""async () => {
            try {
                await fetch('/api/achievements/check', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({event: 'achievements_sync'})
                });
            } catch(e) {}
        }""")
        
        # 2. Visite /achievements
        try:
            page.goto("https://wiki-masters.com/achievements", wait_until="domcontentloaded", timeout=8000)
        except Exception:
            return 0

        time.sleep(0.5)
        claimed_count = 0

        # Limité à 25 succès pour garantir une sortie immédiate
        for _ in range(25):
            btn = page.locator("button:has-text('Réclamer'):not([disabled]):not([aria-disabled='true'])").first
            if btn.count() == 0 or not btn.is_visible() or not btn.is_enabled():
                break

            card_container = btn.locator("xpath=ancestor::div[contains(@class, 'rounded') or contains(@class, 'border')][1]")
            title = "Succès"
            try:
                title = card_container.inner_text().split("\n")[0].strip()
            except Exception:
                pass

            human_delay(0.2, 0.4)
            btn.click()
            claimed_count += 1
            safe_notify(status_callback, f"[{account_name}] 🏆 Succès réclamé : {title} !", "success")
            time.sleep(0.4)

        if claimed_count > 0:
            safe_notify(status_callback, f"[{account_name}] 🎉 {claimed_count} succès réclamé(s) au total !", "success")
        return claimed_count
    except Exception as e:
        safe_notify(status_callback, f"[{account_name}] Erreur vérification succès : {e}", "warning")
        return 0

def sync_account_friends(page, current_account, all_accounts, status_callback=None):
    """
    Interconnecte automatiquement tous les comptes de config.json en tant qu'amis :
    1. Accepte toutes les demandes d'amis en attente.
    2. Envoie des demandes d'amis aux autres comptes enregistrés qui ne sont pas encore amis.
    """
    try:
        curr_name = current_account.get("name", current_account.get("id"))
        # 1. Accepter toutes les demandes d'amis entrantes
        page.evaluate("""async () => {
            try {
                await fetch('/api/friends/accept-all', { method: 'POST' });
            } catch(e) {}
        }""")

        # 2. Récupérer les amitiés existantes
        friends_data = page.evaluate("""async () => {
            try {
                const res = await fetch('/api/friends');
                if (res.ok) return await res.json();
            } catch(e) {}
            return null;
        }""")

        friendships = (friends_data or {}).get("friendships", [])
        known_friends = set()
        for f in friendships:
            addr = (f.get("addressee") or {}).get("username", "").lower()
            req = (f.get("requester") or {}).get("username", "").lower()
            if addr:
                known_friends.add(addr)
            if req:
                known_friends.add(req)

        # 3. Pour chaque autre compte activé
        for other in all_accounts:
            other_name = other.get("name", "").strip()
            if not other_name or other_name.lower() == curr_name.lower():
                continue
            if other_name.lower() not in known_friends:
                # Chercher et envoyer la demande
                search_res = page.evaluate("""async (q) => {
                    try {
                        const r = await fetch(`/api/friends/search?q=${encodeURIComponent(q)}`);
                        return await r.json();
                    } catch(e) { return null; }
                }""", other_name)
                
                users = (search_res or {}).get("users", [])
                target_user = next((u for u in users if u.get("username", "").lower() == other_name.lower()), None)
                if target_user and not target_user.get("friendship"):
                    page.evaluate("""async (id) => {
                        try {
                            await fetch('/api/friends', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({addressee_id: id})
                            });
                        } catch(e) {}
                    }""", target_user.get("id"))
                    safe_notify(status_callback, f"[{curr_name}] 🤝 Demande d'ami envoyée à {other_name}", "info")
                    human_delay(0.5, 1.2)
    except Exception:
        pass

def run_claim_achievements_standalone(account_id, status_callback=None):
    """Exécute manuellement la réclamation des succès pour un compte."""
    acc = get_account_info(account_id)
    name = acc.get("name", account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")
    exe_path = get_browser_executable_for_account(account_id)

    safe_notify(status_callback, f"[{name}] 🏆 Connexion pour réclamer les succès...", "info")
    kill_browser_processes(account_id)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(p_dir),
            executable_path=exe_path,
            headless=True,
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            args=get_browser_launch_args(account_id)
        )
        apply_stealth(context)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            claimed = claim_account_achievements(page, name, status_callback)
            extract_collection_stats(page, account_id)
            if claimed == 0:
                safe_notify(status_callback, f"[{name}] ℹ️ Aucun nouveau succès à réclamer pour le moment.", "info")
            return claimed
        finally:
            context.close()

def run_sync_friends_standalone(account_id, status_callback=None):
    """Exécute manuellement l'interconnexion d'amis pour un compte."""
    config = load_config()
    acc = get_account_info(account_id)
    name = acc.get("name", account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")
    exe_path = get_browser_executable_for_account(account_id)

    safe_notify(status_callback, f"[{name}] 🤝 Connexion pour synchroniser les amis...", "info")
    kill_browser_processes(account_id)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(p_dir),
            executable_path=exe_path,
            headless=True,
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            args=get_browser_launch_args(account_id)
        )
        apply_stealth(context)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://wiki-masters.com/friends", wait_until="domcontentloaded", timeout=25000)
            sync_account_friends(page, acc, config.get("accounts", []), status_callback)
            safe_notify(status_callback, f"[{name}] 🤝 Amis synchronisés avec succès !", "success")
        finally:
            context.close()

def transfer_cards(source_account_id, target_account_name, rarities, keep_duplicates_only=False, status_callback=None):
    """Transfère des cartes par lot entre deux comptes selon les raretés sélectionnées."""
    from transfer import execute_card_transfer
    return execute_card_transfer(
        source_account_id=source_account_id,
        target_account_name=target_account_name,
        rarities=rarities,
        keep_duplicates_only=keep_duplicates_only,
        status_callback=status_callback
    )



def is_account_configured(account_id):
    acc = get_account_info(account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")
    if not p_dir.exists():
        return False
    net_dir = p_dir / "Default" / "Network"
    cookies_file = p_dir / "Default" / "Network" / "Cookies"
    ls_dir = p_dir / "Default" / "Local Storage"
    return (net_dir.exists() and any(net_dir.iterdir())) or (cookies_file.exists()) or (ls_dir.exists() and any(ls_dir.iterdir()))

def get_resolved_executable(account_id=None):
    """Tous les comptes utilisent désormais Google Chrome pour une stabilité et discrétion maximales."""
    return get_chrome_executable()

def get_browser_launch_args(account_id=None):
    """Génère les arguments pour garantir un lancement silencieux sans fenêtre visible."""
    return [
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-sync",
        "--mute-audio",
        "--js-flags=--max-old-space-size=128",
        "--renderer-process-limit=2",
        "--window-position=-32000,-32000",
        "--window-size=1,1",
        "--disable-features=SplashScreen,AutoUpdate"
    ]

def should_run_headless(account_id=None):
    """Google Chrome supporte nativement le headless ultra-léger et discret."""
    return True

def verify_session(account_id):
    acc = get_account_info(account_id)
    exe_path = get_browser_executable_for_account(account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")

    if not is_account_configured(account_id):
        return False

    kill_browser_processes(account_id)
    time.sleep(0.6)

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(p_dir),
                executable_path=exe_path,
                headless=True,
                args=get_browser_launch_args(account_id)
            )
            apply_stealth(context)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://wiki-masters.com/pulls", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            check_and_handle_verification_modal(page)
            is_logged_in = ("/login" not in page.url and "/signup" not in page.url)
            context.close()
            return is_logged_in
    except Exception:
        return False

def close_active_setup():
    global _active_setup_proc
    proc = _active_setup_proc
    if proc is not None and proc.poll() is None:
        pid = proc.pid
        try:
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{ $p.CloseMainWindow() }}"
            ], timeout=4, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
    _active_setup_proc = None

def setup_account(account_id, start_url="https://wiki-masters.com/signup", status_callback=None):
    global _active_setup_proc
    close_active_setup()

    acc = get_account_info(account_id)
    name = acc.get("name", account_id)
    exe_path = get_browser_executable_for_account(account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")
    p_dir.mkdir(parents=True, exist_ok=True)

    b_type = acc.get("browser_type", "chrome")
    b_name = SUPPORTED_BROWSERS.get(b_type, {}).get("name", "Navigateur")

    if not os.path.exists(exe_path):
        safe_notify(status_callback, f"Exécutable {b_name} ({exe_path}) introuvable.", "error")
        return False, f"Exécutable introuvable : {exe_path}"

    kill_browser_processes(account_id)

    safe_notify(status_callback, f"Ouverture de {b_name} pour {name}...", "info")
    safe_notify(status_callback, f"Créez votre compte ou connectez-vous sur WikiMasters, puis fermez {b_name} ou cliquez sur 'J'ai fini'.", "warning")

    try:
        local_proc = subprocess.Popen([
            exe_path,
            f"--user-data-dir={p_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            start_url
        ])
        _active_setup_proc = local_proc

        while local_proc.poll() is None:
            time.sleep(0.8)

        _active_setup_proc = None
        time.sleep(1.5)
        kill_browser_processes(account_id)
        time.sleep(0.5)

        safe_notify(status_callback, f"Vérification de la session {name}...", "info")

        is_valid = verify_session(account_id)
        if is_valid:
            safe_notify(status_callback, f"Session validée pour {name} ! Compte prêt et persistant.", "success")
            return True, "Session validée"
        else:
            if is_account_configured(account_id):
                safe_notify(status_callback, f"Profil enregistré pour {name}. Prêt pour le tirage.", "info")
                return True, "Profil enregistré"
            else:
                safe_notify(status_callback, f"Fenêtre fermée pour {name} sans données de connexion.", "warning")
                return False, "Fenêtre fermée"

    except Exception as e:
        _active_setup_proc = None
        safe_notify(status_callback, f"Erreur lors de la configuration : {e}", "error")
        return False, str(e)

def open_account_browser(account_id, url="https://wiki-masters.com/pulls"):
    """
    Lance le navigateur associé à ce compte avec son profil persistant
    dans une fenêtre visible et autonome.
    Les cookies et sessions de connexion sont automatiquement chargés.
    """
    acc = get_account_info(account_id)
    name = acc.get("name", account_id)
    exe_path = get_browser_executable_for_account(account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")
    p_dir.mkdir(parents=True, exist_ok=True)

    b_type = acc.get("browser_type", "chrome")
    b_name = SUPPORTED_BROWSERS.get(b_type, {}).get("name", "Navigateur")

    if not os.path.exists(exe_path):
        return False, f"Exécutable {b_name} ({exe_path}) introuvable."

    kill_browser_processes(account_id)
    time.sleep(0.3)

    cmd = [
        exe_path,
        f"--user-data-dir={p_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url
    ]
    try:
        subprocess.Popen(cmd)
        return True, f"{b_name} ouvert pour {name}."
    except Exception as e:
        return False, str(e)

def extract_timer_seconds(page):
    try:
        body_text = page.inner_text("body")
        t_match = re.search(r'Prochain dans\s*([0-9]{1,2}:[0-9]{2})', body_text, re.IGNORECASE)
        if t_match:
            parts = t_match.group(1).split(":")
            return int(parts[0]) * 60 + int(parts[1])

        # Chercher dans les locators contenant 'Prochain dans'
        try:
            for el in page.locator("*:has-text('Prochain dans')").all():
                txt = el.inner_text()
                m = re.search(r'Prochain dans\s*([0-9]{1,2}):([0-9]{2})', txt, re.IGNORECASE)
                if m:
                    return int(m.group(1)) * 60 + int(m.group(2))
        except Exception:
            pass

        # Mot-clé proche avec MM:SS (pour éviter de matcher des dates ou heures de l'historique)
        t_near = re.search(r'(?:prochain|dans|attente|minute)[^\n\r\d]{0,25}([0-9]{1,2}):([0-9]{2})', body_text, re.IGNORECASE)
        if t_near:
            return int(t_near.group(1)) * 60 + int(t_near.group(2))
    except Exception:
        pass
    return None

def extract_stock_count(page):
    try:
        ouvrir_btn = page.locator("button:has-text('Ouvrir'):not([disabled])").first
        has_active_open = (ouvrir_btn.count() > 0 and ouvrir_btn.is_visible() and ouvrir_btn.is_enabled())

        body_text = page.inner_text("body")
        m = re.search(r'(\d+)\s*/\s*10', body_text)
        if m:
            count = int(m.group(1))
            if count > 0:
                return count
            elif has_active_open:
                return 1
            return 0

        m_p = re.search(r'(\d+)\s*paquet', body_text, re.IGNORECASE)
        if m_p:
            count = int(m_p.group(1))
            if count > 0:
                return count

        if has_active_open:
            return 1
    except Exception:
        pass
    return 0

def extract_current_card_details(page):
    """
    Extrait le titre et la rareté de la carte actuellement affichée.
    Filtre rigoureusement les boutons d'interface (Ouvrir, Continuer, etc.).
    """
    title = ""
    rarity = "C"
    blacklist_words = [
        "carte", "encore", "wikimasters", "points", "continuer", "ouvrir",
        "ouverture", "ouverture...", "dernière", "derniere", "paquet", "paquets",
        "stock", "collection", "marché", "bataille", "profil", "succès",
        "classement", "connexion", "déconnexion", "échanges", "rechargez",
        "s'abonner", "comment ça marche"
    ]
    try:
        # 1. Rareté : badge officiel en haut à gauche
        badges = page.locator("div[class*='top-2'][class*='left-2'], span[class*='top-2'][class*='left-2']").all()
        for b in badges:
            txt = b.inner_text().strip().upper()
            if txt in RARITY_MAP:
                rarity = txt
                break
        else:
            # Fallback classe de lueur CSS
            glow_el = page.locator("[class*='glow-']").first
            if glow_el.count() > 0:
                cls = glow_el.get_attribute("class") or ""
                for code in ["ur", "sr", "pc", "r", "l"]:
                    if f"glow-{code}" in cls.lower():
                        rarity = code.upper()
                        break

        # 2. Titre de la carte : chercher en priorité dans h3 (titre officiel)
        headings = page.locator("h3").all()
        for h in headings:
            txt = h.inner_text().strip()
            if txt and 2 < len(txt) < 90 and not any(w in txt.lower() for w in blacklist_words):
                title = txt
                break

        # Fallback si h3 n'est pas encore présent : éléments en gras dans le conteneur de carte
        if not title:
            bolds = page.locator("div[class*='card'] strong, div[class*='card'] [class*='font-bold'], [class*='font-bold'], strong").all()
            for b in bolds:
                txt = b.inner_text().strip()
                if txt and 2 < len(txt) < 70 and not any(w in txt.lower() for w in blacklist_words):
                    title = txt
                    break
    except Exception:
        pass

    return title, rarity

def claim_account(account_id, headless=True, target_url=None, status_callback=None, pack_callback=None):
    """
    Exécute la vérification et l'ouverture de TOUS les paquets disponibles.
    Tire en boucle tant qu'il y a du stock (1/10, 2/10...), extrait les raretés
    exactes de chaque carte, et libère 100% de la mémoire dès la fin.
    """
    config = load_config()
    acc = get_account_info(account_id)
    name = acc.get("name", account_id)
    exe_path = get_browser_executable_for_account(account_id)
    p_dir = BASE_DIR / acc.get("profile_dir", f"profiles/{account_id}")
    target_url = target_url or config.get("target_url", "https://wiki-masters.com/pulls")

    if not is_account_configured(account_id):
        return {
            "status": "not_configured",
            "browser": name,
            "browser_key": account_id,
            "details": f"{name} non configuré. Cliquez sur '🔑 Connecter'."
        }

    safe_notify(status_callback, f"[{name}] Vérification furtive du compte...", "info")
    kill_browser_processes(account_id)

    with sync_playwright() as p:
        context = None
        try:
            # Arguments optimisés pour une empreinte RAM et CPU minimale
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(p_dir),
                executable_path=exe_path,
                headless=should_run_headless(account_id),
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                args=get_browser_launch_args(account_id)
            )
            apply_stealth(context)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            # S'assurer que Next.js a fini d'hydrater la page et que le spinner est passé
            try:
                page.wait_for_selector(
                    "button:has-text('Ouvrir'), *:has-text('Prochain dans'), input[type='email'], div.cf-turnstile, iframe[src*='turnstile']",
                    timeout=8000
                )
            except Exception:
                pass

            # Résoudre immédiatement la modale interne 'Vérification rapide' si affichée
            check_and_handle_verification_modal(page, status_callback)

            # Vérifier si un défi Cloudflare Turnstile est présent
            cf_frames = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], div.cf-turnstile")
            if cf_frames.count() > 0:
                safe_notify(status_callback, f"[{name}] 🛡️ Vérification anti-bot détectée. Résolution discrète...", "stealth")
                solved = check_and_handle_turnstile(page)
                if solved:
                    safe_notify(status_callback, f"[{name}] 🛡️ Vérification validée discrètement avec succès.", "success")
                    time.sleep(1.0)
                else:
                    time.sleep(1.5)
                    has_content = page.locator("button:has-text('Ouvrir'), div:has-text('paquets disponibles')").count() > 0
                    if not has_content:
                        context.close()
                        kill_browser_processes(account_id)
                        cfg = load_config()
                        if cfg.get("discord_notify_errors", True):
                            send_discord_notification(
                                f"⚠️ Défi Anti-Bot Détecté — {name}",
                                f"Un défi bloquant a été détecté sur **{name}**.\nOuvrez l'application et cliquez sur **'🛠️ Résoudre'**.",
                                color=0xef4444
                            )
                        return {
                            "status": "captcha_detected",
                            "browser": name,
                            "browser_key": account_id,
                            "seconds_left": 300,
                            "timer_str": "05:00",
                            "details": "⚠️ Défi anti-bot bloquant détecté. Les autres comptes continuent normalement. Cliquez sur '🛠️ Résoudre'."
                        }

            # Vérifier si on est redirigé vers /login
            if "/login" in page.url or "/signup" in page.url:
                time.sleep(0.5)
                if "/login" in page.url or "/signup" in page.url:
                    context.close()
                    kill_browser_processes(account_id)
                    cfg = load_config()
                    if cfg.get("discord_notify_errors", True):
                        send_discord_notification(
                            f"⚠️ Session Expirée — {name}",
                            f"La session du compte **{name}** a expiré.\nVeuillez vous reconnecter via le bouton **'🔑 Connecter'**.",
                            color=0xef4444
                        )
                    return {
                        "status": "login_required",
                        "browser": name,
                        "browser_key": account_id,
                        "details": "Session expirée. Veuillez vous reconnecter."
                    }

            total_packs_opened = 0
            all_pulled_cards = []
            all_rarities = []
            all_pulled_card_objects = []
            latest_screenshot = None
            last_pack_rarity_summary = ""

            # Boucle d'ouverture de TOUS les paquets en attente
            while True:
                stock = extract_stock_count(page)
                ouvrir_btn = page.locator("button:has-text('Ouvrir'):not([disabled])").first
                is_btn_ready = (ouvrir_btn.count() > 0 and ouvrir_btn.is_visible() and ouvrir_btn.is_enabled())

                if not is_btn_ready and stock > 0:
                    time.sleep(0.8)
                    ouvrir_btn = page.locator("button:has-text('Ouvrir'):not([disabled])").first
                    is_btn_ready = (ouvrir_btn.count() > 0 and ouvrir_btn.is_visible() and ouvrir_btn.is_enabled())

                if not is_btn_ready:
                    break

                current_pack_num = total_packs_opened + 1
                safe_notify(status_callback, f"[{name}] 📦 Ouverture du paquet #{current_pack_num} (Stock: {stock})...", "stealth")

                # Clic d'ouverture
                human_delay(0.2, 0.5)
                ouvrir_btn.click()

                # Attente EXPLICITE de la fin de l'animation de déchirure du paquet (3 secondes sur WikiMasters)
                try:
                    page.wait_for_selector(
                        "button.w-12.h-12:not([disabled]), button:has-text('Continuer'), button:has-text('Encore'), text=/Carte\\s*1\\s*\\/\\s*5/i",
                        timeout=12000
                    )
                except Exception:
                    time.sleep(3.2)

                # Si la modale 'Vérification rapide' s'est déclenchée au clic
                if check_and_handle_verification_modal(page, status_callback):
                    time.sleep(1.0)
                    ouvrir_retry = page.locator("button:has-text('Ouvrir'):not([disabled])").first
                    if ouvrir_retry.count() > 0 and ouvrir_retry.is_visible() and ouvrir_retry.is_enabled():
                        ouvrir_retry.click()
                        try:
                            page.wait_for_selector(
                                "button.w-12.h-12:not([disabled]), button:has-text('Continuer'), button:has-text('Encore')",
                                timeout=10000
                            )
                        except Exception:
                            time.sleep(3.0)

                total_packs_opened += 1

                pack_cards = []
                pack_rarities = []
                pack_card_objects = []

                # Révélation précise des 5 cartes du paquet
                for card_idx in range(5):
                    time.sleep(0.4)

                    card_title, card_rarity = extract_current_card_details(page)
                    if not card_title:
                        time.sleep(0.3)
                        card_title, card_rarity = extract_current_card_details(page)

                    if not card_title:
                        card_title = f"Carte #{card_idx + 1}"

                    pack_cards.append(card_title)
                    pack_rarities.append(card_rarity)

                    # Capture d'écran individuelle
                    ts_now = datetime.now().strftime("%Y%m%d_%H%M%S")
                    card_shot_path = str(SCREENSHOTS_DIR / f"{account_id}_{ts_now}_p{current_pack_num}_c{card_idx+1}.png")
                    latest_screenshot = str(SCREENSHOTS_DIR / f"{account_id}_latest.png")
                    try:
                        page.screenshot(path=card_shot_path)
                        import shutil
                        shutil.copyfile(card_shot_path, latest_screenshot)
                    except Exception:
                        card_shot_path = ""

                    pack_card_objects.append({
                        "title": card_title,
                        "rarity": card_rarity,
                        "screenshot": card_shot_path,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })

                    # Navigation vers la carte suivante via la flèche droite pour cartes 1 à 4
                    if card_idx < 4:
                        arrow_next = page.locator("button.w-12.h-12:not([disabled]), button:has(polyline[points*='15 12 9 6']):not([disabled])")
                        if arrow_next.count() > 0:
                            arrow_next.last.click()
                        else:
                            time.sleep(0.3)

                # Validation finale du paquet par 'Continuer' sur la carte 5
                time.sleep(0.4)
                continuer_btn = page.locator("button:has-text('Continuer'):not([disabled]), button.px-8.py-3:not([disabled])").first
                if continuer_btn.count() > 0 and continuer_btn.is_visible():
                    continuer_btn.click()
                else:
                    for cb in page.locator("button:has-text('Continuer')").all():
                        if cb.is_visible() and not cb.is_disabled():
                            cb.click()
                            break

                # Attendre que la modale de paquet se ferme complètement
                try:
                    page.wait_for_selector("button:has-text('Ouvrir'), *:has-text('Prochain dans')", timeout=8000)
                except Exception:
                    time.sleep(1.0)

                check_and_handle_verification_modal(page, status_callback)

                all_pulled_cards.extend(pack_cards)
                all_rarities.extend(pack_rarities)
                all_pulled_card_objects.extend(pack_card_objects)
                last_pack_rarity_summary = format_rarity_summary(pack_rarities)

                safe_notify(status_callback, f"[{name}] ✅ Paquet #{current_pack_num} validé ! ({last_pack_rarity_summary})", "success")

                # Mise à jour immédiate du Top 10 et notification live du paquet
                if pack_card_objects:
                    register_pulled_cards(account_id, pack_card_objects)

                if pack_callback:
                    try:
                        pack_callback({
                            "account_id": account_id,
                            "pack_num": current_pack_num,
                            "cards": pack_cards,
                            "rarities": pack_rarities,
                            "card_objects": pack_card_objects,
                            "screenshot": latest_screenshot,
                            "stock": f"{max(0, stock - 1)} / 10" if isinstance(stock, int) else "—",
                            "rarity_summary": last_pack_rarity_summary
                        })
                    except Exception:
                        pass

                time.sleep(0.5)

            time.sleep(0.5)
            final_stock = extract_stock_count(page)
            timer_sec = extract_timer_seconds(page)
            if timer_sec is None:
                time.sleep(0.8)
                timer_sec = extract_timer_seconds(page)
            if timer_sec is None:
                timer_sec = 60

            if final_stock > 0:
                timer_sec = 5

            mins = timer_sec // 60
            secs = timer_sec % 60
            timer_str = f"{mins:02d}:{secs:02d}"

            global_rarity_summary = format_rarity_summary(all_rarities) if all_rarities else last_pack_rarity_summary

            if total_packs_opened > 0:
                save_history({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "browser": name,
                    "browser_key": account_id,
                    "packs_count": total_packs_opened,
                    "cards": all_pulled_cards,
                    "rarities": all_rarities,
                    "card_objects": all_pulled_card_objects,
                    "rarity_summary": global_rarity_summary,
                    "screenshot": latest_screenshot
                })

                # Notification Discord automatique
                try:
                    cfg = load_config()
                    if cfg.get("discord_webhook"):
                        notify_rare_only = cfg.get("discord_notify_rare_only", True)
                        has_rare = any(r in ["L", "UR", "SR", "R"] for r in all_rarities)
                        
                        if has_rare or not notify_rare_only:
                            color = 0xfbbf24 if any(r == "L" for r in all_rarities) else (
                                0xec4899 if any(r == "UR" for r in all_rarities) else (
                                0xa855f7 if any(r == "SR" for r in all_rarities) else 0x34d399
                            ))
                            badge_header = "👑 LÉGENDAIRE OBTENUE !" if any(r == "L" for r in all_rarities) else (
                                "💎 ULTRA RARE OBTENUE !" if any(r == "UR" for r in all_rarities) else (
                                "⭐ SUPER RARE OBTENUE !" if any(r == "SR" for r in all_rarities) else "🎉 Nouveau Tirage"
                            ))
                            
                            cards_preview = "\n".join([f"`[{c.get('rarity','C')}]` **{c.get('title','')}**" for c in all_pulled_card_objects[:8]])
                            if len(all_pulled_card_objects) > 8:
                                cards_preview += f"\n*...et {len(all_pulled_card_objects) - 8} autre(s) carte(s)*"

                            fields = [
                                {"name": "👤 Compte", "value": f"**{name}**", "inline": True},
                                {"name": "📦 Paquets", "value": f"{total_packs_opened} paquet(s)", "inline": True},
                                {"name": "📊 Raretés", "value": global_rarity_summary or "5 cartes par paquet", "inline": False},
                                {"name": "🃏 Cartes Obtenues", "value": cards_preview or "Cartes enregistrées", "inline": False}
                            ]
                            send_discord_notification(
                                f"{badge_header} — {name}",
                                f"**{name}** a ouvert {total_packs_opened} paquet(s) !\nBilan : {global_rarity_summary}",
                                color=color,
                                fields=fields
                            )
                except Exception:
                    pass

            # 1. Extraction des statistiques réelles de collection (total et raretés)
            col_stats = extract_collection_stats(page, account_id)

            # 2. Auto-claim des succès si l'option est cochée (si paquets ouverts ou périodique)
            should_check_ach = acc.get("auto_achievements", True) and (
                total_packs_opened > 0 or should_check_account_achievements(account_id)
            )
            if should_check_ach:
                try:
                    claim_account_achievements(page, name, status_callback)
                    record_achievements_check(account_id)
                except Exception:
                    pass

            # 3. Interconnexion automatique des amis si l'option est cochée et paquets ouverts
            if acc.get("auto_friends", True) and total_packs_opened > 0:
                try:
                    sync_account_friends(page, acc, config.get("accounts", []), status_callback)
                except Exception:
                    pass

            # 4. Auto-acceptation des échanges reçus entre comptes
            if acc.get("auto_accept_trades", True):
                try:
                    from transfer import accept_incoming_trades
                    trade_res = accept_incoming_trades(page)
                    if trade_res and trade_res.get("ok") and trade_res.get("accepted"):
                        acc_trades = trade_res["accepted"]
                        safe_notify(status_callback, f"[{name}] 🤝 {len(acc_trades)} échange(s) reçu(s) accepté(s) automatiquement !", "success")
                except Exception:
                    pass

            context.close()
            context = None
            kill_browser_processes(account_id)

            if total_packs_opened > 0:
                return {
                    "status": "claimed",
                    "browser": name,
                    "browser_key": account_id,
                    "packs_opened": total_packs_opened,
                    "cards": all_pulled_cards,
                    "rarities": all_rarities,
                    "top_cards": get_account_best_cards(account_id),
                    "rarity_summary": global_rarity_summary,
                    "seconds_left": timer_sec,
                    "timer_str": timer_str,
                    "stock": f"{final_stock} / 10",
                    "screenshot": latest_screenshot,
                    "collection_stats": col_stats or get_account_collection_stats(account_id),
                    "details": f"🎉 {total_packs_opened} paquet(s) ouvert(s) ! [{global_rarity_summary}] | Prochain dans {timer_str}"
                }
            else:
                return {
                    "status": "waiting",
                    "browser": name,
                    "browser_key": account_id,
                    "seconds_left": timer_sec,
                    "timer_str": timer_str,
                    "stock": f"{final_stock} / 10",
                    "top_cards": get_account_best_cards(account_id),
                    "collection_stats": col_stats or get_account_collection_stats(account_id),
                    "details": f"📦 Stock : {final_stock}/10 | Prochain paquet dans {timer_str}"
                }

        except Exception as e:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            kill_browser_processes(account_id)
            return {
                "status": "error",
                "browser": name,
                "browser_key": account_id,
                "seconds_left": 60,
                "details": str(e)
            }

