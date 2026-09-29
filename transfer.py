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
    Tolère la latence du serveur en réessayant les pages lentes (timeouts/504).
    Si keep_duplicates_only=True, ne sélectionne que les exemplaires excédentaires (doublons).
    """
    cards_to_transfer = []
    
    script = """async (raritiesList) => {
        const results = [];
        await Promise.all(raritiesList.map(async (r) => {
            let pageNum = 1;
            while (pageNum <= 100) {
                let pageData = null;
                for (let retry = 0; retry < 3; retry++) {
                    try {
                        const controller = new AbortController();
                        const timeoutId = setTimeout(() => controller.abort(), 16000);
                        const res = await fetch(`/api/my-collection?page=${pageNum}&limit=50&rarity=${r}`, { signal: controller.signal });
                        clearTimeout(timeoutId);
                        if (res.ok) {
                            pageData = await res.json();
                            break;
                        } else if (res.status === 502 || res.status === 503 || res.status === 504 || res.status === 429) {
                            await new Promise(res => setTimeout(res, 1200 + retry * 1000));
                            continue;
                        }
                    } catch (e) {
                        await new Promise(res => setTimeout(res, 1000 + retry * 1000));
                    }
                }
                if (!pageData || !pageData.collection || pageData.collection.length === 0) break;
                for (const item of pageData.collection) {
                    results.push({
                        id: item.id,
                        card_id: item.card_id,
                        count: item.count || 1,
                        title: item.card ? item.card.wikipedia_title : '',
                        rarity: item.card ? item.card.rarity : r
                    });
                }
                if (pageData.collection.length < 50) break;
                pageNum++;
            }
        }));
        return results;
    }"""
    
    raw_cards = page.evaluate(script, rarities)
    if not raw_cards:
        return []

    if keep_duplicates_only:
        seen_card_ids = {}
        for c in raw_cards:
            cid = c["card_id"]
            cnt = c.get("count", 1)
            if cnt > 1:
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
    """Envoie une offre d'échange contenant jusqu'à 100 cartes avec tolérance à la latence du serveur."""
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
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 30000);
                const r = await fetch('/api/trades', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-wiki-calendar-tz': 'Europe/Paris'
                    },
                    body: JSON.stringify(payload),
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                const data = await r.json().catch(() => ({}));
                if (r.ok) {
                    return { ok: true, status: r.status, data };
                }
                // Tolérance 502/504 : vérifier si l'échange est bien passé malgré le timeout de passerelle
                if (r.status === 502 || r.status === 504 || r.status === 500) {
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    try {
                        const checkRes = await fetch('/api/trades?active=1');
                        if (checkRes.ok) {
                            const checkData = await checkRes.json();
                            const activeTrades = checkData.trades || [];
                            const alreadyCreated = activeTrades.some(t =>
                                t.recipient_id === payload.recipient_id &&
                                (t.items || []).length === payload.items.length
                            );
                            if (alreadyCreated) {
                                return { ok: true, status: 200, recovered: true };
                            }
                        }
                    } catch(e) {}
                    await new Promise(resolve => setTimeout(resolve, 1500 + attempt * 1200));
                    continue;
                }
                return { ok: false, status: r.status, data, error: data.error || `Erreur serveur (${r.status})` };
            } catch (e) {
                if (attempt === 2) return { ok: false, error: 'Délai d\\'attente dépassé (latence serveur)' };
                await new Promise(resolve => setTimeout(resolve, 1500 + attempt * 1200));
            }
        }
        return { ok: false, error: 'Échec après 3 tentatives (latence serveur)' };
    }""", payload)
    return res

def accept_incoming_trades(page, from_username=None):
    """
    Vérifie et accepte tous les échanges actifs reçus (optionnellement filtrés par from_username)
    avec temporisation entre les lots pour soulager la base de données de WikiMasters.
    """
    res = page.evaluate("""async (filterUsername) => {
        try {
            let data = null;
            for (let retry = 0; retry < 3; retry++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 16000);
                    const r = await fetch('/api/trades?active=1', { signal: controller.signal });
                    clearTimeout(timeoutId);
                    if (r.ok) { data = await r.json(); break; }
                } catch(e) {}
                await new Promise(r => setTimeout(r, 1400));
            }
            if (!data) return { ok: false, error: 'Impossible de lire les échanges (latence serveur)' };

            const trades = data.trades || [];
            const accepted = [];

            for (const t of trades) {
                const initiatorName = t.initiator ? t.initiator.username : '';
                if (filterUsername && initiatorName.toLowerCase() !== filterUsername.toLowerCase()) {
                    continue;
                }

                // Accepter l'échange avec tentative de récupération sur latence
                let patchSuccess = false;
                for (let patchAttempt = 0; patchAttempt < 3; patchAttempt++) {
                    try {
                        const patchRes = await fetch(`/api/trades/${t.id}`, {
                            method: 'PATCH',
                            headers: {
                                'Content-Type': 'application/json',
                                'x-wiki-calendar-tz': 'Europe/Paris'
                            },
                            body: JSON.stringify({ action: 'accept' })
                        });

                        if (patchRes.ok) {
                            patchSuccess = true;
                            accepted.push({
                                id: t.id,
                                initiator: initiatorName,
                                cards_count: (t.items || []).length
                            });
                            break;
                        } else if (patchRes.status === 502 || patchRes.status === 504 || patchRes.status === 429) {
                            await new Promise(r => setTimeout(r, 1800));
                            continue;
                        }
                    } catch(e) {}
                    await new Promise(r => setTimeout(r, 1400));
                }

                // Pause raisonnable pour éviter d'engorger la base de données sur les gros transferts
                await new Promise(r => setTimeout(r, 1000));
            }
            return { ok: true, accepted };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    }""", from_username)
    return res

