# Distribution Bovo ASF Manager (Windows MSI + Auto-Updates)

Guide complet pour distribuer et maintenir l'app via **MSI installer** avec
mises à jour automatiques poussées depuis un partage réseau.

## 🎯 Architecture retenue

```
┌───────────────────────────────────────────────────────────────┐
│  TA MACHINE DEV (Windows)                                      │
│  - .\build-msi.ps1 produit dist\Bovo-1.7.0-win64.msi          │
│  - .\publish-release.ps1 copie sur le partage + latest.json    │
└────────────────────────────┬──────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────────┐
│  PARTAGE RÉSEAU  \\SERVEUR\Partage\Bovo\                       │
│  - Bovo-Setup.msi          (le dernier installateur)           │
│  - latest.json             (métadonnées de version)            │
│  - archive\Bovo-1.6.0.msi  (historique optionnel)              │
└────────────────────────────┬──────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────────┐
│  POSTES UTILISATEURS                                           │
│  - Au démarrage → check latest.json                            │
│  - Nouvelle version détectée → bandeau "Installer maintenant"  │
│  - Clic → msiexec lance l'installation, app se ferme, MAJ OK   │
└───────────────────────────────────────────────────────────────┘
```

## 🔧 Compilation (une fois par version)

```powershell
cd C:\chemin\vers\bovo

# 1. Bumper la version dans app\version.py (SemVer : MAJOR.MINOR.PATCH)
notepad app\version.py

# 2. Build MSI
.\build-msi.ps1 -Clean -InstallDeps

# 3. Publier la release sur le partage réseau
.\publish-release.ps1 -Share "\\SERVEUR\Partage\Bovo"
```

Le MSI produit s'appelle `dist\Bovo-<version>-win64.msi` (ex : `Bovo-1.7.0-win64.msi`).

## 📦 Installation utilisateur (première fois)

L'utilisateur double-clique sur `\\SERVEUR\Partage\Bovo\Bovo-Setup.msi`.
Windows lance l'assistant standard : Suivant → Installer → Terminer.

Résultat :
- ✅ App installée dans `C:\Program Files\Bovo\`
- ✅ Raccourci menu Démarrer + icône bureau
- ✅ Entrée dans « Ajouter/Supprimer programmes » (désinstallation propre)
- ✅ Données personnelles dans `%APPDATA%\Bovo\` (jamais écrasées lors des MAJ)

**Configuration une fois** dans l'app (Paramètres) :
1. URL du backend REST (ex : `http://serveur-bovo.local:8000`)
2. Source des mises à jour (ex : `\\SERVEUR\Partage\Bovo\latest.json`)

## 🚀 Cycle de mise à jour

### Côté admin (toi)

1. Développe & teste tes changements
2. Bump `app/version.py` (ex : `1.6.0` → `1.7.0`)
3. `.\build-msi.ps1 -Clean` → produit `dist\Bovo-1.7.0-win64.msi`
4. `.\publish-release.ps1 -Share \\SERVEUR\Partage\Bovo -ReleaseNotes "Fix scroll H, colonne ID Ouvrage..."`

Le script `publish-release.ps1` :
- Copie le nouveau MSI vers le partage
- Génère `latest.json` avec la version + chemin MSI
- Archive l'ancien MSI dans `archive\` (optionnel)

### Côté utilisateur

Rien à faire. Au prochain lancement :
1. Bandeau jaune "🚀 Nouvelle version 1.7.0 disponible"
2. Clic sur "Installer maintenant"
3. `msiexec` lance l'installation, l'app se ferme
4. Windows applique la MAJ (garde les paramètres utilisateur intacts)
5. L'utilisateur relance depuis son raccourci — nouvelle version active

Pas d'admin requis si l'MSI a été installé en per-user (voir `setup_msi.py`).
Nécessite admin si install per-machine (recommandé pour partages d'entreprise).

## 🔒 Sécurité et signature

- **Non signé** : Windows SmartScreen peut afficher un avertissement au 1er lancement.
- **Signé** : recommandé pour déploiement pro. Certificat de signature de code
  (~200 €/an chez SSL.com, DigiCert, Sectigo).

  ```powershell
  signtool.exe sign /f cert.pfx /p PASSWORD /tr http://timestamp.digicert.com `
              /td sha256 /fd sha256 dist\Bovo-1.7.0-win64.msi
  ```

## ❓ Dépannage

### « L'installation a échoué »
- Vérifie que tu n'as pas Bovo.exe ouvert.
- Lance msiexec depuis PowerShell admin : `msiexec /i Bovo-Setup.msi /l*v install.log`

### La MAJ ne se déclenche pas
- Vérifie `%APPDATA%\Bovo\logs\bovo.log` : cherche `check_for_update`
- Contrôle que `latest.json` sur le partage est lisible depuis le poste
- Vérifie que le numéro de version dans `latest.json` est **supérieur** à celui installé

### « Impossible d'accéder au partage »
Les postes doivent avoir accès en LECTURE à `\\SERVEUR\Partage\Bovo\`.
Configurer via GPO ou permissions NTFS classiques.

### Désinstaller proprement
Panneau de configuration → Programmes → Bovo ASF Manager → Désinstaller.
Les données `%APPDATA%\Bovo\` sont conservées (à supprimer manuellement si voulu).

## 📁 Structure des fichiers utilisateur

```
%APPDATA%\Bovo\
├── database\bovo.db          ← paramètres, journal, "Se souvenir de moi"
├── logs\bovo.log             ← logs applicatifs
├── documents\                ← cache local des documents téléchargés
└── exports\                  ← PDF/Excel générés
```

Ces fichiers **survivent** aux mises à jour MSI. C'est intentionnel :
les préférences utilisateur ne sont jamais perdues.

## 🆚 MSI vs autres options

| Critère | MSI (choisi) | .exe portable | ClickOnce |
|---|---|---|---|
| Installation propre | ✅ | ❌ | ✅ |
| Désinstallation Windows | ✅ | ❌ | ✅ |
| Mises à jour auto | ✅ (via latest.json) | ❌ manuel | ✅ natif |
| Raccourcis Start Menu | ✅ | ❌ | ✅ |
| Nécessite admin install | ⚠️ par défaut | ❌ | ❌ |
| Support entreprise (GPO) | ✅ | ❌ | ⚠️ |
