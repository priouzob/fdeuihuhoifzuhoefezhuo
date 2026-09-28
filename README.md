# 🎴 WikiMasters Auto-Claimer (Chrome, Brave & Opera)

Programme d'automatisation pour récupérer automatiquement le **paquet de cartes gratuit toutes les 10 minutes** sur **[WikiMasters](https://wiki-masters.com)** sur vos 3 navigateurs (**Google Chrome**, **Brave** et **Opera**).

---

## 🚀 Deux modes d'utilisation

1. **📱 L'Interface Dashboard PySide6 (Recommandé pour second écran)** :
   * Une mini-fenêtre sombre et moderne à placer sur votre second écran.
   * Affiche les **3 comptes** côte à côte (**Google Chrome**, **Brave**, **Opera**).
   * **Compte à rebours en direct** défilant seconde par seconde pour chaque compte.
   * **Aperçu miniature du dernier tirage** : vous pouvez cliquer dessus pour afficher la capture en grand et voir toutes vos cartes.
   * **Bouton de connexion intégré** : un clic sur "🔑 Configurer" ouvre le navigateur pour vous connecter, et la fenêtre se referme automatiquement dès que vous êtes connecté !
   * Tout le moteur d'ouverture tourne **à 100% en arrière-plan** avec toutes les protections anti-détection.
   * Pour la lancer : double-cliquez sur [**`lancer_interface.bat`**](file:///C:/Users/sacha/.gemini/antigravity/scratch/wikimasters-autoclaim/lancer_interface.bat).

2. **👻 Mode Service 100% Invisible (sans aucune fenêtre)** :
   * Si vous ne voulez même pas d'interface ouverte.
   * Pour le lancer : double-cliquez sur [**`lancer_arriere_plan.vbs`**](file:///C:/Users/sacha/.gemini/antigravity/scratch/wikimasters-autoclaim/lancer_arriere_plan.vbs).
   * Pour vérifier : [**`verifier_statut.bat`**](file:///C:/Users/sacha/.gemini/antigravity/scratch/wikimasters-autoclaim/verifier_statut.bat).
   * Pour l'arrêter : [**`arreter_bot.bat`**](file:///C:/Users/sacha/.gemini/antigravity/scratch/wikimasters-autoclaim/arreter_bot.bat).


---

## 📦 Méthode 1 : Programme autonome Python (Recommandé)

### 1. Prérequis déjà configurés
- Les chemins de vos 3 navigateurs sont automatiquement détectés :
  - **Chrome** : `C:\Program Files\Google\Chrome\Application\chrome.exe`
  - **Brave** : `C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe`
  - **Opera** : `D:\Users\sacha\AppData\Local\Programs\Opera\opera.exe`
- Les profils de session sont isolés dans `profiles/` pour éviter tout conflit de verrouillage avec vos sessions quotidiennes.

### 2. Étape 1 : Connexion initiale à vos comptes (à faire 1 seule fois)
1. Double-cliquez sur **`configurer_comptes.bat`** (ou lancez `python bot.py --setup`).
2. Le programme ouvrira successivement une fenêtre pour Chrome, Brave et Opera :
   - Connectez votre compte respectif sur la page de WikiMasters.
   - Une fois connecté, revenez dans le terminal et appuyez sur **Entrée**.
3. Vos sessions restent enregistrées de manière permanente ! Vous n'aurez plus jamais besoin de vous reconnecter.

### 3. Étape 2 : Lancer la récupération automatique
- **En arrière-plan (invisible)** : Double-cliquez sur **`lancer_bot.bat`** (ou `python bot.py`).
- **En mode visible** (pour observer l'ouverture des paquets) : Double-cliquez sur **`lancer_bot_visible.bat`** (ou `python bot.py --visible`).

Le programme :
1. Se rend sur `https://wiki-masters.com/pulls` pour chaque navigateur.
2. Détecte le décompte ou clique immédiatement sur le bouton d'ouverture si disponible.
3. Révèle/valide automatiquement les cartes tirées.
4. Prend une capture d'écran dans le dossier `screenshots/` pour voir vos cartes.
5. Se met en veille pendant 10 minutes (avec un décalage aléatoire de quelques secondes pour un comportement naturel et indétectable).

---

## 🌐 Méthode 2 : Userscript Tampermonkey (Alternative par extension)

Si vous gardez déjà vos navigateurs Chrome, Brave et Opera ouverts :

1. Installez l'extension **[Tampermonkey](https://www.tampermonkey.net/)** sur chacun de vos 3 navigateurs.
2. Ouvrez le fichier **`wikimasters_autoclaim.user.js`** situé dans ce dossier.
3. Copiez l'intégralité du code et créez un "Nouveau script" dans Tampermonkey, puis sauvegardez (**Ctrl + S**).
4. Rendez-vous sur `https://wiki-masters.com/pulls` sur chacun de vos navigateurs :
   - Un encadré bleu et vert **WM Auto-Claim** apparaît en haut à droite.
   - Il surveille le compte à rebours et clique sur le paquet dès qu'il est prêt.

---

## ⚙️ Personnalisation (`config.json`)

Vous pouvez modifier le fichier `config.json` pour ajuster :
- `check_interval_seconds` : Temps d'attente (600 secondes = 10 minutes par défaut).
- `random_jitter_seconds` : Variation aléatoire (±15 secondes pour éviter d'être repéré comme bot).
- `browsers` : Activer ou désactiver l'un des trois navigateurs (`"enabled": true / false`).
