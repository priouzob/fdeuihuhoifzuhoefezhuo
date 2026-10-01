"""
Module Anti-Détection / Stealth Ultra-Avancé pour WikiMasters Auto-Claimer.
Empêche les systèmes anti-bot (Cloudflare Turnstile, Supabase, WAF, canvas/WebGL fingerprinting)
de détecter l'automatisation Playwright/Chromium.
Comprend le déplacement de souris à courbes de Bézier et la gestion furtive de Turnstile.
"""

import time
import math
import random

STEALTH_JS = """
(() => {
    // 1. Masquer proprement navigator.webdriver
    try {
        if ('webdriver' in navigator) {
            delete Object.getPrototypeOf(navigator).webdriver;
        }
    } catch (e) {}
    try {
        delete navigator.webdriver;
    } catch (e) {}

    // 2. Supprimer les variables injectées par Chromium CDP / Selenium
    const cleanupAutomationKeys = () => {
        const keys = [
            'cdc_adoQpoasnfa76pfcZLmcfl_Array',
            'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
            'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
            '$cdc_asdjflasutopfhvcZLmcfl_',
            '__driver_evaluate',
            '__webdriver_evaluate',
            '__selenium_evaluate',
            '__fxdriver_evaluate',
            '__driver_unwrapped',
            '__webdriver_unwrapped',
            '__selenium_unwrapped',
            '__fxdriver_unwrapped'
        ];
        for (const k of keys) {
            try { delete window[k]; } catch (e) {}
            try { delete document[k]; } catch (e) {}
        }
    };
    cleanupAutomationKeys();

    // 3. Simuler window.chrome authentique
    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
            PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
            RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
        },
        loadTimes: function() {},
        csi: function() {}
    };

    // 4. Simuler les plugins réels de Chromium
    const fakePlugins = [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
    ];
    Object.defineProperty(navigator, 'plugins', {
        get: () => fakePlugins,
        configurable: true
    });

    // 5. Langues naturelles françaises
    Object.defineProperty(navigator, 'languages', {
        get: () => ['fr-FR', 'fr', 'en-US', 'en'],
        configurable: true
    });

    // 6. Matériel cohérent
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
        configurable: true
    });

    // 7. Simuler permissions.query standard
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            origQuery(parameters)
    );

    // 8. Masquer le renderer WebGL SwiftShader / llvmpipe
    try {
        const getParameterProto = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (NVIDIA)';
            if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            return getParameterProto.apply(this, arguments);
        };
        if (typeof WebGL2RenderingContext !== 'undefined') {
            const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameterProto2.apply(this, arguments);
            };
        }
    } catch (e) {}

    // 9. Interdire strictement l'ouverture de multiples onglets (1 seule page max par instance)
    try {
        window.open = function(url) {
            if (url) {
                window.location.href = url;
            }
            return window;
        };
        document.addEventListener('click', function(e) {
            const a = e.target && e.target.closest ? e.target.closest('a') : null;
            if (a && a.target === '_blank') {
                a.target = '_self';
            }
        }, true);
    } catch (e) {}
})();
"""

def enforce_single_page(context):
    """
    Garantit qu'il n'y a STRICTEMENT qu'une seule page (onglet) maximum active par instance.
    1. Ferme tous les onglets parasites surnuméraires restaurés par Chromium.
    2. Bloque et ferme immédiatement toute nouvelle tentative d'ouverture d'onglet ou popup.
    """
    try:
        pages = context.pages
        while len(pages) > 1:
            try:
                pages[-1].close()
            except Exception:
                pass
            pages = context.pages

        page = pages[0] if pages else context.new_page()

        def _block_extra_pages(new_page):
            try:
                time.sleep(0.05)
                new_page.close()
            except Exception:
                pass

        context.on("page", _block_extra_pages)
        return page
    except Exception:
        return context.pages[0] if context.pages else context.new_page()

