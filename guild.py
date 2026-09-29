"""
Module de gestion avancée des Guildes pour WikiMasters.
Permet d'inviter et de faire rejoindre automatiquement tous les comptes secondaires
dans la guilde du compte principal défini par l'utilisateur.
"""

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

from stealth import apply_stealth, human_delay, enforce_single_page

def get_tz_header():
    return {"x-wiki-calendar-tz": "Europe/Paris", "Content-Type": "application/json"}

def get_account_guild_info(page):
    """
    Récupère les informations complètes de la guilde pour le compte actuellement ouvert avec tolérance à la latence.
    """
    try:
        data = page.evaluate("""async () => {
            for (let retry = 0; retry < 3; retry++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 14000);
                    const res = await fetch('/api/guilds', { signal: controller.signal });
                    clearTimeout(timeoutId);
                    if (res.ok) return await res.json();
                    if (res.status === 502 || res.status === 503 || res.status === 504 || res.status === 429) {
                        await new Promise(r => setTimeout(r, 1200 + retry * 800));
                        continue;
                    }
                    return { error_status: res.status };
                } catch(e) {
                    await new Promise(r => setTimeout(r, 1000 + retry * 800));
                }
            }
            return { error: 'Latence serveur' };
        }""")
        if not data or not isinstance(data, dict):
            return {"in_guild": False}

        guild = data.get("guild")
        membership = data.get("membership")
        if guild and isinstance(guild, dict) and guild.get("id"):
            return {
                "in_guild": True,
                "guild_id": guild.get("id"),
                "guild_name": guild.get("name", "Sans nom"),
                "description": guild.get("description", ""),
                "role": membership.get("role", "member") if membership else "member",
                "member_count": data.get("member_count", 0),
                "created_by": guild.get("created_by")
            }
        return {"in_guild": False}
    except Exception as e:
        return {"in_guild": False, "error": str(e)}

def get_guild_member_ids(page):
    """Récupère l'ensemble des IDs d'utilisateurs membres de la guilde."""
    try:
        data = page.evaluate("""async () => {
            try {
                const res = await fetch('/api/guilds/members?ids_only=1');
                if (res.ok) return await res.json();
                return null;
            } catch(e) { return null; }
        }""")
        if data and isinstance(data, dict):
            return set(data.get("member_ids", []))
    except Exception:
        pass
    return set()

def get_my_user_id(page):
    """Extrait l'ID utilisateur unique du compte actuellement connecté."""
    try:
        uid = page.evaluate("""async () => {
            try {
                // 1. Via /api/user si disponible
                const r1 = await fetch('/api/user');
                if (r1.ok) {
                    const d1 = await r1.json();
                    if (d1?.id) return d1.id;
                }
            } catch(e) {}
            try {
                // 2. Via /api/guilds membership
                const r2 = await fetch('/api/guilds');
                if (r2.ok) {
                    const d2 = await r2.json();
                    if (d2?.membership?.user_id) return d2.membership.user_id;
                }
            } catch(e) {}
            try {
                // 3. Via notifications
                const r3 = await fetch('/api/notifications');
                if (r3.ok) {
                    const d3 = await r3.json();
                    const n = d3?.notifications?.[0];
                    if (n?.user_id) return n.user_id;
                }
            } catch(e) {}
            return null;
        }""")
        return uid
    except Exception:
        return None

