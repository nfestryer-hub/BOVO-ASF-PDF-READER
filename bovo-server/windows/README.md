# Scripts PowerShell — Bovo ASF Manager Server (Windows)

Utilitaires pour installer, maintenir et migrer le serveur BOVO sur un
poste Windows.

## Contenu

| Script                  | Rôle                                                   |
| :---------------------- | :----------------------------------------------------- |
| `install-docker.ps1`    | Installation via Docker Desktop (recommandé)           |
| `install-native.ps1`    | Installation native (Python + PostgreSQL + NSSM)       |
| `status.ps1`            | Diagnostic rapide (santé API, IP, logs, disque)        |
| `backup.ps1`            | Sauvegarde manuelle ou planifiée (DB + documents)      |
| `migrate-to-vps.ps1`    | Génère une archive prête à téléverser sur un VPS       |

## Utilisation

Ouvrir **PowerShell en administrateur** et autoriser l'exécution :

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
```

### Première installation (Docker Desktop, recommandée)

```powershell
cd C:\chemin\vers\bovo-server\windows
.\install-docker.ps1 -AdminPassword "ibak23"
```

Après un redémarrage éventuel de Docker Desktop, relancer le script.

### Première installation (native)

```powershell
.\install-native.ps1 `
    -PostgresSuperPassword "VotreMotDePassePostgresRoot!" `
    -AdminPassword "ibak23"
```

### Diagnostic

```powershell
.\status.ps1
```

### Planifier une sauvegarde quotidienne à 02:00

```powershell
# Tâche Windows planifiée
schtasks /Create /SC DAILY /ST 02:00 /RL HIGHEST /TN "Bovo Backup" `
    /TR "powershell -ExecutionPolicy Bypass -File C:\Bovo\server\bovo-server\windows\backup.ps1 -Destination D:\Backups\bovo"
```

### Migrer vers un VPS

```powershell
.\migrate-to-vps.ps1
```

Puis suivre les instructions affichées à la fin de l'exécution.

## Voir aussi

- `../DEPLOY_WINDOWS.md` — guide de déploiement complet
- `../README.md` — documentation de l'API
