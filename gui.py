"""
WikiMasters Auto-Claimer — Version Multi-Comptes 100% Google Chrome
Dashboard companion pour second écran :
- Tous les comptes tournent désormais sur Google Chrome avec des profils isolés étanches
- Bouton '➕ Ajouter un compte' pour connecter autant de comptes que désiré
- Synchronisation en direct des comptes à rebours et du stock
- Rareté des cartes obtenues (C, PC, R, SR, UR, L)
- Résolution automatique discrète de la pop-up 'Vérification rapide'
- Consommation de ressources ultra-faible (<0.1% CPU au repos, 0% Chromium entre les tirages)
"""

import os
import sys
import time
import json
import traceback
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).parent.resolve()
DEBUG_LOG = BASE_DIR / "gui_debug.log"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def write_debug(msg):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def handle_exception(exc_type, exc_value, exc_traceback):
    err = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    write_debug(f"CRASH FATAL:\n{err}")

sys.excepthook = handle_exception

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QFrame, QScrollArea,
    QTextEdit, QDialog, QMessageBox, QListWidget, QListWidgetItem,
    QCheckBox, QSizePolicy, QInputDialog, QLineEdit, QRadioButton,
    QButtonGroup, QComboBox
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot, QSize, QRect
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QLinearGradient, QPen, QBrush

import engine
import updater

# ─── Palette de couleurs ────────────────────────────────────────────────────
C_BG       = "#07090f"
C_SURFACE  = "#0d1117"
C_CARD     = "#111827"
C_BORDER   = "#1f2937"
C_BORDER2  = "#374151"
C_TEXT     = "#f1f5f9"
C_MUTED    = "#6b7280"
C_ACCENT   = "#38bdf8"
C_ACCENT2  = "#60a5fa"
C_GREEN    = "#22c55e"
C_YELLOW   = "#f59e0b"
C_RED      = "#ef4444"
C_PURPLE   = "#a78bfa"
C_TEAL     = "#2dd4bf"

ACCOUNT_THEMES = [
    ("stop:0 #1a2a4a, stop:1 #0d1a2e", "#38bdf8", "🌐"),
    ("stop:0 #2a1a0a, stop:1 #1a0d05", "#fb923c", "🦊"),
    ("stop:0 #2a0a2a, stop:1 #1a051a", "#c084fc", "🔮"),
    ("stop:0 #0a2a1a, stop:1 #051a0d", "#4ade80", "🍀"),
    ("stop:0 #2a0a14, stop:1 #1a050d", "#f43f5e", "💎"),
    ("stop:0 #1e293b, stop:1 #0f172a", "#94a3b8", "⭐"),
]

DARK_STYLE = f"""
QMainWindow, QDialog {{
    background-color: {C_BG};
}}
QWidget {{
    color: {C_TEXT};
    font-family: 'Segoe UI', 'Inter', system-ui, -apple-system, sans-serif;
    font-size: 12px;
}}
QFrame#statsBar, QFrame#logFrame, QFrame#headerFrame {{
    background-color: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 12px;
}}
QPushButton {{
    background-color: {C_SURFACE};
    color: {C_TEXT};
    border: 1px solid {C_BORDER2};
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: #1f2937;
    border-color: {C_ACCENT};
    color: {C_ACCENT2};
}}
QPushButton:pressed {{
    background-color: #111827;
}}
QPushButton#btnPrimary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0369a1);
    border: 1px solid #38bdf8;
    color: white;
}}
QPushButton#btnPrimary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #075985);
}}
QPushButton#btnSuccess {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #16a34a);
    border: 1px solid {C_GREEN};
    color: white;
}}
QPushButton#btnSuccess:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #166534, stop:1 #15803d);
}}
QPushButton#btnDanger {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91c1c, stop:1 #dc2626);
    border: 1px solid {C_RED};
    color: white;
}}
QPushButton#btnWarn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b45309, stop:1 #d97706);
    border: 1px solid {C_YELLOW};
    color: white;
}}
QPushButton#btnSmall {{
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 6px;
}}
QPushButton#btnIcon {{
    padding: 5px 8px;
    font-size: 13px;
    border-radius: 8px;
    min-width: 32px;
    max-width: 32px;
}}
QTextEdit, QListWidget {{
    background-color: {C_BG};
    border: none;
    border-radius: 8px;
    color: #9ca3af;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 11px;
    padding: 6px;
}}
QScrollBar:vertical {{
    border: none;
    background: {C_SURFACE};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER2};
    border-radius: 3px;
}}
QScrollBar:horizontal {{
    border: none;
    background: {C_SURFACE};
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {C_BORDER2};
    border-radius: 3px;
}}
QCheckBox {{
    font-size: 12px;
    color: {C_MUTED};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {C_BORDER2};
    background-color: {C_SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {C_ACCENT};
    border-color: {C_ACCENT2};
}}
"""

def make_separator():
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color:{C_BORDER}; background:{C_BORDER}; max-height:1px;")
    return sep

# ─── Modals ──────────────────────────────────────────────────────────────────

