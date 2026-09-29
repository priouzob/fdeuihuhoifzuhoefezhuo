"""
Script de génération du package propre pour l'ami (WikiMasters_Pour_Ami.zip).
Exclut STRICTEMENT tous les cookies, sessions, profils et historiques du développeur.
"""

import os
import sys
import zipfile
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_ZIP = BASE_DIR / "WikiMasters_Pour_Ami.zip"

FILES_TO_INCLUDE = [
    "engine.py",
    "gui.py",
    "stealth.py",
    "transfer.py",
    "updater.py",
    "version.json",
    "installer.bat",
    "Demarrer_WikiMasters.bat",
    "lancer_interface.bat",
    "lancer_debug.bat",
    "launcher.vbs",
    "README_AMI.txt",
    "config.example.json"
]

def create_pack():
    print("=======================================================")
    print("  Génération du package propre pour votre ami...")
    print("=======================================================")

    if OUTPUT_ZIP.exists():
        try:
            OUTPUT_ZIP.unlink()
        except Exception:
            pass

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Ajout des fichiers sources nécessaires
        for fname in FILES_TO_INCLUDE:
            fpath = BASE_DIR / fname
            if fpath.exists():
                zf.write(fpath, arcname=f"fdeuihuhoifzuhoefezhuo/{fname}")
                print(f"  [+] Inclus : {fname}")
            else:
                print(f"  [!] Fichier manquant (ignoré) : {fname}")

        # 2. Ajout d'un config.json par défaut (0 compte, aucune donnée privée)
        default_config = {
            "target_url": "https://wiki-masters.com/pulls",
            "check_interval_seconds": 600,
            "random_jitter_seconds": 15,
            "headless": True,
            "chrome_executable": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "accounts": []
        }
        zf.writestr(
            "fdeuihuhoifzuhoefezhuo/config.json",
            json.dumps(default_config, indent=2, ensure_ascii=False)
        )
        print("  [+] Inclus : config.json vierge (0 compte, 0 cookie)")

    size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print("\n=======================================================")
    print(f"  SUCCÈS : Archive générée avec succès !")
    print(f"  Fichier : {OUTPUT_ZIP}")
    print(f"  Taille  : {size_mb:.2f} Mo")
    print("  Sécurité: 100% propre (aucun cookie ni profil personnel)")
    print("=======================================================")

if __name__ == "__main__":
    create_pack()
