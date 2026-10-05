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

## MAJ 2026-06 (05/06) — Netteté, noir, gras poids, zones élargies
- Bug utilisateur : case « Zone : Aucune » trop petite → texte coupé au rendu. CORRIGÉ (field-zone élargi) + vérifié par testing_agent (iteration_11 : « bug FIXED »).
- Fond régénéré plus net et noir : rendu PDF 6x, redressement, binarisation + courbe de contraste (gamma 1.35) + masque de netteté (unsharp), nettoyage poussières → `clean_v2.png` (1231×2039). Réinjecté dans `ticketBg.js` et le standalone.
- Texte tapé en NOIR pur (#000). Zones poids (fPoids, p2Poids, poidsNet) en GRAS (font-weight 700) pour matcher les gros chiffres arrondis du scan ; petites valeurs en TicketMono fin (match des libellés scannés).
- Ajustements zones (évite tout rognage) : heP1/heP2 15%, zone 28%, padding 0 1px.
- Reste ouvert : si l'utilisateur veut une police free encore plus proche des gros chiffres arrondis du scan, prévoir d'embarquer une police dédiée en base64 (contrainte offline).

## MAJ 2026-06 (05/06) — Alignement vertical des poids
- Bug utilisateur : chiffres P1/P2 et Poids Net non alignés avec les libellés P1:/P2:/kg du scan, et case blanche ne couvrant pas entièrement les chiffres d'origine (dépassement au-dessus).
- Correctif : zones fPoids/p2Poids/poidsNet agrandies (height 27px, line-height 27px, fs 19 gras) et top ajustés à 76.4 / 82.5 / 94.4 % → couverture totale des chiffres d'origine + ligne de base alignée sur P1:/P2:/kg.
- Vérifié par testing_agent (iteration_12 : 100 % périmètre, aperçu = rendu export PDF, aucune régression, aucune erreur console).

## MAJ 2026-06 (05/06) — Alignement poids affiné sur le VRAI rendu PDF
- L'utilisateur a re-signalé un décalage visible dans le PDF. Mesures au niveau html2canvas (sortie réelle) : les chiffres tapés étaient ~0,9 % puis ~0,6 % trop bas vs les libellés P1:/P2:/kg.
- Correctif précis par mesure des lignes de base sur la sortie html2canvas (scale 4) :
  - Standalone `.html` (clone en <span>) : tops poids 75.8 / 81.8 / 93.8 % → aligné (écart ≤ 0,27 %).
  - React `TicketDoc.jsx` (rendu en <div>) : tops poids 75.2 / 81.2 / 93.2 % (≈ -0,6 % vs standalone pour compenser le baseline <div> vs <span> sous html2canvas + synthèse de gras). Écart final digit vs libellé ≈ 0,05 %.
- Vérifié par testing_agent iteration_14 : 100 %, les DEUX versions alignées sur le rendu PDF réel, export PDF OK, non-régression 9/9 autres champs, zéro erreur console.
- Note maintenance : les tops poids diffèrent volontairement entre React et standalone (commenté dans TicketDoc.jsx).
