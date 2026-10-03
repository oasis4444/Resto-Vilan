# Restaurant Manager — Phase 1 à 5 (version française)

Application Flask (Python) mifanaraka amin'ny **Phase 1 à 5** ao amin'ny Cahier des Charges.
Interface 100% frantsay, design "premium" (loko/police manokana, logo).

## Fonctionnalité efa mandeha amin'ity version ity

**Phase 1 — Fototra**
- Login + logout, fanovana mot de passe TERY (obligatoire), email + question secrète
- Fetra fanandramana login (5 fois → blocage 15 minitra)
- Role 5 (Super-Admin, Admin, Gérant Stock, Serveur, Comptable), interface manokana isaky ny iray
- Menu + Recette + Stock ingredient, alerte "stock bas"
- Gestion utilisateur, reset mot de passe (Super-Admin)
- Mode sombre/clair, responsive téléphone/ordinateur

**Phase 2 — Vente**
- Interface Commande/Caisse (Serveur), stock mihena otomatika araka ny recette
- Ticket de caisse imprimable, historika ny vente

**Phase 3 — Achat & Rapports**
- Achat ingredient → stock miakatra otomatika
- Source de financement + solde otomatika
- Rapport/Dashboard: CA, marge isaky ny menu, top menu, alerte stock

**Phase 4 — Import/Export Excel & Sauvegarde**
- Modèle .xlsx (Ingredient/Stock, Menu+Recette, Achat) hampidinina, feno hors-ligne, "importer" indray
- Validation ("liste d'erreurs") alohan'ny fampidirana tanteraka ny données
- Sauvegarde manuelle (bokotra), Restauration avy amin'ny sauvegarde any amin'ny serveur na fichier
- **Réinitialisation à l'état d'origine** (Super-Admin, confirmation, sauvegarde "forcé" mialoha)

**Phase 5 — Design "premium" & Facture**
- Loko sy police (Fraunces/Manrope) miavaka, tsy Bootstrap "par défaut" intsony
- Fampidirana logo, anarana, adiresy, NIF/STAT any amin'ny "Paramètres"
- Facture officielle (miavaka amin'ny ticket tsotra, misy NIF/STAT/cachet)
- PWA (manifest.json + icône) — "installable" eo amin'ny écran d'accueil an'ny téléphone

## Izay mbola tsy vita

**Synchronisation offline tanteraka** (fampiasana rehefa tapaka ny internet, miaraka amin'ny
fitantanana "conflit" matotra) dia mbola tsy natao — mila fotoana sy fitsapana lalina kokoa
ho an'ny "production" tena izy. Manoratra ahy raha vonona hanohy amin'io ianao.

---

## 1. Fampiasana eto an-toerana (test alohan'ny hametraka azy online)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Mandeha amin'ny `http://127.0.0.1:5000` ny application. Compte voalohany:

- **nom d'utilisateur:** `super-adm`
- **mot de passe:** `Ampandrana`

Hangatahina hanova io mot de passe io avy hatrany ianao (normal, araka ny cahier des charges).

---

## 2. Alefaso any amin'ny GitHub

1. Mamorona compte GitHub (github.com) raha mbola tsy manana.
2. Mamorona "repository" vaovao, ohatra `restaurant-manager` (public na private, samy azo atao).
3. Ao amin'ity dossier ity (izay nalaina avy amin'ny Claude), atao:

```bash
git init
git add .
git commit -m "Phase 1: login, roles, menu, stock"
git branch -M main
git remote add origin https://github.com/<anaranao>/restaurant-manager.git
git push -u origin main
```