def apply_stealth(context):
    """Injecte les scripts de masquage anti-détection dans le contexte de navigation."""
    try:
        context.add_init_script(STEALTH_JS)
    except Exception:
        pass
    try:
        enforce_single_page(context)
    except Exception:
        pass


def human_delay(min_sec=0.8, max_sec=2.2):
    """Attend un délai aléatoire simulant un temps de réaction humain naturel."""
    time.sleep(random.uniform(min_sec, max_sec))

def _bezier_point(p0, p1, p2, p3, t):
    """Calcule un point sur une courbe de Bézier cubique pour un mouvement de souris fluide."""
    u = 1 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t
    return uuu * p0 + 3 * uu * t * p1 + 3 * u * tt * p2 + ttt * p3

def human_click(page, locator):
    """
    Effectue un clic naturel simulant la main d'un être humain :
    1. Calcule la position de l'élément avec un léger décalage aléatoire non mécanique
    2. Déplace la souris selon une courbe de Bézier avec accélération et décélération
    3. Attend un micro-délai humain avant de presser puis relâcher le bouton
    """
    try:
        box = locator.bounding_box()
        if not box:
            locator.click(delay=random.randint(50, 120))
            return

        # Coordonnées cibles au sein de l'élément avec variation naturelle
        target_x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
        target_y = box["y"] + box["height"] * random.uniform(0.35, 0.65)

        # Point de départ approximatif de la souris
        start_x = random.uniform(100, 400)
        start_y = random.uniform(100, 300)

        # Points de contrôle pour courber la trajectoire comme un poignet humain
        ctrl1_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-20, 20)
        ctrl1_y = start_y + (target_y - start_y) * random.uniform(0.1, 0.3) + random.uniform(-20, 20)
        ctrl2_x = start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-15, 15)
        ctrl2_y = start_y + (target_y - start_y) * random.uniform(0.7, 0.9) + random.uniform(-15, 15)

        steps = random.randint(10, 16)
        for i in range(steps):
            t = (i + 1) / steps
            # Forme sigmoidale pour accélérer puis ralentir à l'approche de la cible
            t_eased = math.sin(t * math.pi / 2)
            px = _bezier_point(start_x, ctrl1_x, ctrl2_x, target_x, t_eased)
            py = _bezier_point(start_y, ctrl1_y, ctrl2_y, target_y, t_eased)
            page.mouse.move(px, py)
            time.sleep(random.uniform(0.008, 0.018))

        time.sleep(random.uniform(0.08, 0.22))
        page.mouse.down()
        time.sleep(random.uniform(0.06, 0.12))
        page.mouse.up()

    except Exception:
        # En cas d'exception, clic standard sans bloquer
        try:
            locator.click(delay=random.randint(60, 150))
        except Exception:
            pass

def is_turnstile_solved(page):
    """Vérifie si le défi Cloudflare Turnstile a été validé avec succès."""
    try:
        res = page.evaluate("""() => {
            // 1. Vérifier si un champ de réponse Turnstile contient un token valide
            const inputs = document.querySelectorAll('input[name*="cf-turnstile-response"], input[name*="cf_turnstile_response"]');
            for (const inp of inputs) {
                if (inp.value && inp.value.length > 10) return true;
            }
            // 2. Vérifier si aucun iframe Turnstile n'est présent
            const iframes = Array.from(document.querySelectorAll('iframe[src*="cloudflare"], iframe[src*="turnstile"]'));
            if (iframes.length === 0) return true;
            // 3. Vérifier la classe de succès dans le conteneur Turnstile
            const success = document.querySelector('.cf-turnstile.success, div[class*="success"]');
            if (success) return true;
            return false;
        }""")
        return bool(res)
    except Exception:
        return False

