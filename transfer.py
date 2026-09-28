"""
Module de gestion avancée des transferts et échanges de cartes pour WikiMasters.
Permet d'échanger en lot jusqu'à 100 cartes par échange selon les filtres de rareté.
Prend en charge l'acceptation automatique réciproque entre comptes du gestionnaire.
"""

import time
import json
import random
from pathlib import Path
from playwright.sync_api import sync_playwright

from stealth import apply_stealth, human_delay

RARITY_ORDER = ["L", "UR", "SR", "R", "PC", "C"]
MAX_CARDS_PER_TRADE = 100

def get_tz_header():
    return {"x-wiki-calendar-tz": "Europe/Paris", "Content-Type": "application/json"}

def fetch_account_friends(page):
    """Récupère la liste des amis du compte actuellement ouvert."""
    try:
        data = page.evaluate("""async () => {
            try {
                const res = await fetch('/api/friends');
                if (res.ok) return await res.json();
            } catch (e) {}
            return null;
        }""")
        if not data or "friendships" not in data:
            return []
        
        friends = []
        for f in data["friendships"]:
            if f.get("status") == "accepted":
                # Identifier l'autre utilisateur
                other = f.get("addressee") if f.get("requester") and f.get("requester", {}).get("id") else f.get("addressee")
                # On extrait les deux pour être certain
                friends.append(f)
        return data["friendships"]
    except Exception:
        return []

def get_friend_user_id(page, friend_username):
    """Trouve l'user_id d'un ami à partir de son nom d'utilisateur."""
    try:
        friendships = fetch_account_friends(page)
        target_clean = friend_username.lower().strip()
        for f in friendships:
            if f.get("status") == "accepted":
                addr = f.get("addressee", {})
                req = f.get("requester", {})
                if addr.get("username", "").lower() == target_clean:
                    return addr.get("id"), req.get("id") # (friend_id, my_id)
                if req.get("username", "").lower() == target_clean:
                    return req.get("id"), addr.get("id") # (friend_id, my_id)
    except Exception:
        pass
    return None, None

def get_cards_for_transfer(page, rarities, keep_duplicates_only=False):
    """
    Récupère toutes les cartes de la collection correspondant aux raretés sélectionnées.
    Si keep_duplicates_only=True, ne sélectionne que les exemplaires excédentaires (doublons).
    """
    cards_to_transfer = []
    
    script = """async (raritiesList) => {
        const results = [];
        for (const r of raritiesList) {
            let pageNum = 1;
            while (pageNum <= 100) {
                try {
                    const res = await fetch(`/api/my-collection?page=${pageNum}&limit=50&rarity=${r}`);
                    if (!res.ok) break;
                    const data = await res.json();
                    if (!data.collection || data.collection.length === 0) break;
                    for (const item of data.collection) {
                        results.push({
                            id: item.id,
                            card_id: item.card_id,
                            count: item.count || 1,
                            title: item.card ? item.card.wikipedia_title : '',
                            rarity: item.card ? item.card.rarity : r
                        });
                    }
                    if (data.collection.length < 50) break;
                } catch (e) {
                    break;
                }
                pageNum++;
            }
        }
        return results;
    }"""
    
    raw_cards = page.evaluate(script, rarities)
    if not raw_cards:
        return []

    if keep_duplicates_only:
        # Conserver 1 exemplaire par card_id
        seen_card_ids = {}
        for c in raw_cards:
            cid = c["card_id"]
            cnt = c.get("count", 1)
            if cnt > 1:
                # La carte indique elle-même posséder plusieurs exemplaires
                cards_to_transfer.append(c)
            else:
                if cid not in seen_card_ids:
                    seen_card_ids[cid] = c
                else:
                    cards_to_transfer.append(c)
    else:
        cards_to_transfer = raw_cards

    return cards_to_transfer

