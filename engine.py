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
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

from stealth import apply_stealth, human_delay, human_click, check_and_handle_turnstile, check_and_handle_verification_modal

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = BASE_DIR / "history.json"
STATS_FILE = BASE_DIR / "stats.json"

_active_setup_proc = None

def kill_browser_processes(browser_key):
    """Ferme proprement tout processus résiduel du navigateur pour ce profil avant réouverture."""
    try:
        ps_cmd = f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -match 'wikimasters-autoclaim\\\\profiles\\\\{browser_key}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            capture_output=True
        )
    except Exception:
        pass
    time.sleep(0.4)

def load_lifetime_stats():
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

# Dictionnaire des raretés officielles WikiMasters
RARITY_MAP = {
    "C": {"singular": "commune", "plural": "communes"},
    "PC": {"singular": "peu commune", "plural": "peu communes"},
    "R": {"singular": "rare", "plural": "rares"},
    "SR": {"singular": "super rare", "plural": "super rares"},
    "UR": {"singular": "ultra rare", "plural": "ultra rares"},
    "L": {"singular": "légendaire", "plural": "légendaires"},
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
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_history(entry):
    try:
        history = load_history()
        history.insert(0, entry)
        history = history[:500]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        b_key = entry.get("browser_key")
        packs = entry.get("packs_count", 1)
        if b_key:
            update_lifetime_stats(b_key, packs)
    except Exception:
        pass

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
    Extrait instantanément le titre et la rareté de la carte affichée.
    Consommation CPU quasi-nulle car l'arbre DOM est déjà en mémoire.
    """
    title = ""
    rarity = "C"
    try:
        # 1. Rareté : badge en haut à gauche
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

        # 2. Titre de la carte
        headings = page.locator("h3").all()
        for h in headings:
            txt = h.inner_text().strip()
            if txt and 2 < len(txt) < 90 and "carte" not in txt.lower():
                title = txt
                break
        if not title:
            bolds = page.locator("[class*='font-bold'], strong").all()
            for b in bolds:
                txt = b.inner_text().strip()
                if txt and 2 < len(txt) < 70 and not any(w in txt.lower() for w in ["carte", "encore", "wikimasters", "points", "continuer"]):
                    title = txt
                    break
    except Exception:
        pass

    return title, rarity

def claim_account(account_id, headless=True, status_callback=None):
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
    target_url = config.get("target_url", "https://wiki-masters.com/pulls")

    if not is_account_configured(account_id):
        return {
            "status": "not_configured",
            "browser": name,
            "browser_key": account_id,
            "details": f"{name} non configuré. Cliquez sur '🔑 Connecter'."
        }

    # Délai humain aléatoire (anti-détection temporelle)
    human_delay(0.5, 1.8)
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
                page.goto(target_url, wait_until="networkidle", timeout=25000)
            except Exception:
                page.goto(target_url, wait_until="domcontentloaded", timeout=25000)

            # S'assurer que Next.js a fini d'hydrater les paquets et compteurs
            for _ in range(12):
                ouvrir_btn_init = page.locator("button:has-text('Ouvrir'):not([disabled])").first
                if ouvrir_btn_init.count() > 0 and ouvrir_btn_init.is_visible() and ouvrir_btn_init.is_enabled():
                    break
                b_text = page.inner_text("body")
                if "Prochain dans" in b_text:
                    time.sleep(0.5)
                    break
                time.sleep(0.5)

            # Résoudre immédiatement la modale interne 'Vérification rapide' si affichée
            check_and_handle_verification_modal(page, status_callback)

            # Vérifier si un défi Cloudflare Turnstile est présent
            cf_frames = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], div.cf-turnstile")
            if cf_frames.count() > 0:
                safe_notify(status_callback, f"[{name}] 🛡️ Vérification anti-bot détectée. Résolution discrète...", "stealth")
                solved = check_and_handle_turnstile(page)
                if solved:
                    safe_notify(status_callback, f"[{name}] 🛡️ Vérification validée discrètement avec succès.", "success")
                    time.sleep(2.0)
                else:
                    time.sleep(2.5)
                    # Si après tentative le défi persiste et bloque l'accès aux boutons
                    has_content = page.locator("button:has-text('Ouvrir'), div:has-text('paquets disponibles')").count() > 0
                    if not has_content:
                        context.close()
                        return {
                            "status": "captcha_detected",
                            "browser": name,
                            "browser_key": account_id,
                            "seconds_left": 300,
                            "timer_str": "05:00",
                            "details": "⚠️ Défi anti-bot bloquant détecté. Les autres comptes continuent normalement. Cliquez sur '🛠️ Résoudre'."
                        }

            # Vérifier si on est redirigé vers /login
            if "/login" in page.url:
                context.close()
                return {
                    "status": "login_required",
                    "browser": name,
                    "browser_key": account_id,
                    "details": "Session expirée. Veuillez vous reconnecter."
                }

            total_packs_opened = 0
            all_pulled_cards = []
            all_rarities = []
            latest_screenshot = None
            last_pack_rarity_summary = ""

            # Boucle d'ouverture de TOUS les paquets en attente
            while True:
                stock = extract_stock_count(page)
                ouvrir_btn = page.locator("button:has-text('Ouvrir'):not([disabled])").first

                is_btn_ready = (ouvrir_btn.count() > 0 and ouvrir_btn.is_visible() and ouvrir_btn.is_enabled())

                # Si le stock affiche >= 1 mais que le bouton met un instant à devenir cliquable
                if stock > 0 and not is_btn_ready:
                    time.sleep(1.5)
                    ouvrir_btn = page.locator("button:has-text('Ouvrir'):not([disabled])").first
                    is_btn_ready = (ouvrir_btn.count() > 0 and ouvrir_btn.is_visible() and ouvrir_btn.is_enabled())

                if not is_btn_ready and stock == 0:
                    break

                if not is_btn_ready:
                    break

                current_pack_num = total_packs_opened + 1
                safe_notify(status_callback, f"[{name}] 📦 Ouverture du paquet #{current_pack_num} (Stock disponible: {stock})...", "stealth")

                human_delay(0.6, 1.3)
                human_click(page, ouvrir_btn)
                time.sleep(1.2)

                # Si la modale 'Vérification rapide' s'est déclenchée au clic
                if check_and_handle_verification_modal(page, status_callback):
                    time.sleep(1.5)
                    ouvrir_retry = page.locator("button:has-text('Ouvrir'):not([disabled])").first
                    if ouvrir_retry.count() > 0 and ouvrir_retry.is_visible() and ouvrir_retry.is_enabled():
                        human_click(page, ouvrir_retry)

                total_packs_opened += 1

                # Attente fluide de l'apparition des cartes
                human_delay(2.2, 3.2)

                pack_cards = []
                pack_rarities = []

                # Révélation des 5 cartes
                for card_idx in range(5):
                    card_title, card_rarity = extract_current_card_details(page)
                    if card_title and card_title not in pack_cards:
                        pack_cards.append(card_title)
                    pack_rarities.append(card_rarity)

                    if card_idx == 4:
                        # Attendre que l'animation 3D de rotation de la 5ème carte soit 100% terminée et stable
                        time.sleep(1.8)
                        # Ré-extraire au cas où le texte s'est affiché après la rotation
                        c_title, c_rarity = extract_current_card_details(page)
                        if c_title and c_title not in pack_cards:
                            pack_cards[-1] = c_title
                        if c_rarity:
                            pack_rarities[-1] = c_rarity

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        latest_screenshot = str(SCREENSHOTS_DIR / f"{account_id}_latest.png")
                        archive_shot = str(SCREENSHOTS_DIR / f"{account_id}_{timestamp}.png")
                        try:
                            page.screenshot(path=latest_screenshot)
                            page.screenshot(path=archive_shot)
                        except Exception:
                            pass

                    # Flèche suivante
                    arrow_next = page.locator("button:has(polyline[points='9 18 15 12 9 6']):not([disabled])").first
                    if arrow_next.count() > 0 and arrow_next.is_visible() and arrow_next.is_enabled():
                        human_delay(0.4, 0.9)
                        human_click(page, arrow_next)
                    else:
                        human_delay(0.3, 0.6)

                # Validation finale du paquet par 'Continuer'
                continuer_btn = page.locator("button:has-text('Continuer'):not([disabled])").first
                if continuer_btn.count() > 0 and continuer_btn.is_visible() and continuer_btn.is_enabled():
                    human_delay(0.7, 1.2)
                    human_click(page, continuer_btn)
                    human_delay(2.0, 3.0)
                else:
                    human_delay(1.5, 2.5)

                check_and_handle_verification_modal(page, status_callback)

                all_pulled_cards.extend(pack_cards)
                all_rarities.extend(pack_rarities)
                last_pack_rarity_summary = format_rarity_summary(pack_rarities)

                safe_notify(status_callback, f"[{name}] ✅ Paquet #{current_pack_num} validé ! ({last_pack_rarity_summary})", "success")
                human_delay(1.2, 2.2)

            time.sleep(1.2)
            final_stock = extract_stock_count(page)
            timer_sec = extract_timer_seconds(page)
            if timer_sec is None:
                time.sleep(1.5)
                timer_sec = extract_timer_seconds(page)
            if timer_sec is None:
                # Si le timer n'a pas pu être lu, revérifier rapidement dans 60s
                # au lieu de bloquer l'application pendant 10 minutes (600s) !
                timer_sec = 60

            # Si des paquets sont encore disponibles (stock > 0), revérifier dans 5s
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
                    "rarity_summary": global_rarity_summary,
                    "screenshot": latest_screenshot
                })

            context.close()
            context = None

            if total_packs_opened > 0:
                return {
                    "status": "claimed",
                    "browser": name,
                    "browser_key": account_id,
                    "packs_opened": total_packs_opened,
                    "cards": all_pulled_cards,
                    "rarities": all_rarities,
                    "rarity_summary": global_rarity_summary,
                    "seconds_left": timer_sec,
                    "timer_str": timer_str,
                    "stock": f"{final_stock} / 10",
                    "screenshot": latest_screenshot,
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
                    "details": f"📦 Stock : {final_stock}/10 | Prochain paquet dans {timer_str}"
                }

        except Exception as e:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            return {
                "status": "error",
                "browser": name,
                "browser_key": account_id,
                "seconds_left": 60,
                "details": str(e)
            }