def execute_bulk_donation(source_account_ids, target_account_name, rarities, keep_duplicates_only=False, status_callback=None):
    """
    Exécute le don centralisé de cartes depuis PLUSIEURS comptes sources vers UN compte cible unique.
    1. Pour chaque compte source sélectionné :
       - Connexion au profil source
       - Récupération des cartes selon les raretés
       - Envoi des offres d'échange (par lots de 100 cartes)
       - Extraction des nouvelles stats du compte source
    2. Connexion au compte cible (une seule fois à la fin) :
       - Réception et acceptation automatique de TOUS les échanges reçus
       - Extraction des nouvelles stats du compte cible
    """
    import engine

    def notify(msg, level="info"):
        if status_callback:
            try:
                status_callback(msg, level)
            except Exception:
                pass

    config = engine.load_config()
    target_acc = next((a for a in config.get("accounts", []) if a.get("name", "").lower() == target_account_name.lower() or a.get("id") == target_account_name), None)
    if not target_acc:
        return False, f"Compte destinataire '{target_account_name}' introuvable."

    target_id = target_acc.get("id")
    target_real_name = target_acc.get("name", target_account_name)

    # Exclure le compte cible de la liste des donateurs
    valid_sources = [sid for sid in source_account_ids if sid != target_id]
    if not valid_sources:
        return False, "Aucun compte donateur sélectionné."

    notify(f"🌟 Lancement du don centralisé : {len(valid_sources)} compte(s) donateur(s) vers {target_real_name}...", "info")

    grand_total_transferred = 0
    accounts_donated = []
    failed_sources = []

    for s_idx, source_id in enumerate(valid_sources, 1):
        engine.mark_account_busy(source_id)
        source_acc = engine.get_account_info(source_id)
        source_name = source_acc.get("name", source_id)
        source_pdir = engine.BASE_DIR / source_acc.get("profile_dir", f"profiles/{source_id}")
        exe_path = engine.get_browser_executable_for_account(source_id)

        notify(f"[{source_name}] 🔄 [{s_idx}/{len(valid_sources)}] Analyse des cartes à donner pour {target_real_name}...", "info")
        engine.kill_browser_processes(source_id)

        with sync_playwright() as p:
            context = None
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(source_pdir),
                    executable_path=exe_path,
                    headless=True,
                    viewport={"width": 1366, "height": 768},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                    args=engine.get_browser_launch_args(source_id)
                )
                apply_stealth(context)
                page = context.pages[0] if context.pages else context.new_page()

                try:
                    page.goto("https://wiki-masters.com/trades", wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    pass
                time.sleep(1.2)

                # Résolution de l'ID ami
                recipient_id, my_id = get_friend_user_id(page, target_real_name)
                if not recipient_id or not my_id:
                    # Recherche de l'utilisateur
                    search_res = page.evaluate("""async (q) => {
                        try {
                            const r = await fetch(`/api/friends/search?q=${encodeURIComponent(q)}`);
                            return await r.json();
                        } catch(e) { return null; }
                    }""", target_real_name)

                    users = (search_res or {}).get("users", [])
                    target_user = next((u for u in users if u.get("username", "").lower() == target_real_name.lower()), None)
                    if target_user:
                        recipient_id = target_user.get("id")
                        my_id = page.evaluate("""async () => {
                            try {
                                const r = await fetch('/api/user');
                                const d = await r.json();
                                return d.id;
                            } catch(e) { return null; }
                        }""")
                        page.evaluate("""async (id) => {
                            try {
                                await fetch('/api/friends', {
                                    method: 'POST',
                                    headers: {'Content-Type': 'application/json'},
                                    body: JSON.stringify({addressee_id: id})
                                });
                            } catch(e) {}
                        }""", recipient_id)
                        notify(f"[{source_name}] 🤝 Demande d'ami envoyée à {target_real_name}.", "warning")

                if not recipient_id or not my_id:
                    notify(f"[{source_name}] ⚠️ Impossible de résoudre l'ami {target_real_name}. Passage au compte suivant.", "warning")
                    failed_sources.append(source_name)
                    continue

                notify(f"[{source_name}] 🔍 Analyse de la collection ({', '.join(rarities)})...", "info")
                cards = get_cards_for_transfer(page, rarities, keep_duplicates_only=keep_duplicates_only)

                if not cards:
                    mode_str = " (doublons uniquement)" if keep_duplicates_only else ""
                    notify(f"[{source_name}] ℹ️ Aucune carte correspondante {', '.join(rarities)}{mode_str} à donner sur ce compte.", "info")
                    continue

                notify(f"[{source_name}] 📦 {len(cards)} cartes prêtes au don. Envoi des lots...", "info")

                chunks = [cards[i:i + MAX_CARDS_PER_TRADE] for i in range(0, len(cards), MAX_CARDS_PER_TRADE)]
                batches_count = len(chunks)
                account_sent = 0

                for c_idx, chunk in enumerate(chunks, 1):
                    notify(f"[{source_name}] 🚀 Envoi du lot {c_idx}/{batches_count} ({len(chunk)} cartes)...", "info")
                    res = send_trade_offer(page, recipient_id, my_id, chunk)
                    if not res.get("ok"):
                        notify(f"[{source_name}] ⚠️ Échec de l'envoi du lot {c_idx}: {res.get('error', 'Erreur')}", "error")
                    else:
                        account_sent += len(chunk)
                        grand_total_transferred += len(chunk)
                        notify(f"[{source_name}] ✅ Lot {c_idx}/{batches_count} envoyé ({len(chunk)} cartes) !", "success")
                    human_delay(1.0, 1.8)

                if account_sent > 0:
                    accounts_donated.append((source_name, account_sent))
                    engine.extract_collection_stats(page, source_id)

            except Exception as e:
                notify(f"[{source_name}] ⚠️ Erreur pendant le don : {e}", "error")
                failed_sources.append(source_name)
            finally:
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass
                engine.kill_browser_processes(source_id)
                engine.unmark_account_busy(source_id)

    # 2. ÉTAPE 2 : Connexion au compte destinataire pour TOUT valider d'un coup
    if grand_total_transferred > 0:
        engine.mark_account_busy(target_id)
        target_pdir = engine.BASE_DIR / target_acc.get("profile_dir", f"profiles/{target_id}")
        target_exe = engine.get_browser_executable_for_account(target_id)

        notify(f"[{target_real_name}] 📥 Connexion pour accepter automatiquement tous les dons reçus ({grand_total_transferred} cartes)...", "info")
        engine.kill_browser_processes(target_id)

        with sync_playwright() as p:
            context = None
            try:
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
                except Exception:
                    pass
                time.sleep(2.0)

                # Accepter TOUS les échanges reçus (tous initiateurs confondus)
                accept_res = accept_incoming_trades(page, from_username=None)
                accepted_trades = accept_res.get("accepted", [])
                if accepted_trades:
                    notify(f"[{target_real_name}] 🎉 {len(accepted_trades)} don(s) validé(s) ! (+{grand_total_transferred} cartes ajoutées)", "success")
                else:
                    notify(f"[{target_real_name}] ℹ️ Offres en attente de traitement.", "info")

                engine.extract_collection_stats(page, target_id)
            except Exception as e:
                notify(f"[{target_real_name}] ⚠️ Erreur lors de l'acceptation : {e}", "warning")
            finally:
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass
                engine.kill_browser_processes(target_id)
                engine.unmark_account_busy(target_id)

    if grand_total_transferred > 0:
        summary_parts = [f"{name}: {cnt}" for name, cnt in accounts_donated]
        summary_str = ", ".join(summary_parts)
        summary_msg = f"🎉 Tous les dons sont terminés ! {grand_total_transferred} cartes centralisées sur {target_real_name} [Détail : {summary_str}]."
        notify(summary_msg, "success")
        return True, summary_msg
    else:
        return False, "Aucune carte n'a pu être donnée (aucune carte correspondante ou erreurs de session)."

def execute_card_transfer(source_account_id, target_account_name, rarities, keep_duplicates_only=False, status_callback=None):
    """
    Rétrocompatibilité : effectue un don unique de source_account_id vers target_account_name.
    """
    return execute_bulk_donation(
        source_account_ids=[source_account_id],
        target_account_name=target_account_name,
        rarities=rarities,
        keep_duplicates_only=keep_duplicates_only,
        status_callback=status_callback
    )

