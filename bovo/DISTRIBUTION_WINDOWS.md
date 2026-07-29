# Distribution Bovo ASF Manager (Windows)

Guide pour compiler et distribuer l'application sur un partage réseau.

## 🎯 Modèle de déploiement

- **Toi** (admin) : compiles `Bovo.exe` sur ton PC dev, copies sur `\\SERVEUR\Partage\Bovo\`.
- **Tes utilisateurs** : lancent `\\SERVEUR\Partage\Bovo\Bovo.exe` directement, ou créent un raccourci sur leur bureau.
- **Mises à jour** : tu remplaces le `.exe` sur le partage — les utilisateurs récupèrent la nouvelle version au prochain lancement.

Aucun Python ni dépendance à installer sur les postes utilisateurs.

## 🔧 Compilation

### Prérequis (ton PC de build uniquement)

- **Windows** 10 ou 11
- **Python 3.11+** — installe depuis <https://www.python.org/downloads/>
  - À l'installation, coche **"Add Python to PATH"**
- (Optionnel) **UPX** pour compresser l'exe : <https://upx.github.io/> — placer `upx.exe` dans le PATH

### Build

```powershell
cd C:\chemin\vers\bovo
.\build-windows.ps1 -Clean -InstallDeps
```

Après quelques minutes :

```
✅ Build réussi !
   Exécutable : C:\...\bovo\dist\Bovo.exe
   Taille     : ~55 Mo (compressé UPX) ou ~90 Mo (sans UPX)
```

### Options du script

| Option | Effet |
|---|---|
| `-Clean` | Supprime `build\` et `dist\` avant de rebuild |
| `-InstallDeps` | Force la (ré)installation de pip + pyinstaller |
| _(rien)_ | Build incrémental rapide |

## 📦 Distribution

```powershell
Copy-Item .\dist\Bovo.exe '\\SERVEUR\Partage\Bovo\Bovo.exe' -Force
```

C'est tout ! Tes utilisateurs auront la nouvelle version au prochain lancement.

## 📁 Où sont stockées les données utilisateur ?

**Pas** à côté de l'exe (partage en lecture seule). Elles sont stockées **par utilisateur** dans :

```
%APPDATA%\Bovo\
├── database\bovo.db          ← paramètres + journal + « Se souvenir de moi »
├── logs\bovo.log             ← logs applicatifs
└── exports\                  ← PDF/Excel générés localement
```

Chaque utilisateur a sa propre config, indépendante des autres, même sur un poste partagé.

## 🚦 Configuration serveur (première utilisation)

Au tout premier lancement, l'app demande l'URL du backend FastAPI :
- Format : `http://serveur-bovo.local:8000` (ou l'IP du serveur)
- Cette URL est mémorisée dans `%APPDATA%\Bovo\` — plus jamais à ressaisir.

## 🖼️ Icône personnalisée (optionnel)

Pour avoir une icône Bovo à la place de l'icône Python générique :

1. Crée ou récupère un fichier `.ico` (256×256 idéalement)
2. Place-le en `assets/icon.ico`
3. Relance `build-windows.ps1`

## 🔒 Anti-virus / SmartScreen

Comme `Bovo.exe` n'est pas signé avec un certificat commercial :
- Windows SmartScreen peut afficher un avertissement au premier lancement
  → l'utilisateur clique **"Informations complémentaires" → "Exécuter quand même"**
- Certains antivirus peuvent le mettre en quarantaine
  → ajoute une exception pour le chemin du partage

**Pour éviter tout ça** : signer l'exe avec un certificat de signature de code (~200 €/an, ex : SSL.com, DigiCert). Non obligatoire.

## ❓ Dépannage

### « Windows a protégé votre ordinateur »
Normal la première fois. Cliquer sur « Informations complémentaires » puis « Exécuter quand même ».

### L'exe met du temps à démarrer
Normal en mode `--onefile` (5-10 s au premier lancement) : Windows décompresse l'exe en mémoire. Les lancements suivants sont plus rapides (cache disque).

### « Impossible d'accéder au serveur »
Vérifie que le backend FastAPI est bien démarré et que l'URL configurée est joignable depuis le poste utilisateur (`ping serveur-bovo.local`).

### Une DLL manque
Le PC de build utilise probablement une DLL système absente sur les postes utilisateurs. Solution : ajouter la DLL manquante à la section `binaries` de `bovo.spec` OU installer le Redistributable Visual C++ sur les postes cibles.