def resolve_user_id_for_username(page, target_username):
    """Trouve l'user_id d'un compte à partir de son nom (amis ou recherche)."""
    try:
        clean_target = target_username.lower().strip()

        # 1. Vérifier dans la liste d'amis
        friends_data = page.evaluate("""async () => {
            try {
                const res = await fetch('/api/friends');
                if (res.ok) return await res.json();
            } catch(e) {}
            return null;
        }""")

        if friends_data and "friendships" in friends_data:
            for f in friends_data["friendships"]:
                addr = f.get("addressee", {})
                req = f.get("requester", {})
                if addr.get("username", "").lower() == clean_target:
                    return addr.get("id")
                if req.get("username", "").lower() == clean_target:
                    return req.get("id")

        # 2. Recherche utilisateur globale
        search_res = page.evaluate("""async (q) => {
            try {
                const r = await fetch(`/api/friends/search?q=${encodeURIComponent(q)}`);
                if (r.ok) return await r.json();
            } catch(e) {}
            return null;
        }""", target_username)

        users = (search_res or {}).get("users", [])
        for u in users:
            if u.get("username", "").lower() == clean_target:
                return u.get("id")

    except Exception:
        pass
    return None

def invite_to_guild(page, user_id):
    """Envoie une invitation de guilde à un utilisateur avec tolérance à la latence."""
    try:
        res = page.evaluate("""async (uid) => {
            for (let attempt = 0; attempt < 3; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 16000);
                    const r = await fetch('/api/guilds/invite', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ user_id: uid }),
                        signal: controller.signal
                    });
                    clearTimeout(timeoutId);
                    if (r.ok) return { ok: true };
                    const err = await r.json().catch(() => ({}));
                    if (r.status === 502 || r.status === 504 || r.status === 429) {
                        await new Promise(res => setTimeout(res, 1500 + attempt * 1000));
                        continue;
                    }
                    if (err.error && (err.error.includes('déjà') || err.error.includes('already') || err.error.includes('member'))) {
                        return { ok: true, note: err.error };
                    }
                    return { ok: false, error: err.error || 'Erreur inconnue' };
                } catch(e) {
                    await new Promise(res => setTimeout(res, 1200 + attempt * 1000));
                }
            }
            return { ok: false, error: 'Échec après 3 tentatives (latence serveur)' };
        }""", user_id)
        return res
    except Exception as e:
        return {"ok": False, "error": str(e)}

def join_guild(page, guild_id):
    """Rejoint la guilde spécifiée avec tolérance à la latence."""
    try:
        res = page.evaluate("""async (gid) => {
            for (let attempt = 0; attempt < 3; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 16000);
                    const r = await fetch('/api/guilds/join', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ guild_id: gid }),
                        signal: controller.signal
                    });
                    clearTimeout(timeoutId);
                    if (r.ok) return { ok: true };
                    const err = await r.json().catch(() => ({}));
                    if (r.status === 502 || r.status === 504 || r.status === 429) {
                        await new Promise(res => setTimeout(res, 1500 + attempt * 1000));
                        continue;
                    }
                    if (err.error && (err.error.includes('déjà') || err.error.includes('already') || err.error.includes('member'))) {
                        return { ok: true, note: err.error };
                    }
                    return { ok: false, error: err.error || 'Erreur inconnue' };
                } catch(e) {
                    await new Promise(res => setTimeout(res, 1200 + attempt * 1000));
                }
            }
            return { ok: false, error: 'Échec après 3 tentatives (latence serveur)' };
        }""", guild_id)
        return res
    except Exception as e:
        return {"ok": False, "error": str(e)}

def leave_guild(page):
    """Quitte la guilde actuelle avec tolérance à la latence."""
    try:
        res = page.evaluate("""async () => {
            for (let attempt = 0; attempt < 3; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 14000);
                    const r = await fetch('/api/guilds/leave', { method: 'POST', signal: controller.signal });
                    clearTimeout(timeoutId);
                    if (r.ok) return { ok: true };
                    const err = await r.json().catch(() => ({}));
                    if (r.status === 502 || r.status === 504 || r.status === 429) {
                        await new Promise(res => setTimeout(res, 1500));
                        continue;
                    }
                    return { ok: false, error: err.error || 'Erreur inconnue' };
                } catch(e) {
                    await new Promise(res => setTimeout(res, 1200));
                }
            }
            return { ok: false, error: 'Échec après 3 tentatives (latence serveur)' };
        }""")
        return res
    except Exception as e:
        return {"ok": False, "error": str(e)}