def is_bot_challenge_active(page):
    """
    Vérifie si une pop-up de vérification ou un défi Cloudflare Turnstile non résolu
    bloque actuellement l'écran ou l'accès aux boutons de tirage.
    """
    try:
        # 1. Vérifier les textes caractéristiques des pop-ups de vérification
        modal_texts = [
            "text='Vérification rapide'",
            "text='Vérification de sécurité'",
            "text='Vérification requise'",
            "text='Vérification anti-bot'",
            "text='Vérification'",
            "text='pas de script ni bot'",
            "text='confirme que tu utilises'",
            "text='Je ne suis pas un robot'",
            "text='Prouvez que vous êtes un humain'",
            "text='Vérifier que vous êtes un humain'",
            "text='Confirmation requise'",
        ]
        for sel in modal_texts:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except Exception:
                pass

        # 2. Vérifier si une modale ou dialogue contient un Turnstile ou un avertissement bot
        dialog_selectors = [
            "[role='dialog']:has(iframe[src*='challenges.cloudflare.com'])",
            "[role='dialog']:has(iframe[src*='turnstile'])",
            "[role='dialog']:has(div.cf-turnstile)",
            "[role='dialog']:has-text('robot')",
            "[role='dialog']:has-text('bot')",
            "[role='dialog']:has-text('Vérification')",
            "div[class*='modal']:has(iframe[src*='challenges.cloudflare.com'])",
            "div[class*='modal']:has(div.cf-turnstile)",
            "div[class*='modal']:has-text('robot')",
            "div[class*='modal']:has-text('Vérification')",
        ]
        for sel in dialog_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except Exception:
                pass

        # 3. Widget Cloudflare Turnstile visible et non résolu
        cf_frames = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], div.cf-turnstile")
        if cf_frames.count() > 0:
            if not is_turnstile_solved(page):
                first_cf = cf_frames.first
                if first_cf.is_visible():
                    return True
    except Exception:
        pass
    return False

def check_and_handle_turnstile(page):
    """
    Vérifie si un widget Cloudflare Turnstile ('Je ne suis pas un robot') est présent
    et effectue une interaction humaine discrète pour le valider.
    Retourne True si le défi est résolu.
    """
    try:
        cf_frames = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], iframe[title*='Cloudflare'], iframe[title*='Turnstile'], div.cf-turnstile iframe").all()
        if not cf_frames:
            return False

        for frame_loc in cf_frames:
            if not frame_loc.is_visible():
                continue

            frame = frame_loc.content_frame()
            clicked = False

            if frame:
                # 1. Tenter de cliquer sur les sélecteurs internes connus de Turnstile
                for target_sel in [
                    "label.ctp-checkbox-label",
                    "div.ctp-checkbox-container",
                    "span.mark",
                    "div[class*='cb-c']",
                    "div#checkbox",
                    "input[type='checkbox']",
                    "#challenge-stage",
                    "body"
                ]:
                    try:
                        target = frame.locator(target_sel).first
                        if target.count() > 0:
                            human_delay(0.3, 0.7)
                            target.click(force=True, delay=random.randint(60, 120))
                            clicked = True
                            break
                    except Exception:
                        pass

            # 2. Si le frame est inaccessible ou l'élément masqué, cliquer sur l'iframe aux coordonnées de la checkbox
            if not clicked:
                try:
                    human_delay(0.3, 0.7)
                    # La case à cocher Turnstile se situe invariablement à x=30, y=30
                    frame_loc.click(position={"x": 30, "y": 30}, delay=random.randint(70, 140))
                    clicked = True
                except Exception:
                    pass

            if clicked:
                human_delay(1.5, 2.5)
                if is_turnstile_solved(page):
                    return True

        # Vérification finale après délai de validation Cloudflare
        time.sleep(1.0)
        return is_turnstile_solved(page)

    except Exception:
        pass
    return False

