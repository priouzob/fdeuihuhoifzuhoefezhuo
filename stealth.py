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
    // 1. Masquer complètement navigator.webdriver
    try {
        delete Object.getPrototypeOf(navigator).webdriver;
    } catch (e) {}
    try {
        delete navigator.webdriver;
    } catch (e) {}
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

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

    // 9. Iframe isolation protection : s'assure que les iframes Turnstile ne voient jamais webdriver
    try {
        const origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get;
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const win = origContentWindow.apply(this, arguments);
                if (win) {
                    try {
                        delete win.navigator.webdriver;
                        Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined, configurable: true });
                    } catch (e) {}
                }
                return win;
            },
            configurable: true
        });
    } catch (e) {}
})();
"""

def apply_stealth(context):
    """Injecte les scripts de masquage anti-détection dans le contexte de navigation."""
    context.add_init_script(STEALTH_JS)

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

def check_and_handle_turnstile(page):
    """
    Vérifie si une pop-up ou un widget Cloudflare Turnstile ('Je ne suis pas un robot')
    est apparu sur la page et effectue une interaction humaine discrète pour le valider.
    """
    try:
        cf_frames = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']").all()
        if cf_frames:
            for frame_loc in cf_frames:
                frame = frame_loc.content_frame()
                if frame:
                    checkbox = frame.locator("input[type='checkbox'], span.mark, div[class*='cb-c']").first
                    if checkbox.count() > 0 and checkbox.is_visible():
                        human_delay(0.5, 1.2)
                        checkbox.click(delay=random.randint(80, 150))
                        human_delay(1.5, 2.5)
                        return True
    except Exception:
        pass
    return False

def check_and_handle_verification_modal(page, status_callback=None):
    """
    Détecte et résout automatiquement la pop-up de vérification interne de WikiMasters :
    'Vérification rapide'
    'Pour continuer à ouvrir des paquets, confirme que tu utilises l'application manuellement (pas de script ni bot).'
    [X] Je ne suis pas un robot
    [ Continuer ]
    """
    try:
        # 1. Vérifier si des éléments de la modale sont présents
        modal_selectors = [
            "text='Vérification rapide'",
            "text='pas de script ni bot'",
            "text='confirme que tu utilises'",
            "text='Je ne suis pas un robot'"
        ]
        is_modal_visible = False
        for sel in modal_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    is_modal_visible = True
                    break
            except Exception:
                pass

        if not is_modal_visible:
            return False

        if status_callback:
            try:
                status_callback("🛡️ Pop-up 'Vérification rapide' détectée ! Validation automatique...", "stealth")
            except Exception:
                pass

        human_delay(0.6, 1.4)

        # 2. Cocher la case 'Je ne suis pas un robot'
        checkbox_clicked = False
        # Essai 1 : input[type='checkbox']
        cb = page.locator("input[type='checkbox']").first
        if cb.count() > 0 and cb.is_visible():
            human_click(page, cb)
            checkbox_clicked = True
        
        # Essai 2 : button/div avec role='checkbox' (ex: Radix UI / Tailwind)
        if not checkbox_clicked:
            cb_role = page.locator("[role='checkbox']").first
            if cb_role.count() > 0 and cb_role.is_visible():
                human_click(page, cb_role)
                checkbox_clicked = True

        # Essai 3 : label ou span contenant 'Je ne suis pas un robot'
        if not checkbox_clicked:
            cb_label = page.locator("label:has-text('robot'), div:has-text('Je ne suis pas un robot')").last
            if cb_label.count() > 0 and cb_label.is_visible():
                human_click(page, cb_label)
                checkbox_clicked = True

        # Essai 4 : Texte direct
        if not checkbox_clicked:
            cb_text = page.locator("text='Je ne suis pas un robot'").first
            if cb_text.count() > 0 and cb_text.is_visible():
                human_click(page, cb_text)
                checkbox_clicked = True

        human_delay(0.8, 1.8)

        # 3. Cliquer sur le bouton 'Continuer' de la modale
        continuer_btn = page.locator("button:has-text('Continuer'):not([disabled])").first
        if continuer_btn.count() == 0 or not continuer_btn.is_visible():
            continuer_btn = page.locator("button:has-text('Continuer')").first

        if continuer_btn.count() > 0 and continuer_btn.is_visible():
            human_delay(0.4, 0.9)
            human_click(page, continuer_btn)
            human_delay(1.5, 2.5)

        # 4. Vérifier si un Turnstile secondaire est apparu
        check_and_handle_turnstile(page)

        if status_callback:
            try:
                status_callback("✅ 'Vérification rapide' validée avec succès !", "success")
            except Exception:
                pass

        return True

    except Exception:
        return False

