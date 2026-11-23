# -*- coding: utf-8 -*-
"""
=====================================================================================
 EXPORT DES ÉVÉNEMENTS WHOSCORED DE LA LIGUE 1  →  donnees/whoscored_ligue1.csv
=====================================================================================

POURQUOI
  Les transitions (pertes → tir adverse en 15 s), le contre-pressing (récupération en 5 s),
  le vrai PPDA et l'origine du danger concédé demandent les événements match par match.
  Ton script Auxerre (aspiration.py) les a déjà téléchargés pour TOUTE la Ligue 1 : ils sont
  dans le cache de soccerdata (C:\\Users\\julie\\soccerdata\\data\\WhoScored).
  Ce script réutilise ses fonctions pour relire ce cache (rapide) et ajouter les matchs
  joués depuis (environ 3 minutes par nouveau match), puis écrit un seul fichier.

LANCEMENT (depuis le dossier OM_diagnostic, une fenêtre Chrome s'ouvre : ne pas la fermer)
  & 'C:\\Users\\julie\\AppData\\Local\\Programs\\Python\\Python311\\python.exe' export_whoscored.py
  puis :
  & 'C:\\Users\\julie\\AppData\\Local\\Programs\\Python\\Python311\\python.exe' preparation.py
"""

import importlib.util
from datetime import date, timedelta
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent / "donnees"
SCRIPT_AUXERRE = Path(__file__).resolve().parent.parent / "Auxerre_OM" / "aspiration.py"

# On charge aspiration.py comme une boîte à outils (sa fonction main() n'est pas lancée)
spec = importlib.util.spec_from_file_location("aspiration", SCRIPT_AUXERRE)
asp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asp)
asp.DOSSIER_DONNEES = DOSSIER                                   # ses fichiers vont dans NOTRE dossier
asp.DATE_DU_MATCH = (date.today() + timedelta(days=1)).isoformat()   # tous les matchs déjà joués

asp.log("Ouverture de WhoScored et lecture du calendrier…")
ws, cal = asp.ouvrir_whoscored()
ids = cal["game_id"].tolist()
asp.log(f"{len(ids)} matchs de Ligue 1 joués : lecture du cache (les nouveaux matchs sont téléchargés)…")
brut = asp.telecharger_evenements(ws, ids)
ev = asp.preparer_evenements(brut, cal)
ev = ev.drop(columns=[c for c in ("joueurs_formation", "postes_formation") if c in ev.columns])
ev.to_csv(DOSSIER / "whoscored_ligue1.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
asp.log(f"Terminé : {ev['game_id'].nunique()} matchs, {len(ev)} événements → donnees/whoscored_ligue1.csv")
asp.log("Relance maintenant preparation.py, puis l'application.")
