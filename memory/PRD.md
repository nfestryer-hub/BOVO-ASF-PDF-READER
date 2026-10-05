# PRD — Générateur de tickets de pesée (ASTEO) en PDF

## Problème / Demande initiale
Logiciel de création de ticket de pesée en PDF au bon format/taille. Interface de
remplissage qui garde EXACTEMENT la même mise en page que le ticket de la photo :
le texte fixe (étoiles, ASTEO, adresse, libellés) reste inchangé, seuls les champs de
valeur (surlignés en jaune) sont modifiables. Bouton « Enregistrer sous PDF », le nom
du fichier est une suite de chiffres saisie manuellement.

## Choix utilisateur
- Format PDF : ticket étroit 80 mm (rouleau de caisse), hauteur automatique.
- Nom du fichier : saisi manuellement.
- Champs modifiables : TOUS les champs de valeur.
- POIDS NET : saisi manuellement.
- Historique : NON — application purement front, aucune donnée stockée (pas de backend/DB).
- Fidélité stricte à la photo (caractères, étoiles, libellés).

## Architecture
- Frontend React uniquement (aucun endpoint backend ajouté ; backend template inchangé).
- PDF généré côté client : html2canvas (rendu d'un ticket « propre » hors écran, sans
  surlignage) + jsPDF, format [80mm, hauteur auto].
- Aucune persistance.

## Fichiers clés
- `src/pages/TicketMaker.jsx` : état du ticket (DEFAULTS), panneau d'actions, nom de
  fichier, `handleSave()` (html2canvas scale 2 + jsPDF `.save(<nom>.pdf)`), ticket
  imprimable hors écran (printRef).
- `src/components/TicketDoc.jsx` : rendu du ticket. `editable=true` → inputs surlignés
  jaune (data-testid `field-<clé>`) ; `editable=false` → texte noir propre (version PDF).
- `src/App.css` : styles fidèles au ticket (police monospace Cousine, référence
  manuscrite Caveat en bleu).

## Implémenté (2026-06)
- Ticket ASTEO reproduit fidèlement (texte fixe + étoiles + libellés).
- 16 champs de valeur éditables en ligne, surlignés en jaune, auto-dimensionnés.
- Nom de fichier manuel + export « Enregistrer sous PDF » (80 mm) fonctionnel.
- Bouton Réinitialiser.
- Testé (frontend) : rendu, édition des 16 champs, téléchargement PDF valide (%PDF),
  reset. Correctif appliqué : largeur du champ manuscrit BL.

## Backlog (P1/P2)
- P1 : Impression directe (window.print) en plus de l'enregistrement PDF.
- P2 : Export en PDF vectoriel (texte sélectionnable) plutôt qu'image.
- P2 : Modèles multiples / autres en-têtes d'entreprise.
- P2 : Calcul automatique optionnel du poids net (différence F − P2).

## Prochaines actions
- Selon retour utilisateur sur la fidélité exacte de la mise en page.

## MAJ 2026-06 (05/06) — Refonte « fond scanné + zones blanches »
- Changement majeur demandé par l'utilisateur : repartir du vrai ticket scanné (PDF fourni) comme FOND FIXE et ne rendre modifiables que des ZONES BLANCHES posées sur les valeurs variables. Remplace entièrement l'ancien générateur « texte reconstruit ».
- Pipeline image : extraction du scan depuis le PDF, redressement (profil de projection), binarisation, suppression des poussières, recadrage auto → fond propre `clean_final4.png` (1025×1693).
- Fond embarqué en base64 : React dans `/app/frontend/src/ticketBg.js` (export TICKET_BG/W/H) ; standalone en `url(data:image/png;base64,...)` inline (offline, ~896 KB).
- 12 zones éditables (left/top/width % + height/font px) : nPesee, date, heP1, heP2, nCamion, client, zone, provenance, produit, fPoids, p2Poids, poidsNet. NON éditables (dans le fond) : Badge, DSD, libellés, en-tête, adresse, « kg ».
- Police des zones = TicketMono (monospace déjà utilisée). Zones blanches invisibles au rendu (fusion parfaite avec le scan).
- Fichiers : `TicketDoc.jsx` réécrit (fond + inputs absolus), `TicketMaker.jsx` (DEFAULTS=valeurs du scan, textes mis à jour, chargement polices), `App.css` (focus zones), standalone `logiciel-ticket-asteo.html` (CSS `.scanticket/.f`, markup inputs positionnés, DEFAULTS, buildNodeFromData copie style+classe, autosize no-op).
- Machinerie PDF/impression/multi-tickets A4 inchangée (opère sur le nœud `#ticket`). Vérifié : édition OK, html2canvas rend le clone sans erreur, jsPDF présent, rendu export = aperçu.
