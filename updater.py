"""
Module de mise à jour automatique HTTP pour WikiMasters Auto-Claimer.
Télécharge les scripts mis à jour directement depuis GitHub sans nécessiter Git.
IMPORTANT : Ne touche JAMAIS au dossier profiles/, ni à config.json, ni à history.json.
Les sessions, cookies et comptes de l'utilisateur sont préservés à 100%.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
VERSION_FILE = BASE_DIR / "version.json"

DEFAULT_REPO = "priouzob/wikimasters-autoclaim"
DEFAULT_BRANCH = "main"
DEFAULT_FILES = ["engine.py", "gui.py", "stealth.py", "updater.py", "transfer.py"]

def load_version_info():
    if VERSION_FILE.exists():
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "version": "1.0.0",
        "github_repo": DEFAULT_REPO,
        "branch": DEFAULT_BRANCH,
        "files": DEFAULT_FILES
    }

def save_version_info(data):
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def get_local_version():
    return load_version_info().get("version", "1.0.0")

def parse_version_tuple(v_str):
    """Convertit '1.2.3' en tuple (1, 2, 3) pour comparaison fiable."""
    try:
        cleaned = v_str.lower().lstrip("v").strip()
        return tuple(int(x) for x in cleaned.split("."))
    except Exception:
        return (0, 0, 0)

def fetch_remote_version_info(timeout=3):
    """Récupère les métadonnées de version depuis GitHub raw."""
    info = load_version_info()
    repo = info.get("github_repo", DEFAULT_REPO)
    branch = info.get("branch", DEFAULT_BRANCH)
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/version.json"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "WikiMasters-AutoClaim-Updater/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)

def check_for_updates(timeout=3):
    """
    Vérifie si une nouvelle version est disponible sur GitHub.
    Retourne : (has_update: bool, remote_version: str, info_dict: dict)
    """
    try:
        local_v = get_local_version()
        remote_data = fetch_remote_version_info(timeout=timeout)
        remote_v = remote_data.get("version", "1.0.0")

        if parse_version_tuple(remote_v) > parse_version_tuple(local_v):
            return True, remote_v, remote_data
        return False, remote_v, remote_data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, get_local_version(), {"error": "Dépôt GitHub non trouvé ou pas encore public"}
        return False, get_local_version(), {"error": f"Erreur HTTP {e.code}"}
    except Exception as e:
        return False, get_local_version(), {"error": str(e)}

def perform_update(status_callback=None, timeout=5):
    """
    Télécharge et remplace les fichiers de code (.py) modifiés.
    Garantit que profiles/ et config.json ne sont JAMAIS modifiés.
    """
    def log(msg):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass
        else:
            print(f"[Updater] {msg}")

    has_update, remote_v, remote_data = check_for_updates(timeout=timeout)
    if not has_update:
        err = remote_data.get("error") if isinstance(remote_data, dict) else None
        if err:
            return False, f"Vérification impossible ({err})."
        return False, f"Vous disposez déjà de la dernière version (v{get_local_version()})."

    info = load_version_info()
    repo = info.get("github_repo", DEFAULT_REPO)
    branch = info.get("branch", DEFAULT_BRANCH)
    files_to_download = remote_data.get("files", DEFAULT_FILES)

    # Sécurité absolue : interdiction de toucher aux fichiers utilisateur
    # Ces fichiers contiennent les cookies, sessions et données persos de chaque utilisateur
    FORBIDDEN_FILES = [
        "config.json", "history.json", "stats.json",
        "profiles", "screenshots",          # dossiers entiers bloqués
        ".bak", ".log", ".tmp",             # fichiers temporaires/backup
    ]
    files_to_download = [
        f for f in files_to_download
        if not any(forbidden in f.lower() for forbidden in FORBIDDEN_FILES)
        and not f.startswith("/")           # pas de chemins absolus
        and ".." not in f                  # pas de path traversal
        and f.endswith(".py")              # uniquement des fichiers Python
    ]

    log(f"Téléchargement de la mise à jour v{remote_v}...")

    downloaded_files = []
    try:
        for filename in files_to_download:
            file_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{filename}"
            target_path = BASE_DIR / filename
            tmp_path = BASE_DIR / f"{filename}.tmp"

            req = urllib.request.Request(
                file_url,
                headers={"User-Agent": "WikiMasters-AutoClaim-Updater/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()

            with open(tmp_path, "wb") as f:
                f.write(data)

            downloaded_files.append((tmp_path, target_path))

        # Si tous les téléchargements ont réussi, on remplace de manière atomique
        for tmp_path, target_path in downloaded_files:
            if target_path.exists():
                bak_path = Path(str(target_path) + ".bak")
                try:
                    if bak_path.exists():
                        bak_path.unlink()
                    target_path.rename(bak_path)
                except Exception:
                    pass

            tmp_path.rename(target_path)

            bak_path = Path(str(target_path) + ".bak")
            if bak_path.exists():
                try:
                    bak_path.unlink()
                except Exception:
                    pass

        # Mise à jour du version.json local
        info["version"] = remote_v
        info["files"] = files_to_download
        save_version_info(info)

        log(f"Mise à jour v{remote_v} installée avec succès !")
        return True, f"Mise à jour v{remote_v} installée avec succès !"

    except Exception as e:
        # Nettoyage des fichiers temporaires en cas d'erreur
        for tmp_path, _ in downloaded_files:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        log(f"Échec de la mise à jour : {e}")
        return False, f"Erreur lors de la mise à jour : {e}"

if __name__ == "__main__":
    silent = ("--silent" in sys.argv)
    if not silent:
        print(f"=== WikiMasters Auto-Claimer Updater (v{get_local_version()}) ===")
        print("Vérification des mises à jour sur GitHub...")

    success, msg = perform_update()
    if not silent:
        print(msg)
    elif success:
        print(f"[Updater] {msg}")