def check_and_handle_verification_modal(page, status_callback=None):
    """
    Détecte et résout automatiquement toute pop-up de vérification interne de WikiMasters
    (Vérification rapide, case 'Je ne suis pas un robot', Turnstile interne, bouton Continuer).
    """
    try:
        if not is_bot_challenge_active(page):
            return False

        safe_notify_cb = status_callback if callable(status_callback) else None
        if safe_notify_cb:
            try:
                safe_notify_cb("🛡️ Pop-up de vérification anti-bot détectée ! Validation automatique...", "stealth")
            except Exception:
                pass

        human_delay(0.5, 1.0)

        # 1. Si un widget Cloudflare Turnstile est présent dans la modale, tenter de le résoudre d'abord
        check_and_handle_turnstile(page)

        # 2. Cocher la case 'Je ne suis pas un robot' (supporte Radix UI, Tailwind, sr-only, custom svg)
        checkbox_clicked = False
        cb_selectors = [
            "button[role='checkbox']",
            "[role='checkbox']",
            "label:has-text('robot')",
            "label:has-text('humain')",
            "label:has-text('bot')",
            "div:has-text('Je ne suis pas un robot')",
            "span:has-text('Je ne suis pas un robot')",
            "input[type='checkbox']",
        ]
        for cb_sel in cb_selectors:
            try:
                cb_loc = page.locator(cb_sel).first
                if cb_loc.count() > 0:
                    if cb_loc.is_visible():
                        human_click(page, cb_loc)
                        checkbox_clicked = True
                        break
                    else:
                        cb_loc.click(force=True)
                        checkbox_clicked = True
                        break
            except Exception:
                pass

        # 3. Fallback Javascript pour cocher la case si les locators Playwright ont échoué
        if not checkbox_clicked:
            try:
                clicked_js = page.evaluate("""() => {
                    const cb = document.querySelector('button[role="checkbox"], input[type="checkbox"]');
                    if (cb) { cb.click(); return true; }
                    const all = Array.from(document.querySelectorAll('label, div, span'));
                    const robotEl = all.find(el => (el.innerText || '').toLowerCase().includes('robot'));
                    if (robotEl) { robotEl.click(); return true; }
                    return false;
                }""")
                if clicked_js:
                    checkbox_clicked = True
            except Exception:
                pass

        human_delay(0.6, 1.2)

        # 4. Attendre et cliquer sur le bouton de confirmation / continuation de la modale
        btn_selectors = [
            "button:has-text('Continuer'):not([disabled])",
            "button:has-text('Valider'):not([disabled])",
            "button:has-text('Confirmer'):not([disabled])",
            "button:has-text('OK'):not([disabled])",
            "button:has-text('J\\'ai compris'):not([disabled])",
            "button:has-text('Continuer')",
            "button:has-text('Valider')",
            "button:has-text('Confirmer')",
        ]

        btn_to_click = None
        wait_start = time.time()
        while time.time() - wait_start < 3.5:
            for b_sel in btn_selectors:
                try:
                    b_loc = page.locator(b_sel).first
                    if b_loc.count() > 0 and b_loc.is_visible() and b_loc.is_enabled():
                        btn_to_click = b_loc
                        break
                except Exception:
                    pass
            if btn_to_click:
                break
            time.sleep(0.3)

        if btn_to_click:
            human_delay(0.3, 0.7)
            human_click(page, btn_to_click)
        else:
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const b = btns.find(el => {
                    const t = (el.innerText || '').toLowerCase();
                    return (t.includes('continuer') || t.includes('valider') || t.includes('confirmer') || t.includes('compris')) && !el.disabled;
                });
                if (b) b.click();
            }""")

        human_delay(1.2, 2.0)

        # 5. Vérifier si un Turnstile secondaire est apparu suite au clic
        check_and_handle_turnstile(page)

        # 6. Vérifier si la modale a disparu
        modal_dismissed = not is_bot_challenge_active(page)
        if modal_dismissed and safe_notify_cb:
            try:
                safe_notify_cb("✅ Pop-up de vérification validée avec succès !", "success")
            except Exception:
                pass

        return modal_dismissed

    except Exception:
        return False

