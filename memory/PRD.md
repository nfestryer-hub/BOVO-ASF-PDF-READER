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