class ImageModal(QDialog):
    def __init__(self, image_path, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.image_path = str(image_path)
        self.original_pixmap = QPixmap(self.image_path)
        self.resize(1050, 700)
        self.setMinimumSize(600, 420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        self.setStyleSheet(DARK_STYLE + f"QDialog{{background:{C_BG};}}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        title_lbl = QLabel(f"📸  {title}")
        title_lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{C_ACCENT2};")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        btn_open_external = QPushButton("🔍  Afficheur Windows (100% Plein écran)")
        btn_open_external.setStyleSheet(
            f"QPushButton {{ background:{C_SURFACE}; color:{C_TEXT}; border:1px solid {C_BORDER2}; "
            f"border-radius:6px; padding:6px 12px; font-size:11px; font-weight:600; }} "
            f"QPushButton:hover {{ border-color:{C_ACCENT}; color:#38bdf8; }}"
        )
        btn_open_external.setToolTip("Ouvrir la capture dans l'application Photos de Windows en pleine résolution")
        btn_open_external.clicked.connect(self.open_in_windows)
        top_bar.addWidget(btn_open_external)

        layout.addLayout(top_bar)

        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignCenter)
        self.img_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img_lbl.setStyleSheet(f"background:{C_CARD}; border:1px solid {C_BORDER}; border-radius:12px; padding:6px;")
        layout.addWidget(self.img_lbl, 1)

        btn_close = QPushButton("✕  Fermer")
        btn_close.setObjectName("btnPrimary")
        btn_close.setFixedWidth(120)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignCenter)

        self.update_image()

    def update_image(self):
        if not self.original_pixmap.isNull():
            w = max(self.img_lbl.width() - 20, 200)
            h = max(self.img_lbl.height() - 20, 200)
            scaled = self.original_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_lbl.setPixmap(scaled)
        else:
            self.img_lbl.setText("Image introuvable ou en cours de génération.")
            self.img_lbl.setStyleSheet(f"color:{C_MUTED}; font-size:14px;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image()

    def open_in_windows(self):
        if os.path.exists(self.image_path):
            try:
                os.startfile(self.image_path)
            except Exception:
                pass

class HistoryModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historique des tirages WikiMasters")
        self.resize(840, 580)
        self.setStyleSheet(DARK_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        hdr = QHBoxLayout()
        title_lbl = QLabel("📜  Historique des tirages automatiques")
        title_lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{C_ACCENT2};")
        hdr.addWidget(title_lbl)
        hdr.addStretch()

        btn_clear = QPushButton("🗑  Tout effacer")
        btn_clear.setObjectName("btnDanger")
        btn_clear.setObjectName("btnSmall")
        btn_clear.clicked.connect(self.clear_history)
        hdr.addWidget(btn_clear)
        layout.addLayout(hdr)

        layout.addWidget(make_separator())

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            f"QListWidget{{background:{C_SURFACE}; border:1px solid {C_BORDER}; border-radius:10px;}}"
        )
        layout.addWidget(self.list_widget)
        self.refresh_list()

        btn_close = QPushButton("Fermer")
        btn_close.setFixedWidth(120)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignCenter)

    def refresh_list(self):
        self.list_widget.clear()
        history = engine.load_history()
        if not history:
            item = QListWidgetItem("  Aucun tirage enregistré pour le moment.")
            item.setForeground(QColor(C_MUTED))
            self.list_widget.addItem(item)
            return

        for h in history:
            ts = h.get("timestamp", "")
            bkey = h.get("browser_key", "")
            bname = h.get("browser", bkey)
            packs = h.get("packs_count", 1)
            rarity = h.get("rarity_summary", "")
            cards = h.get("cards", [])

            rarity_part = f"  ⭐ {rarity}" if rarity else ""
            cards_part = "\n    • " + "\n    • ".join(cards) if cards else ""
            text = f"🌐 {bname}  —  {ts}  —  {packs} paquet(s){rarity_part}{cards_part}"

            item = QListWidgetItem(text)
            item.setForeground(QColor(C_TEXT))
            self.list_widget.addItem(item)

    def clear_history(self):
        confirm = QMessageBox.question(
            self, "Confirmation",
            "Effacer tout l'historique des tirages ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                with open(engine.HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f)
                self.refresh_list()
            except Exception:
                pass

class TopCardsModal(QDialog):
    def __init__(self, initial_account_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🏆 Classement des 10 Meilleures Cartes par Compte")
        self.resize(880, 640)
        self.setMinimumSize(720, 480)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        self.setStyleSheet(DARK_STYLE + f"QDialog{{background:{C_BG};}}")

        self.accounts = engine.get_accounts()
        if not self.accounts:
            self.accounts = [{"id": "compte_1", "name": "Compte 1"}]

        self.current_acc_id = initial_account_id or (self.accounts[0]["id"] if self.accounts else "compte_1")
        if not any(a["id"] == self.current_acc_id for a in self.accounts):
            self.current_acc_id = self.accounts[0]["id"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # ── En-tête ──────────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_title_col = QVBoxLayout()
        top_title_col.setSpacing(3)

        title_lbl = QLabel("🏆  Top 10 des Cartes les plus Rares")
        title_lbl.setStyleSheet("font-size:18px; font-weight:800; color:#fbbf24; letter-spacing:0.3px;")
        subtitle_lbl = QLabel(
            "Chaque compte garde automatiquement ses 10 meilleures cartes (L > UR > SR > R > PC > C).\n"
            "Dès qu'une carte plus prestigieuse est tirée, la moins rare est automatiquement supprimée."
        )
        subtitle_lbl.setStyleSheet(f"font-size:11px; color:{C_MUTED};")
        top_title_col.addWidget(title_lbl)
        top_title_col.addWidget(subtitle_lbl)
        top_bar.addLayout(top_title_col)
        top_bar.addStretch()

        layout.addLayout(top_bar)
        layout.addWidget(make_separator())

        # ── Sélecteur de compte (Boutons Onglets) ─────────────────────────────
        acc_bar = QHBoxLayout()
        acc_bar.setSpacing(8)
        lbl_acc = QLabel("Compte :")
        lbl_acc.setStyleSheet(f"font-size:12px; font-weight:700; color:{C_TEXT};")
        acc_bar.addWidget(lbl_acc)

        self.account_btn_group = QButtonGroup(self)
        self.account_btn_group.setExclusive(True)
        self.acc_buttons = {}

        for acc in self.accounts:
            acc_id = acc["id"]
            acc_name = acc.get("name", acc_id)
            btn = QPushButton(f"👤  {acc_name}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            if acc_id == self.current_acc_id:
                btn.setChecked(True)
            self._apply_acc_btn_style(btn, btn.isChecked())
            btn.clicked.connect(lambda checked, aid=acc_id: self.select_account(aid))
            self.account_btn_group.addButton(btn)
            self.acc_buttons[acc_id] = btn
            acc_bar.addWidget(btn)

        acc_bar.addStretch()

        self.lbl_stats_summary = QLabel("")
        self.lbl_stats_summary.setStyleSheet("font-size:11px; font-weight:600; color:#a855f7;")
        acc_bar.addWidget(self.lbl_stats_summary)

        layout.addLayout(acc_bar)

        # ── Zone Scrollable pour la liste des cartes ─────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(10)

        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, 1)

        layout.addWidget(make_separator())

        # ── Barre inférieure ─────────────────────────────────────────────────
        bottom_bar = QHBoxLayout()
        lbl_info = QLabel("💡 Seules les 10 cartes au sommet sont conservées par compte. Aucune surcharge mémoire.")
        lbl_info.setStyleSheet(f"font-size:10px; color:{C_MUTED}; font-style:italic;")
        bottom_bar.addWidget(lbl_info)
        bottom_bar.addStretch()

        btn_close = QPushButton("✕  Fermer")
        btn_close.setObjectName("btnPrimary")
        btn_close.setFixedWidth(120)
        btn_close.clicked.connect(self.close)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

        # Charger l'affichage
        self.refresh_cards_view()

    def _apply_acc_btn_style(self, btn, is_selected):
        if is_selected:
            btn.setStyleSheet(
                "QPushButton { background: #3b1d54; color: #f3e8ff; border: 1px solid #a855f7; "
                "border-radius: 8px; padding: 6px 14px; font-size: 11px; font-weight: 700; }"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: {C_SURFACE}; color: {C_TEXT}; border: 1px solid {C_BORDER}; "
                f"border-radius: 8px; padding: 6px 14px; font-size: 11px; font-weight: 500; }} "
                f"QPushButton:hover {{ border-color: #6366f1; color: #ffffff; }}"
            )

    def select_account(self, account_id):
        self.current_acc_id = account_id
        for aid, btn in self.acc_buttons.items():
            self._apply_acc_btn_style(btn, aid == account_id)
        self.refresh_cards_view()

    def refresh_cards_view(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        cards = engine.get_account_best_cards(self.current_acc_id)

        if cards:
            rarity_counts = {}
            for c in cards:
                r = c.get("rarity", "C")
                rarity_counts[r] = rarity_counts.get(r, 0) + 1
            order = ["L", "UR", "SR", "R", "PC", "C"]
            summary_parts = []
            for r_code in order:
                cnt = rarity_counts.get(r_code, 0)
                if cnt > 0:
                    badge = engine.RARITY_MAP.get(r_code, {}).get("name", r_code)
                    summary_parts.append(f"{cnt} {badge}")
            self.lbl_stats_summary.setText(f"📊 {len(cards)}/10 conservées : " + ", ".join(summary_parts))
        else:
            self.lbl_stats_summary.setText("📊 0/10 carte conservée")

        if not cards:
            empty_frame = QFrame()
            empty_frame.setStyleSheet(f"background:{C_SURFACE}; border:1px dashed {C_BORDER2}; border-radius:12px; padding:40px;")
            ev = QVBoxLayout(empty_frame)
            ev.setAlignment(Qt.AlignCenter)
            lbl_empty_icon = QLabel("🎴")
            lbl_empty_icon.setStyleSheet("font-size:36px; border:none; background:transparent;")
            lbl_empty_icon.setAlignment(Qt.AlignCenter)
            lbl_empty_text = QLabel("Aucune carte rare enregistrée pour ce compte pour le moment.\nEffectuez des tirages de paquets pour remplir votre Top 10 !")
            lbl_empty_text.setAlignment(Qt.AlignCenter)
            lbl_empty_text.setStyleSheet(f"font-size:12px; color:{C_MUTED}; border:none; background:transparent;")
            ev.addWidget(lbl_empty_icon)
            ev.addWidget(lbl_empty_text)
            self.cards_layout.addWidget(empty_frame)
            self.cards_layout.addStretch()
            return

        medals = {0: "🥇", 1: "🥈", 2: "🥉"}

        for idx, card in enumerate(cards):
            c_row = QFrame()
            c_row.setStyleSheet(
                f"QFrame {{ background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 10px; }} "
                f"QFrame:hover {{ border-color: {C_BORDER2}; background: #131b26; }}"
            )
            rh = QHBoxLayout(c_row)
            rh.setContentsMargins(14, 10, 14, 10)
            rh.setSpacing(14)

            # 1. Rang
            medal = medals.get(idx, f"#{idx+1}")
            lbl_rank = QLabel(f"{medal}")
            lbl_rank.setFixedWidth(40)
            lbl_rank.setAlignment(Qt.AlignCenter)
            lbl_rank.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; border: none; background: transparent;")
            rh.addWidget(lbl_rank)

            # 2. Badge de rareté officiel
            r_code = card.get("rarity", "C").upper()
            r_info = engine.RARITY_MAP.get(r_code, {"name": r_code, "color": "#94a3b8", "bg": "#1e293b", "badge": r_code})
            badge_text = r_info.get("badge", r_code)
            lbl_badge = QLabel(f" {badge_text} ")
            lbl_badge.setStyleSheet(
                f"color: {r_info['color']}; background: {r_info['bg']}; "
                f"border: 1px solid {r_info['color']}66; border-radius: 6px; "
                f"font-size: 11px; font-weight: 800; padding: 4px 8px;"
            )
            rh.addWidget(lbl_badge)

            # 3. Titre et Date
            title_col = QVBoxLayout()
            title_col.setSpacing(2)
            c_title = card.get("title", "Carte sans nom")
            lbl_name = QLabel(c_title)
            lbl_name.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {C_TEXT}; border: none; background: transparent;")

            c_ts = card.get("timestamp", "")
            lbl_time = QLabel(f"📅 Tirée le {c_ts}" if c_ts else "")
            lbl_time.setStyleSheet(f"font-size: 10px; color: {C_MUTED}; border: none; background: transparent;")
            title_col.addWidget(lbl_name)
            if c_ts:
                title_col.addWidget(lbl_time)
            rh.addLayout(title_col, 1)

            # 4. Bouton voir capture (si disponible)
            shot = card.get("screenshot")
            if shot and os.path.exists(shot):
                btn_view = QPushButton("📷  Voir tirage")
                btn_view.setStyleSheet(
                    f"QPushButton {{ background: #1e293b; color: #94a3b8; border: 1px solid {C_BORDER}; "
                    f"border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 600; }} "
                    f"QPushButton:hover {{ border-color: {C_ACCENT}; color: #38bdf8; }}"
                )
                btn_view.setCursor(Qt.PointingHandCursor)
                btn_view.clicked.connect(lambda checked, s=shot, t=c_title: self.view_card_shot(s, t))
                rh.addWidget(btn_view)

            # 5. Bouton supprimer manuellement
            btn_delete = QPushButton("🗑️")
            btn_delete.setFixedSize(28, 28)
            btn_delete.setToolTip("Supprimer cette carte du Top 10")
            btn_delete.setStyleSheet(
                "QPushButton { background: #ef444415; border: 1px solid #ef444433; border-radius: 6px; color: #ef4444; font-size: 11px; } "
                "QPushButton:hover { background: #ef4444; color: #ffffff; }"
            )
            btn_delete.setCursor(Qt.PointingHandCursor)
            btn_delete.clicked.connect(lambda checked, c_idx=idx, name=c_title: self.delete_card(c_idx, name))
            rh.addWidget(btn_delete)

            self.cards_layout.addWidget(c_row)

        self.cards_layout.addStretch()

    def view_card_shot(self, shot_path, card_name):
        if shot_path and os.path.exists(shot_path):
            dlg = ImageModal(shot_path, f"Tirage — {card_name}", self)
            dlg.exec()

    def delete_card(self, card_index, card_name):
        confirm = QMessageBox.question(
            self, "Supprimer la carte",
            f"Voulez-vous supprimer '{card_name}' du Top 10 de ce compte ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            engine.delete_account_card(self.current_acc_id, card_index)
            self.refresh_cards_view()

class TransferCardsModal(QDialog):
    transfer_completed = Signal()

    def __init__(self, initial_source_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 Transfert de Cartes par Rareté — WikiMasters")
        self.resize(760, 680)
        self.setMinimumSize(680, 560)
        self.setStyleSheet(DARK_STYLE + f"QDialog{{background:{C_BG};}}")

        self.accounts = engine.get_accounts()
        if not self.accounts:
            self.accounts = [{"id": "compte_1", "name": "Compte 1"}]

        self.initial_source_id = initial_source_id or self.accounts[0]["id"]
        self.worker = None

        self.init_ui()
        self.update_source_account()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # ── Header ──
        h_layout = QHBoxLayout()
        icon = QLabel("🔄")
        icon.setStyleSheet("font-size: 26px;")
        t_col = QVBoxLayout()
        t_col.setSpacing(2)
        title = QLabel("Transfert de Cartes Automatique")
        title.setStyleSheet("font-size: 17px; font-weight: 800; color: #34d399;")
        subtitle = QLabel("Transfère des lots de cartes (jusqu'à 100 par échange) selon leur rareté d'un compte à un autre.")
        subtitle.setStyleSheet(f"font-size: 11px; color: {C_MUTED};")
        t_col.addWidget(title)
        t_col.addWidget(subtitle)
        h_layout.addWidget(icon)
        h_layout.addLayout(t_col)
        h_layout.addStretch()
        layout.addLayout(h_layout)

        layout.addWidget(make_separator())

        # ── Sélection Source & Destination ──
        acc_frame = QFrame()
        acc_frame.setStyleSheet(f"background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 12px; padding: 12px;")
        acc_layout = QHBoxLayout(acc_frame)
        acc_layout.setSpacing(16)

        # Source
        src_col = QVBoxLayout()
        src_col.setSpacing(6)
        src_lbl = QLabel("Compte Source (Envoyeur) :")
        src_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {C_TEXT};")
        self.cb_source = QComboBox()
        self.cb_source.setStyleSheet(f"QComboBox {{ background: {C_CARD}; border: 1px solid {C_BORDER2}; border-radius: 8px; padding: 8px 12px; color: {C_TEXT}; font-weight: 600; font-size: 12px; }}")
        for a in self.accounts:
            self.cb_source.addItem(f"👤 {a.get('name', a['id'])}", a["id"])
        
        idx = self.cb_source.findData(self.initial_source_id)
        if idx >= 0:
            self.cb_source.setCurrentIndex(idx)
        self.cb_source.currentIndexChanged.connect(self.update_source_account)
        src_col.addWidget(src_lbl)
        src_col.addWidget(self.cb_source)

        arrow_lbl = QLabel("➡️")
        arrow_lbl.setStyleSheet("font-size: 22px; margin-top: 14px;")

        # Destination
        dst_col = QVBoxLayout()
        dst_col.setSpacing(6)
        dst_lbl = QLabel("Compte Destinataire (Receveur) :")
        dst_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {C_TEXT};")
        self.cb_target = QComboBox()
        self.cb_target.setStyleSheet(f"QComboBox {{ background: {C_CARD}; border: 1px solid {C_BORDER2}; border-radius: 8px; padding: 8px 12px; color: {C_TEXT}; font-weight: 600; font-size: 12px; }}")
        dst_col.addWidget(dst_lbl)
        dst_col.addWidget(self.cb_target)

        acc_layout.addLayout(src_col, 1)
        acc_layout.addWidget(arrow_lbl)
        acc_layout.addLayout(dst_col, 1)
        layout.addWidget(acc_frame)

        # ── Raretés ──
        rarity_frame = QFrame()
        rarity_frame.setStyleSheet(f"background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 12px; padding: 12px;")
        rf_layout = QVBoxLayout(rarity_frame)
        rf_layout.setSpacing(10)

        rf_title_row = QHBoxLayout()
        rf_title = QLabel("Raretés à transférer :")
        rf_title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {C_TEXT};")
        rf_title_row.addWidget(rf_title)
        rf_title_row.addStretch()

        # Boutons filtres rapides
        btn_c_only = QPushButton("Communes (C)")
        btn_c_only.setStyleSheet(f"font-size: 10px; padding: 3px 8px; border-radius: 5px;")
        btn_c_only.clicked.connect(lambda: self.select_rarity_preset(["C"]))

        btn_c_pc = QPushButton("C + PC")
        btn_c_pc.setStyleSheet(f"font-size: 10px; padding: 3px 8px; border-radius: 5px;")
        btn_c_pc.clicked.connect(lambda: self.select_rarity_preset(["C", "PC"]))

        btn_all = QPushButton("Tout sélectionner")
        btn_all.setStyleSheet(f"font-size: 10px; padding: 3px 8px; border-radius: 5px;")
        btn_all.clicked.connect(lambda: self.select_rarity_preset(["C", "PC", "R", "SR", "UR", "L"]))

        btn_none = QPushButton("Tout décocher")
        btn_none.setStyleSheet(f"font-size: 10px; padding: 3px 8px; border-radius: 5px;")
        btn_none.clicked.connect(lambda: self.select_rarity_preset([]))

        rf_title_row.addWidget(btn_c_only)
        rf_title_row.addWidget(btn_c_pc)
        rf_title_row.addWidget(btn_all)
        rf_title_row.addWidget(btn_none)
        rf_layout.addLayout(rf_title_row)

        chk_row = QHBoxLayout()
        chk_row.setSpacing(16)
        self.rarity_checks = {}

        rarities_def = [
            ("C", "⚪ Commune", "#94a3b8", True),
            ("PC", "🔷 Peu Commune", "#38bdf8", False),
            ("R", "✨ Rare", "#34d399", False),
            ("SR", "⭐ Super Rare", "#a855f7", False),
            ("UR", "💎 Ultra Rare", "#ec4899", False),
            ("L", "👑 Légendaire", "#fbbf24", False)
        ]

        for code, label, color, default_chk in rarities_def:
            chk = QCheckBox(label)
            chk.setChecked(default_chk)
            chk.setStyleSheet(f"QCheckBox {{ color: {color}; font-weight: 700; font-size: 12px; }}")
            chk.toggled.connect(self.update_preview)
            self.rarity_checks[code] = chk
            chk_row.addWidget(chk)
        chk_row.addStretch()
        rf_layout.addLayout(chk_row)

        # Options de mode
        mode_box = QHBoxLayout()
        mode_box.setSpacing(20)
        self.rb_all = QRadioButton("📦  Tout transférer sans conserver d'exemplaire")
        self.rb_all.setChecked(True)
        self.rb_all.setToolTip("Transfère absolument toutes les cartes des raretés sélectionnées.")
        self.rb_all.toggled.connect(self.update_preview)

        self.rb_duplicates = QRadioButton("🛡️  Garder 1 exemplaire de chaque carte (Doublons uniquement)")
        self.rb_duplicates.setChecked(False)
        self.rb_duplicates.setToolTip("Ne transfère que les cartes en plusieurs exemplaires pour préserver la complétion de votre collection.")
        self.rb_duplicates.toggled.connect(self.update_preview)

        mode_box.addWidget(self.rb_all)
        mode_box.addWidget(self.rb_duplicates)
        mode_box.addStretch()
        rf_layout.addLayout(mode_box)

        layout.addWidget(rarity_frame)

        # ── Résumé & Estimation ──
        self.lbl_estimate = QLabel("📊  Estimation : En attente d'analyse...")
        self.lbl_estimate.setStyleSheet(f"font-size: 12px; font-weight: 700; color: #a78bfa; padding: 4px 6px;")
        layout.addWidget(self.lbl_estimate)

        # ── Barre de progression & Logs ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"QProgressBar {{ background: {C_CARD}; border-radius: 4px; }} QProgressBar::chunk {{ background: #10b981; border-radius: 4px; }}")
        layout.addWidget(self.progress_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(120)
        self.log_view.setStyleSheet(f"background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 8px; color: {C_TEXT}; font-family: Consolas, monospace; font-size: 11px; padding: 6px;")
        layout.addWidget(self.log_view)

        # ── Boutons bas ──
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        self.btn_start = QPushButton("🚀  Lancer le transfert")
        self.btn_start.setObjectName("btnPrimary")
        self.btn_start.setStyleSheet(f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857); border: 1px solid #10b981; color: white; font-size: 13px; font-weight: 800; padding: 9px 20px; border-radius: 8px; }} QPushButton:hover {{ background: #047857; }}")
        self.btn_start.clicked.connect(self.start_transfer)

        self.btn_close = QPushButton("✕  Fermer")
        self.btn_close.clicked.connect(self.accept)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_start)
        btn_box.addWidget(self.btn_close)
        layout.addLayout(btn_box)

    def select_rarity_preset(self, codes):
        for code, chk in self.rarity_checks.items():
            chk.setChecked(code in codes)
        self.update_preview()

    def update_source_account(self):
        source_id = self.cb_source.currentData()
        self.cb_target.clear()
        for a in self.accounts:
            if a["id"] != source_id:
                self.cb_target.addItem(f"👤 {a.get('name', a['id'])}", a["id"])
        self.update_preview()

    def update_preview(self):
        source_id = self.cb_source.currentData()
        stats = engine.get_account_collection_stats(source_id)
        selected_r = [code for code, chk in self.rarity_checks.items() if chk.isChecked()]
        if not stats or "rarityCounts" not in stats:
            self.lbl_estimate.setText(f"📊  Raretés sélectionnées : {', '.join(selected_r) if selected_r else 'Aucune'}")
            return
        rc = stats.get("rarityCounts", {})
        total_matching = sum(rc.get(r, 0) for r in selected_r)
        batches = max(1, (total_matching + 99) // 100) if total_matching > 0 else 0
        mode_str = " (doublons uniquement)" if self.rb_duplicates.isChecked() else ""
        self.lbl_estimate.setText(f"📊  {total_matching} cartes correspondantes détectées sur ce compte (~{batches} lot(s) de 100 cartes){mode_str}")

    def log(self, text, level="info"):
        color = "#10b981" if level == "success" else "#38bdf8" if level == "info" else "#f59e0b" if level == "warning" else "#ef4444"
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"<span style='color:#6b7280;'>[{ts}]</span> <span style='color:{color};'>{text}</span>")
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_transfer(self):
        source_id = self.cb_source.currentData()
        target_name = self.cb_target.currentText().replace("👤 ", "").strip()
        selected_r = [code for code, chk in self.rarity_checks.items() if chk.isChecked()]
        if not selected_r:
            QMessageBox.warning(self, "Attention", "Veuillez sélectionner au moins une rareté à transférer.")
            return

        keep_dup = self.rb_duplicates.isChecked()
        mode_label = "Doublons uniquement" if keep_dup else "Tous les exemplaires"

        confirm = QMessageBox.question(
            self, "Confirmer le transfert",
            f"Êtes-vous sûr de vouloir transférer les cartes ({', '.join(selected_r)})\n"
            f"depuis '{self.cb_source.currentText()}' vers '{target_name}' ?\n\n"
            f"Mode : {mode_label}\n"
            f"Les lots d'échange seront envoyés et validés automatiquement.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        self.btn_start.setEnabled(False)
        self.cb_source.setEnabled(False)
        self.cb_target.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.log(f"🚀 Démarrage du transfert vers {target_name}...", "info")

        self.worker = TransferWorker(source_id, target_name, selected_r, keep_dup)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_transfer_finished)
        self.worker.start()

    def on_transfer_finished(self, ok, msg):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if ok else 0)
        self.btn_start.setEnabled(True)
        self.cb_source.setEnabled(True)
        self.cb_target.setEnabled(True)
        self.transfer_completed.emit()
        if ok:
            QMessageBox.information(self, "Transfert Réussi", msg)
        else:
            QMessageBox.warning(self, "Transfert Incomplet", msg)

class AddAccountDialog(QDialog):
    def __init__(self, default_name="Compte", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter un compte — WikiMasters")
        self.setFixedWidth(470)
        self.setStyleSheet(DARK_STYLE)

        self.account_name = default_name
        self.start_url = "https://wiki-masters.com/signup"
        self.browser_type = "chrome"
        self.browser_name = "Google Chrome"
        self.confirmed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title_lbl = QLabel("➕  Ajouter un nouveau compte")
        title_lbl.setStyleSheet(f"font-size:16px; font-weight:800; color:{C_TEXT};")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Un profil hermétique et indépendant sera créé. "
            "Vos identifiants et cookies y restent enregistrés de manière 100% privée en local."
        )
        desc_lbl.setStyleSheet(f"font-size:11px; color:{C_MUTED};")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        layout.addWidget(make_separator())

        # 1. Nom du compte
        name_title = QLabel("Nom du compte dans l'application :")
        name_title.setStyleSheet(f"font-size:12px; font-weight:600; color:{C_TEXT};")
        layout.addWidget(name_title)

        self.name_input = QLineEdit(default_name)
        self.name_input.setStyleSheet(
            f"QLineEdit {{ background:{C_SURFACE}; color:{C_TEXT}; border:1px solid {C_BORDER2}; "
            f"border-radius:8px; padding:8px 12px; font-size:13px; font-weight:600; }}"
            f"QLineEdit:focus {{ border-color:{C_ACCENT}; }}"
        )
        layout.addWidget(self.name_input)

        # 2. Choix du navigateur
        browser_title = QLabel("Navigateur à utiliser :")
        browser_title.setStyleSheet(f"font-size:12px; font-weight:600; color:{C_TEXT}; margin-top:4px;")
        layout.addWidget(browser_title)

        available = engine.get_available_browsers()
        self.browser_group = QButtonGroup(self)

        chrome_ok = available.get("chrome", {}).get("installed", False)
        brave_ok  = available.get("brave", {}).get("installed", False)
        edge_ok   = available.get("edge", {}).get("installed", False)
        opera_ok  = available.get("opera", {}).get("installed", False)

        self.radio_chrome = QRadioButton(f"🌐  Google Chrome {'(Installé)' if chrome_ok else '(Non détecté)'}")
        self.radio_brave  = QRadioButton(f"🦁  Brave Browser {'(Installé)' if brave_ok else '(Non détecté)'}")
        self.radio_edge   = QRadioButton(f"🌊  Microsoft Edge {'(Installé)' if edge_ok else '(Non détecté)'}")
        self.radio_opera  = QRadioButton(f"🔴  Opera / Opera GX {'(Installé)' if opera_ok else '(Non détecté)'}")

        for r in [self.radio_chrome, self.radio_brave, self.radio_edge, self.radio_opera]:
            r.setStyleSheet(f"QRadioButton {{ color:{C_TEXT}; font-size:12px; padding:2px 0; }}")
            self.browser_group.addButton(r)
            layout.addWidget(r)

        if chrome_ok:
            self.radio_chrome.setChecked(True)
        elif brave_ok:
            self.radio_brave.setChecked(True)
        elif edge_ok:
            self.radio_edge.setChecked(True)
        else:
            self.radio_chrome.setChecked(True)

        # 3. Action
        action_title = QLabel("Action à effectuer :")
        action_title.setStyleSheet(f"font-size:12px; font-weight:600; color:{C_TEXT}; margin-top:4px;")
        layout.addWidget(action_title)

        self.action_group = QButtonGroup(self)
        self.radio_create = QRadioButton("🌟  Créer un nouveau compte WikiMasters (Inscription)")
        self.radio_create.setChecked(True)
        self.radio_create.setStyleSheet(f"QRadioButton {{ color:{C_TEXT}; font-size:12px; padding:2px 0; }}")

        self.radio_login = QRadioButton("🔑  Connecter un compte WikiMasters déjà existant (Connexion)")
        self.radio_login.setStyleSheet(f"QRadioButton {{ color:{C_TEXT}; font-size:12px; padding:2px 0; }}")

        self.action_group.addButton(self.radio_create)
        self.action_group.addButton(self.radio_login)
        layout.addWidget(self.radio_create)
        layout.addWidget(self.radio_login)

        hint_lbl = QLabel("💡 Une fois connecté dans le navigateur, fermez-le ou cliquez sur 'J'ai fini' : le compte sera immédiatement synchronisé.")
        hint_lbl.setStyleSheet(f"font-size:10px; color:{C_TEAL}; font-style:italic;")
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)

        layout.addWidget(make_separator())

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_submit = QPushButton("🚀  Lancer la configuration")
        self.btn_submit.setObjectName("btnPrimary")
        self.btn_submit.clicked.connect(self.on_submit)
        btn_box.addWidget(self.btn_submit)

        layout.addLayout(btn_box)

    def on_submit(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Nom requis", "Veuillez entrer un nom pour ce compte.")
            return
        self.account_name = name

        if self.radio_brave.isChecked():
            self.browser_type = "brave"
            self.browser_name = "Brave Browser"
        elif self.radio_edge.isChecked():
            self.browser_type = "edge"
            self.browser_name = "Microsoft Edge"
        elif self.radio_opera.isChecked():
            self.browser_type = "opera"
            self.browser_name = "Opera"
        else:
            self.browser_type = "chrome"
            self.browser_name = "Google Chrome"

        if self.radio_create.isChecked():
            self.start_url = "https://wiki-masters.com/signup"
        else:
            self.start_url = "https://wiki-masters.com/login"
        self.confirmed = True
        self.accept()

# ─── Workers ─────────────────────────────────────────────────────────────────

class SetupWorker(QThread):
    log_signal = Signal(str, str)
    finished_signal = Signal(str, bool, str)

    def __init__(self, account_id, start_url="https://wiki-masters.com/signup"):
        super().__init__()
        self.account_id = account_id
        self.start_url = start_url

    def run(self):
        success, msg = engine.setup_account(
            self.account_id,
            start_url=self.start_url,
            status_callback=lambda text, level: self.log_signal.emit(text, level)
        )
        self.finished_signal.emit(self.account_id, success, msg)

class BackgroundClaimWorker(QThread):
    log_signal = Signal(str, str)
    account_started_signal = Signal(str)
    account_result_signal = Signal(str, dict)
    cycle_finished_signal = Signal()

    def __init__(self, account_ids):
        super().__init__()
        self.account_ids = account_ids

    def run(self):
        for acc_id in self.account_ids:
            self.account_started_signal.emit(acc_id)
            res = engine.claim_account(
                acc_id,
                headless=True,
                status_callback=lambda text, level: self.log_signal.emit(text, level)
            )
            self.account_result_signal.emit(acc_id, res)
            time.sleep(0.4)
        self.cycle_finished_signal.emit()

class TransferWorker(QThread):
    log_signal = Signal(str, str)
    finished_signal = Signal(bool, str)

    def __init__(self, source_account_id, target_name, rarities, keep_duplicates_only):
        super().__init__()
        self.source_account_id = source_account_id
        self.target_name = target_name
        self.rarities = rarities
        self.keep_duplicates_only = keep_duplicates_only

    def run(self):
        ok, msg = engine.transfer_cards(
            self.source_account_id,
            self.target_name,
            self.rarities,
            keep_duplicates_only=self.keep_duplicates_only,
            status_callback=lambda text, level: self.log_signal.emit(text, level)
        )
        self.finished_signal.emit(ok, msg)

class ClaimAchievementsWorker(QThread):
    log_signal = Signal(str, str)
    finished_signal = Signal(str, int)

    def __init__(self, account_id):
        super().__init__()
        self.account_id = account_id

    def run(self):
        claimed = engine.run_claim_achievements_standalone(
            self.account_id,
            status_callback=lambda text, level: self.log_signal.emit(text, level)
        )
        self.finished_signal.emit(self.account_id, claimed)

class SyncFriendsWorker(QThread):
    log_signal = Signal(str, str)
    finished_signal = Signal(str)

    def __init__(self, account_id):
        super().__init__()
        self.account_id = account_id

    def run(self):
        engine.run_sync_friends_standalone(
            self.account_id,
            status_callback=lambda text, level: self.log_signal.emit(text, level)
        )
        self.finished_signal.emit(self.account_id)


# ─── Donut Timer ─────────────────────────────────────────────────────────────

class DonutTimer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(94, 94)
        self._value = 0
        self._max   = 600
        self._text  = "--:--"
        self._color = QColor(C_ACCENT)
        self._active = False

    def set_countdown(self, seconds, total=600):
        self._value = max(0, min(seconds, total))
        self._max   = total
        mins = self._value // 60
        secs = self._value % 60
        self._text  = f"{mins:02d}:{secs:02d}"
        self._active = True
        self._color = QColor(C_GREEN) if seconds == 0 else QColor(C_ACCENT)
        self.update()

    def set_idle(self):
        self._active = False
        self._text = "--:--"
        self._color = QColor(C_MUTED)
        self.update()

    def set_claiming(self):
        self._active = True
        self._text = "⟳"
        self._color = QColor(C_YELLOW)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 7
        rect = QRect(margin, margin, w - 2 * margin, h - 2 * margin)

        pen_track = QPen(QColor(C_BORDER2), 7, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_track)
        painter.drawEllipse(rect)

        if self._active and self._max > 0:
            elapsed = self._max - self._value
            span = int(360 * 16 * elapsed / self._max)
            pen_arc = QPen(self._color, 7, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen_arc)
            painter.drawArc(rect, 90 * 16, -span)

        painter.setPen(QColor(self._color))
        f = QFont("Segoe UI", 12, QFont.Bold)
        if len(self._text) <= 2:
            f.setPointSize(16)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignCenter, self._text)

class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

class AddAccountCard(ClickableFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(160)
        self.setStyleSheet(
            f"QFrame {{ background: {C_SURFACE}; border: 2px dashed {C_BORDER2}; border-radius: 16px; }} "
            f"QFrame:hover {{ border-color: {C_ACCENT}; background: #111d2e; }}"
        )
        self.setCursor(Qt.PointingHandCursor)
        af_layout = QVBoxLayout(self)
        af_layout.setAlignment(Qt.AlignCenter)
        af_layout.setSpacing(8)

        lbl_plus = QLabel("➕")
        lbl_plus.setStyleSheet("font-size: 28px; border:none; background:transparent;")
        lbl_plus.setAlignment(Qt.AlignCenter)
        lbl_txt = QLabel("Ajouter un\ncompte")
        lbl_txt.setStyleSheet("font-size: 13px; font-weight: bold; color: #94a3b8; border:none; background:transparent;")
        lbl_txt.setAlignment(Qt.AlignCenter)

        af_layout.addWidget(lbl_plus)
        af_layout.addWidget(lbl_txt)

# ─── Account Card ────────────────────────────────────────────────────────────

class AccountCard(QFrame):
    setup_requested = Signal(str)
    claim_requested = Signal(str)
    refresh_requested = Signal(str)
    finish_setup_requested = Signal(str)
    delete_requested = Signal(str)
    rename_requested = Signal(str, str)
    open_browser_requested = Signal(str)
    transfer_requested = Signal(str)
    claim_achievements_requested = Signal(str)
    sync_friends_requested = Signal(str)

    def __init__(self, account_id, title, theme_idx=0, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.title_text = title
        self.setObjectName("accountCard")

        grad, accent, icon_sym = ACCOUNT_THEMES[theme_idx % len(ACCOUNT_THEMES)]
        self.icon_symbol = icon_sym
        self._accent = accent

        self.remaining_seconds = 0
        self.total_claimed  = 0
        self.last_claim_time = "Aucun"
        self.screenshot_path = None
        self.is_setting_up   = False
        self.is_connected    = False
        self.is_claiming     = False
        self.is_captcha_blocked = False

        self.setFixedWidth(310)
        self.setStyleSheet(
            f"QFrame#accountCard {{"
            f"  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,{grad});"
            f"  border: 1px solid {C_BORDER};"
            f"  border-radius: 16px;"
            f"}}"
            f"QFrame#accountCard:hover {{"
            f"  border: 1px solid {accent}55;"
            f"}}"
        )

        self.init_ui()
        self.hydrate_from_history()
        self.update_configured_state()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            child = self.childAt(pos)
            if child in (self, self.title_lbl, self.sub_lbl, self.icon_lbl, self.donut, self.lbl_stock, self.lbl_total, self.lbl_rarity, self.lbl_last_time, self.lbl_cards):
                self.open_browser_requested.emit(self.account_id)
                event.accept()
                return
        super().mousePressEvent(event)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(10)

        # ── Header row ──────────────────────────────────────────────────────
        hrow = QHBoxLayout()
        hrow.setSpacing(8)

        acc = engine.get_account_info(self.account_id)
        b_type = acc.get("browser_type", "chrome").lower()
        b_map = {
            "chrome": ("🌐", "Google Chrome"),
            "brave":  ("🦁", "Brave"),
            "edge":   ("🌊", "Microsoft Edge"),
            "opera":  ("🔴", "Opera"),
        }
        b_icon, b_display = b_map.get(b_type, ("🌐", "Google Chrome"))

        self.icon_lbl = QLabel(b_icon)
        self.icon_lbl.setFixedSize(34, 34)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setCursor(Qt.PointingHandCursor)
        self.icon_lbl.setToolTip(f"Cliquer pour ouvrir {b_display} connecté avec la session de ce compte")
        self.icon_lbl.setStyleSheet(
            f"font-size:18px; background:{self._accent}22; border-radius:9px; border:1px solid {self._accent}44;"
        )
        self.icon_lbl.mousePressEvent = lambda e: self.open_browser_requested.emit(self.account_id)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        self.title_lbl = QLabel(self.title_text)
        self.title_lbl.setStyleSheet(f"font-size:13px; font-weight:700; color:{C_TEXT};")
        self.title_lbl.setCursor(Qt.PointingHandCursor)
        self.title_lbl.setToolTip(f"Cliquer pour ouvrir {b_display} connecté (Double-clic pour renommer)")
        self.title_lbl.mousePressEvent = lambda e: self.open_browser_requested.emit(self.account_id)
        self.title_lbl.mouseDoubleClickEvent = lambda e: self.prompt_rename()

        btn_rename = QPushButton("✏️")
        btn_rename.setFixedSize(22, 22)
        btn_rename.setToolTip(f"Renommer {self.title_text}")
        btn_rename.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #94a3b8; font-size: 11px; border-radius: 4px; padding: 0px; } "
            "QPushButton:hover { background: #1f2937; color: #38bdf8; }"
        )
        btn_rename.clicked.connect(self.prompt_rename)

        title_row.addWidget(self.title_lbl)
        title_row.addWidget(btn_rename)
        title_row.addStretch()

        self.sub_lbl = QLabel(f"Profil {b_display}")
        self.sub_lbl.setStyleSheet(f"font-size:10px; color:{C_MUTED};")
        self.sub_lbl.setCursor(Qt.PointingHandCursor)
        self.sub_lbl.setToolTip(f"Cliquer pour ouvrir {b_display} connecté")
        self.sub_lbl.mousePressEvent = lambda e: self.open_browser_requested.emit(self.account_id)
        name_col.addLayout(title_row)
        name_col.addWidget(self.sub_lbl)

        hrow.addWidget(self.icon_lbl)
        hrow.addLayout(name_col)
        hrow.addStretch()

        self.status_badge = QLabel("Non connecté")
        self.status_badge.setStyleSheet(
            f"background:#78350f; color:#fde68a; padding:3px 9px; "
            f"border-radius:999px; font-size:10px; font-weight:700;"
        )
        hrow.addWidget(self.status_badge)

        btn_del = QPushButton("🗑️")
        btn_del.setFixedSize(26, 26)
        btn_del.setToolTip(f"Supprimer le compte {self.title_text}")
        btn_del.setStyleSheet(
            "QPushButton { background:#ef444418; border:1px solid #ef444440; border-radius:6px; color:#ef4444; font-size:12px; padding:0; } "
            "QPushButton:hover { background:#ef4444; color:#ffffff; font-weight:bold; }"
        )
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self.account_id))
        hrow.addWidget(btn_del)

        layout.addLayout(hrow)
        layout.addWidget(make_separator())

        # ── Timer + Stats row ───────────────────────────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(10)

        self.donut = DonutTimer()
        mid.addWidget(self.donut)

        stats_col = QVBoxLayout()
        stats_col.setSpacing(5)

        self.lbl_stock = QLabel("📦  Stock : —")
        self.lbl_stock.setStyleSheet(f"font-size:12px; font-weight:600; color:{self._accent};")

        self.lbl_total = QLabel("🎴  Total : 0 paquet(s)")
        self.lbl_total.setStyleSheet(f"font-size:11px; color:{C_MUTED};")

        self.lbl_collection = QLabel("🃏  Collection : —")
        self.lbl_collection.setStyleSheet(f"font-size:11px; font-weight:700; color:{C_TEXT};")
        self.lbl_collection.setWordWrap(True)

        self.lbl_rarity = QLabel("⭐  Raretés : —")
        self.lbl_rarity.setStyleSheet(f"font-size:10px; color:{C_TEAL}; font-weight:600;")
        self.lbl_rarity.setWordWrap(True)

        self.lbl_last_time = QLabel("🕐  Dernier : —")
        self.lbl_last_time.setStyleSheet(f"font-size:10px; color:{C_MUTED};")

        stats_col.addWidget(self.lbl_stock)
        stats_col.addWidget(self.lbl_total)
        stats_col.addWidget(self.lbl_collection)
        stats_col.addWidget(self.lbl_rarity)
        stats_col.addWidget(self.lbl_last_time)
        stats_col.addStretch()

        mid.addLayout(stats_col)
        layout.addLayout(mid)

        # ── Cartes obtenues / Top 10 Preview ───────────────────────────────
        self.lbl_cards = QLabel("🏆  Top 10 : En attente du premier tirage…")
        self.lbl_cards.setStyleSheet(
            f"font-size:10px; color:{C_MUTED}; font-style:italic; padding:6px 8px;"
            f"background:{C_SURFACE}; border-radius:8px; border:1px solid {C_BORDER};"
        )
        self.lbl_cards.setWordWrap(True)
        self.lbl_cards.setCursor(Qt.PointingHandCursor)
        self.lbl_cards.setToolTip("Cliquer pour voir le Top 10 des cartes les plus rares de ce compte")
        self.lbl_cards.mousePressEvent = lambda e: self.open_top_cards()
        layout.addWidget(self.lbl_cards)

        # ── Screenshot preview ─────────────────────────────────────────────
        self.preview_frame = ClickableFrame()
        self.preview_frame.setFixedHeight(85)
        self.preview_frame.setStyleSheet(
            f"background:{C_BG}; border:1px dashed {C_BORDER}; border-radius:10px;"
        )
        prev_layout = QVBoxLayout(self.preview_frame)
        prev_layout.setContentsMargins(4, 4, 4, 4)
        self.preview_img = QLabel("📷  Aperçu du tirage")
        self.preview_img.setAlignment(Qt.AlignCenter)
        self.preview_img.setStyleSheet(f"color:{C_BORDER2}; font-size:10px; border:none; background:transparent;")
        prev_layout.addWidget(self.preview_img)
        self.preview_frame.clicked.connect(self.open_large_preview)
        self.preview_frame.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.preview_frame)

        # ── Options modulaires (Auto-succès & Auto-amis) ──────────────────
        opts_box = QHBoxLayout()
        opts_box.setSpacing(12)

        self.chk_auto_achievements = QCheckBox("🏆 Auto-succès")
        self.chk_auto_achievements.setChecked(acc.get("auto_achievements", True))
        self.chk_auto_achievements.setToolTip("Réclame automatiquement les succès débloqués et les Wikibidous associés")
        self.chk_auto_achievements.setStyleSheet(f"QCheckBox {{ color: {C_TEXT}; font-size: 11px; font-weight: 600; }}")
        self.chk_auto_achievements.toggled.connect(lambda v: engine.set_account_option(self.account_id, "auto_achievements", v))

        self.chk_auto_friends = QCheckBox("🤝 Auto-amis")
        self.chk_auto_friends.setChecked(acc.get("auto_friends", True))
        self.chk_auto_friends.setToolTip("Accepte automatiquement les demandes d'amis et interconnecte tous vos comptes")
        self.chk_auto_friends.setStyleSheet(f"QCheckBox {{ color: {C_TEXT}; font-size: 11px; font-weight: 600; }}")
        self.chk_auto_friends.toggled.connect(lambda v: engine.set_account_option(self.account_id, "auto_friends", v))

        opts_box.addWidget(self.chk_auto_achievements)
        opts_box.addWidget(self.chk_auto_friends)
        opts_box.addStretch()
        layout.addLayout(opts_box)

        # ── Boutons Milieu : Top 10 + Transférer + Succès + Ouvrir Navigateur ─
        mid_btns = QHBoxLayout()
        mid_btns.setSpacing(6)

        self.btn_top_cards = QPushButton("🏆 Top 10")
        self.btn_top_cards.setStyleSheet(
            f"QPushButton {{ background:{C_SURFACE}; color:#e0e7ff; border:1px solid #6366f1; "
            f"border-radius:8px; padding:6px 6px; font-size:11px; font-weight:700; }} "
            f"QPushButton:hover {{ background:#312e81; border-color:#818cf8; color:#ffffff; }}"
        )
        self.btn_top_cards.setCursor(Qt.PointingHandCursor)
        self.btn_top_cards.setToolTip("Afficher le classement des 10 meilleures cartes de ce compte")
        self.btn_top_cards.clicked.connect(self.open_top_cards)

        self.btn_transfer = QPushButton("🔄 Transférer")
        self.btn_transfer.setStyleSheet(
            f"QPushButton {{ background:{C_SURFACE}; color:#a7f3d0; border:1px solid #059669; "
            f"border-radius:8px; padding:6px 6px; font-size:11px; font-weight:700; }} "
            f"QPushButton:hover {{ background:#064e3b; border-color:#34d399; color:#ffffff; }}"
        )
        self.btn_transfer.setCursor(Qt.PointingHandCursor)
        self.btn_transfer.setToolTip(f"Transférer des cartes depuis {self.title_text} vers un autre compte")
        self.btn_transfer.clicked.connect(lambda: self.transfer_requested.emit(self.account_id))

        self.btn_achieve = QPushButton("🏆 Succès")
        self.btn_achieve.setStyleSheet(
            f"QPushButton {{ background:{C_SURFACE}; color:#fef08a; border:1px solid #ca8a04; "
            f"border-radius:8px; padding:6px 6px; font-size:11px; font-weight:700; }} "
            f"QPushButton:hover {{ background:#713f12; border-color:#eab308; color:#ffffff; }}"
        )
        self.btn_achieve.setCursor(Qt.PointingHandCursor)
        self.btn_achieve.setToolTip(f"Réclamer manuellement les succès maintenant pour {self.title_text}")
        self.btn_achieve.clicked.connect(lambda: self.claim_achievements_requested.emit(self.account_id))

        self.btn_open_browser = QPushButton(f"{b_icon}")
        self.btn_open_browser.setFixedWidth(34)
        self.btn_open_browser.setStyleSheet(
            f"QPushButton {{ background:{C_SURFACE}; color:{C_TEXT}; border:1px solid {self._accent}77; "
            f"border-radius:8px; padding:6px 4px; font-size:12px; font-weight:600; }} "
            f"QPushButton:hover {{ background:{self._accent}22; border-color:{self._accent}; color:#ffffff; }}"
        )
        self.btn_open_browser.setCursor(Qt.PointingHandCursor)
        self.btn_open_browser.setToolTip(f"Ouvre {b_display} connecté avec la session de ce compte")
        self.btn_open_browser.clicked.connect(lambda: self.open_browser_requested.emit(self.account_id))

        mid_btns.addWidget(self.btn_top_cards)
        mid_btns.addWidget(self.btn_transfer)
        mid_btns.addWidget(self.btn_achieve)
        mid_btns.addWidget(self.btn_open_browser)
        layout.addLayout(mid_btns)

        # ── Action buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_setup = QPushButton("🔑  Connecter")
        self.btn_setup.clicked.connect(self.on_setup_clicked)
        self.btn_setup.setToolTip(f"Ouvrir {b_display} pour connecter ou reconfigurer ce compte")

        self.btn_claim = QPushButton("⚡  Tirer")
        self.btn_claim.setObjectName("btnPrimary")
        self.btn_claim.setToolTip("Ouvre immédiatement tous les paquets de ce compte")
        self.btn_claim.clicked.connect(self.on_claim_clicked)

        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setObjectName("btnIcon")
        self.btn_refresh.setToolTip("Actualiser le stock et le timer")
        self.btn_refresh.clicked.connect(lambda: self.refresh_requested.emit(self.account_id))

        btn_row.addWidget(self.btn_setup)
        btn_row.addWidget(self.btn_claim)
        btn_row.addWidget(self.btn_refresh)
        layout.addLayout(btn_row)

    # ── Logique ─────────────────────────────────────────────────────────────

    def prompt_rename(self):
        new_name, ok = QInputDialog.getText(
            self, "Renommer le compte",
            f"Nouveau nom pour '{self.title_text}' :",
            text=self.title_text
        )
        if ok and new_name.strip() and new_name.strip() != self.title_text:
            self.set_account_name(new_name.strip())

    def set_account_name(self, new_name):
        self.title_text = new_name
        self.title_lbl.setText(new_name)
        engine.rename_account(self.account_id, new_name)
        self.rename_requested.emit(self.account_id, new_name)

    def on_claim_clicked(self):
        if self.is_captcha_blocked:
            self.setup_requested.emit(self.account_id)
        else:
            self.claim_requested.emit(self.account_id)

    def on_setup_clicked(self):
        if self.is_setting_up:
            self.finish_setup_requested.emit(self.account_id)
        else:
            self.setup_requested.emit(self.account_id)

    def set_captcha_mode(self, active=True):
        self.is_captcha_blocked = active
        if active:
            self.set_status("⚠️  Anti-Bot", "#92400e", "#fde68a")
            self.sub_lbl.setText("Défi détecté — cliquez sur Résoudre")
            self.btn_claim.setObjectName("btnWarn")
            self.btn_claim.setText("🛠  Résoudre")
            self.btn_claim.style().unpolish(self.btn_claim)
            self.btn_claim.style().polish(self.btn_claim)
        else:
            self.btn_claim.setText("⚡  Tirer")
            self.btn_claim.setObjectName("btnPrimary")
            self.btn_claim.style().unpolish(self.btn_claim)
            self.btn_claim.style().polish(self.btn_claim)
            self.update_configured_state()

    def hydrate_from_history(self):
        history = engine.load_history()
        lifetime = engine.load_lifetime_stats()
        total_p = lifetime.get(self.account_id, {}).get("total_packs", 0)
        if total_p == 0:
            for entry in history:
                if entry.get("browser_key") == self.account_id:
                    total_p += entry.get("packs_count", 1)

        found = False
        for entry in history:
            if entry.get("browser_key") == self.account_id:
                if not found:
                    found = True
                    t = entry.get("timestamp", "")
                    self.lbl_last_time.setText(f"🕐  Dernier : {t}")
                    rs = entry.get("rarity_summary", "")
                    if rs:
                        self.lbl_rarity.setText(f"⭐  {rs}")
                    cards = entry.get("cards", [])
                    if cards:
                        shown = cards[:3]
                        more  = f"  (+{len(cards)-3})" if len(cards) > 3 else ""
                        self.lbl_cards.setText("  •  " + "  •  ".join(shown) + more)
                    shot = entry.get("screenshot")
                    if shot and os.path.exists(shot):
                        self._load_preview(shot)

        if not self.screenshot_path:
            ls = SCREENSHOTS_DIR / f"{self.account_id}_latest.png"
            if ls.exists():
                self._load_preview(str(ls))

        self.total_claimed = total_p
        self.lbl_total.setText(f"🎴  Total : {total_p} paquet(s)")
        self.update_top_cards_preview()
        self.update_collection_stats_display()

    def update_collection_stats_display(self):
        stats = engine.get_account_collection_stats(self.account_id)
        if stats and "total" in stats:
            total = stats.get("total", 0)
            rc = stats.get("rarityCounts", {})
            breakdown = []
            if rc.get("L", 0) > 0: breakdown.append(f"{rc['L']} 👑")
            if rc.get("UR", 0) > 0: breakdown.append(f"{rc['UR']} 💎")
            if rc.get("SR", 0) > 0: breakdown.append(f"{rc['SR']} ⭐")
            if rc.get("R", 0) > 0: breakdown.append(f"{rc['R']} ✨")
            if rc.get("PC", 0) > 0: breakdown.append(f"{rc['PC']} 🔷")
            if rc.get("C", 0) > 0: breakdown.append(f"{rc['C']} ⚪")

            summary_str = ", ".join(breakdown) if breakdown else ""
            fmt_total = f"{total:,}".replace(",", " ")
            self.lbl_collection.setText(f"🃏  {fmt_total} cartes ({summary_str})")
            self.lbl_collection.setToolTip(
                f"Collection de {self.title_text} :\n"
                f"• Total : {fmt_total} cartes\n"
                f"• Légendaires (L) : {rc.get('L', 0)}\n"
                f"• Ultra Rares (UR) : {rc.get('UR', 0)}\n"
                f"• Super Rares (SR) : {rc.get('SR', 0)}\n"
                f"• Rares (R) : {rc.get('R', 0)}\n"
                f"• Peu Communes (PC) : {rc.get('PC', 0)}\n"
                f"• Communes (C) : {rc.get('C', 0)}\n"
                f"Dernière synchro : {stats.get('updated_at', 'récemment')}"
            )
        else:
            self.lbl_collection.setText("🃏  Collection : En attente...")
            self.lbl_collection.setToolTip("Synchronisation automatique au prochain tirage ou actualisation")


    def _load_preview(self, path):
        self.screenshot_path = path
        pix = QPixmap(path)
        if not pix.isNull():
            self.preview_img.setText("")
            self.preview_img.setPixmap(
                pix.scaled(270, 75, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def set_status(self, text, bg, fg):
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(
            f"background:{bg}; color:{fg}; padding:3px 9px; "
            f"border-radius:999px; font-size:10px; font-weight:700;"
        )

    def set_setting_up_mode(self, active=True):
        self.is_setting_up = active
        if active:
            self.set_status("🔄  Config…", "#1e3a5f", "#93c5fd")
            self.btn_setup.setText("✅  J'ai fini")
            self.btn_setup.setObjectName("btnSuccess")
            self.btn_setup.style().unpolish(self.btn_setup)
            self.btn_setup.style().polish(self.btn_setup)
            self.sub_lbl.setText("Connexion Chrome en cours…")
        else:
            self.btn_setup.setObjectName("")
            self.btn_setup.style().unpolish(self.btn_setup)
            self.btn_setup.style().polish(self.btn_setup)
            self.update_configured_state()

    def update_configured_state(self):
        is_conf = engine.is_account_configured(self.account_id)
        if is_conf:
            self.is_connected = True
            self.set_status("✅  Prêt", "#14532d", "#86efac")
            self.btn_setup.setText("🔄  Reconnecter")
            self.sub_lbl.setText("Prochain paquet dans :")
        else:
            self.is_connected = False
            self.remaining_seconds = 0
            self.donut.set_idle()
            self.sub_lbl.setText("Non connecté — cliquez sur Connecter")
            self.set_status("●  Non connecté", "#451a03", "#fde68a")
            self.btn_setup.setText("🔑  Connecter")

    def tick_second(self):
        if self.is_connected and self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self.donut.set_countdown(self.remaining_seconds)
            if self.remaining_seconds == 0:
                self.set_status("🎁  Prêt !", "#065f46", "#6ee7b7")
                self.sub_lbl.setText("Paquet disponible !")
                self.donut.set_countdown(0)

    def set_countdown(self, seconds):
        self.is_connected = True
        self.remaining_seconds = max(0, seconds)
        self.donut.set_countdown(self.remaining_seconds)
        self.sub_lbl.setText("Prochain paquet dans :")

    def set_claiming_state(self):
        self.is_claiming = True
        self.donut.set_claiming()
        self.set_status("⟳  En cours…", "#1e3a5f", "#93c5fd")
        self.sub_lbl.setText("Ouverture des paquets…")

    def update_pack_data(self, stock=None, cards=None, shot_path=None, packs_opened=0, rarity_summary=""):
        if stock is not None:
            self.lbl_stock.setText(f"📦  Stock : {stock}")

        if packs_opened > 0:
            self.total_claimed += packs_opened
            self.lbl_total.setText(f"🎴  Total : {self.total_claimed} paquet(s)")
            self.lbl_last_time.setText(f"🕐  Dernier : {datetime.now().strftime('%H:%M:%S')}")

        if rarity_summary:
            self.lbl_rarity.setText(f"⭐  {rarity_summary}")

        self.update_top_cards_preview()

        if shot_path and os.path.exists(shot_path):
            self._load_preview(shot_path)

    def open_top_cards(self):
        dlg = TopCardsModal(initial_account_id=self.account_id, parent=self.window())
        dlg.exec()
        self.update_top_cards_preview()

    def update_top_cards_preview(self):
        top = engine.get_account_best_cards(self.account_id)
        if top:
            parts = [f"[{c.get('rarity','C')}] {c.get('title','')}" for c in top[:2]]
            more = f" (+{len(top)-2})" if len(top) > 2 else ""
            self.lbl_cards.setText("🏆 " + "  •  ".join(parts) + more)
            self.lbl_cards.setStyleSheet(
                f"font-size:10px; color:#c7d2fe; font-weight:600; padding:6px 8px;"
                f"background:{C_SURFACE}; border-radius:8px; border:1px solid #4338ca;"
            )
        else:
            self.lbl_cards.setText("🏆  Top 10 : En attente du premier tirage…")
            self.lbl_cards.setStyleSheet(
                f"font-size:10px; color:{C_MUTED}; font-style:italic; padding:6px 8px;"
                f"background:{C_SURFACE}; border-radius:8px; border:1px solid {C_BORDER};"
            )

    def open_large_preview(self, event=None):
        latest = SCREENSHOTS_DIR / f"{self.account_id}_latest.png"
        path = str(latest) if latest.exists() else self.screenshot_path
        if path and os.path.exists(path):
            dlg = ImageModal(path, f"Dernier tirage — {self.title_text}", self)
            dlg.exec()
        else:
            QMessageBox.information(
                self,
                "Aperçu du tirage",
                f"Aucune capture de tirage disponible pour '{self.title_text}'.\n\n"
                "Effectuez un premier tirage avec le bouton ⚡ Tirer pour capturer les cartes obtenues !"
            )

# ─── Main Window ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WikiMasters Auto-Claimer — Google Chrome Multi-Comptes")
        self.resize(1120, 820)
        self.setMinimumSize(920, 700)
        self.setStyleSheet(DARK_STYLE)

        self.is_running    = True
        self.claim_worker  = None
        self.setup_worker  = None
        self.sound_enabled = True
        self._tick_count   = 0
        self.account_cards = {}
        self._pending_claim_queue = []

        self.init_ui()

        # Empêcher la mise en veille de Windows pendant le farm automatique nocturne
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except Exception:
            pass

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.tick_clock)
        self.clock_timer.start(1000)

        QTimer.singleShot(1500, self._initial_sync)
        QTimer.singleShot(4000, lambda: self.check_updates_gui(silent_if_none=True))

    def _initial_sync(self):
        configured = [acc["id"] for acc in engine.get_accounts() if engine.is_account_configured(acc["id"])]
        if configured:
            self.log(f"🔍  Synchronisation initiale ({len(configured)} compte(s))…", "info")
            self.trigger_claim_cycle(configured)

    def init_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top header bar ────────────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_frame.setFixedHeight(62)
        hh = QHBoxLayout(header_frame)
        hh.setContentsMargins(20, 0, 20, 0)
        hh.setSpacing(12)

        logo = QLabel("🎴")
        logo.setStyleSheet("font-size:22px;")
        app_title = QLabel("WikiMasters Auto-Claimer")
        app_title.setStyleSheet(f"font-size:16px; font-weight:800; color:{C_TEXT}; letter-spacing:0.5px;")
        app_sub = QLabel("100% Google Chrome · Multi-Comptes Furtif")
        app_sub.setStyleSheet(f"font-size:10px; color:{C_MUTED};")
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(app_title)
        title_col.addWidget(app_sub)

        hh.addWidget(logo)
        hh.addLayout(title_col)
        hh.addStretch()

        self.stealth_badge = QLabel("🛡  STEALTH")
        self.stealth_badge.setStyleSheet(
            f"background:#052e16; color:#4ade80; border:1px solid #166534; "
            f"padding:4px 12px; border-radius:999px; font-size:10px; font-weight:700; letter-spacing:1px;"
        )
        hh.addWidget(self.stealth_badge)

        v_str = updater.get_local_version()
        self.btn_update = QPushButton(f"🔄 v{v_str}")
        self.btn_update.setObjectName("btnSmall")
        self.btn_update.setToolTip("Rechercher des mises à jour sur GitHub (vos comptes et cookies restent préservés)")
        self.btn_update.setStyleSheet(
            "QPushButton { background:#1e293b; color:#38bdf8; border:1px solid #0284c7; font-weight:700; border-radius:6px; padding:4px 8px; } "
            "QPushButton:hover { background:#0369a1; color:white; }"
        )
        self.btn_update.clicked.connect(lambda: self.check_updates_gui(silent_if_none=False))
        hh.addWidget(self.btn_update)

        self.chk_pin = QCheckBox("📌 Épingler")
        self.chk_pin.setToolTip("Maintenir la fenêtre au premier plan sur second écran")
        self.chk_pin.stateChanged.connect(self.toggle_always_on_top)
        hh.addWidget(self.chk_pin)

        self.chk_sound = QCheckBox("🔊")
        self.chk_sound.setChecked(True)
        self.chk_sound.setToolTip("Alertes sonores")
        self.chk_sound.stateChanged.connect(lambda s: setattr(self, "sound_enabled", s == Qt.Checked))
        hh.addWidget(self.chk_sound)

        btn_top10 = QPushButton("🏆  Top 10")
        btn_top10.setObjectName("btnSmall")
        btn_top10.setStyleSheet(
            "QPushButton { background:#2e1065; color:#f3e8ff; border:1px solid #a855f7; font-weight:700; border-radius:6px; padding:4px 10px; } "
            "QPushButton:hover { background:#4c1d95; color:white; }"
        )
        btn_top10.setToolTip("Consulter le Top 10 des cartes les plus rares conservées par compte")
        btn_top10.clicked.connect(self.open_top_cards)
        hh.addWidget(btn_top10)

        btn_hist = QPushButton("📜  Historique")
        btn_hist.setObjectName("btnSmall")
        btn_hist.clicked.connect(self.open_history)
        hh.addWidget(btn_hist)

        btn_transfer = QPushButton("🔄  Transférer")
        btn_transfer.setObjectName("btnSmall")
        btn_transfer.setStyleSheet("QPushButton { background:#064e3b; color:#a7f3d0; border:1px solid #059669; font-weight:700; border-radius:6px; padding:4px 10px; } QPushButton:hover { background:#047857; color:white; }")
        btn_transfer.setToolTip("Transférer des cartes en lot par rareté entre vos comptes")
        btn_transfer.clicked.connect(lambda: self.open_transfer_modal())
        hh.addWidget(btn_transfer)

        btn_friends = QPushButton("🤝  Amis")
        btn_friends.setObjectName("btnSmall")
        btn_friends.setStyleSheet("QPushButton { background:#1e1b4b; color:#c7d2fe; border:1px solid #4338ca; font-weight:700; border-radius:6px; padding:4px 10px; } QPushButton:hover { background:#312e81; color:white; }")
        btn_friends.setToolTip("Synchroniser et interconnecter tous les comptes en amis")
        btn_friends.clicked.connect(self.sync_all_friends)
        hh.addWidget(btn_friends)

        self.btn_toggle = QPushButton("⏸  Pause")
        self.btn_toggle.setObjectName("btnPrimary")
        self.btn_toggle.setObjectName("btnSmall")
        self.btn_toggle.clicked.connect(self.toggle_loop)
        hh.addWidget(self.btn_toggle)

        btn_add = QPushButton("➕  Ajouter un compte")
        btn_add.setObjectName("btnSmall")
        btn_add.setStyleSheet(f"background:#1e3a5f; border-color:#38bdf8; color:#e0f2fe; font-weight:700;")
        btn_add.clicked.connect(self.prompt_add_account)
        hh.addWidget(btn_add)

        self.btn_force = QPushButton("⚡  Tirer maintenant")
        self.btn_force.setObjectName("btnSuccess")
        self.btn_force.setToolTip("Ouvre tous les paquets prêts sur l'ensemble des comptes")
        self.btn_force.clicked.connect(lambda: self.trigger_claim_cycle())
        hh.addWidget(self.btn_force)

        root_layout.addWidget(header_frame)

        # ── Stats bar ────────────────────────────────────────────────────
        stats_frame = QFrame()
        stats_frame.setObjectName("statsBar")
        stats_frame.setFixedHeight(42)
        stats_frame.setStyleSheet(
            f"QFrame#statsBar{{background:{C_SURFACE}; border-bottom:1px solid {C_BORDER}; border-radius:0px;}}"
        )
        sh = QHBoxLayout(stats_frame)
        sh.setContentsMargins(22, 0, 22, 0)
        sh.setSpacing(24)

        self.lbl_total_packs = QLabel("📦  Total : 0 paquets ouverts")
        self.lbl_total_packs.setStyleSheet(f"font-size:11px; font-weight:600; color:{C_YELLOW};")
        sh.addWidget(self.lbl_total_packs)

        sep1 = QLabel("|")
        sep1.setStyleSheet(f"color:{C_BORDER2};")
        sh.addWidget(sep1)

        self.lbl_total_cards = QLabel("🃏  Collection : —")
        self.lbl_total_cards.setStyleSheet(f"font-size:11px; font-weight:600; color:{C_GREEN};")
        sh.addWidget(self.lbl_total_cards)

        sep2 = QLabel("|")
        sep2.setStyleSheet(f"color:{C_BORDER2};")
        sh.addWidget(sep2)

        self.lbl_next_pull = QLabel("⏱  Prochain tirage : —")
        self.lbl_next_pull.setStyleSheet(f"font-size:11px; font-weight:600; color:{C_ACCENT2};")
        sh.addWidget(self.lbl_next_pull)

        sh.addStretch()

        self.lbl_status_bar = QLabel("Tous les comptes sont isolés et gérés par Google Chrome.")
        self.lbl_status_bar.setStyleSheet(f"font-size:10px; color:{C_MUTED};")
        sh.addWidget(self.lbl_status_bar)

        root_layout.addWidget(stats_frame)

        # ── Main content (Scroll Area for Accounts) ──────────────────────
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 14, 18, 14)
        content_layout.setSpacing(14)

        # Scroll Area pour les cartes de comptes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(385)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.cards_layout = QHBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(14)
        self.cards_layout.setAlignment(Qt.AlignLeft)

        # Charger dynamiquement les comptes depuis la configuration
        self.reload_account_cards()

        scroll.setWidget(self.scroll_content)
        content_layout.addWidget(scroll)

        # ── Log console ──────────────────────────────────────────────────
        log_frame = QFrame()
        log_frame.setObjectName("logFrame")
        log_vl = QVBoxLayout(log_frame)
        log_vl.setContentsMargins(12, 10, 12, 10)
        log_vl.setSpacing(6)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)

        log_lbl = QLabel("◉  Journal d'activité")
        log_lbl.setStyleSheet(f"font-size:11px; font-weight:700; color:{C_MUTED}; letter-spacing:0.5px;")
        log_header.addWidget(log_lbl)
        log_header.addStretch()

        self.live_dot = QLabel("●")
        self.live_dot.setStyleSheet(f"color:{C_GREEN}; font-size:12px;")
        log_header.addWidget(self.live_dot)
        self.live_visible = True

        btn_copy = QPushButton("📋  Copier")
        btn_copy.setObjectName("btnSmall")
        btn_copy.setFixedHeight(24)
        btn_copy.setToolTip("Copie le journal complet dans le presse-papiers")
        btn_copy.clicked.connect(self.copy_logs)
        log_header.addWidget(btn_copy)

        btn_clear = QPushButton("🗑  Effacer")
        btn_clear.setObjectName("btnSmall")
        btn_clear.setFixedHeight(24)
        btn_clear.clicked.connect(lambda: self.log_box.clear())
        log_header.addWidget(btn_clear)

        log_vl.addLayout(log_header)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(130)
        log_vl.addWidget(self.log_box)

        content_layout.addWidget(log_frame)
        root_layout.addWidget(content)

        self.setCentralWidget(root)
        self.update_global_stats()
        self.log("✅  Interface prête. Tous les profils sont centralisés sur Google Chrome !", "success")

    def reload_account_cards(self):
        # Nettoyer les anciennes cartes
        for acc_id, card in list(self.account_cards.items()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.account_cards.clear()

        # Nettoyer l'éventuel bouton add existant
        if hasattr(self, "add_account_frame") and self.add_account_frame:
            self.cards_layout.removeWidget(self.add_account_frame)
            self.add_account_frame.deleteLater()

        accounts = engine.get_accounts()
        for idx, acc in enumerate(accounts):
            card = AccountCard(acc["id"], acc.get("name", f"Compte {idx+1}"), theme_idx=idx, parent=self)
            card.setup_requested.connect(self.start_account_setup)
            card.claim_requested.connect(self.start_single_claim)
            card.refresh_requested.connect(self.start_single_refresh)
            card.finish_setup_requested.connect(self.finish_account_setup)
            card.delete_requested.connect(self.confirm_delete_account)
            card.rename_requested.connect(self.handle_account_renamed)
            card.open_browser_requested.connect(self.launch_account_browser)
            card.transfer_requested.connect(self.open_transfer_modal)
            card.claim_achievements_requested.connect(self.claim_achievements_for_account)
            card.sync_friends_requested.connect(self.sync_friends_for_account)
            self.cards_layout.addWidget(card)
            self.account_cards[acc["id"]] = card

        # Ajouter la carte interactive 'Ajouter un compte'
        self.add_account_frame = AddAccountCard(self)
        self.add_account_frame.clicked.connect(self.prompt_add_account)
        self.cards_layout.addWidget(self.add_account_frame)

    def open_transfer_modal(self, source_account_id=None):
        dlg = TransferCardsModal(initial_source_id=source_account_id, parent=self)
        dlg.transfer_completed.connect(self.refresh_all_collection_stats)
        dlg.exec()

    def refresh_all_collection_stats(self):
        for card in self.account_cards.values():
            card.update_collection_stats_display()
        self.update_global_stats()

    def claim_achievements_for_account(self, account_id):
        card = self.account_cards.get(account_id)
        name = card.title_text if card else account_id
        self.log(f"[{name}] 🏆 Réclamation des succès en arrière-plan...", "info")
        worker = ClaimAchievementsWorker(account_id)
        worker.log_signal.connect(self.log)
        def on_done(aid, claimed):
            if card:
                card.update_collection_stats_display()
            self.update_global_stats()
            if claimed > 0:
                self.play_chime()
        worker.finished_signal.connect(on_done)
        worker.start()
        if not hasattr(self, "_active_bg_workers"):
            self._active_bg_workers = []
        self._active_bg_workers.append(worker)

    def sync_friends_for_account(self, account_id):
        card = self.account_cards.get(account_id)
        name = card.title_text if card else account_id
        self.log(f"[{name}] 🤝 Synchronisation des amis...", "info")
        worker = SyncFriendsWorker(account_id)
        worker.log_signal.connect(self.log)
        worker.finished_signal.connect(lambda aid: self.log(f"[{name}] ✓ Amis synchronisés avec succès !", "success"))
        worker.start()
        if not hasattr(self, "_active_bg_workers"):
            self._active_bg_workers = []
        self._active_bg_workers.append(worker)

    def sync_all_friends(self):
        self.log("🤝 Synchronisation et interconnexion de tous les comptes...", "info")
        configured = [acc["id"] for acc in engine.get_accounts() if engine.is_account_configured(acc["id"])]
        if not configured:
            self.log("Aucun compte configuré.", "warning")
            return
        worker = SyncFriendsWorker(configured[0])
        worker.log_signal.connect(self.log)
        worker.finished_signal.connect(lambda aid: self.log("✓ Tous les comptes sont interconnectés en amis !", "success"))
        worker.start()
        if not hasattr(self, "_active_bg_workers"):
            self._active_bg_workers = []
        self._active_bg_workers.append(worker)

    def prompt_add_account(self):
        try:
            dlg = AddAccountDialog(default_name=f"Compte {len(self.account_cards) + 1}", parent=self)
            if dlg.exec() and dlg.confirmed:
                name = dlg.account_name
                start_url = dlg.start_url
                b_type = dlg.browser_type
                b_name = dlg.browser_name
                new_acc = engine.add_new_account(name, browser_type=b_type)
                self.reload_account_cards()
                self.update_global_stats()
                action_desc = "création" if "/signup" in start_url else "connexion"
                self.log(f"➕ Compte '{name}' créé avec {b_name} ! Ouverture pour {action_desc}…", "success")
                self.start_account_setup(new_acc["id"], start_url=start_url)
        except Exception as e:
            write_debug(f"Erreur prompt_add_account : {e}\n{traceback.format_exc()}")
            self.log(f"✕ Erreur lors de l'ajout du compte : {e}", "error")

    def handle_account_renamed(self, account_id, new_name):
        self.log(f"✏️  Compte renommé en '{new_name}' avec succès !", "success")

    def confirm_delete_account(self, account_id):
        acc = engine.get_account_info(account_id)
        name = acc.get("name", account_id)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Supprimer le compte")
        msg_box.setText(f"Voulez-vous vraiment supprimer le compte '{name}' ?")
        msg_box.setInformativeText("Cette action retirera ce compte de l'application et supprimera sa session locale.")
        msg_box.setIcon(QMessageBox.Warning)
        btn_del = msg_box.addButton("🗑️ Supprimer", QMessageBox.YesRole)
        btn_cancel = msg_box.addButton("Annuler", QMessageBox.NoRole)
        msg_box.setDefaultButton(btn_cancel)
        msg_box.exec()

        if msg_box.clickedButton() == btn_del:
            engine.delete_account(account_id, remove_files=True)
            self.reload_account_cards()
            self.update_global_stats()
            self.log(f"🗑️ Compte '{name}' et ses données locales supprimés.", "warning")

    def launch_account_browser(self, account_id):
        acc = engine.get_account_info(account_id)
        name = acc.get("name", account_id)
        b_type = acc.get("browser_type", "chrome")
        b_name = engine.SUPPORTED_BROWSERS.get(b_type, {}).get("name", "Navigateur")
        self.log(f"🌐 Lancement de {b_name} pour '{name}'...", "info")
        ok, msg = engine.open_account_browser(account_id)
        if ok:
            self.log(f"✅ {msg}", "success")
        else:
            self.log(f"✕ {msg}", "error")
            QMessageBox.warning(self, "Erreur de lancement", f"Impossible d'ouvrir le navigateur pour '{name}' :\n\n{msg}")

    # ── Slots & Logic ────────────────────────────────────────────────────────

    def copy_logs(self):
        text = self.log_box.toPlainText()
        QApplication.clipboard().setText(text)
        self.log("📋  Journal copié dans le presse-papiers !", "success")

    def toggle_always_on_top(self, state):
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.log("📌  Fenêtre épinglée au premier plan.", "info")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
            self.log("📌  Épinglage désactivé.", "info")

    def play_chime(self):
        if self.sound_enabled:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

    def update_global_stats(self):
        lifetime = engine.load_lifetime_stats()
        total = sum(s.get("total_packs", 0) for s in lifetime.values())
        if total == 0:
            history = engine.load_history()
            total = sum(h.get("packs_count", 1) for h in history)
        self.lbl_total_packs.setText(f"📦  Total : {total} paquet(s) ouverts")

        col_stats = engine.load_collection_stats()
        total_cards_fleet = sum(cs.get("total", 0) for cs in col_stats.values())
        if hasattr(self, "lbl_total_cards"):
            if total_cards_fleet > 0:
                fmt_tc = f"{total_cards_fleet:,}".replace(",", " ")
                self.lbl_total_cards.setText(f"🃏  Collection : {fmt_tc} cartes")
            else:
                self.lbl_total_cards.setText("🃏  Collection : —")

        cards = list(self.account_cards.values())
        active = [c.remaining_seconds for c in cards if c.is_connected and c.remaining_seconds > 0]
        if active:
            s = min(active)
            self.lbl_next_pull.setText(f"⏱  Prochain : {s//60:02d}:{s%60:02d}")
        else:
            connected = [c for c in cards if c.is_connected]
            if connected:
                self.lbl_next_pull.setText("⏱  Prochain : bientôt…")
            else:
                self.lbl_next_pull.setText("⏱  Prochain : —")

    def open_top_cards(self):
        dlg = TopCardsModal(parent=self)
        dlg.exec()
        for card in self.account_cards.values():
            card.update_top_cards_preview()

    def open_history(self):
        dlg = HistoryModal(self)
        dlg.exec()

    def check_updates_gui(self, silent_if_none=False):
        try:
            has_update, remote_v, info = updater.check_for_updates()
            if has_update:
                reply = QMessageBox.question(
                    self, "Mise à jour disponible",
                    f"Une nouvelle version v{remote_v} est disponible sur GitHub !\n\n"
                    f"La mise à jour remplacera uniquement les fichiers de code.\n"
                    f"Vos comptes, cookies et historiques seront STRICTEMENT préservés.\n\n"
                    f"Voulez-vous installer la mise à jour maintenant ?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.log(f"📥 Téléchargement de la mise à jour v{remote_v}…", "info")
                    success, msg = updater.perform_update(status_callback=lambda m: self.log(m, "info"))
                    if success:
                        self.log(f"✅ Version v{remote_v} installée avec succès !", "success")
                        self.btn_update.setText(f"🔄 v{remote_v}")
                        QMessageBox.information(
                            self, "Mise à jour réussie",
                            f"La version v{remote_v} a été installée avec succès !\n\n"
                            f"Veuillez relancer l'application pour activer les nouveautés."
                        )
                    else:
                        self.log(f"✕ Échec de la mise à jour : {msg}", "error")
            else:
                if not silent_if_none:
                    err = info.get("error") if isinstance(info, dict) else None
                    if err:
                        QMessageBox.warning(self, "Vérification des mises à jour", f"Information : {err}")
                    else:
                        local_v = updater.get_local_version()
                        QMessageBox.information(self, "À jour", f"Vous disposez déjà de la version la plus récente (v{local_v}).")
        except Exception as e:
            if not silent_if_none:
                QMessageBox.warning(self, "Erreur", f"Erreur lors de la vérification : {e}")

    def log(self, message, level="info"):
        now = datetime.now().strftime("%H:%M:%S")
        colors = {
            "info":    C_ACCENT2,
            "success": C_GREEN,
            "warning": C_YELLOW,
            "error":   C_RED,
            "stealth": C_PURPLE,
        }
        col = colors.get(level, C_MUTED)
        prefix_icons = {
            "info": "›",
            "success": "✓",
            "warning": "⚠",
            "error": "✕",
            "stealth": "◈",
        }
        icon = prefix_icons.get(level, "›")
        html = (
            f"<span style='color:#374151;'>[{now}]</span> "
            f"<span style='color:{col};'>{icon}</span> "
            f"<span style='color:{col}; font-weight:500;'>{message}</span>"
        )
        self.log_box.append(html)
        self.lbl_status_bar.setText(message[:90] + ("…" if len(message) > 90 else ""))

    def tick_clock(self):
        self._tick_count += 1

        if self._tick_count % 2 == 0:
            self.live_visible = not self.live_visible
            self.live_dot.setStyleSheet(
                f"color:{C_GREEN if self.live_visible else C_BORDER2}; font-size:12px;"
            )
            # Rechargement automatique et transparent du Top 10 sans redémarrer le logiciel
            try:
                bc_file = engine.BEST_CARDS_FILE
                if bc_file.exists():
                    mtime = bc_file.stat().st_mtime
                    if not hasattr(self, "_last_bc_mtime"):
                        self._last_bc_mtime = mtime
                    elif mtime != self._last_bc_mtime:
                        self._last_bc_mtime = mtime
                        for card in self.account_cards.values():
                            card.update_top_cards_preview()
            except Exception:
                pass

        if not self.is_running:
            return

        for card in self.account_cards.values():
            card.tick_second()

        self.update_global_stats()

        ready = [
            acc_id for acc_id, card in self.account_cards.items()
            if card.is_connected and card.remaining_seconds == 0 and not card.is_claiming and acc_id not in self._pending_claim_queue
        ]
        if ready:
            for k in ready:
                card = self.account_cards.get(k)
                if card and (self.claim_worker and self.claim_worker.isRunning()):
                    card.sub_lbl.setText("En file d'attente…")
            self.queue_claim(ready)

    def toggle_loop(self):
        self.is_running = not self.is_running
        if self.is_running:
            self.btn_toggle.setText("⏸  Pause")
            self.btn_toggle.setObjectName("btnPrimary")
            self.log("▶  Boucle automatique reprise.", "info")
        else:
            self.btn_toggle.setText("▶  Reprendre")
            self.btn_toggle.setObjectName("btnSuccess")
            self.log("⏸  Boucle automatique en pause.", "warning")
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)

    def queue_claim(self, account_ids=None):
        if account_ids is None:
            account_ids = [
                acc["id"] for acc in engine.get_accounts()
                if engine.is_account_configured(acc["id"])
            ]
        for aid in account_ids:
            if aid not in self._pending_claim_queue:
                self._pending_claim_queue.append(aid)
        self._process_claim_queue()

    def _process_claim_queue(self):
        if self.claim_worker and self.claim_worker.isRunning():
            return
        if not self._pending_claim_queue:
            return

        batch = list(self._pending_claim_queue)
        self._pending_claim_queue.clear()

        accounts_to_run = [aid for aid in batch if aid in self.account_cards]
        if not accounts_to_run:
            return

        self.claim_worker = BackgroundClaimWorker(accounts_to_run)
        self.claim_worker.log_signal.connect(self.log)
        self.claim_worker.account_started_signal.connect(self.handle_account_started)
        self.claim_worker.account_result_signal.connect(self.handle_account_result)
        self.claim_worker.cycle_finished_signal.connect(self.handle_cycle_finished)
        self.claim_worker.start()

    def handle_account_started(self, account_id):
        card = self.account_cards.get(account_id)
        if card:
            card.is_claiming = True
            card.set_claiming_state()

    def trigger_claim_cycle(self, account_ids=None):
        self.queue_claim(account_ids)

    def handle_cycle_finished(self):
        for card in self.account_cards.values():
            if not card.is_connected or card.remaining_seconds > 0:
                card.is_claiming = False
        self.update_global_stats()
        if self._pending_claim_queue:
            QTimer.singleShot(400, self._process_claim_queue)
        else:
            self.log("✓  Cycle terminé. En attente du prochain timer.", "success")

    def handle_account_result(self, account_id, res):
        card = self.account_cards.get(account_id)
        if not card:
            return

        card.is_claiming = False
        status       = res.get("status")
        details      = res.get("details", "")
        browser_name = res.get("browser", account_id)
        sec          = res.get("seconds_left", 600)
        stock        = res.get("stock")
        cards        = res.get("cards", [])
        shot         = res.get("screenshot")
        opened       = res.get("packs_opened", 0)
        rarity       = res.get("rarity_summary", "")

        if status == "claimed":
            card.set_status("🎉  Récupéré !", "#14532d", "#86efac")
            card.set_countdown(sec)
            card.update_pack_data(stock=stock, cards=cards, shot_path=shot,
                                   packs_opened=opened, rarity_summary=rarity)
            card.sub_lbl.setText("Prochain paquet dans :")
            self.log(f"[{browser_name}] {details}", "success")
            self.play_chime()

        elif status == "waiting":
            card.set_status("✅  Prêt", "#14532d", "#86efac")
            card.set_countdown(sec)
            card.update_pack_data(stock=stock)
            card.sub_lbl.setText("Prochain paquet dans :")
            self.log(f"[{browser_name}] {details}", "info")

        elif status == "captcha_detected":
            card.set_captcha_mode(True)
            card.set_countdown(sec)
            self.log(
                f"[{browser_name}] ⚠  Défi anti-bot. Les autres comptes continuent. "
                f"Cliquez sur 🛠 Résoudre.", "warning"
            )

        elif status == "login_required":
            card.is_connected = False
            card.remaining_seconds = 0
            card.donut.set_idle()
            card.sub_lbl.setText("Session expirée")
            card.set_status("⚠  Déconnecté", "#451a03", "#fde68a")
            self.log(f"[{browser_name}] Session expirée. Reconnectez-vous.", "warning")

        elif status == "not_configured":
            card.is_connected = False
            card.donut.set_idle()
            card.sub_lbl.setText("Non configuré")
            card.set_status("●  Non connecté", "#451a03", "#fde68a")

        else:
            card.set_status("✕  Erreur", "#7f1d1d", "#fca5a5")
            card.set_countdown(60)
            card.sub_lbl.setText("Réessai dans 1 min…")
            self.log(f"[{browser_name}] Erreur : {details}", "error")

    def start_single_claim(self, account_id):
        card = self.account_cards.get(account_id)
        title = card.title_text if card else account_id
        self.log(f"⚡  Tirage manuel : {title}…", "info")
        self.trigger_claim_cycle([account_id])

    def start_single_refresh(self, account_id):
        card = self.account_cards.get(account_id)
        title = card.title_text if card else account_id
        self.log(f"↻  Actualisation : {title}…", "info")
        self.trigger_claim_cycle([account_id])

    def start_account_setup(self, account_id, start_url="https://wiki-masters.com/login"):
        if self.setup_worker and self.setup_worker.isRunning():
            self.log("Fermeture de la configuration précédente…", "warning")
            engine.close_active_setup()
            self.setup_worker.terminate()
            self.setup_worker.wait(1000)
            self.setup_worker = None

        card = self.account_cards.get(account_id)
        if card:
            card.set_setting_up_mode(True)

        acc = engine.get_account_info(account_id)
        name = acc.get("name", account_id)
        b_type = acc.get("browser_type", "chrome")
        b_name = engine.SUPPORTED_BROWSERS.get(b_type, {}).get("name", "Navigateur")
        action_name = "création / inscription" if "/signup" in start_url else "connexion"
        self.log(f"🔑  Ouverture de {b_name} pour {name} ({action_name})…", "info")
        self.setup_worker = SetupWorker(account_id, start_url=start_url)
        self.setup_worker.log_signal.connect(self.log)
        self.setup_worker.finished_signal.connect(self.handle_setup_finished)
        self.setup_worker.start()

    def finish_account_setup(self, account_id):
        card = self.account_cards.get(account_id)
        title = card.title_text if card else account_id
        self.log(f"✅  Configuration terminée pour {title}.", "info")
        engine.close_active_setup()

    def handle_setup_finished(self, account_id, success, msg):
        card = self.account_cards.get(account_id)
        if card:
            card.set_setting_up_mode(False)
            card.set_captcha_mode(False)
            card.update_configured_state()
            card.is_connected = True
            card.set_status("✅  Prêt", "#14532d", "#86efac")
            card.sub_lbl.setText("Synchronisation en cours…")
            card.donut.set_claiming()
        self.setup_worker = None

        acc = engine.get_account_info(account_id)
        name = acc.get("name", account_id)
        if success:
            self.log(f"✅  {name} configuré et prêt !", "success")
        else:
            self.log(f"Profil enregistré pour {name}. Vérification du statut…", "info")

        # Déclenche immédiatement la vérification et le premier tirage
        self.queue_claim([account_id])

# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    write_debug("Initialisation de QApplication...")
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        app.setStyle("Fusion")
        write_debug("Création de MainWindow...")
        window = MainWindow()
        write_debug("Affichage de MainWindow (show)...")
        window.show()
        window.raise_()
        window.activateWindow()
        write_debug("MainWindow affichée avec succès, entrée dans app.exec()...")
        sys.exit(app.exec())
    except Exception as e:
        err_msg = f"ERREUR FATALE : {e}\n{traceback.format_exc()}"
        write_debug(err_msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"WikiMasters Auto-Claimer n'a pas pu démarrer :\n\n{e}\n\nConsultez le fichier 'gui_debug.log' pour voir les détails.",
                "Erreur de démarrage — WikiMasters",
                0x10
            )
        except Exception:
            pass

if __name__ == "__main__":
    main()
