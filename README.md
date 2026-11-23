# Diagnostic d'équipe — exemple : Olympique de Marseille (Ligue 1 2026-2027)

Application Streamlit d'aide à la décision pour un staff : chaque indicateur est classé face aux
96 clubs des 5 grands championnats (ou aux 18 clubs de Ligue 1), accompagné d'un constat, de pistes
à creuser et d'un champ « décision ».

**Pages** : Synthèse · Résultats & réalisme · Quand concède-t-on ? · Comment concède-t-on ? (côtés,
ballons aériens, seconds ballons, équipes de référence) · Production offensive · Pressing & transitions ·
Joueurs : ce qui pêche · Qui est sur le terrain ? · Détail match par match.

## Données
- FotMob (données Opta) : 545 matchs des 5 grands championnats — xG, tirs, joueurs.
- WhoScored (événements) : matchs de Ligue 1 — pertes, récupérations, transitions, PPDA, origine du danger.

Les tableaux prêts à l'emploi sont dans `donnees/`. Les fichiers bruts ne sont pas publiés.

## Lancer en local
```
pip install -r requirements.txt
streamlit run app.py
```

## Mettre à jour les données (sur le PC d'origine)
```
python export_whoscored.py     # événements WhoScored de la Ligue 1
python preparation.py          # recalcule tous les tableaux de donnees/
```

Projet réalisé par Jérôme (GitHub : jmoog89) — data analyst football.