*(Raha tsy mahay `git` amin'ny console ianao, azo atao ihany koa ny "drag & drop" ireo fichier
mivantana ao amin'ny pejy github.com/<anaranao>/restaurant-manager amin'ny alalan'ny "Add file →
Upload files".)*

---

## 3. Alefaso any amin'ny PythonAnywhere

1. Mamorona compte pythonanywhere.com (\"Beginner/Free\" maimaimpoana).
2. Misokatra **Consoles → Bash**, dia:

   ```bash
   git clone https://github.com/<anaranao>/restaurant-manager.git
   cd restaurant-manager
   pip install --user -r requirements.txt
   ```

3. Mankany amin'ny tab **Web**, dia:
   - "Add a new web app" → "Manual configuration" → misafidy ny version Python (3.10+)
   - Ao amin'ny fizarana **Code**:
     - "Source code": `/home/<anaranao>/restaurant-manager`
     - "Working directory": `/home/<anaranao>/restaurant-manager`
   - Ao amin'ny fizarana **WSGI configuration file**, soloy ny votoaty amin'izao (araka ny
     anaranao mihitsy):

     ```python
     import sys
     path = '/home/<anaranao>/restaurant-manager'
     if path not in sys.path:
         sys.path.insert(0, path)

     from app import app as application
     ```

4. **Reload** ny Web app (bokotra maitso lehibe eo ambony) → mandeha amin'ny
   `https://<anaranao>.pythonanywhere.com` ny application!

### Fanavaozana manaraka (rehefa misy fanovana kaody)

```bash
# Ao amin'ny console PythonAnywhere:
cd restaurant-manager
git pull
```

...dia tsindrio ny bokotra **Reload** ao amin'ny tab Web.

---

## 4. Variable d'environnement voatolotra (raha efa amin'ny production)

Ao amin'ny fizarana **Files → WSGI configuration file** (na fichier `.env` raha mampiasa
`python-dotenv`), azo apetraka ireto mba tsy ho eo amin'ny kaody mivantana ny zava-miafina:

```python
import os
os.environ['SECRET_KEY'] = 'asio teny miafina lava sy sarotra eto'
os.environ['SUPER_ADMIN_USERNAME'] = 'super-adm'
os.environ['SUPER_ADMIN_PASSWORD'] = 'ovay ity mot de passe ity'
```

---

## 5. Firafitry ny dossier (structure)

```
restaurant-manager/
├── app.py              # factory Flask, création DB, compte Super-Admin
├── config.py           # paramètre (DB, clé secrète, super-admin par défaut)
├── extensions.py       # instances db / login_manager
├── models.py           # User, Ingredient, MenuItem, RecipeItem
├── auth.py             # login, logout, changement mdp, mdp oublié
├── decorators.py       # contrôle d'accès par rôle
├── routes.py           # dashboard, menu, stock, utilisateurs
├── seed.py             # création automatique du compte Super-Admin
├── requirements.txt
├── templates/          # pages HTML (Jinja2 + Bootstrap 5)
└── static/css/         # style.css (dark/light mode)
```

---

## Version 2 (30/09/2026) — Fanitsiana nangatahan'ny tompon'ny restaurant

- Logo V'lany Gasy (login, sidebar, accueil, ticket, facture) — `static/images/restaurant-logo.png`
- Pejy **Accueil** tsy misy chiffre aorian'ny login ; ny chiffre dia ao amin'ny **Tableau de bord** ihany (`/dashboard`)
- **Dépenses fixes** (lisitra isam-bolana, Admin ihany no manova, bokotra « Payer ») sy **Dépenses variables** mifanila ; « Vue globale » = ilay pejy taloha
- Ticket : hafatra fisaorana **iray** (azo ovaina ao amin'ny Paramètres), taratasy 58/80 mm, halavana araka ny commande
- Fiche menu azo imprimena, Carte du restaurant, lisitra ingrédients (fiche d'inventaire)
- **Code ingrédient** (Poulet → PLT, Yaourt → YRT...) : recherche, recette, Excel
- Nom d'utilisateur azo ovaina ; anaran'ny rôle azo ovaina (Paramètres)
- Excel : .xlsx/.csv, colonne fantarina amin'ny anarany, export → import tsy misy doublon, export Achats/Dépenses/Ventes, import Dépenses
- Ora eto Madagasikara (UTC+3) amin'ny fampisehoana rehetra

**Fametrahana :** aorian'ny `git pull`, alefaso indray mandeha : `python3 mise_a_jour_v2.py` (manao copie de sécurité ny base aloha), avy eo « Reload ».
Ny colonne vaovao dia ampiana ho azy isaky ny manomboka ny logiciel (`migrations.py`).

## Version 3 (30/09/2026)
- Menu : bokotra **Modifier** (anarana, prix, catégorie, recette, sary), **fafana sary** (voafafa tanteraka amin'ny serveur), **fafana menu** (tsy mbola nivarotra → voafafa tanteraka ; efa nivarotra → miala amin'ny carte fa mijanona ao amin'ny historique, azo averina)
- Ingrédient : azo fafana raha tsy mbola nampiasaina (achat, recette, journal)
- Paramètres : « Imprimer automatiquement le ticket après chaque vente »
- Fanamboarana : vente misy menu tsy disponible intsony tsy mahatonga erreur intsony
Tsy mila script vaovao : ampiana ho azy ny colonne rehefa manao « Reload ».

## Version 4 (01/10/2026)
- Recette : toerana azo anoratana (anarana na code) misy lisitra mivoaka, ary « + Créer » hamoronana ingrédient vaovao avy hatrany (unité azo safidiana)
- Fanatsarana kely : logo Accueil tsy voatapaka intsony, soratra Tableau de bord tsy mifanindry amin'ny icône
- Torolàlana PDF ho an'ny tompony : Guide_VlanyGasy_Restaurant_Manager.pdf
