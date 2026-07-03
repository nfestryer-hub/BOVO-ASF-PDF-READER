# Bovo ASF Manager — Compilation en exécutable

## Structure après compilation

Après compilation avec `build_exe.bat` (Windows) ou `build_exe.sh` (Linux/macOS),
le dossier `dist/BovoASF/` contient tout ce qu'il faut :

```
dist/BovoASF/
├── BovoASF.exe            ← Double-clic pour lancer l'app (mode fenêtre, pas de terminal)
├── assets/                ← 🎨 PERSONNALISATION SANS RECOMPILER
│   ├── app.ico            ←    L'icône Windows (barre des tâches, raccourci)
│   ├── logo.png           ←    Le logo affiché dans le splash / login / accueil
│   └── icons/             ←    Icônes des menus (calendar.png, home.png, etc.)
├── database/              ← (créé au 1er lancement) SQLite locale
├── logs/                  ← (créé au 1er lancement) journal d'activité
└── *.dll, *.pyd           ← Dépendances Python bundlées (ne pas toucher)
```

## Comment changer l'icône ou le logo ?

### Sans recompiler (recommandé)

1. Prépare tes fichiers :
   * `app.ico` — **icône Windows** (format `.ico` multi-tailles 16/32/48/64/128/256)
   * `logo.png` — **logo BOVO** (PNG carré recommandé, min 512×512)

2. Remplace directement les deux fichiers dans `dist/BovoASF/assets/`.

3. Ferme et relance `BovoASF.exe` — la nouvelle icône/logo apparaît immédiatement.

> **Astuce** : `resource_path()` dans `app/utils.py` cherche en priorité les
> fichiers **à côté de l'exécutable**. Il retombe sur ceux embarqués
> dans le binaire seulement si les tiens sont introuvables.

### En recompilant (pour figer la nouvelle version)

1. Remplace `bovo/assets/app.ico` et `bovo/assets/logo.png` dans le code source.
2. Relance `build_exe.bat` — la nouvelle version sera embarquée par défaut.

## Créer un fichier `.ico` valide

Windows attend un `.ico` avec plusieurs tailles. Le plus simple :

```python
from PIL import Image
img = Image.open("mon_logo.png").convert("RGBA")
img.save("app.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
```

Ou en ligne : [redketchup.io/icon-converter](https://redketchup.io/icon-converter)
(dépose ton PNG → télécharge le .ico multi-tailles).

## Prérequis pour compiler

* Windows 10/11 ou Linux/macOS
* Python 3.11 ou plus récent (téléchargeable sur [python.org](https://python.org))
* Coché « Add Python to PATH » lors de l'installation

## Distribution à un poste terrain

1. Compile sur **le poste qui reçoit** (ou une VM identique) — l'exe est
   spécifique au système d'exploitation. Un `.exe` fait sur Windows 11
   fonctionne sur Windows 10 aussi.
2. Zippe **tout le dossier `dist/BovoASF/`** (∼260 Mo décompressé).
3. Envoie le zip. L'utilisateur décompresse où il veut (Bureau, Documents…)
   et double-clique `BovoASF.exe`. **Aucune installation, aucun admin requis.**

## Signature Windows (optionnel — production)

Pour éviter le SmartScreen « Éditeur inconnu » :

```
signtool sign /f MyCert.pfx /p PASSWORD /tr http://timestamp.digicert.com /td sha256 /fd sha256 BovoASF.exe
```

Nécessite un certificat de code (Code Signing Certificate) — Sectigo, DigiCert,
∼80–200 €/an.

## Dépannage

| Symptôme | Solution |
|---|---|
| « Impossible de démarrer, DLL manquante » | Vérifier que le dossier `_internal/` a été copié avec l'exe (contient les DLL Python). Ne jamais séparer `BovoASF.exe` de `_internal/`. |
| Icône par défaut Windows au lieu de la nôtre | Explorer Windows garde en cache les icônes. Fais `Shift+F5` sur le bureau ou renomme temporairement l'exe. |
| Antivirus bloque l'exe | Faux positif classique de PyInstaller. Signer l'exe (voir ci-dessus) ou ajouter une exception dans l'AV. |
| L'exe plante au démarrage sans message | Lance-le en mode console : édite `bovo.spec`, mets `console=True`, recompile. Tu verras le traceback complet. |