def execute_guild_sync(main_account_id=None, status_callback=None):
    """
    Synchronise tous les comptes dans la guilde du compte principal :
    1. Connexion au compte principal :
       - Récupération de l'ID et du nom de sa guilde
       - Vérification des membres actuels de la guilde
       - Envoi d'une invitation à tous les comptes qui ne sont pas encore membres
    2. Connexion successive aux comptes invités :
       - Si le compte est dans une autre guilde, il la quitte
       - Il accepte et rejoint la guilde du compte principal
    """
    import engine

    def notify(msg, level="info"):
        if status_callback:
            try:
                status_callback(msg, level)
            except Exception:
                pass

    config = engine.load_config()
    accounts = config.get("accounts", [])
    if not accounts:
        return False, "Aucun compte configuré."

    main_id = main_account_id or config.get("main_account_id") or accounts[0]["id"]
    main_acc = next((a for a in accounts if a["id"] == main_id), accounts[0])
    main_name = main_acc.get("name", main_acc["id"])
    main_pdir = engine.BASE_DIR / main_acc.get("profile_dir", f"profiles/{main_acc['id']}")
    exe_path = engine.get_browser_executable_for_account(main_acc["id"])

    notify(f"🏰 [Compte Principal: {main_name}] Connexion et analyse de la guilde...", "info")
    engine.kill_browser_processes(main_acc["id"])

    target_guild_id = None
    target_guild_name = None
    existing_member_ids = set()
    accounts_to_invite = []

    # ── Étape 1 : Analyser la guilde du compte principal et inviter ──
    with sync_playwright() as p:
        ctx = None
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(main_pdir),
                executable_path=exe_path,
                headless=True,
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                args=engine.get_browser_launch_args(main_acc["id"])
            )
            apply_stealth(ctx)
            page = enforce_single_page(ctx)


            try:
                page.goto("https://www.wiki-masters.com/guild", wait_until="domcontentloaded", timeout=25000)
            except Exception:
                pass
            time.sleep(1.2)

            g_info = get_account_guild_info(page)
            if not g_info.get("in_guild"):
                return False, f"Le compte principal '{main_name}' n'appartient à aucune guilde. Créez ou rejoignez d'abord une guilde sur {main_name}."

            target_guild_id = g_info["guild_id"]
            target_guild_name = g_info["guild_name"]
            existing_member_ids = get_guild_member_ids(page)

            notify(f"🏰 Guilde détectée : « {target_guild_name} » ({g_info.get('member_count', 0)} membres).", "success")

            # Identifier les autres comptes à inviter
            other_accounts = [a for a in accounts if a["id"] != main_acc["id"]]

            for other in other_accounts:
                other_name = other.get("name", other["id"])
                user_id = resolve_user_id_for_username(page, other_name)
                
                if user_id and user_id in existing_member_ids:
                    notify(f"[{other_name}] ✅ Déjà membre de la guilde « {target_guild_name} ».", "info")
                    continue

                if not user_id:
                    # Résolution alternative via search
                    user_id = resolve_user_id_for_username(page, other_name)

                accounts_to_invite.append({
                    "account": other,
                    "name": other_name,
                    "user_id": user_id
                })

            if not accounts_to_invite:
                notify(f"✨ Tous les comptes ({len(accounts)}) sont déjà dans la guilde « {target_guild_name} » !", "success")
                return True, f"Tous les comptes sont déjà dans la guilde « {target_guild_name} » !"

            # Envoyer les invitations depuis le compte principal
            for item in accounts_to_invite:
                o_name = item["name"]
                u_id = item["user_id"]
                if not u_id:
                    notify(f"[{o_name}] ⚠️ Impossible d'obtenir l'user_id. On tentera de rejoindre directement.", "warning")
                    continue

                notify(f"[{main_name}] 💌 Envoi de l'invitation de guilde pour {o_name}...", "info")
                inv_res = invite_to_guild(page, u_id)
                if inv_res.get("ok"):
                    notify(f"[{main_name}] ✉️ Invitation envoyée avec succès à {o_name} !", "success")
                else:
                    err_msg = inv_res.get("error", "")
                    if "already" in err_msg.lower() or "déjà" in err_msg.lower():
                        notify(f"[{main_name}] ℹ️ {o_name} est déjà invité ou membre.", "info")
                    else:
                        notify(f"[{main_name}] ⚠️ Note invitation {o_name}: {err_msg}", "warning")
                human_delay(0.6, 1.2)

        finally:
            if ctx:
                ctx.close()
            engine.kill_browser_processes(main_acc["id"])

    # ── Étape 2 : Chaque compte invité rejoint la guilde ──
    joined_count = 0
    for item in accounts_to_invite:
        acc = item["account"]
        name = item["name"]
        pdir = engine.BASE_DIR / acc.get("profile_dir", f"profiles/{acc['id']}")
        exe = engine.get_browser_executable_for_account(acc["id"])

        notify(f"[{name}] 🚀 Connexion pour rejoindre « {target_guild_name} »...", "info")
        engine.kill_browser_processes(acc["id"])

        with sync_playwright() as p:
            ctx2 = None
            try:
                ctx2 = p.chromium.launch_persistent_context(
                    user_data_dir=str(pdir),
                    executable_path=exe,
                    headless=True,
                    viewport={"width": 1366, "height": 768},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                    args=engine.get_browser_launch_args(acc["id"])
                )
                apply_stealth(ctx2)
                page2 = enforce_single_page(ctx2)


                try:
                    page2.goto("https://www.wiki-masters.com/guild", wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    pass
                time.sleep(1.0)

                # Vérifier si déjà dans cette guilde
                curr_g = get_account_guild_info(page2)
                if curr_g.get("in_guild") and curr_g.get("guild_id") == target_guild_id:
                    notify(f"[{name}] ✅ Déjà bien membre de « {target_guild_name} » !", "success")
                    joined_count += 1
                    continue
                elif curr_g.get("in_guild"):
                    notify(f"[{name}] 🔄 Quitte l'ancienne guilde « {curr_g.get('guild_name')} »...", "info")
                    leave_guild(page2)
                    time.sleep(1.0)

                # Rejoindre la guilde cible
                notify(f"[{name}] 🏰 Acceptation et adhésion à « {target_guild_name} »...", "info")
                join_res = join_guild(page2, target_guild_id)
                if join_res.get("ok"):
                    notify(f"[{name}] 🎉 A rejoint avec succès la guilde « {target_guild_name} » !", "success")
                    joined_count += 1
                else:
                    # Essayer via navigation directe sur l'URL d'invitation
                    try:
                        page2.goto(f"https://www.wiki-masters.com/guild?invite={target_guild_id}", wait_until="networkidle", timeout=15000)
                        time.sleep(1.5)
                        retry_join = join_guild(page2, target_guild_id)
                        if retry_join.get("ok"):
                            notify(f"[{name}] 🎉 A rejoint avec succès la guilde « {target_guild_name} » !", "success")
                            joined_count += 1
                        else:
                            notify(f"[{name}] ⚠️ Réponse adhésion : {retry_join.get('error', join_res.get('error'))}", "warning")
                    except Exception as e:
                        notify(f"[{name}] ❌ Échec d'adhésion : {e}", "error")

            finally:
                if ctx2:
                    ctx2.close()
                engine.kill_browser_processes(acc["id"])

    notify(f"🏰 Synchronisation Guilde terminée : {joined_count}/{len(accounts_to_invite)} nouveaux compte(s) ont rejoint « {target_guild_name} ».", "success")
    return True, f"Tous les comptes font désormais partie de la guilde « {target_guild_name} » !"