def send_trade_offer(page, recipient_id, my_id, cards_batch):
    """Envoie une offre d'échange contenant jusqu'à 100 cartes."""
    payload = {
        "recipient_id": recipient_id,
        "items": [
            {
                "user_card_id": c["id"],
                "card_id": c["card_id"],
                "offered_by": my_id
            }
            for c in cards_batch
        ],
        "initiator_wikibidous": 0,
        "recipient_wikibidous": 0
    }

    res = page.evaluate("""async (payload) => {
        try {
            const r = await fetch('/api/trades', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-wiki-calendar-tz': 'Europe/Paris'
                },
                body: JSON.stringify(payload)
            });
            const data = await r.json().catch(() => ({}));
            return { ok: r.ok, status: r.status, data };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    }""", payload)
    return res

def accept_incoming_trades(page, from_username=None):
    """
    Vérifie et accepte tous les échanges actifs reçus (optionnellement filtrés par from_username).
    """
    res = page.evaluate("""async (filterUsername) => {
        try {
            const r = await fetch('/api/trades?active=1');
            if (!r.ok) return { ok: false, error: 'Impossible de lire les échanges' };
            const data = await r.json();
            const trades = data.trades || [];
            const accepted = [];

            for (const t of trades) {
                // Vérifier si l'échange est reçu
                const initiatorName = t.initiator ? t.initiator.username : '';
                if (filterUsername && initiatorName.toLowerCase() !== filterUsername.toLowerCase()) {
                    continue;
                }

                // Accepter l'échange
                const patchRes = await fetch(`/api/trades/${t.id}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-wiki-calendar-tz': 'Europe/Paris'
                    },
                    body: JSON.stringify({ action: 'accept' })
                });

                if (patchRes.ok) {
                    accepted.push({
                        id: t.id,
                        initiator: initiatorName,
                        cards_count: (t.items || []).length
                    });
                }
            }
            return { ok: true, accepted };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    }""", from_username)
    return res

def execute_card_transfer(source_account_id, target_account_name, rarities, keep_duplicates_only=False, status_callback=None):
    """
    Exécute le transfert de cartes de source_account_id vers target_account_name.
    1. Ouvre le compte source.
    2. Récupère les cartes correspondant aux raretés demandées.
    3. Envoie des offres d'échange par lots de 100 cartes.
    4. Si le compte destinataire est un des comptes enregistrés, ouvre le compte destinataire
       et accepte automatiquement les échanges reçus.
    """
    import engine

    def notify(msg, level="info"):
        if status_callback:
            try:
                status_callback(msg, level)
            except Exception:
                pass

    config = engine.load_config()
    source_acc = engine.get_account_info(source_account_id)
    source_name = source_acc.get("name", source_account_id)
    source_pdir = engine.BASE_DIR / source_acc.get("profile_dir", f"profiles/{source_account_id}")
    exe_path = engine.get_browser_executable_for_account(source_account_id)

    notify(f"[{source_name}] 🔄 Préparation du transfert vers {target_account_name}...", "info")

    engine.kill_browser_processes(source_account_id)

    total_transferred = 0
    batches_count = 0

    with sync_playwright() as p:
        # 1. ÉTAPE 1 : Connexion au compte source
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(source_pdir),
            executable_path=exe_path,
            headless=True,
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            args=engine.get_browser_launch_args(source_account_id)
        )
        apply_stealth(context)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto("https://wiki-masters.com/trades", wait_until="domcontentloaded", timeout=25000)
            time.sleep(1.5)

            # Résolution de l'ID ami
            recipient_id, my_id = get_friend_user_id(page, target_account_name)
            if not recipient_id or not my_id:
                # Essayer de chercher l'utilisateur
                search_res = page.evaluate("""async (q) => {
                    try {
                        const r = await fetch(`/api/friends/search?q=${encodeURIComponent(q)}`);
                        return await r.json();
                    } catch(e) { return null; }
                }""", target_account_name)
                
                users = (search_res or {}).get("users", [])
                target_user = next((u for u in users if u.get("username", "").lower() == target_account_name.lower()), None)
                if target_user:
                    recipient_id = target_user.get("id")
                    my_id = page.evaluate("""async () => {
                        try {
                            const r = await fetch('/api/user');
                            const d = await r.json();
                            return d.id;
                        } catch(e) { return null; }
                    }""")
                    # Envoyer demande d'ami
                    page.evaluate("""async (id) => {
                        try {
                            await fetch('/api/friends', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({addressee_id: id})
                            });
                        } catch(e) {}
                    }""", recipient_id)
                    notify(f"[{source_name}] 🤝 Demande d'ami envoyée à {target_account_name}. L'échange nécessite qu'il accepte.", "warning")
                
                if not recipient_id or not my_id:
                    context.close()
                    return False, f"Impossible de trouver l'identifiant pour {target_account_name}."

            notify(f"[{source_name}] 🔍 Analyse des cartes à transférer ({', '.join(rarities)})...", "info")
            cards = get_cards_for_transfer(page, rarities, keep_duplicates_only=keep_duplicates_only)

            if not cards:
                context.close()
                mode_str = " (doublons uniquement)" if keep_duplicates_only else ""
                return False, f"Aucune carte {', '.join(rarities)}{mode_str} trouvée sur {source_name}."

            notify(f"[{source_name}] 📦 {len(cards)} cartes prêtes au transfert. Envoi en cours...", "info")

            # Découpage en lots de 100 cartes
            chunks = [cards[i:i + MAX_CARDS_PER_TRADE] for i in range(0, len(cards), MAX_CARDS_PER_TRADE)]
            batches_count = len(chunks)

            for idx, chunk in enumerate(chunks, 1):
                notify(f"[{source_name}] 🚀 Envoi du lot {idx}/{batches_count} ({len(chunk)} cartes)...", "info")
                res = send_trade_offer(page, recipient_id, my_id, chunk)
                if not res.get("ok"):
                    notify(f"[{source_name}] ⚠️ Échec de l'envoi du lot {idx}: {res.get('error', 'Erreur')}", "error")
                else:
                    total_transferred += len(chunk)
                    notify(f"[{source_name}] ✅ Lot {idx}/{batches_count} envoyé avec succès !", "success")
                human_delay(1.5, 2.5)

            # Mettre à jour les stats du compte source
            engine.extract_collection_stats(page, source_account_id)

        finally:
            context.close()

    # 2. ÉTAPE 2 : Si le compte destinataire est géré par le logiciel, accepter automatiquement !
    target_acc = next((a for a in config.get("accounts", []) if a.get("name", "").lower() == target_account_name.lower()), None)
    if target_acc and total_transferred > 0:
        target_id = target_acc.get("id")
        target_pdir = engine.BASE_DIR / target_acc.get("profile_dir", f"profiles/{target_id}")
        target_exe = engine.get_browser_executable_for_account(target_id)

        notify(f"[{target_account_name}] 📥 Connexion pour accepter automatiquement les {total_transferred} cartes...", "info")
        engine.kill_browser_processes(target_id)

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(target_pdir),
                executable_path=target_exe,
                headless=True,
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                args=engine.get_browser_launch_args(target_id)
            )
            apply_stealth(context)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto("https://wiki-masters.com/trades", wait_until="domcontentloaded", timeout=25000)
                time.sleep(2.0)

                # Accepter tous les échanges reçus venant de source_name
                accept_res = accept_incoming_trades(page, from_username=source_name)
                accepted_trades = accept_res.get("accepted", [])
                if accepted_trades:
                    notify(f"[{target_account_name}] 🎉 {len(accepted_trades)} échange(s) validé(s) ! ({total_transferred} cartes ajoutées)", "success")
                else:
                    notify(f"[{target_account_name}] ℹ️ Offres en attente de validation manuelle.", "info")

                # Mettre à jour les stats du compte destinataire
                engine.extract_collection_stats(page, target_id)

            finally:
                context.close()

    summary_msg = f"🎉 Transfert terminé : {total_transferred} cartes transférées de {source_name} vers {target_account_name} !"
    notify(summary_msg, "success")
    return True, summary_msg

