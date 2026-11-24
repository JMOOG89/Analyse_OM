# -*- coding: utf-8 -*-
"""
=====================================================================================
 APPLICATION STREAMLIT — DIAGNOSTIC DE NOTRE ÉQUIPE (exemple : OM)        (version 2)
=====================================================================================

CE QUE FAIT CE FICHIER
  Lit les tableaux produits par preparation.py (dossier donnees) et construit un outil de
  travail pour le staff : Synthèse → 7 pages → Détail match par match.

PRINCIPE : CHAQUE INDICATEUR AMÈNE UNE DÉCISION
  Chaque carte ★ suit le même chemin :
     1. Le chiffre et son rang (96 clubs des 5 grands championnats, ou 18 clubs de Ligue 1
        pour les indicateurs tirés des événements WhoScored)
     2. → Constat : ce que dit le chiffre, calculé automatiquement
     3. ? Et donc : les questions à se poser, ce qu'il faut creuser, les leviers possibles
     4. ✎ Décision : le champ où le staff note la suite (enregistré dans donnees/notes_staff.json)

SOURCES
  - FotMob (données Opta) : 545 matchs des 5 championnats — xG, tirs, joueurs.
  - WhoScored (événements) : matchs de Ligue 1 — pertes, récupérations, transitions, PPDA,
    origine du danger. Disponible après export_whoscored.py puis preparation.py.

LANCEMENT (après preparation.py), depuis le dossier OM_diagnostic :
  & 'C:\\Users\\julie\\AppData\\Local\\Programs\\Python\\Python311\\python.exe' -m streamlit run app.py
"""

# =====================================================================================
# 0. IMPORTS
# =====================================================================================
import json
import re
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
import streamlit as st
from mplsoccer import VerticalPitch

# =====================================================================================
# 1. RÉGLAGES ET COULEURS
# =====================================================================================
DOSSIER = Path(__file__).resolve().parent / "donnees"
FICHIER_NOTES = DOSSIER / "notes_staff.json"

BLEU_OM, ORANGE, NAVY, GRIS = "#0A60A8", "#C2410C", "#1F3A5A", "#5B6573"
VERT, ROUGE, TEXTE = "#15803D", "#B91C1C", "#14202E"
FOND_TERRAIN, LIGNES_TERRAIN = "#F3F5F1", "#9AA79A"
TRANCHES = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]
COTES = ["Gauche", "Axe", "Droite"]
MIN_JOUEUR = 450          # minutes minimum pour entrer dans la population de comparaison d'un poste
MIN_NOS_JOUEURS = 150     # minutes minimum pour qu'un de nos joueurs ait une fiche
PETIT_ECHANTILLON = 450   # en dessous : fiche affichée avec un avertissement

STATUTS = {"Point fort": ("#DCFCE7", "#166534"), "Point faible": ("#FEE2E2", "#991B1B"),
           "Dans la moyenne": ("#EEF1F5", "#334155")}

PAGES = [
    ("Synthèse", "Vue d'ensemble", "Où en est-on, et que faut-il travailler en priorité ?"),
    ("1. Résultats & réalisme", "Vue d'ensemble", "Nos résultats reflètent-ils ce qu'on produit et ce qu'on concède ?"),
    ("2. Quand concède-t-on ?", "Sans ballon", "À quels moments du match et dans quel état du score se fait-on déborder ?"),
    ("3. Comment concède-t-on ?", "Sans ballon", "Par quel côté, sur quel type de tir, après quelle perte de balle ?"),
    ("Piste 1 · Défendre les centres", "Piste de travail",
     "Qui défend le mieux les centres, avant (éviter, limiter) et après (placement, duel, 2e ballon) ? Que leur prendre ?"),
    ("Piste 2 · Protéger la zone de vérité", "Piste de travail",
     "Comment les meilleures défenses empêchent-elles d'entrer dans la surface et de tirer face au but ?"),
    ("4. Production offensive", "Avec ballon", "Crée-t-on assez, selon le score et selon le moment du match ?"),
    ("5. Pressing & transitions", "Transitions", "Notre pressing récupère-t-il le ballon, et que se passe-t-il quand on le perd ?"),
    ("6. Joueurs : ce qui pêche", "Joueurs", "Poste par poste, où nos joueurs se situent-ils face aux 5 grands championnats ?"),
    ("7. Qui est sur le terrain ?", "Joueurs", "Concède-t-on plus ou moins selon les joueurs alignés, et de quel côté ?"),
    ("Détail match par match", "Niveau 3", "Tous les chiffres, match par match"),
]
PAGES_TITRES = [p[0] for p in PAGES]
COULEURS_PHASE = {"Piste de travail": ("#FEF3C7", "#92400E"), "Vue d'ensemble": ("#EEF1F5", "#334155"), "Avec ballon": ("#ECE9FB", "#4C3DB0"),
                  "Sans ballon": ("#FBE9F1", "#9D2257"), "Transitions": ("#E3F5F8", "#0E6675"),
                  "Joueurs": ("#E0E7FF", "#3730A3"), "Niveau 3": ("#FFF4E0", "#92400E")}

st.set_page_config(page_title="Diagnostic équipe", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"""
<style>
.block-container {{padding-top: 3.2rem; padding-bottom: 1rem;}}
.carte {{background:#fff;border:1px solid #E1E4DC;border-radius:10px;padding:10px 14px 6px 14px;color:{TEXTE};}}
.kl {{font-size:12.5px;color:#5B6573;}}
.kv {{font-size:30px;font-weight:700;line-height:1.15;margin:2px 0 2px 0;}}
.pill {{display:inline-block;font-size:11.5px;padding:2px 9px;border-radius:999px;background:#EEF1F5;color:#334155;
       margin:4px 4px 0 0;font-weight:600;}}
.question {{font-size:14px;color:#5B6573;margin:2px 0 10px 0;}}
.titre {{font-size:18px;font-weight:700;margin:18px 0 2px 0;color:{TEXTE};background:#F3F5F1;
         border-left:5px solid {NAVY};padding:5px 10px;}}
.sous {{font-size:12.5px;color:#5B6573;margin:2px 0 6px 0;}}
.lecture {{font-size:13.5px;color:{TEXTE};background:#FFF7ED;border-left:4px solid {ORANGE};padding:6px 10px;
           margin:4px 0 10px 0;}}
.creuser {{font-size:13.5px;color:{TEXTE};background:#EEF4FB;border-left:4px solid {BLEU_OM};padding:8px 12px;
           margin:4px 0 10px 0;}}
.mode {{font-size:13px;color:{TEXTE};background:#F6F7F4;border:1px dashed #C9CFC4;padding:8px 12px;border-radius:8px;
        margin:4px 0 10px 0;}}
.constat {{font-size:12.5px;color:{TEXTE};margin:6px 0 2px 0;}}
.axe {{font-size:12px;font-weight:700;letter-spacing:0.04em;color:{GRIS};text-transform:uppercase;margin:4px 0 2px 2px;}}
</style>
""", unsafe_allow_html=True)


# =====================================================================================
# 2. LECTURE DES DONNÉES
# =====================================================================================
@st.cache_data
def lire(nom, date_fichier=None):
    chemin = DOSSIER / nom
    if not chemin.exists():
        return None
    df = pd.read_csv(chemin, sep=";", decimal=",", encoding="utf-8-sig", low_memory=False)
    for col in df.columns:
        if df[col].dtype == object and set(df[col].dropna().astype(str).str.lower().unique()) <= {"true", "false"}:
            df[col] = df[col].astype(str).str.lower().eq("true")
    return df


def charger(nom):
    chemin = DOSSIER / nom
    return lire(nom, chemin.stat().st_mtime if chemin.exists() else None)


def lire_notes():
    return json.loads(FICHIER_NOTES.read_text(encoding="utf-8")) if FICHIER_NOTES.exists() else {}


def sauver_note(cle):
    notes = lire_notes()
    notes[cle] = st.session_state[cle]
    try:
        FICHIER_NOTES.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass   # en ligne, le disque peut être en lecture seule : la note reste dans la session


if not (DOSSIER / "equipes.csv").exists():
    st.error("Aucune donnée trouvée. Lance d'abord **preparation.py**, puis relance cette application.")
    st.stop()

META = json.loads((DOSSIER / "meta.json").read_text(encoding="utf-8"))
EQUIPE, LIGUE = META["equipe"], META["ligue"]
EQ = charger("equipes.csv")
EQ = EQ.copy()
EQ["equipe_id"] = EQ["equipe_id"].astype(str)
NOUS = EQ[EQ["equipe_id"] == str(META["equipe_id"])].iloc[0]
L1 = EQ[EQ["ligue"] == LIGUE]
MATCHS = charger("matchs.csv")
MATCHS["date"] = pd.to_datetime(MATCHS["date"])
TIRS = charger("tirs.csv")
JOUEURS = charger("joueurs.csv")
JOUEURS["equipe_id"] = JOUEURS["equipe_id"].astype(str)
ONOFF = charger("on_off.csv")
NB = len(EQ)

# --- événements WhoScored (facultatif) ---
WS = charger("ws_equipes.csv")
NOM_WS = META.get("equipe_whoscored", EQUIPE)
WS_OK = WS is not None and bool((WS["equipe"] == NOM_WS).any())
WS_NOUS = WS[WS["equipe"] == NOM_WS].iloc[0] if WS_OK else None
WS_PERTES = charger("ws_pertes.csv") if WS_OK else None
WS_RECUPS = charger("ws_recups.csv") if WS_OK else None
WS_TIRS = charger("ws_tirs_concedes.csv") if WS_OK else None
WS_JOUEURS = charger("ws_joueurs_l1.csv") if WS_OK else None
BASES = {"96": (EQ, NOUS, NB, "5 champ."), "L1": (WS, WS_NOUS if WS_OK else None, len(WS) if WS_OK else 0, LIGUE)}


# =====================================================================================
# 3. INDICATEURS ★ : définition, sens, et ce qu'ils doivent déclencher
#    sens = +1 : plus c'est haut, mieux c'est ; -1 : plus c'est bas, mieux c'est ; 0 = style.
#    axe   = la question à laquelle l'indicateur répond (la synthèse prend UN chantier par axe,
#            pour que chaque carte apporte une information différente).
#    base  = "96" (FotMob, 5 championnats) ou "L1" (événements WhoScored, Ligue 1).
#    resume = True : indicateur « parapluie » (montré dans le fil rouge, pas dans les cartes auto).
# =====================================================================================
IND = {
    # ---------------------------------------------------------------- Résultats
    "1.1": dict(lib="Points par match", col="pts_m", sens=1, d=2, src="résultats", axe="Résultats", resume=True,
                faible="Comparer avec la différence de xG (1.2) : si elle est bonne, les résultats devraient suivre ; "
                       "sinon le problème est dans le jeu, pas dans la réussite.",
                fort="Vérifier que les points reposent sur la production (1.2) et pas seulement sur la réussite (1.3, 1.4)."),
    "1.2": dict(lib="Différence de xG par match", col="xg_diff_m", sens=1, d=2, src="xG Opta", axe="Résultats",
                resume=True,
                faible="Est-ce l'attaque (4.1) ou la défense (2.1) qui tire la différence vers le bas ? "
                       "Commencer par le côté le plus mal classé.",
                fort="Base saine : les résultats doivent finir par suivre la production."),
    "1.3": dict(lib="Buts marqués − xG par match", col="buts_moins_xg", sens=1, d=2, src="xG Opta", axe="Réussite",
                faible="Finition en dessous des occasions : regarder la finition par joueur (page 4) et la page 6.",
                fort="On marque plus que prévu : souvent peu durable. Ne pas compter dessus pour masquer d'autres manques."),
    "1.4": dict(lib="Buts encaissés − xG concédés par match", col="buts_contre_moins_xga", sens=-1, d=2,
                src="xG Opta", axe="Réussite",
                faible="On encaisse plus que les occasions adverses ne le laissent prévoir : regarder le gardien "
                       "(buts évités, page 6) et les erreurs menant à un but.",
                fort="Le gardien et la réussite nous sauvent : sans eux, le classement serait plus bas. Corriger le "
                     "volume d'occasions concédées (page 3) avant que la réussite ne tourne."),
    "1.5": dict(lib="Points perdus après avoir mené (par match)", col="pts_perdus_en_menant_m", sens=-1, d=2,
                src="chronologie des buts", axe="Quand",
                faible="Revoir les matchs concernés (Détail) : à quelle minute le match bascule ? Après un changement ? "
                       "Le bloc recule-t-il ? → page 2, état du score.",
                fort="Bonne gestion des avances."),
    # ---------------------------------------------------------------- Quand
    "2.1": dict(lib="xG concédés par match", col="xg_contre_m", sens=-1, d=2, src="xG Opta", axe="Comment",
                resume=True,
                faible="Découper : QUAND (page 2 : mi-temps, tranches, état du score) et COMMENT (page 3 : côté, "
                       "type de tir, transitions).",
                fort="Défense solide sur l'ensemble des matchs."),
    "2.2": dict(lib="xG concédés en 1re mi-temps", col="xga_1mt_m", sens=-1, d=2, src="xG Opta (tirs)", axe="Quand",
                faible="Problème d'entame ou d'organisation de départ : comparer selon le système adverse (Détail).",
                fort="Le plan de départ fonctionne."),
    "2.3": dict(lib="xG concédés en 2e mi-temps", col="xga_2mt_m", sens=-1, d=2, src="xG Opta (tirs)", axe="Quand",
                faible="Trois pistes à séparer : (1) physique — comparer avec les données GPS du club (distance, "
                       "sprints après 60') ; (2) changements — minute et profil des entrants (Détail) ; "
                       "(3) pressing — le PPDA par tranche (page 5) montre-t-il un pressing qui s'éteint ?",
                fort="Bonne tenue sur la durée."),
    "2.4": dict(lib="Part des xG concédés après la pause", col="part_xga_2mt", sens=-1, d=0, unite=" %",
                src="xG Opta (tirs)", axe="Quand",
                faible="On ne concède pas seulement beaucoup : on concède surtout après la pause. Chercher ce qui change "
                       "entre les deux mi-temps (consignes, changements, physique, score).",
                fort="Pas de baisse en 2e mi-temps."),
    "2.5": dict(lib="xG concédés pour 90 min passées à mener", col="xga90_Mène", sens=-1, d=2, src="xG Opta + score",
                axe="Quand",
                faible="Quand on mène, le bloc recule-t-il trop ? Y a-t-il une consigne de gestion ? Revoir en vidéo "
                       "les 15 minutes qui suivent nos buts.",
                fort="On sait tenir un avantage."),
    "2.6": dict(lib="xG concédés pour 90 min passées à égalité", col="xga90_Nul", sens=-1, d=2, src="xG Opta + score",
                axe="Quand",
                faible="Base défensive fragile même sans contexte de score : regarder l'organisation (page 3).",
                fort="Organisation solide à score neutre."),
    "2.7": dict(lib="xG concédés pour 90 min passées à être mené", col="xga90_Mené", sens=-1, d=2,
                src="xG Opta + score", axe="Quand",
                faible="En prenant des risques pour revenir, on s'expose : est-ce maîtrisé (risque assumé) ou subi ?",
                fort="On reste équilibré même en courant après le score."),
    # ---------------------------------------------------------------- Comment
    "3.1": dict(lib="Tirs concédés par match", col="tirs_contre_m", sens=-1, d=1, src="Opta", axe="Comment",
                faible="Problème de VOLUME : l'adversaire arrive trop souvent au tir. Regarder où il entre "
                       "(côtés, transitions) et le pressing (page 5).",
                fort="On limite le nombre de tirs adverses."),
    "3.2": dict(lib="xG par tir concédé", col="xga_par_tir", sens=-1, d=3, src="xG Opta (tirs)", axe="Comment",
                faible="Problème de QUALITÉ : les tirs concédés sont proches et dangereux. Regarder les grosses "
                       "occasions (liste en bas de page 3) : qui est battu, sur quelle séquence ?",
                fort="On pousse l'adversaire à tirer de loin."),
    "3.3": dict(lib="Grosses occasions concédées par match", col="grosses_occ_contre_m", sens=-1, d=1, src="Opta",
                axe="Comment",
                faible="Revoir chaque grosse occasion en vidéo : erreur individuelle, défaut de couverture, "
                       "transition mal négociée ?",
                fort="Peu d'occasions franches concédées."),
    "3.4": dict(lib="xG concédés face au but (tirs entre les poteaux)", col="xga_cote_Axe_m", sens=-1, d=2,
                src="xG Opta (tirs)", axe="Comment",
                faible="L'adversaire tire trop souvent dans l'axe, face au but : la protection de la zone devant le "
                       "but (défenseurs centraux, milieu qui redescend) est en cause plus que les côtés.",
                fort="L'axe est bien protégé."),
    "3.5": dict(lib="xG concédés de la tête par match", col="xga_type_Tête_m", sens=-1, d=2, src="xG Opta (tirs)",
                axe="Comment",
                faible="Têtes concédées : sur CPA ou dans le jeu (centres) ? Le détail est sous le graphique « type de "
                       "tir ». Dans le jeu : qui laisse centrer, qui perd le duel au point de chute ?",
                fort="Les centres adverses sont bien défendus."),
    "3.6": dict(lib="xG concédés en contre-attaque par match", col="xga_sit_Contre-attaque_m", sens=-1, d=2,
                src="xG Opta (tirs)", axe="Comment",
                faible="Équilibre à la perte : combien de joueurs restent derrière quand on attaque ? Voir page 5.",
                fort="Bonne protection à la perte du ballon."),
    "3.7": dict(lib="xG concédés sur coups de pied arrêtés par match", col="xg_cpa_contre_m", sens=-1, d=2,
                src="xG Opta", axe="Comment",
                faible="Revoir le marquage (zone / individuel) et les premiers ballons.",
                fort="CPA défensifs maîtrisés."),
    "3.8": dict(lib="xG concédés après un ballon aérien dans notre surface", col="xga_aerien_10s_match", sens=-1,
                d=2, src="WhoScored", base="L1", axe="Comment",
                faible="Centres et longs ballons dans notre surface : on laisse centrer trop facilement, ou on perd le "
                       "duel au point de chute, ou on ne sécurise pas le 2e ballon ? Voir le côté et la distance du "
                       "ballon aérien, et les duels aériens perdus (page 6).",
                fort="Les ballons aériens dans notre surface sont bien défendus."),
    "3.9": dict(lib="xG concédés sur seconds ballons (après arrêt, dégagement, duel)", col="xga_second_ballon_match",
                sens=-1, d=2, src="WhoScored", base="L1", axe="Comment",
                faible="Passivité après notre intervention : qui attaque le ballon après un arrêt ou un dégagement ? "
                       "Consigne possible : un joueur dédié à la zone de 2e ballon.",
                fort="On sécurise bien les seconds ballons."),
    # ---------------------------------------------------------------- Avec ballon
    "4.1": dict(lib="xG créés par match", col="xg_m", sens=1, d=2, src="xG Opta", axe="Avec ballon",
                faible="Crée-t-on peu de tirs (4.2) ou des tirs de mauvaise qualité (4.3) ?",
                fort="Production offensive au niveau."),
    "4.2": dict(lib="Tirs par match", col="tirs_m", sens=1, d=1, src="Opta", axe="Avec ballon",
                faible="On arrive peu au tir : regarder les entrées dans la surface (4.4) et la projection.",
                fort="Volume de tirs élevé."),
    "4.3": dict(lib="xG par tir", col="xg_par_tir", sens=1, d=3, src="xG Opta (tirs)", axe="Avec ballon",
                faible="Trop de frappes lointaines ? Travailler la patience et les dernières passes.",
                fort="Les tirs sont de bonne qualité."),
    "4.4": dict(lib="Ballons touchés dans la surface adverse", col="touches_surface_m", sens=1, d=1, src="Opta",
                axe="Avec ballon",
                faible="On n'occupe pas la surface : combien de joueurs y entrent sur nos attaques ?",
                fort="Forte présence dans la surface."),
    "4.5": dict(lib="xG créés pour 90 min passées à mener", col="xg90_Mène", sens=1, d=2, src="xG Opta + score",
                axe="Avec ballon",
                faible="Quand on mène, on n'attaque plus : l'adversaire peut se ruer vers l'avant sans risque.",
                fort="On continue à menacer en menant : l'adversaire ne peut pas se ruer vers l'avant."),
    "4.6": dict(lib="xG créés entre la 61e et la 75e minute", col="xg_61-75_m", sens=1, d=2, src="xG Opta (tirs)",
                axe="Avec ballon",
                faible="Baisse de régime offensive en milieu de 2e mi-temps : si elle coïncide avec un pic de xG "
                       "concédés (page 2), c'est tout le bloc qui baisse, pas seulement la défense.",
                fort="On garde du rythme offensif en milieu de 2e mi-temps."),
    # ---------------------------------------------------------------- Pressing & transitions
    "5.1": dict(lib="Possession moyenne", col="possession_m", sens=0, d=0, unite=" %", src="Opta", axe="Style",
                faible="", fort=""),
    "5.2": dict(lib="Pressing (≈ PPDA, 5 championnats)", col="ppda_approx", sens=-1, d=1, src="approximation",
                axe="Pressing",
                faible="L'adversaire construit tranquillement chez lui : choix assumé (bloc médian) ou manque "
                       "d'intensité ? Voir le vrai PPDA Ligue 1 (5.5) et son évolution par tranche.",
                fort="Pressing intense : vérifier ce qu'il coûte en fin de match (★ 2.3, PPDA par tranche)."),
    "5.3": dict(lib="% duels au sol gagnés", col="pct_duels_sol", sens=1, d=0, unite=" %", src="Opta", axe="Pressing",
                faible="On perd les duels : qui en particulier ? (page 6, « % duels au sol gagnés »)",
                fort="Équipe solide dans les duels."),
    "5.4": dict(lib="% duels aériens gagnés", col="pct_duels_aeriens", sens=1, d=0, unite=" %", src="Opta",
                axe="Pressing",
                faible="Faiblesse dans les airs : impact sur les têtes concédées (★ 3.5) et les CPA (★ 3.7).",
                fort="Domination aérienne : arme sur CPA offensifs."),
    # ---- événements WhoScored (Ligue 1)
    "5.5": dict(lib="PPDA (vrai, Ligue 1)", col="ppda", sens=-1, d=1, src="WhoScored", base="L1", axe="Pressing",
                faible="On laisse l'adversaire faire beaucoup de passes chez lui avant d'intervenir.",
                fort="Pressing parmi les plus intenses de Ligue 1 : regarder s'il tient sur 90 minutes (PPDA par tranche)."),
    "5.6": dict(lib="Contre-pressing : ballons repris en 5 s après une perte", col="contre_pressing_pct", sens=1, d=0,
                unite=" %", src="WhoScored", base="L1", axe="Pressing",
                faible="À la perte, on ne réagit pas assez vite : distances entre joueurs au moment de la perte, "
                       "nombre de joueurs autour du ballon ? À revoir en vidéo sur les pertes du camp adverse.",
                fort="Réaction à la perte efficace : le contre-pressing est une arme."),
    "5.7": dict(lib="Récupérations hautes par match (40 derniers mètres)", col="recup_hautes_match", sens=1, d=1,
                src="WhoScored", base="L1", axe="Pressing",
                faible="Le pressing ne récupère pas haut : déclenchement trop tardif ou mal coordonné ?",
                fort="Le pressing récupère haut : en tire-t-on des tirs (5.8) ?"),
    "5.8": dict(lib="Récupération → tir en moins de 15 s (par match)", col="recup_tir_match", sens=1, d=1,
                src="WhoScored", base="L1", axe="Pressing",
                faible="On récupère mais on ne frappe pas vite : projection, appels en profondeur, premier choix.",
                fort="Transition offensive efficace."),
    "5.9": dict(lib="Transitions concédées : tir adverse < 15 s après notre perte", col="transitions_concedees_match",
                sens=-1, d=1, src="WhoScored", base="L1", axe="Comment",
                faible="Nos pertes se payent cash : où perd-on le ballon (carte page 5), qui le perd, combien de "
                       "joueurs sont derrière le ballon ? C'est notre organisation de repli qui est en cause.",
                fort="Bonne organisation de repli : nos pertes ne mènent pas à des tirs."),
}


def disponible(id_):
    return IND[id_].get("base", "96") == "96" or WS_OK


# =====================================================================================
# 4. PETITS OUTILS
# =====================================================================================
def fmt(n, d=1, unite=""):
    if n is None or pd.isna(n):
        return "–"
    return f"{n:.{d}f}".replace(".", ",") + unite


def ordinal(n):
    return "1er" if n == 1 else f"{n}e"


def base(id_):
    return BASES[IND[id_].get("base", "96")]


def rang_df(df, nous, col, sens):
    s = df[col].dropna()
    v = nous[col]
    return int((s > v).sum() + 1) if sens >= 0 else int((s < v).sum() + 1)


def rang(col, sens, df=None):
    """Rang de notre équipe (1 = meilleur) dans df (par défaut les 96 clubs)."""
    df = EQ if df is None else df
    return rang_df(df, NOUS, col, sens)


def rang_ind(id_):
    df, nous, _, _ = base(id_)
    return rang_df(df, nous, IND[id_]["col"], IND[id_]["sens"])


def statut(id_):
    i = IND[id_]
    if i["sens"] == 0:
        return "Style"
    _, _, n, _ = base(id_)
    r = rang_ind(id_)
    return "Point fort" if r <= n / 3 else "Point faible" if r > 2 * n / 3 else "Dans la moyenne"


def score_ind(id_):
    """100 = meilleur club, 0 = pire (pour trier les cartes de la synthèse)."""
    _, _, n, _ = base(id_)
    return 100 * (1 - (rang_ind(id_) - 1) / max(n - 1, 1))


def titre(texte, sous_titre=""):
    st.markdown(f'<div class="titre">{texte}</div>' + (f'<div class="sous">{sous_titre}</div>' if sous_titre else ""),
                unsafe_allow_html=True)


def gras(texte):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texte)


def lecture(texte):
    st.markdown(f'<div class="lecture">→ {gras(texte)}</div>', unsafe_allow_html=True)


def mode_emploi(texte):
    st.markdown(f'<div class="mode">ⓘ {gras(texte)}</div>', unsafe_allow_html=True)


def a_creuser(points, titre_="À creuser ensuite"):
    items = "".join(f"<li>{gras(p)}</li>" for p in points)
    st.markdown(f'<div class="creuser"><b>? {titre_}</b><ul style="margin:4px 0 0 0">{items}</ul></div>',
                unsafe_allow_html=True)


def bloc(titre_, fonction, sous_titre=""):
    titre(titre_, sous_titre)
    try:
        fonction()
    except Exception as erreur:
        st.info(f"Visuel indisponible : {erreur}")


def afficher(fig):
    st.pyplot(fig)
    plt.close(fig)


def graphique(taille=(6, 3.4)):
    fig, ax = plt.subplots(figsize=taille)
    for c in ("top", "right"):
        ax.spines[c].set_visible(False)
    ax.tick_params(colors=GRIS, labelsize=9)
    return fig, ax


def note(cle, libelle="✎ Décision / prochaine étape", zone=False, hauteur=110):
    if cle not in st.session_state:
        st.session_state[cle] = lire_notes().get(cle, "")
    if zone:
        st.text_area(libelle, key=cle, on_change=sauver_note, args=(cle,), height=hauteur)
    else:
        st.text_input(libelle, key=cle, on_change=sauver_note, args=(cle,), placeholder="Donc, pour nous…")


def moy(col, df=None):
    return (EQ if df is None else df)[col].mean()


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).lower().strip()


def message_whoscored():
    st.info("Cette partie utilise les **événements WhoScored** (pertes, récupérations, passes). Pour l'activer : "
            "lancer **export_whoscored.py** (relit le cache de ton script Auxerre), puis **preparation.py**, puis "
            "relancer l'application.")


# =====================================================================================
# 5. CARTES INDICATEURS ★
# =====================================================================================
def mini_frise(id_, statut_):
    """Chaque point = un club (Ligue 1 en gris foncé), nous en gros. Trait = moyenne. À droite = mieux."""
    i = IND[id_]
    df, nous, _, _ = base(id_)
    col = i["col"]
    fig, ax = plt.subplots(figsize=(3.6, 0.6))
    if i.get("base", "96") == "96":
        autres = df[df["equipe_id"] != nous["equipe_id"]]
        couleurs = np.where(autres["ligue"] == LIGUE, "#8A94A0", "#D5DAD0")
    else:
        autres = df[df["equipe"] != nous["equipe"]]
        couleurs = "#8A94A0"
    ax.scatter(autres[col], np.zeros(len(autres)), s=20, c=couleurs, zorder=2)
    couleur = {"Point fort": VERT, "Point faible": ROUGE}.get(statut_, NAVY)
    ax.scatter([nous[col]], [0], s=120, color=couleur, edgecolors="white", zorder=3)
    ax.axvline(df[col].mean(), color=TEXTE, lw=0.8, ls=":", zorder=1)
    ax.set_yticks([])
    for c in ("top", "right", "left"):
        ax.spines[c].set_visible(False)
    ax.tick_params(labelsize=7, colors=GRIS, length=2)
    if i["sens"] < 0:
        ax.invert_xaxis()
    fig.subplots_adjust(left=0.03, right=0.97, top=0.95, bottom=0.45)
    afficher(fig)


def constat(id_):
    i = IND[id_]
    df, nous, n, lib_base = base(id_)
    v, m = nous[i["col"]], df[i["col"]].mean()
    u = i.get("unite", "")
    if i["sens"] == 0:
        return f"{fmt(v, i['d'], u)} contre {fmt(m, i['d'], u)} en moyenne ({lib_base})."
    r = rang_ind(id_)
    qualif = "mieux" if (v > m) == (i["sens"] > 0) else "moins bien"
    extreme = ""
    if r <= 3:
        extreme = f" — **parmi les 3 meilleurs ({lib_base})**"
    elif r >= n - 2:
        extreme = f" — **parmi les 3 pires ({lib_base})**"
    if abs(m) < 0.2 * abs(v) or abs(m) < 0.05:
        ecart_txt = f"{'+' if v - m > 0 else '−'}{fmt(abs(v - m), i['d'], u)} par rapport à la moyenne"
    else:
        ecart = (v - m) / abs(m) * 100
        ecart_txt = f"{fmt(abs(ecart), 0)} % {'au-dessus' if ecart > 0 else 'en dessous'} de la moyenne"
    suite = f" ; moyenne {LIGUE} : {fmt(moy(i['col'], L1), i['d'], u)}" if i.get("base", "96") == "96" else ""
    return f"{ecart_txt} ({fmt(m, i['d'], u)}), donc {qualif} que la moyenne{suite}{extreme}."


def carte_kpi(id_, avec_decision=True, sur_titre=""):
    if sur_titre:
        st.markdown(f'<div class="axe">{sur_titre}</div>', unsafe_allow_html=True)
    i = IND[id_]
    if not disponible(id_):
        st.markdown(f'<div class="carte"><div class="kl">★ {id_} · {i["lib"]}</div><div class="kv">–</div>'
                    f'<div class="kl">Nécessite les événements WhoScored (export_whoscored.py).</div></div>',
                    unsafe_allow_html=True)
        return
    df, nous, n, lib_base = base(id_)
    statut_ = statut(id_)
    fond, texte = STATUTS.get(statut_, ("#E0E7FF", "#3730A3"))
    couleur_valeur = {"Point fort": VERT, "Point faible": ROUGE}.get(statut_, TEXTE)
    pastilles = f'<span class="pill" style="background:{fond};color:{texte}">{statut_}</span>'
    if i["sens"] != 0:
        pastilles += f'<span class="pill">{ordinal(rang_ind(id_))} / {n} ({lib_base})</span>'
        if i.get("base", "96") == "96":
            pastilles += f'<span class="pill">{ordinal(rang(i["col"], i["sens"], L1))} / {len(L1)} en {LIGUE}</span>'
    if i["src"] == "approximation":
        pastilles += '<span class="pill" style="background:#FFF4E0;color:#92400E">≈ approximation</span>'
    bord = couleur_valeur if statut_ in ("Point fort", "Point faible") else "#E1E4DC"
    st.markdown(f'<div class="carte" style="border-top:4px solid {bord}">'
                f'<div class="kl">★ {id_} · {i["lib"]}</div>'
                f'<div class="kv" style="color:{couleur_valeur}">{fmt(nous[i["col"]], i["d"], i.get("unite", ""))}</div>'
                f'{pastilles}<div class="constat">→ {gras(constat(id_))}</div>'
                f'<div class="kl" style="margin-top:4px;font-size:11px">Source : {i["src"]}</div></div>',
                unsafe_allow_html=True)
    mini_frise(id_, statut_)
    texte_suite = i["faible"] if statut_ == "Point faible" else i["fort"] if statut_ == "Point fort" else (
        i["faible"] if i["sens"] else "")
    if texte_suite and avec_decision:
        with st.expander("? Et donc : que creuser, que changer"):
            st.markdown(texte_suite)
            note(f"decision_{id_}")


def rangee(ids, avec_decision=True, sur_titres=None):
    sur_titres = sur_titres or [""] * len(ids)
    for col, i, s in zip(st.columns(len(ids)), ids, sur_titres):
        with col:
            carte_kpi(i, avec_decision, s)


def entete(i):
    titre_, phase, question = PAGES[i]
    fond, texte = COULEURS_PHASE[phase]
    c1, c2 = st.columns([3, 1])
    ws_txt = (f"<br>Événements WhoScored : {META.get('nb_matchs_whoscored', 0)} matchs (maj {META.get('maj_whoscored')})"
              if WS_OK else "")
    with c1:
        st.markdown(f'<div style="font-size:28px;font-weight:700;color:{TEXTE}">{titre_} '
                    f'<span class="pill" style="background:{fond};color:{texte};vertical-align:middle">{phase}</span></div>'
                    f'<div class="question">Question du staff : {question}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="text-align:right;font-size:12px;color:{GRIS};padding-top:8px">{EQUIPE} · '
                    f'{META["nb_matchs"]} matchs de {LIGUE} {META["saison"]}<br>Comparé aux {NB} clubs des 5 grands '
                    f'championnats<br>{META["source"]} · extrait le {META["extrait_le"]}{ws_txt}</div>',
                    unsafe_allow_html=True)


# =====================================================================================
# 6. GRAPHIQUES RÉUTILISÉS
# =====================================================================================
def barres_comparees(cols, etiquettes, titre_y, taille=(7, 3.3), d=2, df=None, nous=None, lib_moy=None):
    """Barres : nous / moyenne Ligue 1 / moyenne 5 championnats (ou nous / moyenne d'une autre base)."""
    fig, ax = graphique(taille)
    x = np.arange(len(cols))
    if df is None:
        series = [(EQUIPE, [NOUS[c] for c in cols], BLEU_OM),
                  (f"Moy. {LIGUE}", [moy(c, L1) for c in cols], "#8A94A0"),
                  ("Moy. 5 champ.", [moy(c) for c in cols], "#D5DAD0")]
    else:
        series = [(EQUIPE, [nous[c] for c in cols], BLEU_OM), (lib_moy, [df[c].mean() for c in cols], "#8A94A0")]
    largeur = 0.8 / len(series)
    for k, (lib, vals, coul) in enumerate(series):
        b = ax.bar(x + (k - (len(series) - 1) / 2) * largeur, vals, largeur, label=lib, color=coul)
        if k == 0:
            for rect, v in zip(b, vals):
                ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(), fmt(v, d), ha="center", va="bottom",
                        fontsize=8, color=BLEU_OM, fontweight="bold")
    ax.set_xticks(x, etiquettes)
    ax.set_ylabel(titre_y, color=GRIS, fontsize=9)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0))
    afficher(fig)


def nuage(df, nous_mask, x, y, lib_x, lib_y, etiquette, inverser_x=False, inverser_y=False, quadrants=None,
          etiqueter_tous=False, taille=(6.4, 4.6)):
    """Nuage de points générique : nous en bleu, les autres en gris. Lignes = moyennes."""
    fig, ax = graphique(taille)
    autres, nous = df[~nous_mask], df[nous_mask]
    ax.scatter(autres[x], autres[y], s=26, color="#B9C0B4")
    ax.scatter(nous[x], nous[y], s=150, color=BLEU_OM, edgecolors="white", zorder=4)
    for _, r in nous.iterrows():
        ax.annotate(r[etiquette], (r[x], r[y]), xytext=(6, 6), textcoords="offset points", fontsize=10,
                    fontweight="bold", color=BLEU_OM, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    if etiqueter_tous:
        for _, r in autres.iterrows():
            ax.annotate(r[etiquette], (r[x], r[y]), xytext=(3, 3), textcoords="offset points", fontsize=6.5, color=GRIS)
    ax.axvline(df[x].mean(), color=GRIS, lw=0.7, ls=":")
    ax.axhline(df[y].mean(), color=GRIS, lw=0.7, ls=":")
    ax.set_xlabel(lib_x, color=GRIS, fontsize=9)
    ax.set_ylabel(lib_y, color=GRIS, fontsize=9)
    if inverser_x:
        ax.invert_xaxis()
    if inverser_y:
        ax.invert_yaxis()
    for (qx, qy, txt) in quadrants or []:
        ax.text(qx, qy, txt, transform=ax.transAxes, fontsize=8, color=GRIS, style="italic",
                ha="left" if qx < 0.5 else "right", va="top" if qy > 0.5 else "bottom")
    afficher(fig)


def nuage_equipes(x, y, lib_x, lib_y, **kw):
    l1 = EQ["ligue"] == LIGUE
    df = EQ.assign(etiq=np.where(l1, EQ["equipe"], ""))
    nuage(df, df["equipe_id"] == NOUS["equipe_id"], x, y, lib_x, lib_y, "etiq", etiqueter_tous=True, **kw)


def nuage_l1(x, y, lib_x, lib_y, **kw):
    nuage(WS, WS["equipe"] == WS_NOUS["equipe"], x, y, lib_x, lib_y, "equipe", etiqueter_tous=True, **kw)


def demi_terrain(titre_legende, taille=(5.6, 5)):
    p = VerticalPitch(pitch_type="uefa", half=True, pitch_color=FOND_TERRAIN, line_color=LIGNES_TERRAIN, linewidth=1,
                      pad_bottom=-8)
    fig, ax = p.draw(figsize=taille)
    fig.set_facecolor("white")
    ax.set_title(titre_legende, fontsize=10, color=TEXTE)
    return p, fig, ax


def carte_tirs(df, titre_legende):
    """Demi-terrain vertical : un rond par tir, taille = xG, rouge = but."""
    p, fig, ax = demi_terrain(titre_legende)
    buts = df["resultat"].eq("Goal")
    for masque, coul, lib in ((~buts & (df["mi_temps"] == 1), "#8A94A0", "1re MT"),
                              (~buts & (df["mi_temps"] == 2), ORANGE, "2e MT"), (buts, ROUGE, "But")):
        d = df[masque]
        p.scatter(d["x"], d["y"], s=d["xg"] * 600 + 15, color=coul, edgecolors="white", alpha=0.8, ax=ax, label=lib,
                  zorder=3)
    ax.legend(loc="lower left", fontsize=8, frameon=False, ncol=3)
    afficher(fig)


# =====================================================================================
# 7. PAGES
# =====================================================================================
def page_synthese():
    entete(0)
    candidats = [k for k, v in IND.items() if v["sens"] != 0 and not v.get("resume") and disponible(k)]
    par_axe = {}
    for k in candidats:
        par_axe.setdefault(IND[k]["axe"], []).append(k)
    # Chantiers : le pire indicateur de chaque question, puis les 3 questions les plus mal classées
    axes_chantier = {"Quand": "Quand concède-t-on ?", "Comment": "Comment concède-t-on ?",
                     "Avec ballon": "Avec le ballon", "Pressing": "Pressing & duels", "Réussite": "Réussite"}
    pires = sorted([(min(par_axe[a], key=score_ind), a) for a in axes_chantier if a in par_axe],
                   key=lambda t: score_ind(t[0]))[:3]
    meilleurs = sorted([(max(par_axe[a], key=score_ind), a) for a in axes_chantier if a in par_axe],
                       key=lambda t: -score_ind(t[0]))[:3]
    st.markdown("Les cartes sont **choisies automatiquement**, **une par question** pour que chacune apporte une "
                "information différente : pour chaque question (Quand ? Comment ? Avec le ballon ? Pressing ? "
                "Réussite ?), l'indicateur le plus mal classé, puis les 3 questions les plus préoccupantes.")
    titre(f"Le problème n°1 : {fmt(NOUS['xg_contre_m'], 2)} xG concédés par match "
          f"({ordinal(rang('xg_contre_m', -1))} / {NB})", "les cartes ci-dessous découpent ce problème")
    st.markdown(f'<div class="titre" style="border-left-color:{ROUGE}">Nos 3 chantiers prioritaires</div>',
                unsafe_allow_html=True)
    rangee([k for k, _ in pires], sur_titres=[axes_chantier[a] for _, a in pires])
    st.markdown(f'<div class="titre" style="border-left-color:{VERT}">Nos 3 points forts (à protéger)</div>',
                unsafe_allow_html=True)
    rangee([k for k, _ in meilleurs], sur_titres=[axes_chantier[a] for _, a in meilleurs])

    titre("Le fil rouge", "la question qui ressort des données, et où aller la creuser")
    lecture(f"{EQUIPE} concède **{fmt(NOUS['xg_contre_m'], 2)} xG par match**, dont **{fmt(NOUS['part_xga_2mt'], 0)} % "
            f"après la pause**. La tranche **61-75** cumule le pic de xG concédés "
            f"({fmt(NOUS['xga_61-75_m'], 2)}, {ordinal(rang('xga_61-75_m', -1))} / {NB}) et un creux offensif "
            f"({fmt(NOUS['xg_61-75_m'], 2)} xG créés, {ordinal(rang('xg_61-75_m', 1))} / {NB}) : c'est tout le bloc "
            f"qui baisse. Le danger vient surtout de **face au but** ({fmt(NOUS['xga_cote_Axe_m'], 2)} xG/match, "
            f"{ordinal(rang('xga_cote_Axe_m', -1))} / {NB}) et de **la tête** ({fmt(NOUS['xga_type_Tête_m'], 2)}, "
            f"{ordinal(rang('xga_type_Tête_m', -1))} / {NB}).")
    a_creuser(["**Quand ?** → page 2 : tranches de 15 minutes et état du score.",
               "**Comment ?** → page 3 : côté, type de tir, transitions après nos pertes.",
               "**Le pressing tient-il ?** → page 5 : PPDA par tranche, contre-pressing, récupérations.",
               "**Qui ?** → pages 6 et 7 : joueurs en difficulté à leur poste, et xG concédés selon qui joue.",
               "**Hors de ces données** : GPS (baisse physique après 60'), vidéo des grosses occasions (liste page 3)."])
    for col, (cle, t, couleur) in zip(st.columns(3), [("garde", "Ce qu'on garde", VERT),
                                                       ("corrige", "Ce qu'on corrige", ROUGE),
                                                       ("creuse", "Ce qu'on creuse cette semaine", BLEU_OM)]):
        with col:
            st.markdown(f'<div style="font-size:16px;font-weight:700;color:{couleur};border-top:3px solid {couleur};'
                        f'padding-top:6px">{t}</div>', unsafe_allow_html=True)
            note(f"synthese_{cle}", t, zone=True, hauteur=130)
    with st.expander("Comment sont choisis et classés les indicateurs ?"):
        st.markdown(
            f"- Les indicateurs FotMob sont comparés aux {NB} clubs des 5 championnats ; ceux tirés des événements "
            "WhoScored (pertes, récupérations, PPDA réel) aux clubs de Ligue 1.\n"
            "- **Point fort** = premier tiers des clubs, **point faible** = dernier tiers, en tenant compte du sens.\n"
            "- Les indicateurs « parapluie » (xG concédés au total, différence de xG, points) ne sont pas repris dans "
            "les cartes : ils résument les autres.\n"
            "- Les découpages par mi-temps, tranche, côté et état du score additionnent les xG de chaque tir : le "
            "total peut différer de quelques centièmes du total officiel (penaltys notamment).")


def page_1():
    entete(1)
    rangee(["1.1", "1.2", "1.3"])
    rangee(["1.4", "1.5"])
    g, d = st.columns(2)
    with g:
        bloc("Résultats et xG, match par match", trace_matchs, "barres = xG créés (bleu) et concédés (rouge)")
    with d:
        bloc("Production vs concession : les 96 clubs",
             lambda: nuage_equipes("xg_m", "xg_contre_m", "xG créés par match →", "← xG concédés par match",
                                   inverser_y=True,
                                   quadrants=[(0.98, 0.98, "domine ses matchs"), (0.02, 0.02, "subit ses matchs")]),
             "en haut à droite = crée beaucoup et concède peu ; noms = clubs de Ligue 1")
    pas_gagnes = MATCHS[MATCHS["a_mene"] & (MATCHS["resultat"] != "V")]
    if len(pas_gagnes):
        lecture("Matchs où l'on a mené sans gagner : " + ", ".join(
            f"**{r.adversaire}** ({r.bp}-{r.bc}, {fmt(r.xga_2mt, 2)} xG concédés en 2e MT)" for r in pas_gagnes.itertuples()))
    a_creuser([f"Si 1.2 est négatif, les résultats actuels ({fmt(NOUS['pts_m'], 2)} pts/match) sont-ils durables ?",
               "Revoir en vidéo les matchs où l'avance a été perdue (liste ci-dessus) : même scénario à chaque fois ?"])


def trace_matchs():
    m = MATCHS
    fig, ax = graphique((7, 3.4))
    x = np.arange(len(m))
    ax.bar(x - 0.2, m["xg"], 0.4, color=BLEU_OM, label="xG créés")
    ax.bar(x + 0.2, m["xga"], 0.4, color=ROUGE, alpha=0.8, label="xG concédés")
    for k, r in enumerate(m.itertuples()):
        coul = {"V": VERT, "N": GRIS, "D": ROUGE}[r.resultat]
        ax.text(k, max(r.xg, r.xga) + 0.12, f"{r.bp}-{r.bc}", ha="center", fontsize=8, color=coul, fontweight="bold")
    ax.set_xticks(x, [f"{a[:10]}\n{l}" for a, l in zip(m["adversaire"], m["lieu"])], fontsize=7, rotation=45, ha="right")
    ax.legend(frameon=False, fontsize=8)
    afficher(fig)


EXPLICATION_ETAT = ("**Comment lire « pour 90 minutes passées à mener »** : on additionne les xG concédés pendant "
                    "toutes les minutes où l'on menait au score, et on ramène ce total à 90 minutes. "
                    "« 2,77 » veut dire : *si l'on menait pendant tout un match, on concéderait 2,77 xG à ce rythme*. "
                    "Cela permet de comparer les trois situations même si l'on n'y passe pas le même temps.")


def page_2():
    entete(2)
    rangee(["2.2", "2.3", "2.4", "1.5"])
    g, d = st.columns(2)
    with g:
        bloc("xG concédés par tranche de 15 minutes",
             lambda: barres_comparees([f"xga_{t}_m" for t in TRANCHES], TRANCHES, "xG concédés / match"),
             "les tranches 31-45+ et 76-90+ incluent le temps additionnel")
        pires = sorted(TRANCHES, key=lambda t: NOUS[f"xga_{t}_m"] / moy(f"xga_{t}_m"), reverse=True)[:2]
        lecture("Tranches les plus préoccupantes (écart à la moyenne) : " + ", ".join(
            f"**{t}** ({fmt(NOUS[f'xga_{t}_m'], 2)} contre {fmt(moy(f'xga_{t}_m'), 2)}, "
            f"{ordinal(rang(f'xga_{t}_m', -1))} / {NB})" for t in pires))
    with d:
        bloc("1re et 2e mi-temps, match par match", trace_mi_temps,
             "xG concédés ; chiffres sous les barres = minute de notre 1er changement")
        pire = MATCHS.sort_values("xga_2mt", ascending=False).head(3)
        lecture("Pires 2es mi-temps : " + ", ".join(
            f"**{r.adversaire}** ({fmt(r.xga_2mt, 2)} xG, 1er changement à la {int(r.min_1er_changement)}')"
            for r in pire.itertuples()))

    titre("Selon le score", "xG concédés pour 90 minutes passées dans chaque situation")
    mode_emploi(EXPLICATION_ETAT)
    rangee(["2.5", "2.6", "2.7"])
    g, d = st.columns(2)
    with g:
        bloc("xG concédés selon le score",
             lambda: barres_comparees(["xga90_Mène", "xga90_Nul", "xga90_Mené"],
                                      ["Quand on mène", "À égalité", "Quand on est mené"], "xG concédés / 90 min"), "")
    with d:
        bloc("Temps passé dans chaque situation",
             lambda: barres_comparees(["part_temps_Mène", "part_temps_Nul", "part_temps_Mené"],
                                      ["Mène", "Égalité", "Mené"], "% du temps de jeu", d=0), "")
    lecture(f"On concède beaucoup **dans toutes les situations** : {fmt(NOUS['xga90_Mène'], 2)} quand on mène, "
            f"{fmt(NOUS['xga90_Nul'], 2)} à égalité, {fmt(NOUS['xga90_Mené'], 2)} mené (moyennes : "
            f"{fmt(moy('xga90_Mène'), 2)}, {fmt(moy('xga90_Nul'), 2)}, {fmt(moy('xga90_Mené'), 2)}). Le problème n'est "
            "donc pas seulement la gestion d'un avantage : c'est l'organisation de base.")
    a_creuser([
        "**Physique** : les données GPS du club montrent-elles une baisse (distance, sprints) après 60' ? "
        "FotMob ne donne pas ces chiffres pour la Ligue 1.",
        "**Pressing** : le PPDA par tranche (page 5) se dégrade-t-il en même temps que les xG concédés ?",
        "**Changements** : le 1er changement arrive-t-il trop tard dans les matchs où la 2e MT dérape ?",
        "**Adversaire** : les équipes qui nous ont fait mal en 2e MT ont-elles changé de système ? (page Détail)"])
    note("decision_page2", "✎ Décision sur la gestion du match", zone=True, hauteur=90)


def trace_mi_temps():
    m = MATCHS
    fig, ax = graphique((7, 3.4))
    x = np.arange(len(m))
    ax.bar(x, m["xga_1mt"], 0.6, color="#8A94A0", label="1re MT")
    ax.bar(x, m["xga_2mt"], 0.6, bottom=m["xga_1mt"], color=ORANGE, label="2e MT")
    for k, r in enumerate(m.itertuples()):
        ax.text(k, -0.35, str(r.minutes_changements).split(" ")[0] if isinstance(r.minutes_changements, str) else "",
                ha="center", fontsize=7, color=GRIS)
    ax.set_ylim(-0.5, None)
    ax.set_xticks(x, [a[:10] for a in m["adversaire"]], fontsize=7, rotation=45, ha="right")
    ax.legend(frameon=False, fontsize=8)
    afficher(fig)


# ------------------------------------------------------------------ PAGE 3
TYPES_PASSE = ["Centre", "Long ballon aérien dans la surface", "Remise en retrait", "Passe en profondeur",
               "Passe courte / combinaison", "2e ballon : rebond après arrêt ou tir contré",
               "2e ballon : après un dégagement", "2e ballon : après un duel ou un contrôle raté",
               "Ballon perdu par nous", "Récupération ou dribble adverse", "Coup de pied arrêté"]
DEFINITIONS_PASSE = {
    "Centre": "centre dans le jeu (hors corner / coup franc), quelle que soit la distance.",
    "Long ballon aérien dans la surface": "passe longue ou levée (≥ 25 m ou « long ballon ») qui tombe dans notre "
                                          "surface sans être notée comme un centre.",
    "Remise en retrait": "passe en retrait depuis le bord de la surface ou la ligne de but.",
    "Passe en profondeur": "passe dans le dos de notre défense.",
    "Passe courte / combinaison": "toute autre passe : remises, une-deux, passes dans les pieds autour et dans "
                                  "notre surface.",
    "2e ballon : rebond après arrêt ou tir contré": "notre gardien arrête ou un joueur contre, l'adversaire reprend.",
    "2e ballon : après un dégagement": "on dégage, le ballon ne sort pas de la zone et l'adversaire frappe.",
    "2e ballon : après un duel ou un contrôle raté": "on touche le ballon (duel, contrôle, déviation) sans le "
                                                     "sécuriser, l'adversaire frappe.",
    "Ballon perdu par nous": "passe ratée, dépossédé ou erreur de notre part juste avant le tir.",
    "Récupération ou dribble adverse": "l'adversaire récupère ou élimine seul, sans passe.",
    "Coup de pied arrêté": "corner, coup franc, touche.",
}


def barres_horizontales(cols, etiquettes, df, nous, lib_moy, titre_x, d=2, taille=None):
    """Barres horizontales triées : nous (bleu) et la moyenne (gris), écart écrit au bout."""
    vals = [(nous[c], df[c].mean(), e) for c, e in zip(cols, etiquettes)]
    vals.sort(key=lambda t: t[0])
    fig, ax = graphique(taille or (7, 0.42 * len(vals) + 0.8))
    y = np.arange(len(vals))
    ax.barh(y + 0.18, [v[0] for v in vals], 0.36, color=BLEU_OM, label=EQUIPE)
    ax.barh(y - 0.18, [v[1] for v in vals], 0.36, color="#B9C0B4", label=lib_moy)
    for yy, (n, m, _) in zip(y, vals):
        ax.text(n + 0.005, yy + 0.18, f"{fmt(n, d)}" + (f"  (×{fmt(n / m, 1)})" if m > 0.005 and n / m >= 1.4 else ""),
                va="center", fontsize=8, color=BLEU_OM, fontweight="bold")
    ax.set_yticks(y, [v[2] for v in vals], fontsize=8.5)
    ax.set_xlabel(titre_x, color=GRIS, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    afficher(fig)


def references_defensives():
    """Les clubs de Ligue 1 qui défendent le mieux les centres et les seconds ballons : chiffres, système, joueurs."""
    titre("Les références : qui défend le mieux ce qui nous pose problème ?",
          "clubs de Ligue 1 — le danger est rapporté au nombre de situations, pour distinguer « subit peu de centres » "
          "et « défend bien les centres »")
    sujet = st.radio("Sujet", ["Centres adverses", "Seconds ballons dans notre surface"], horizontal=True)
    systemes = {sans_accents(e): s_ for e, s_ in zip(L1["equipe"], L1["systeme"])} if "systeme" in L1.columns else {}
    aeriens = {sans_accents(e): v for e, v in zip(L1["equipe"], L1["pct_duels_aeriens"])}
    w = WS.copy()
    w["Système"] = w["equipe"].map(lambda e: systemes.get(sans_accents(e), ""))
    w["% duels aériens"] = w["equipe"].map(lambda e: aeriens.get(sans_accents(e), np.nan))
    if sujet == "Centres adverses":
        x, y, cle = "centres_adv_match", "pct_centres_suivis_tir", "xg_apres_centres_match"
        lib_x, lib_y = "← centres adverses par match (laisse centrer)", "← % des centres suivis d'un tir en 10 s"
        cols = {"equipe": "Club", "centres_adv_match": "Centres subis /match", "pct_centres_reussis_adv": "% centres réussis",
                "pct_centres_suivis_tir": "% suivis d'un tir", "xg_apres_centres_match": "xG après centres /match",
                "% duels aériens": "% duels aériens", "Système": "Système"}
        quad = [(0.98, 0.98, "subit peu de centres et les défend bien"), (0.02, 0.02, "laisse centrer et se fait punir")]
    else:
        x, y, cle = "interventions_surface_match", "pct_interventions_suivies_tir", "xg_apres_interventions_match"
        lib_x, lib_y = "← nos interventions dans la surface par match", "← % suivies d'un tir adverse en 10 s"
        cols = {"equipe": "Club", "interventions_surface_match": "Interventions /match",
                "pct_interventions_suivies_tir": "% suivies d'un tir", "xg_apres_interventions_match": "xG après /match",
                "xga_second_ballon_match": "xG 2e ballon /match", "% duels aériens": "% duels aériens", "Système": "Système"}
        quad = [(0.98, 0.98, "peu sollicité et sécurise le 2e ballon"), (0.02, 0.02, "très sollicité, 2e ballon perdu")]
    g, d = st.columns([1, 1.15])
    with g:
        try:
            nuage_l1(x, y, lib_x, lib_y, inverser_x=True, inverser_y=True, quadrants=quad)
        except Exception as erreur:
            st.info(f"Visuel indisponible : {erreur}")
    with d:
        t = w.sort_values(y)[list(cols)].rename(columns=cols)
        fmt_ = {c: "{:.1f}" for c in t.columns if c not in ("Club", "Système")}
        fmt_.update({c: "{:.2f}" for c in t.columns if c.startswith("xG")})
        st.dataframe(t.style.format(fmt_).apply(lambda r: ["background-color:#E0ECF8;font-weight:600"
                                                           if r["Club"] == NOM_WS else "" for _ in r], axis=1),
                     hide_index=True, height=38 + 35 * len(t))
    meilleurs = w.sort_values(y).head(3)
    lecture(f"{EQUIPE} : **{fmt(WS_NOUS[y], 1)} %** ({ordinal(int((WS[y] < WS_NOUS[y]).sum() + 1))} / {len(WS)}). "
            "Les références : " + " ; ".join(f"**{r.equipe}** ({fmt(getattr(r, y), 1)} %, {r.Système.split(',')[0]})"
                                             for r in meilleurs.itertuples()) + ".")

    # ---- joueurs de référence
    fm = JOUEURS[JOUEURS["ligue"] == LIGUE][["joueur_id", "% duels aériens gagnés", "Duels aériens gagnés /90"]].copy()
    fm["jid"] = pd.to_numeric(fm["joueur_id"], errors="coerce")
    jr = WS_JOUEURS.assign(jid=pd.to_numeric(WS_JOUEURS["joueur_id"], errors="coerce")) \
        .merge(fm.drop(columns="joueur_id").drop_duplicates("jid"), on="jid", how="left")
    g, d = st.columns(2)
    with g:
        st.markdown("**Défenseurs centraux : les airs** (Ligue 1, ≥ 450 min)")
        dc = jr[(jr["poste"] == "Défenseur central") & (jr["minutes_ws"] >= MIN_JOUEUR)].copy()
        dc = dc.sort_values(["aeriens_perdus_tir_90", "% duels aériens gagnés"], ascending=[True, False])
        nous_dc = dc[dc["equipe"] == NOM_WS]
        t = pd.concat([dc[dc["equipe"] != NOM_WS].head(6), nous_dc])
        t = t[["joueur", "equipe", "% duels aériens gagnés", "Duels aériens gagnés /90", "aeriens_perdus_tir_90",
               "duels_perdus_tir_90"]].rename(columns={"joueur": "Joueur", "equipe": "Club",
                                                       "aeriens_perdus_tir_90": "Aériens perdus → tir /90",
                                                       "duels_perdus_tir_90": "Duels perdus → tir /90"})
        st.dataframe(t.style.format({c: "{:.2f}" for c in t.columns[2:]})
                     .apply(lambda r: ["background-color:#E0ECF8" if r["Club"] == NOM_WS else "" for _ in r], axis=1),
                     hide_index=True)
    with d:
        st.markdown("**Latéraux : laisser centrer, et se faire punir** (Ligue 1, ≥ 450 min)")
        lat = jr[(jr["poste"] == "Latéral / piston") & (jr["minutes_ws"] >= MIN_JOUEUR) & (jr["cote"] != "Axe")].copy()
        lat["% centres punis"] = lat["centres_adv_cote_tir"] / lat["centres_adv_cote"].replace(0, np.nan) * 100
        lat = lat.sort_values("xg_apres_centres_adv_cote_90")
        t = pd.concat([lat[lat["equipe"] != NOM_WS].head(6), lat[lat["equipe"] == NOM_WS]])
        t = t[["joueur", "equipe", "cote", "centres_adv_cote_90", "% centres punis", "xg_apres_centres_adv_cote_90"]] \
            .rename(columns={"joueur": "Joueur", "equipe": "Club", "cote": "Côté",
                             "centres_adv_cote_90": "Centres adverses de son côté /90",
                             "xg_apres_centres_adv_cote_90": "xG après ces centres /90"})
        st.dataframe(t.style.format({"Centres adverses de son côté /90": "{:.1f}", "% centres punis": "{:.0f} %",
                                     "xG après ces centres /90": "{:.2f}"})
                     .apply(lambda r: ["background-color:#E0ECF8" if r["Club"] == NOM_WS else "" for _ in r], axis=1),
                     hide_index=True)
        st.caption(f"Médiane des latéraux de {LIGUE} : {fmt(lat['centres_adv_cote_90'].median(), 1)} centres de leur côté "
                   f"/90, {fmt(lat['% centres punis'].median(), 0)} % punis, "
                   f"{fmt(lat['xg_apres_centres_adv_cote_90'].median(), 2)} xG /90.")
    with st.expander("Et en Europe : les équipes qui concèdent le moins de la tête (5 championnats)"):
        e = EQ.sort_values("xga_type_Tête_m").head(10)[["equipe", "ligue", "xga_type_Tête_m", "pct_duels_aeriens",
                                                        "xg_contre_m", "systeme"]]
        e.columns = ["Club", "Ligue", "xG concédés de la tête /match", "% duels aériens", "xG concédés /match", "Système"]
        st.dataframe(e.style.format({"xG concédés de la tête /match": "{:.2f}", "% duels aériens": "{:.0f}",
                                     "xG concédés /match": "{:.2f}"}), hide_index=True)
    a_creuser(["Revoir en vidéo 2 ou 3 matchs des clubs de référence contre des équipes qui centrent beaucoup : "
               "où se placent les centraux au point de chute, qui couvre l'entrée de surface pour le 2e ballon, "
               "le latéral côté opposé ferme-t-il le second poteau ?",
               "Le système compte-t-il ? Comparer les références à 3 défenseurs centraux et celles à 4.",
               "Profils de latéraux qui laissent peu centrer : ils cadrent tôt le porteur — à comparer avec nos "
               "latéraux (tableau de droite)."], "À étudier chez les références")


def page_3():
    entete(3)
    rangee(["3.1", "3.2", "3.3"])
    g, d = st.columns(2)
    with g:
        bloc("Volume ou qualité ?",
             lambda: nuage_equipes("tirs_contre_m", "xga_par_tir", "← tirs concédés par match",
                                   "← xG par tir concédé", inverser_x=True, inverser_y=True,
                                   quadrants=[(0.98, 0.98, "peu de tirs, peu dangereux"),
                                              (0.02, 0.02, "beaucoup de tirs, dangereux")]),
             "en haut à droite = solide ; en bas à gauche = on concède beaucoup ET de bonne qualité")
        vol, qual = rang("tirs_contre_m", -1), rang("xga_par_tir", -1)
        lecture(f"Volume : **{ordinal(vol)} / {NB}**. Qualité : **{ordinal(qual)} / {NB}**. "
                + ("Le problème est d'abord le **volume**." if vol > qual else
                   "Le problème est d'abord la **qualité** des tirs concédés : on laisse tirer de près."))
    with d:
        cols = ["Jeu placé", "Contre-attaque", "Corner", "Autre CPA", "Coup franc direct", "Penalty"]
        bloc("xG concédés par situation",
             lambda: barres_comparees([f"xga_sit_{c}_m" for c in cols],
                                      ["Jeu\nplacé", "Contre", "Corner", "Autre\nCPA", "CF\ndirect", "Penalty"],
                                      "xG concédés / match"), "")
        pire = max(cols, key=lambda c: NOUS[f"xga_sit_{c}_m"] - moy(f"xga_sit_{c}_m"))
        lecture(f"Plus gros écart à la moyenne : **{pire}** ({fmt(NOUS[f'xga_sit_{pire}_m'], 2)} xG/match contre "
                f"{fmt(moy(f'xga_sit_{pire}_m'), 2)}, {ordinal(rang(f'xga_sit_{pire}_m', -1))} / {NB}).")

    # ---------------- CE QUI AMÈNE LE TIR
    titre("Qu'est-ce qui amène le tir adverse ?", "dernière passe de l'adversaire, ou ce qui s'est passé juste avant "
                                                  "quand il n'y a pas eu de passe (Ligue 1, WhoScored)")
    if not WS_OK:
        message_whoscored()
    else:
        g, d = st.columns([1.25, 1])
        with g:
            bloc("xG concédés par type d'action", lambda: barres_horizontales(
                [f"xga_passe_{t}_match" for t in TYPES_PASSE], TYPES_PASSE, WS, WS_NOUS, f"Moy. {LIGUE}",
                "xG concédés / match (×2,1 = deux fois la moyenne)"), "")
        with d:
            ecarts = sorted(TYPES_PASSE, key=lambda t: WS_NOUS[f"xga_passe_{t}_match"] - WS[f"xga_passe_{t}_match"].mean(),
                            reverse=True)[:3]
            lecture("Plus gros écarts avec la Ligue 1 : " + " ; ".join(
                f"**{t}** ({fmt(WS_NOUS[f'xga_passe_{t}_match'], 2)} contre {fmt(WS[f'xga_passe_{t}_match'].mean(), 2)})"
                for t in ecarts) + ".")
            tc = WS_TIRS[WS_TIRS["type_passe"] != "Penalty"]
            croise = pd.crosstab(tc["type_passe"], tc["partie_corps"], values=tc["xg"], aggfunc="sum").fillna(0)
            croise = croise.reindex([t for t in TYPES_PASSE if t in croise.index])
            croise["Total"] = croise.sum(axis=1)
            st.markdown("**Tête ou pied, selon ce qui amène le tir** (xG concédés, total saison)")
            st.dataframe(croise.style.format("{:.2f}").background_gradient(cmap="Reds", axis=None),
                         height=38 + 35 * len(croise))
            with st.expander("Définition de chaque type"):
                for t, dfn in DEFINITIONS_PASSE.items():
                    st.markdown(f"- **{t}** : {dfn}")

        # ---------------- BALLONS AÉRIENS
        titre("Les ballons aériens dans notre surface",
              "tir adverse dans les 10 s qui suivent un centre ou un long ballon aérien dans notre surface — même si on "
              "a d'abord repoussé (c'est là que se jouent le duel au point de chute et le 2e ballon)")
        rangee(["3.8", "3.5"])
        g, d = st.columns(2)
        aer = WS_TIRS[WS_TIRS["ballon_aerien_10s"] & (WS_TIRS["type_passe"] != "Penalty")].copy()
        with g:
            bloc("De quel côté part le ballon aérien ?",
                 lambda: barres_comparees([f"xga_aerien_{c}_match" for c in COTES], ["Notre gauche", "Axe",
                                                                                     "Notre droite"],
                                          "xG concédés / match", df=WS, nous=WS_NOUS, lib_moy=f"Moy. {LIGUE}"), "")
        with d:
            aer["Distance"] = pd.cut(aer["aerien_distance_but_m"], [0, 20, 30, 200],
                                     labels=["< 20 m (centre au ras de la surface)", "20 à 30 m",
                                             "> 30 m (centre ou ballon long de loin)"])
            t = aer.groupby(["aerien_type", "Distance"], observed=True).agg(Tirs=("xg", "size"), xG=("xg", "sum"),
                                                                             Têtes=("partie_corps",
                                                                                    lambda s: int((s == "Tête").sum())))
            st.markdown("**D'où part le ballon aérien** (distance à notre but)")
            st.dataframe(t.reset_index().rename(columns={"aerien_type": "Type"}).style.format({"xG": "{:.2f}"}),
                         hide_index=True)
            loin = aer[aer["aerien_distance_but_m"] > 30]
            if len(aer):
                lecture(f"**{fmt(loin['xg'].sum() / aer['xg'].sum() * 100, 0)} % du danger aérien** vient de ballons "
                        f"partis à **plus de 30 m** de notre but ({len(loin)} tirs) : des centres de loin et des longs "
                        "ballons, pas des débordements jusqu'à la ligne. Le porteur a le temps de lever la tête : "
                        "le cadrer plus tôt, et le marquage au point de chute est en cause.")
        cote_pire = max(COTES, key=lambda c: WS_NOUS[f"xga_aerien_{c}_match"] - WS[f"xga_aerien_{c}_match"].mean())
        lecture(f"**{fmt(WS_NOUS['tirs_aerien_10s_match'], 1)} tirs par match** suivent un ballon aérien dans notre "
                f"surface (moyenne {LIGUE} : {fmt(WS['tirs_aerien_10s_match'].mean(), 1)}), pour "
                f"**{fmt(WS_NOUS['xga_aerien_10s_match'], 2)} xG** (moyenne {fmt(WS['xga_aerien_10s_match'].mean(), 2)}). "
                f"Le côté le plus exposé : **{ {'Gauche': 'notre gauche', 'Droite': 'notre droite', 'Axe': 'l’axe'}[cote_pire] }** "
                f"({fmt(WS_NOUS[f'xga_aerien_{cote_pire}_match'], 2)} xG/match).")

        # ---------------- SECONDS BALLONS
        titre("Les seconds ballons : passivité après un arrêt, un dégagement ou un duel ?",
              "l'adversaire frappe sans avoir fait de passe, juste après que l'un des nôtres a touché le ballon")
        c1, _ = st.columns(2)
        with c1:
            carte_kpi("3.9")
        g, d = st.columns([1, 1.25])
        sb = [t for t in TYPES_PASSE if t.startswith("2e ballon")]
        with g:
            bloc("Seconds ballons concédés, par origine",
                 lambda: barres_comparees([f"xga_passe_{t}_match" for t in sb],
                                          ["Rebond après\narrêt / contre", "Après un\ndégagement",
                                           "Après un duel /\ncontrôle raté"],
                                          "xG concédés / match", df=WS, nous=WS_NOUS, lib_moy=f"Moy. {LIGUE}"), "")
        with d:
            s = WS_TIRS[WS_TIRS["type_passe"].isin(sb)].sort_values("xg", ascending=False)
            t = s[["adversaire", "minute", "intervention_nous", "type_passe", "tireur", "partie_corps", "xg", "but"]].copy()
            t["type_passe"] = t["type_passe"].str.replace("2e ballon : ", "")
            t["minute"] = t["minute"].astype(int).astype(str) + "'"
            t.columns = ["Adversaire", "Min.", "Notre dernier contact", "Origine", "Tireur", "Corps", "xG", "But"]
            st.markdown("**La liste vidéo des seconds ballons** — qui a touché le ballon en dernier chez nous")
            st.dataframe(t, hide_index=True, height=min(38 + 35 * len(t), 380),
                         column_config={"xG": st.column_config.ProgressColumn("xG", format="%.2f", min_value=0,
                                                                              max_value=1)})
        qui = s["intervention_nous"].str.replace(r" \(.*\)", "", regex=True).value_counts().head(3)
        lecture(f"**{len(s)} seconds ballons** concédés pour **{fmt(s['xg'].sum(), 1)} xG** "
                f"({fmt(WS_NOUS['xga_second_ballon_match'], 2)} par match, moyenne {LIGUE} : "
                f"{fmt(WS['xga_second_ballon_match'].mean(), 2)}). Derniers contacts les plus fréquents : "
                + ", ".join(f"**{n}** ({k})" for n, k in qui.items()) + ".")

    if WS_OK and "pct_centres_suivis_tir" in WS.columns:
        references_defensives()

    # ---------------- PAR QUEL CÔTÉ ?
    titre("Par quel côté ?", "notre gauche / face au but / notre droite, vu depuis notre but")
    rangee(["3.4", "3.6"])
    g, d = st.columns(2)
    with g:
        bloc("Où le tir est-il pris ? (tous les clubs)",
             lambda: barres_comparees([f"xga_cote_{c}_m" for c in COTES],
                                      ["Notre gauche", "Face au but\n(entre les poteaux)", "Notre droite"],
                                      "xG concédés / match"),
             "FotMob : position du tireur")
    with d:
        if WS_OK:
            bloc("D'où part l'action ? (Ligue 1)",
                 lambda: barres_comparees([f"xga_origine_{c}_match" for c in COTES],
                                          ["Notre gauche", "Axe", "Notre droite"], "xG concédés / match",
                                          df=WS, nous=WS_NOUS, lib_moy=f"Moy. {LIGUE}"),
                 "couloir de la dernière passe (ou du ballon aérien) avant le tir")
        else:
            message_whoscored()
    lecture(f"Face au but : **{fmt(NOUS['xga_cote_Axe_m'], 2)}** xG/match ({ordinal(rang('xga_cote_Axe_m', -1))} / "
            f"{NB}). Les côtés comptent surtout comme **point de départ** du danger (centres, remises) : voir le "
            "graphique de droite et la page 7 (xG concédés par côté selon les joueurs alignés).")

    # ---------------- CARTE + LISTE VIDÉO
    contre = TIRS[TIRS["camp"] == "contre"]
    g, d = st.columns([1, 1.2])
    with g:
        moment = st.radio("Tirs affichés", ["Tous", "1re mi-temps", "2e mi-temps", "Quand on mène", "Têtes"],
                          horizontal=True)
        sel = {"Tous": contre, "1re mi-temps": contre[contre["mi_temps"] == 1],
               "2e mi-temps": contre[contre["mi_temps"] == 2], "Quand on mène": contre[contre["etat_score"] == "Mène"],
               "Têtes": contre[contre["categorie"] == "Tête"]}[moment]
        bloc("D'où l'adversaire tire-t-il ?", lambda: carte_tirs(sel, f"{len(sel)} tirs · {fmt(sel['xg'].sum(), 1)} xG"),
             "taille = xG du tir ; notre but en haut, notre gauche à droite de l'image")
    with d:
        titre("Les grosses occasions concédées : la liste vidéo", "à revoir en priorité (xG ≥ 0,25)")
        g_occ = contre[contre["xg"] >= 0.25].sort_values("xg", ascending=False)
        t = g_occ[["adversaire", "minute", "etat_score", "joueur", "situation", "categorie", "xg"]].copy()
        t["minute"] = t["minute"].astype(int).astype(str) + "'"
        t.columns = ["Adversaire", "Min.", "Score (nous)", "Tireur", "Situation", "Type", "xG"]
        st.dataframe(t, hide_index=True, height=min(38 + 35 * len(t), 420),
                     column_config={"xG": st.column_config.ProgressColumn("xG", format="%.2f", min_value=0, max_value=1)})
    a_creuser(["**Ballons aériens** : qui laisse centrer (latéral, ailier qui ne revient pas) et qui perd le duel au "
               "point de chute ? (page 6 : duels aériens perdus suivis d'un tir)",
               "**Seconds ballons** : après un arrêt ou un dégagement, qui attaque le ballon ? Consigne possible : un "
               "milieu dédié à la zone de 2e ballon (entrée de surface) sur les centres adverses.",
               "**Combinaisons courtes dans la surface** : le milieu défensif redescend-il entre les centraux quand un "
               "latéral sort ?"])
    note("decision_page3", "✎ Décision sur l'organisation défensive", zone=True, hauteur=90)



# ------------------------------------------------------------------ PAGE 4
def page_4():
    entete(6)
    rangee(["4.1", "4.2", "4.3", "4.4"])

    titre("Baisse de régime ? Ce qu'on crée et ce qu'on concède, tranche par tranche",
          "même échelle pour les deux courbes ; pointillés = moyenne des 5 championnats")

    def courbes():
        fig, ax = graphique((9, 3.4))
        x = np.arange(len(TRANCHES))
        cree = [NOUS[f"xg_{t}_m"] for t in TRANCHES]
        conc = [NOUS[f"xga_{t}_m"] for t in TRANCHES]
        ax.plot(x, cree, marker="o", color=BLEU_OM, lw=2.2, label="xG créés")
        ax.plot(x, conc, marker="o", color=ROUGE, lw=2.2, label="xG concédés")
        ax.plot(x, [moy(f"xg_{t}_m") for t in TRANCHES], color=GRIS, lw=1, ls=":", label="moyenne (créés = concédés)")
        ax.fill_between(x, cree, conc, where=np.array(conc) > np.array(cree), color=ROUGE, alpha=0.08)
        for k, (a, b) in enumerate(zip(cree, conc)):
            ax.text(k, a + 0.02, fmt(a, 2), ha="center", fontsize=8, color=BLEU_OM)
            ax.text(k, b + 0.02, fmt(b, 2), ha="center", fontsize=8, color=ROUGE)
        ax.set_xticks(x, TRANCHES)
        ax.set_ylabel("xG / match", color=GRIS, fontsize=9)
        ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
        afficher(fig)
    try:
        courbes()
    except Exception as erreur:
        st.info(f"Visuel indisponible : {erreur}")
    meilleure = max(TRANCHES, key=lambda t: NOUS[f"xg_{t}_m"] - moy(f"xg_{t}_m"))
    pire = min(TRANCHES, key=lambda t: NOUS[f"xg_{t}_m"] - moy(f"xg_{t}_m"))
    lecture(f"Notre meilleure tranche offensive : **{meilleure}** ({fmt(NOUS[f'xg_{meilleure}_m'], 2)} xG créés, "
            f"{ordinal(rang(f'xg_{meilleure}_m', 1))} / {NB}). La plus faible : **{pire}** "
            f"({fmt(NOUS[f'xg_{pire}_m'], 2)}, {ordinal(rang(f'xg_{pire}_m', 1))} / {NB}), au moment où l'on concède "
            f"{fmt(NOUS[f'xga_{pire}_m'], 2)} xG ({ordinal(rang(f'xga_{pire}_m', -1))} / {NB}).")
    rangee(["4.6"])

    titre("Ce qu'on crée selon le score", "xG créés pour 90 minutes passées dans chaque situation")
    mode_emploi(EXPLICATION_ETAT.replace("concédés", "créés").replace("concéderait", "créerait"))
    g, d = st.columns([1.2, 1])
    with g:
        bloc("xG créés et concédés selon le score",
             lambda: barres_comparees(["xg90_Mène", "xg90_Nul", "xg90_Mené"],
                                      ["Quand on mène", "À égalité", "Quand on est mené"], "xG créés / 90 min"),
             "bleu = nous ; gris = moyennes")
    with d:
        t = pd.DataFrame({
            "Situation": ["Quand on mène", "À égalité", "Quand on est mené"],
            "xG créés /90": [NOUS["xg90_Mène"], NOUS["xg90_Nul"], NOUS["xg90_Mené"]],
            "xG concédés /90": [NOUS["xga90_Mène"], NOUS["xga90_Nul"], NOUS["xga90_Mené"]],
            "% du temps": [NOUS["part_temps_Mène"], NOUS["part_temps_Nul"], NOUS["part_temps_Mené"]]})
        t["Bilan /90"] = t["xG créés /90"] - t["xG concédés /90"]
        st.dataframe(t.style.format({"xG créés /90": "{:.2f}", "xG concédés /90": "{:.2f}", "% du temps": "{:.0f} %",
                                     "Bilan /90": "{:+.2f}"}), hide_index=True)
        lecture(f"Quand on mène, on crée **{fmt(NOUS['xg90_Mène'], 2)}** et on concède **{fmt(NOUS['xga90_Mène'], 2)}** "
                f"par 90 min : bilan {fmt(NOUS['xg90_Mène'] - NOUS['xga90_Mène'], 2)}. On continue d'attaquer "
                f"({ordinal(rang('xg90_Mène', 1))} / {NB}), mais on s'expose : l'équipe est coupée en deux.")
    rangee(["4.5"])

    pour = TIRS[TIRS["camp"] == "pour"]
    g, d = st.columns([1, 1.2])
    with g:
        bloc("D'où tirons-nous ?", lambda: carte_tirs(pour, f"{len(pour)} tirs · {fmt(pour['xg'].sum(), 1)} xG"), "")
    with d:
        titre("Qui tire, et avec quelle réussite ?", "buts − xG : positif = finit mieux que prévu")
        t = pour.groupby("joueur").agg(tirs=("xg", "size"), xg=("xg", "sum"),
                                       buts=("resultat", lambda s: int((s == "Goal").sum()))).reset_index()
        t["buts − xG"] = t["buts"] - t["xg"]
        t = t.sort_values("xg", ascending=False).head(10)
        st.dataframe(t.rename(columns={"joueur": "Joueur", "tirs": "Tirs", "xg": "xG", "buts": "Buts"}), hide_index=True,
                     column_config={"xG": st.column_config.ProgressColumn("xG", format="%.2f", min_value=0,
                                                                          max_value=float(t["xg"].max() or 1)),
                                    "buts − xG": st.column_config.NumberColumn(format="%+.2f")})
    a_creuser(["La tranche où l'on crée le moins est-elle celle où l'on concède le plus ? Si oui : physique, "
               "changements ou consigne de gestion — à croiser avec la page 2 et le PPDA par tranche (page 5).",
               "En menant, on crée mais on concède encore plus : l'écart entre le bloc offensif et le bloc défensif "
               "est-il trop grand ? (vidéo : distances entre lignes après nos buts)"])
    note("decision_page4", "✎ Décision offensive", zone=True, hauteur=90)


# ------------------------------------------------------------------ PAGE 5
def page_5():
    entete(7)
    titre("Le pressing", "PPDA = passes que l'adversaire fait chez lui avant qu'on intervienne : plus c'est bas, plus on presse")
    rangee(["5.2", "5.5", "5.3", "5.4"])
    ecart_l1 = moy("ppda_approx", L1) - moy("ppda_approx")
    mode_emploi(
        f"**Pourquoi l'OM est bien classé en Ligue 1 et seulement moyen en Europe (★ 5.2) ?** La Ligue 1 entière presse "
        f"moins que les autres championnats sur cette mesure : moyenne {fmt(moy('ppda_approx', L1), 1)} contre "
        f"{fmt(moy('ppda_approx'), 1)} pour les 5 championnats ({'+' if ecart_l1 > 0 else ''}{fmt(ecart_l1, 1)}). "
        f"Les adversaires de Ligue 1 font en moyenne {fmt(moy('passes_adv_camp_adverse_m', L1), 0)} passes par match "
        f"dans leur moitié, contre {fmt(moy('passes_adv_camp_adverse_m'), 0)} sur l'ensemble des 5 championnats : on "
        "les laisse davantage construire. Un pressing « fort pour la Ligue 1 » est donc « moyen pour l'Europe ». "
        "Le ★ 5.2 est une approximation (FotMob ne localise pas les actions défensives) ; le ★ 5.5 est le vrai "
        "PPDA calculé sur les événements WhoScored, comparé aux clubs de Ligue 1.")

    if not WS_OK:
        titre("Contre-pressing, récupérations, transitions")
        message_whoscored()
        rangee(["3.6"])
        return

    titre("Notre pressing récupère-t-il le ballon ?", "Ligue 1 — événements WhoScored")
    rangee(["5.6", "5.7", "5.8", "5.9"])
    g, d = st.columns(2)
    with g:
        bloc("Le pressing tient-il sur 90 minutes ?", trace_ppda_tranches,
             "PPDA par tranche de 15 min : plus la courbe monte, moins on presse")
        pires = sorted(TRANCHES, key=lambda t: WS_NOUS[f"ppda_{t}"] - WS[f"ppda_{t}"].mean(), reverse=True)[:1]
        lecture(f"Tranche où notre pressing décroche le plus par rapport à la Ligue 1 : **{pires[0]}** "
                f"(PPDA {fmt(WS_NOUS[f'ppda_{pires[0]}'], 1)} contre {fmt(WS[f'ppda_{pires[0]}'].mean(), 1)}). "
                "À croiser avec la tranche où l'on concède le plus (page 2).")
    with d:
        bloc("Contre-pressing et transitions concédées",
             lambda: nuage_l1("contre_pressing_pct", "transitions_concedees_match",
                              "ballons repris en 5 s après une perte (%) →", "← tirs adverses < 15 s après notre perte",
                              inverser_y=True, quadrants=[(0.98, 0.98, "réagit vite, ne se fait pas punir"),
                                                          (0.02, 0.02, "réagit peu, se fait punir")]),
             "chaque point = un club de Ligue 1")
        lecture(f"On reprend le ballon dans les 5 s après **{fmt(WS_NOUS['contre_pressing_pct'], 0)} %** de nos pertes "
                f"(moyenne {fmt(WS['contre_pressing_pct'].mean(), 0)} %) ; **{fmt(WS_NOUS['pct_pertes_tir_adverse'], 1)} %** "
                f"de nos pertes mènent à un tir adverse en moins de 15 s (moyenne "
                f"{fmt(WS['pct_pertes_tir_adverse'].mean(), 1)} %).")

    g, d = st.columns(2)
    with g:
        bloc("Récupérer haut… et en faire quelque chose ?",
             lambda: nuage_l1("recup_hautes_match", "pct_recup_hautes_tir", "récupérations hautes par match →",
                              "% suivies d'un tir en moins de 15 s →",
                              quadrants=[(0.98, 0.98, "pressing efficace"), (0.02, 0.02, "pressing peu rentable")]),
             "le pressing est « efficace » s'il récupère haut ET si ces ballons finissent en tir")
    with d:
        bloc("Où perdons-nous les ballons qui mènent à un tir adverse ?", carte_pertes,
             "chaque point = une perte de balle dans le jeu ; rouge = tir adverse dans les 15 s")
    p = WS_PERTES
    punies = p[p["tir_15s"]]
    camp = (punies["x_perte"] < 50).mean() * 100 if len(punies) else np.nan
    lecture(f"**{len(punies)} pertes** ont mené à un tir adverse en moins de 15 s ({fmt(punies['xg_15s'].sum(), 1)} xG), "
            f"dont **{fmt(camp, 0)} % dans notre moitié**. Récupérations adverses suivies d'un tir, par tranche : "
            + ", ".join(f"{t} : {int(punies['tranche'].eq(t).sum())}" for t in TRANCHES) + ".")
    a_creuser(["**Organisation de repli** : sur les pertes « rouges » de la carte, combien de joueurs sont derrière le "
               "ballon ? Les latéraux sont-ils hauts en même temps ?",
               "**Contre-pressing** : comparer en vidéo les pertes reprises en 5 s et les autres — distance du 2e "
               "joueur au porteur adverse.",
               "**Pressing lancé** : sur les séquences où l'on récupère haut, quel déclencheur (passe en retrait, "
               "contrôle orienté vers la ligne) ? Le reproduire.",
               "Joueurs qui perdent le plus de ballons punis : page 6 (pertes suivies d'un tir adverse)."])
    note("decision_page5", "✎ Décision sur le pressing et le repli", zone=True, hauteur=90)


def trace_ppda_tranches():
    fig, ax = graphique((7, 3.2))
    x = np.arange(len(TRANCHES))
    nous = [WS_NOUS[f"ppda_{t}"] for t in TRANCHES]
    moyenne = [WS[f"ppda_{t}"].mean() for t in TRANCHES]
    ax.plot(x, nous, marker="o", color=BLEU_OM, lw=2.2, label=EQUIPE)
    ax.plot(x, moyenne, marker="o", color="#8A94A0", lw=1.4, ls="--", label=f"Moy. {LIGUE}")
    for k, v in enumerate(nous):
        ax.text(k, v + 0.3, fmt(v, 1), ha="center", fontsize=8, color=BLEU_OM)
    ax.set_xticks(x, TRANCHES)
    ax.set_ylabel("PPDA (bas = presse fort)", color=GRIS, fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    afficher(fig)


def carte_pertes():
    """Pertes vues par nous (x = 100 → but adverse), attaque vers le haut. Rouge : taille ET couleur = xG du tir adverse."""
    from mplsoccer import VerticalPitch as VP
    p = VP(pitch_type="opta", pitch_color=FOND_TERRAIN, line_color=LIGNES_TERRAIN, linewidth=1)
    fig, ax = p.draw(figsize=(4.8, 6.4))
    fig.set_facecolor("white")
    d = WS_PERTES
    ok = d[~d["tir_15s"]]
    ko = d[d["tir_15s"]].sort_values("xg_15s")
    p.scatter(ok["x_perte"], ok["y_perte"], s=8, color="#C9CFC4", alpha=0.5, ax=ax, zorder=2)
    sc = p.scatter(ko["x_perte"], ko["y_perte"], s=ko["xg_15s"].clip(upper=0.8) * 900 + 25, c=ko["xg_15s"],
                   cmap="Reds", vmin=0, vmax=0.5, edgecolors=TEXTE, linewidths=0.4, ax=ax, zorder=3)
    for _, r in ko[ko["xg_15s"] >= 0.25].iterrows():
        ax.annotate(f"{r['joueur_perte'].split()[-1]} · {fmt(r['xg_15s'], 2)}", (r["y_perte"], r["x_perte"]),
                    xytext=(6, -3), textcoords="offset points", fontsize=7, color=TEXTE,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", fraction=0.035, pad=0.02)
    cb.set_label("xG du tir adverse qui suit la perte (gris = perte sans tir)", fontsize=7.5, color=GRIS)
    cb.ax.tick_params(labelsize=7)
    ax.set_title("nous attaquons vers le haut · noms = pertes à ≥ 0,25 xG", fontsize=8.5, color=GRIS)
    afficher(fig)



# ------------------------------------------------------------------ PAGE 6 : JOUEURS
# Pour chaque famille de postes : (critère, sens, nature)
#   nature "qualité" : ce que le joueur réussit ou rate — sert à repérer « ce qui pêche »
#   nature "volume"  : quantité d'actions, dépendante du style de l'équipe et du placement — affiché comme
#                      contexte, jamais compté comme un défaut
CRITERES = {
    "Gardien": [("Buts évités (xGOT − buts) /90", 1, "qualité"), ("% arrêts", 1, "qualité"),
                ("Sorties aériennes /90", 1, "volume"), ("Sorties hors surface /90", 1, "volume"),
                ("% longs ballons", 1, "qualité"), ("Erreurs menant à un but", -1, "qualité")],
    "Défenseur central": [("% duels aériens gagnés", 1, "qualité"), ("% duels au sol gagnés", 1, "qualité"),
                          ("Dribblé /90", -1, "qualité"), ("Erreurs menant à un but", -1, "qualité"),
                          ("Fautes commises /90", -1, "qualité"), ("Passes qui cassent une ligne /90", 1, "qualité"),
                          ("% longs ballons", 1, "qualité"), ("Interceptions /90 (ajusté poss.)", 1, "volume"),
                          ("Tacles /90 (ajusté poss.)", 1, "volume"), ("Récupérations /90 (ajusté poss.)", 1, "volume"),
                          ("Dégagements /90", 1, "volume"), ("Tirs contrés /90", 1, "volume")],
    "Latéral / piston": [("Dribblé /90", -1, "qualité"), ("% duels au sol gagnés", 1, "qualité"),
                         ("% duels aériens gagnés", 1, "qualité"), ("% centres réussis", 1, "qualité"),
                         ("xA /90", 1, "qualité"), ("Occasions créées /90", 1, "qualité"),
                         ("Passes dernier tiers /90", 1, "qualité"), ("Pertes de balle (dépossédé) /90", -1, "qualité"),
                         ("Tacles /90 (ajusté poss.)", 1, "volume"), ("Interceptions /90 (ajusté poss.)", 1, "volume"),
                         ("Récupérations /90 (ajusté poss.)", 1, "volume"), ("Centres réussis /90", 1, "volume")],
    "Milieu défensif / central": [("% duels au sol gagnés", 1, "qualité"), ("% duels aériens gagnés", 1, "qualité"),
                                  ("Dribblé /90", -1, "qualité"), ("Passes qui cassent une ligne /90", 1, "qualité"),
                                  ("Passes dernier tiers /90", 1, "qualité"), ("xA /90", 1, "qualité"),
                                  ("Pertes de balle (dépossédé) /90", -1, "qualité"), ("Fautes commises /90", -1, "qualité"),
                                  ("Récupérations /90 (ajusté poss.)", 1, "volume"),
                                  ("Tacles /90 (ajusté poss.)", 1, "volume"),
                                  ("Interceptions /90 (ajusté poss.)", 1, "volume"), ("Occasions créées /90", 1, "volume")],
    "Milieu offensif": [("xG /90", 1, "qualité"), ("xA /90", 1, "qualité"), ("Grosses occasions créées /90", 1, "qualité"),
                        ("% dribbles réussis", 1, "qualité"), ("% duels au sol gagnés", 1, "qualité"),
                        ("Occasions créées /90", 1, "volume"), ("Passes dernier tiers /90", 1, "volume"),
                        ("Dribbles réussis /90", 1, "volume"), ("Touches dans la surface /90", 1, "volume"),
                        ("Pertes de balle (dépossédé) /90", -1, "volume"), ("Récupérations /90 (ajusté poss.)", 1, "volume")],
    "Ailier": [("xG /90", 1, "qualité"), ("xA /90", 1, "qualité"), ("% dribbles réussis", 1, "qualité"),
               ("Finition (xGOT − xG) /90", 1, "qualité"), ("Dribblé /90", -1, "qualité"),
               ("Tirs /90", 1, "volume"), ("Occasions créées /90", 1, "volume"), ("Dribbles réussis /90", 1, "volume"),
               ("Touches dans la surface /90", 1, "volume"), ("Centres réussis /90", 1, "volume"),
               ("Pertes de balle (dépossédé) /90", -1, "volume"), ("Récupérations /90 (ajusté poss.)", 1, "volume")],
    "Attaquant": [("xG hors penalty /90", 1, "qualité"), ("Finition (xGOT − xG) /90", 1, "qualité"),
                  ("xA /90", 1, "qualité"), ("% duels aériens gagnés", 1, "qualité"), ("% duels au sol gagnés", 1, "qualité"),
                  ("Buts /90", 1, "volume"), ("Tirs /90", 1, "volume"), ("Touches dans la surface /90", 1, "volume"),
                  ("Occasions créées /90", 1, "volume"), ("Pertes de balle (dépossédé) /90", -1, "volume"),
                  ("Récupérations /90 (ajusté poss.)", 1, "volume")],
}
# Pour chaque critère faible : (ce que ça veut dire, concrètement ; consigne / piste de travail)
EN_CLAIR = {
    "Dribblé /90": ("Se fait éliminer balle au pied",
                    "Cadrer à distance et orienter vers l'extérieur, ne pas se jeter ; vérifier que le milieu côté "
                    "ballon le couvre."),
    "% duels au sol gagnés": ("Perd ses duels au sol", "Travail d'intervention (timing, appuis) ; éviter le duel "
                                                       "isolé sans couverture."),
    "% duels aériens gagnés": ("Perd ses duels aériens", "Le protéger sur les centres et le jeu long (prise d'appui, "
                                                         "marquage au point de chute) ; travail de timing de saut."),
    "Erreurs menant à un but": ("A commis une erreur qui a coûté un but", "Revoir la séquence ; simplifier ses choix "
                                                                          "dans notre surface."),
    "Fautes commises /90": ("Fait beaucoup de fautes", "Rester debout, temporiser : chaque faute près de notre "
                                                       "surface donne un coup de pied arrêté."),
    "Passes qui cassent une ligne /90": ("Fait peu avancer le jeu par la passe",
                                         "Chercher l'appui entre les lignes plutôt que la passe latérale ; prise "
                                         "d'information avant la réception."),
    "% longs ballons": ("Jeu long imprécis", "Réserver le jeu long aux situations préparées (appel, cible aérienne)."),
    "% centres réussis": ("Centres peu précis", "Centrer moins mais mieux : entrer dans la surface ou chercher la "
                                                "remise en retrait."),
    "xA /90": ("Offre peu d'occasions de qualité à ses partenaires",
               "Chercher la dernière passe dans la surface (remise en retrait) plutôt que le centre de loin."),
    "Occasions créées /90": ("Sert peu de tirs à ses partenaires", "Plus de prises de risque dans la dernière passe."),
    "Passes dernier tiers /90": ("Amène peu le ballon dans le dernier tiers",
                                 "Se proposer plus haut, jouer vers l'avant au premier contrôle."),
    "Pertes de balle (dépossédé) /90": ("Perd souvent le ballon sous pression",
                                        "Une ou deux touches dans notre moitié ; voir plus bas si ses pertes mènent "
                                        "vraiment à des tirs adverses."),
    "xG /90": ("Se procure peu d'occasions", "Attaquer la surface plus souvent (appels au premier poteau, dans le dos)."),
    "xG hors penalty /90": ("Se procure peu d'occasions", "Plus de présence dans la surface, appels dans le dos."),
    "Grosses occasions créées /90": ("Offre peu d'occasions franches à ses partenaires (tir avec une forte chance "
                                     "de but)", "Viser la zone du point de penalty et des 6 m dans la dernière passe."),
    "% dribbles réussis": ("Échoue souvent dans ses dribbles", "Choisir le moment du 1 contre 1 : dans le dernier "
                                                               "tiers, avec un soutien derrière lui."),
    "Finition (xGOT − xG) /90": ("Cadre mal ses occasions", "Travail de finition spécifique (viser les côtés)."),
    "Buts évités (xGOT − buts) /90": ("Encaisse plus que prévu sur les tirs cadrés", "Travail spécifique gardien "
                                                                                     "(placement, appuis)."),
    "% arrêts": ("Arrête peu de tirs cadrés", "Travail spécifique gardien."),
}
EXPLICATIONS = {
    "Tacles /90 (ajusté poss.)": "volume, pas niveau : un joueur bien placé tacle peu. Ajusté à la possession. Contexte.",
    "Interceptions /90 (ajusté poss.)": "volume ajusté à la possession : dépend du bloc demandé. Contexte.",
    "Récupérations /90 (ajusté poss.)": "volume ajusté à la possession : dépend du rôle dans le pressing. Contexte.",
}
# Actions qui coûtent (WhoScored, Ligue 1) : (colonne, libellé, en clair, consigne). Plus c'est bas, mieux c'est.
COUTS = [
    ("pertes_punies_90", "Pertes suivies d'un tir adverse /90",
     "Perd des ballons qui mènent à un tir adverse en moins de 15 s",
     "Sécuriser le premier choix sous pression ; ne pas conduire dans l'axe de notre moitié."),
    ("pertes_notre_moitie_90", "Pertes dans notre moitié /90", "Perd le ballon dans notre moitié",
     "Relance plus simple ou plus directe quand l'adversaire presse haut."),
    ("duels_perdus_tir_90", "Duels perdus suivis d'un tir /90",
     "Perd des duels (au sol ou aériens) qui mènent à un tir adverse en moins de 10 s",
     "Temporiser plutôt que plonger ; ne pas engager le duel sans couverture."),
    ("dribble_subi_tir_90", "Dribblé, puis tir adverse /90", "Se fait éliminer et l'action finit en tir",
     "Cadrer à distance, orienter vers l'extérieur, demander la couverture."),
    ("aeriens_perdus_tir_90", "Duels aériens perdus suivis d'un tir /90",
     "Perd des ballons aériens qui finissent en tir", "Marquage au point de chute, prise d'appui avant le saut."),
    ("centres_adv_cote_90", "Centres adverses depuis son couloir /90",
     "Laisse centrer l'adversaire de son côté", "Cadrer plus tôt le porteur, fermer l'angle de centre ; l'ailier doit "
                                                "doubler."),
    ("fautes_notre_tiers_90", "Fautes dans notre tiers /90", "Fait des fautes près de notre surface",
     "Rester debout : chaque faute donne un coup de pied arrêté dangereux."),
    ("xg_cout_90", "xG concédés après ses pertes et duels perdus /90",
     "Ses pertes et duels perdus coûtent beaucoup de xG", "Prioriser la vidéo sur ses séquences (liste page 3 et 5)."),
]
POSTES_CENTRES = ["Latéral / piston", "Ailier"]


def criteres(poste):
    return CRITERES.get(poste, [])


def population(poste):
    return JOUEURS[(JOUEURS["poste"] == poste) & (JOUEURS["minutes"] >= MIN_JOUEUR)]


def percentile_serie(s, v, sens):
    s = s.dropna()
    if pd.isna(v) or not len(s):
        return np.nan
    return 100 * ((s < v).sum() + 0.5 * (s == v).sum()) / len(s) if sens > 0 else \
        100 * ((s > v).sum() + 0.5 * (s == v).sum()) / len(s)


def percentile(poste, crit, sens, v):
    return percentile_serie(population(poste)[crit], v, sens)


def population_ws(poste):
    return WS_JOUEURS[(WS_JOUEURS["poste"] == poste) & (WS_JOUEURS["minutes_ws"] >= MIN_JOUEUR)] \
        if WS_JOUEURS is not None else pd.DataFrame()


def couts_poste(poste):
    return [c for c in COUTS if c[0] != "centres_adv_cote_90" or poste in POSTES_CENTRES]


def ligne_ws(nom, equipe_ws=None):
    if WS_JOUEURS is None:
        return None
    eq_ws = equipe_ws or NOM_WS
    w = WS_JOUEURS[(WS_JOUEURS["equipe"] == eq_ws) & (WS_JOUEURS["joueur"].map(sans_accents) == sans_accents(nom))]
    if not len(w):
        fam = sans_accents(nom).split()[-1]
        w = WS_JOUEURS[(WS_JOUEURS["equipe"] == eq_ws) & (WS_JOUEURS["joueur"].map(lambda n: sans_accents(n).split()[-1]) == fam)]
    return w.iloc[0] if len(w) else None


def barres_percentiles(valeurs, titre_x, taille_ligne=0.38):
    """valeurs = liste de (libellé, percentile, valeur affichée, nature)."""
    fig, ax = graphique((6.6, taille_ligne * len(valeurs) + 0.6))
    y = np.arange(len(valeurs))[::-1]
    couleurs = ["#B9C3D6" if n == "volume" else ROUGE if v < 25 else ORANGE if v < 50 else "#8A94A0" if v < 75
                else VERT for _, v, _, n in valeurs]
    ax.barh(y, [0 if pd.isna(v) else v for _, v, _, _ in valeurs], color=couleurs, height=0.65)
    ax.barh(y, [100] * len(y), color="#F1F3EE", height=0.65, zorder=0)
    for yy, (lib, v, val, n) in zip(y, valeurs):
        ax.text((0 if pd.isna(v) else min(v, 100)) + 1.5, yy, f"P{fmt(v, 0)}  ({val})", va="center", fontsize=8,
                color=TEXTE)
    ax.set_yticks(y, [lib + ("  ·contexte" if n == "volume" else "") for lib, _, _, n in valeurs], fontsize=8.5)
    ax.axvline(50, color=GRIS, lw=0.7, ls=":")
    ax.set_xlim(0, 125)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel(titre_x, fontsize=8, color=GRIS)
    afficher(fig)


def diagnostic_fotmob(j, poste):
    """Critères FotMob du joueur : percentile, valeur, médiane du poste."""
    pop = population(poste)
    out = []
    for c, s, n in criteres(poste):
        out.append(dict(crit=c, sens=s, nature=n, p=percentile_serie(pop[c], j[c], s), v=j[c], med=pop[c].median()))
    return out


def diagnostic_ws(w, poste):
    pop = population_ws(poste)
    out = []
    if w is None or not len(pop):
        return out
    for col, lib, clair, consigne in couts_poste(poste):
        out.append(dict(col=col, lib=lib, clair=clair, consigne=consigne, p=percentile_serie(pop[col], w[col], -1),
                        v=w[col], med=pop[col].median()))
    return out


def nos_joueurs():
    j = JOUEURS[(JOUEURS["equipe_id"] == str(META["equipe_id"])) & JOUEURS["au_club"]
                & (JOUEURS["minutes"] >= MIN_NOS_JOUEURS) & JOUEURS["poste"].isin(CRITERES)]
    return j.sort_values("minutes", ascending=False)


def page_6():
    entete(8)
    nos = nos_joueurs()
    titre("Vue d'ensemble : ce qui pêche, joueur par joueur",
          f"joueurs encore au club ayant joué au moins {MIN_NOS_JOUEURS} min. « P20 » = mieux que 20 % des joueurs "
          "du même poste (100 = le meilleur). Un point « qui pêche » = dans les 25 % les plus faibles.")
    lignes = []
    for _, j in nos.iterrows():
        dfm = diagnostic_fotmob(j, j["poste"])
        qual = [d for d in dfm if d["nature"] == "qualité" and pd.notna(d["p"])]
        faibles = sorted([d for d in qual if d["p"] < 25], key=lambda d: d["p"])
        forts = sorted([d for d in qual if d["p"] >= 75], key=lambda d: -d["p"])
        w = ligne_ws(j["joueur"])
        dws = [d for d in diagnostic_ws(w, j["poste"]) if pd.notna(d["p"]) and d["p"] < 25]
        lignes.append({"Joueur": j["joueur"] + (" ⚠" if j["minutes"] < PETIT_ECHANTILLON else ""), "Poste": j["poste"],
                       "Min.": int(j["minutes"]),
                       "Niveau au poste": np.nanmean([d["p"] for d in qual]) if qual else np.nan,
                       "Ce qui pêche (jeu)": " · ".join(f"{EN_CLAIR.get(d['crit'], (d['crit'],))[0]} (P{fmt(d['p'], 0)})"
                                                        for d in faibles[:2]) or "–",
                       "Actions qui coûtent": " · ".join(f"{d['clair']} (P{fmt(d['p'], 0)})"
                                                         for d in sorted(dws, key=lambda d: d["p"])[:2]) or "–",
                       "Points forts": ", ".join(d["crit"] for d in forts[:2]) or "–"})
    vue = pd.DataFrame(lignes)
    st.dataframe(vue, hide_index=True, height=38 + 35 * len(vue),
                 column_config={"Niveau au poste": st.column_config.ProgressColumn(format="P%.0f", min_value=0,
                                                                                   max_value=100)})
    st.caption(f"⚠ = moins de {PETIT_ECHANTILLON} minutes : chiffres fragiles. « Niveau au poste » = moyenne des "
               "percentiles de qualité. Les joueurs partis sont retirés automatiquement.")

    # ---- fiche d'un joueur ----
    titre("Fiche joueur : ce qui pêche, en clair, et la consigne qui va avec")
    c1, c2 = st.columns([1, 1])
    with c1:
        nom = st.selectbox("Joueur", nos["joueur"].tolist())
    j = nos[nos["joueur"] == nom].iloc[0]
    postes_possibles = list(CRITERES)
    with c2:
        poste = st.selectbox("Comparer au poste", postes_possibles, index=postes_possibles.index(j["poste"]),
                             help="Par défaut : le poste où il a joué le plus de minutes.")
    st.markdown(f"**{nom}** · {poste} · {int(j['minutes'])} min · {int(j['titularisations'])} titularisations · "
                f"{int(j['buts'])} but(s), {int(j['passes_dec'])} passe(s) déc."
                + (" · ⚠ petit échantillon" if j["minutes"] < PETIT_ECHANTILLON else ""))
    dfm = diagnostic_fotmob(j, poste)
    w = ligne_ws(nom)
    dws = diagnostic_ws(w, poste)
    g, d = st.columns([1.1, 1])
    with g:
        try:
            barres_percentiles([(x["crit"], x["p"], fmt(x["v"], 2), x["nature"]) for x in dfm],
                               f"Son jeu — percentile parmi les {len(population(poste))} « {poste} » des 5 championnats "
                               f"(≥ {MIN_JOUEUR} min) ; bleu pâle = volume (contexte)")
        except Exception as erreur:
            st.info(f"Visuel indisponible : {erreur}")
        if dws:
            try:
                barres_percentiles([(x["lib"], x["p"], fmt(x["v"], 2), "qualité") for x in dws],
                                   f"Actions qui coûtent — percentile parmi les {len(population_ws(poste))} « {poste} » "
                                   f"de {LIGUE} (100 = celui à qui ça coûte le moins)")
            except Exception as erreur:
                st.info(f"Visuel indisponible : {erreur}")
        elif not WS_OK:
            message_whoscored()
    with d:
        points = []
        for x in sorted([x for x in dfm if x["nature"] == "qualité" and pd.notna(x["p"]) and x["p"] < 25],
                        key=lambda x: x["p"]):
            clair, consigne = EN_CLAIR.get(x["crit"], (x["crit"], "à vérifier en vidéo."))
            points.append(f"**{clair}** — {fmt(x['v'], 2)} contre {fmt(x['med'], 2)} pour un {poste.lower()} médian "
                          f"(P{fmt(x['p'], 0)}).<br>&nbsp;&nbsp;➜ <i>{consigne}</i>")
        for x in sorted([x for x in dws if pd.notna(x["p"]) and x["p"] < 25], key=lambda x: x["p"]):
            points.append(f"**{x['clair']}** — {fmt(x['v'], 2)} par match contre {fmt(x['med'], 2)} pour un "
                          f"{poste.lower()} médian de {LIGUE} (P{fmt(x['p'], 0)}).<br>&nbsp;&nbsp;➜ <i>{x['consigne']}</i>")
        if points:
            a_creuser(points, f"Ce qui pêche chez {nom}, et la consigne")
        else:
            st.success("Rien dans les 25 % les plus faibles du poste, ni dans son jeu ni dans les actions qui coûtent.")
        if w is not None:
            lecture(f"Sur la saison (WhoScored) : **{int(w['pertes'])} pertes** dans le jeu dont **{int(w['pertes_punies'])} "
                    f"suivies d'un tir adverse** ; **{int(w['duels_perdus'])} duels perdus** dont "
                    f"**{int(w['duels_perdus_tir'])} suivis d'un tir** ; {int(w['erreurs'])} erreur(s)"
                    + (f" ; {int(w['centres_adv_cote'])} centres adverses depuis son couloir pendant qu'il jouait"
                       if poste in POSTES_CENTRES else "") + ".")
        with st.expander("Que mesure chaque critère ?"):
            for c, _, n in criteres(poste):
                st.markdown(f"- **{c}** ({n}) : {EN_CLAIR.get(c, (EXPLICATIONS.get(c, ''),))[0]}")
            for col, lib, clair, _ in couts_poste(poste):
                st.markdown(f"- **{lib}** : {clair}.")
        crit_ref = [x["crit"] for x in sorted(dfm, key=lambda x: x["p"] if pd.notna(x["p"]) else 999)
                    if x["nature"] == "qualité"][0]
        sens = {c: s for c, s, _ in criteres(poste)}[crit_ref]
        autres_clubs = population(poste)[population(poste)["equipe_id"] != str(META["equipe_id"])]
        meilleurs = autres_clubs.sort_values(crit_ref, ascending=sens < 0).head(5)
        titre(f"Références du poste sur « {crit_ref} »", "les 5 meilleurs des 5 championnats : profils à étudier")
        st.dataframe(meilleurs[["joueur", "equipe", crit_ref, "minutes", "ligue"]].rename(
            columns={"joueur": "Joueur", "equipe": "Club", "ligue": "Ligue", "minutes": "Min."}), hide_index=True)
        note(f"decision_joueur_{j['joueur_id']}", f"✎ Consigne retenue pour {nom}")

    # ---- pertes et création ----
    titre("Pertes de balle et création : le déchet est-il « rentable » ?",
          "un créateur perd forcément des ballons puisqu'il tente plus — la question est ce qu'il produit en échange")
    offensifs = ["Milieu offensif", "Ailier", "Attaquant", "Milieu défensif / central", "Latéral / piston"]
    choix = st.selectbox("Poste", offensifs, index=offensifs.index(j["poste"]) if j["poste"] in offensifs else 1)
    ref = population(choix).copy()
    nous_ref = nos[nos["poste"] == choix]
    df = pd.concat([ref[ref["equipe_id"] != str(META["equipe_id"])], nous_ref])
    masque = df["equipe_id"] == str(META["equipe_id"])
    try:
        nuage(df, masque, "Pertes de balle (dépossédé) /90", "xG + xA /90", "← pertes de balle /90 (dépossédé)",
              "xG + xA /90 (ce qu'il produit) →", "joueur", inverser_x=True,
              quadrants=[(0.98, 0.98, "produit beaucoup, perd peu"), (0.02, 0.98, "créateur à risque assumé"),
                         (0.98, 0.02, "sûr mais peu décisif"), (0.02, 0.02, "perd sans produire")], taille=(8, 4.6))
    except Exception as erreur:
        st.info(f"Visuel indisponible : {erreur}")

    # ---- pertes qui coûtent : nous et une autre équipe ----
    titre("Les pertes et duels qui coûtent : nous comparés à une autre équipe",
          "« % punies » = part de ses pertes de balle dans le jeu suivies d'un tir adverse dans les 15 secondes")
    if not WS_OK:
        message_whoscored()
        return
    autres = sorted(e for e in WS["equipe"].unique() if e != NOM_WS)
    defaut = "Paris Saint-Germain" if "Paris Saint-Germain" in autres else autres[0]
    autre = st.selectbox("Comparer avec", autres, index=autres.index(defaut))
    cols_eq = [("pertes_match", "Pertes dans le jeu / match"), ("pertes_punies_match", "→ suivies d'un tir adverse / match"),
               ("pct_pertes_tir_adverse", "% punies"), ("duels_perdus_tir_match", "Duels perdus → tir / match"),
               ("dribble_subi_tir_match", "Dribblé → tir / match"), ("aeriens_perdus_tir_match", "Aériens perdus → tir / match"),
               ("xg_transitions_concedees_match", "xG concédés après nos pertes / match")]
    comp = pd.DataFrame({"Indicateur": [l for _, l in cols_eq],
                         EQUIPE: [WS_NOUS[c] for c, _ in cols_eq],
                         autre: [WS.loc[WS["equipe"] == autre, c].iloc[0] for c, _ in cols_eq],
                         f"Moy. {LIGUE}": [WS[c].mean() for c, _ in cols_eq],
                         f"Rang {EQUIPE} (1 = coûte le moins)": [int((WS[c] < WS_NOUS[c]).sum() + 1) if c != "pertes_match"
                                                                 else int((WS[c] < WS_NOUS[c]).sum() + 1) for c, _ in cols_eq]})
    st.dataframe(comp.style.format({EQUIPE: "{:.2f}", autre: "{:.2f}", f"Moy. {LIGUE}": "{:.2f}"}), hide_index=True)
    g, d = st.columns(2)
    cols_j = ["joueur", "poste", "minutes_ws", "pertes_90", "pertes_punies", "pct_pertes_punies", "duels_perdus_tir",
              "xg_cout_90"]
    noms_j = {"joueur": "Joueur", "poste": "Poste", "minutes_ws": "Min.", "pertes_90": "Pertes /90",
              "pertes_punies": "Pertes punies", "pct_pertes_punies": "% punies", "duels_perdus_tir": "Duels perdus → tir",
              "xg_cout_90": "xG coûtés /90"}
    for col, eq_ in ((g, NOM_WS), (d, autre)):
        with col:
            st.markdown(f"**{eq_}**")
            t = WS_JOUEURS[(WS_JOUEURS["equipe"] == eq_) & (WS_JOUEURS["minutes_ws"] >= MIN_NOS_JOUEURS)]
            if eq_ == NOM_WS:
                t = t[t["au_club"].fillna(True).astype(bool)]
            t = t.sort_values("xg_cout_90", ascending=False)[cols_j].rename(columns=noms_j)
            st.dataframe(t.style.format({"Min.": "{:.0f}", "Pertes /90": "{:.1f}", "% punies": "{:.0f} %",
                                         "xG coûtés /90": "{:.2f}"}).background_gradient(subset=["xG coûtés /90"],
                                                                                          cmap="Reds", vmin=0, vmax=0.3),
                         hide_index=True, height=38 + 35 * min(len(t), 14))
    lecture(f"{EQUIPE} : **{fmt(WS_NOUS['pct_pertes_tir_adverse'], 1)} %** de pertes punies "
            f"({ordinal(int((WS['pct_pertes_tir_adverse'] < WS_NOUS['pct_pertes_tir_adverse']).sum() + 1))} / {len(WS)}), "
            f"{autre} : {fmt(WS.loc[WS['equipe'] == autre, 'pct_pertes_tir_adverse'].iloc[0], 1)} %, moyenne "
            f"{fmt(WS['pct_pertes_tir_adverse'].mean(), 1)} %. On perd **moins** de ballons que la moyenne "
            f"({fmt(WS_NOUS['pertes_match'], 0)} contre {fmt(WS['pertes_match'].mean(), 0)} par match) mais ils se "
            "payent plus souvent : c'est l'**organisation derrière le ballon** au moment de la perte qui est en cause, "
            "plus que le volume de pertes.")
    st.caption("Volumes défensifs FotMob ajustés à la possession du club : valeur × 50 / (100 − possession). "
               "Pertes et duels WhoScored : une perte = ballon perdu dans le jeu suivi d'une vraie possession adverse "
               "(hors touche, 6 m, coup franc, corner) ; un duel perdu = joueur dribblé, tacle ou duel aérien perdu.")



# ------------------------------------------------------------------ PAGE 7 : ON / OFF
def texte_ou_tiret(df, formats):
    """Colonnes affichées en texte : « – » quand la valeur manque (ex. pas assez de minutes sans le joueur)."""
    df = df.copy()
    for col, f in formats.items():
        df[col] = [("–" if pd.isna(v) else f.format(v).replace(".", ",")) for v in df[col]]
    return df


def page_7():
    entete(9)
    mode_emploi("**Ajusté à l'adversaire** : chaque match est pondéré par la force offensive de l'adversaire (ses xG "
                "créés par match ÷ moyenne de sa ligue). Concéder 3 xG contre une attaque 1,6 fois plus forte que la "
                "moyenne « vaut » 1,9 xG contre une équipe moyenne. La colonne **Difficulté** donne le coefficient moyen "
                "des adversaires affrontés par le joueur (1,2 = adversaires 20 % plus forts que la moyenne).")
    ajuste = st.toggle("Ajuster à la force de l'adversaire", value=True)
    sfx = "_adj" if ajuste else ""
    au_club = set(JOUEURS.loc[(JOUEURS["equipe_id"] == str(META["equipe_id"])) & JOUEURS["au_club"], "joueur_id"].astype(str))
    o = ONOFF[(ONOFF["minutes_on"] >= MIN_NOS_JOUEURS) & ONOFF["joueur_id"].astype(str).isin(au_club)].copy()
    sans_ok = o["minutes_off"] >= 90
    o["écart"] = np.where(sans_ok, o[f"xg_contre_on_90{sfx}"] - o[f"xg_contre_off_90{sfx}"], np.nan)

    g, d = st.columns([1.05, 1])
    with g:
        def trace():
            t = o.sort_values(f"xg_contre_on_90{sfx}", ascending=False)
            fig, ax = graphique((6.4, 0.36 * len(t) + 0.9))
            y = np.arange(len(t))
            moyenne = t[f"xg_contre_on_90{sfx}"].mean()
            coul = [VERT if v < moyenne - 0.15 else ROUGE if v > moyenne + 0.15 else "#8A94A0"
                    for v in t[f"xg_contre_on_90{sfx}"]]
            ax.barh(y, t[f"xg_contre_on_90{sfx}"], color=coul, height=0.6)
            ax.axvline(moyenne, color=TEXTE, lw=0.8, ls=":")
            for yy, v, dif in zip(y, t[f"xg_contre_on_90{sfx}"], t["difficulte"]):
                ax.text(v + 0.03, yy, f"{fmt(v, 2)}   (diff. {fmt(dif, 2)})", va="center", fontsize=7.5)
            ax.set_yticks(y, t["joueur"], fontsize=8.5)
            ax.set_xlim(0, t[f"xg_contre_on_90{sfx}"].max() + 0.9)
            ax.set_xlabel("xG concédés /90 quand il est sur le terrain" + (" (ajusté)" if ajuste else "")
                          + " — pointillé = moyenne de nos joueurs", fontsize=8, color=GRIS)
            afficher(fig)
        bloc("Avec lui sur le terrain, combien concède-t-on ?", trace,
             "vert = on concède nettement moins que la moyenne de l'équipe quand il joue ; tous les joueurs, même "
             "ceux qui ne sortent jamais (ex. un milieu de référence)")
    with d:
        t = o.sort_values(f"xg_contre_on_90{sfx}")[["joueur", "minutes_on", "difficulte", f"xg_contre_on_90{sfx}",
                                                     f"xg_contre_off_90{sfx}", "écart", f"xg_pour_on_90{sfx}",
                                                     "minutes_off"]].copy()
        t.loc[t["minutes_off"] < 90, f"xg_contre_off_90{sfx}"] = np.nan
        t.columns = ["Joueur", "Min. avec", "Difficulté", "xGA/90 avec", "xGA/90 sans", "Écart", "xG/90 avec", "Min. sans"]
        t = texte_ou_tiret(t, {"xGA/90 sans": "{:.2f}", "Écart": "{:+.2f}"})
        st.dataframe(t.style.format({"Min. avec": "{:.0f}", "Min. sans": "{:.0f}", "Difficulté": "{:.2f}",
                                     "xGA/90 avec": "{:.2f}", "xG/90 avec": "{:.2f}"})
                     .background_gradient(subset=["xGA/90 avec"], cmap="RdYlGn_r"),
                     hide_index=True, height=38 + 35 * len(t))
        st.caption("« Sans » affiché seulement si le joueur a passé au moins 90 minutes hors du terrain.")
        with st.expander("Adversaires affrontés par chaque joueur"):
            st.dataframe(o[["joueur", "adversaires"]].rename(columns={"joueur": "Joueur", "adversaires": "Adversaires"}),
                         hide_index=True)
    ref = o[o["joueur"].str.contains("jbjerg", case=False)]
    if len(ref):
        r = ref.iloc[0]
        lecture(f"Repère : avec **{r['joueur']}**, on concède **{fmt(r[f'xg_contre_on_90{sfx}'], 2)} xG/90** "
                f"(difficulté {fmt(r['difficulte'], 2)}). Les joueurs nettement au-dessus de ce repère au même poste "
                "sont ceux à regarder en vidéo en priorité.")

    titre("Et par côté ?", "xG concédés sur notre gauche / face au but / notre droite quand le joueur est sur le terrain")
    cote = st.radio("Côté", ["Gauche", "Axe", "Droite"], horizontal=True,
                    format_func=lambda c: {"Gauche": "Notre gauche", "Axe": "Face au but", "Droite": "Notre droite"}[c])
    o[f"écart {cote}"] = np.where(sans_ok, o[f"xga_{cote}_on_90{sfx}"] - o[f"xga_{cote}_off_90{sfx}"], np.nan)
    tc = o.sort_values(f"xga_{cote}_on_90{sfx}")[["joueur", "minutes_on", "difficulte", f"xga_{cote}_on_90{sfx}",
                                                   f"xga_{cote}_off_90{sfx}", f"écart {cote}", "minutes_off"]].copy()
    tc.loc[tc["minutes_off"] < 90, f"xga_{cote}_off_90{sfx}"] = np.nan
    tc.columns = ["Joueur", "Min. avec", "Difficulté", "xGA/90 avec", "xGA/90 sans", "Écart", "Min. sans"]
    tc = texte_ou_tiret(tc, {"xGA/90 sans": "{:.2f}", "Écart": "{:+.2f}"})
    st.dataframe(tc.style.format({"Min. avec": "{:.0f}", "Min. sans": "{:.0f}", "Difficulté": "{:.2f}",
                                  "xGA/90 avec": "{:.2f}"})
                 .background_gradient(subset=["xGA/90 avec"], cmap="RdYlGn_r"), hide_index=True, height=38 + 35 * len(tc))
    a_creuser(["Côté gauche : si plusieurs joueurs du même côté (latéral + ailier) concèdent peu quand ils jouent, "
               "c'est le **duo** qui protège le couloir. Qui joue à leur place quand ils sortent, et avec quelles consignes ?",
               "Les valeurs « sans » calculées sur peu de minutes reposent sur 1 ou 2 matchs : à confirmer en vidéo.",
               "Croiser avec la page 6 : un joueur au-dessus du repère ET avec des actions qui coûtent = priorité vidéo."])
    note("decision_page7", "✎ Décision sur la composition / les changements", zone=True, hauteur=90)



# ------------------------------------------------------------------ PISTES DE TRAVAIL (outils communs)
EM = charger("equipes_matchs.csv")
WS_CENTRES = charger("ws_centres_concedes.csv") if WS_OK else None
WS_ENTREES = charger("ws_entrees_concedees.csv") if WS_OK else None
WS_EXEMPLES = charger("ws_exemples_video.csv") if WS_OK else None
WS_CENTRES_L1 = charger("ws_centres_l1.csv") if WS_OK else None
WS_TIRS_L1 = charger("ws_tirs_l1.csv") if WS_OK else None
WS_AC = charger("ws_anti_centres.csv") if WS_OK else None
WS_AC_SEQ = charger("ws_anti_centres_sequences.csv") if WS_OK else None


def selection_references(df, criteres, etiquette="equipe", k_min=2, k_max=6):
    """
    Score = moyenne des écarts à la moyenne (en écarts-types), orientés pour que + = mieux.
    On garde les équipes situées AVANT le plus grand écart de score entre la 2e et la 6e place :
    un groupe de tête net plutôt qu'un nombre fixe (qualitatif).
    criteres = {colonne: sens}, sens = -1 si « plus bas = mieux ».
    """
    d = df.dropna(subset=list(criteres)).copy()
    z = pd.DataFrame({c: (d[c] - d[c].mean()) / (d[c].std() or 1) * s for c, s in criteres.items()})
    d["score"] = z.mean(axis=1)
    d = d.sort_values("score", ascending=False).reset_index(drop=True)
    ecarts = {k: d.loc[k - 1, "score"] - d.loc[k, "score"] for k in range(k_min, min(k_max, len(d) - 1) + 1)}
    k = max(ecarts, key=ecarts.get)
    nous = d.index[d[etiquette].isin([EQUIPE, NOM_WS])]
    rang_nous = int(nous[0]) + 1 if len(nous) else None
    texte = (f"**{k} équipe(s) retenue(s)** : le plus grand écart de score entre la 2e et la 6e place se situe après "
             f"la {k}e ({fmt(ecarts[k], 2)} contre {fmt(np.mean([e for kk, e in ecarts.items() if kk != k]), 2)} en "
             f"moyenne pour les autres écarts)." + (f" {EQUIPE} : {ordinal(rang_nous)} / {len(d)}." if rang_nous else ""))
    return d, d.head(k)[etiquette].tolist(), texte


PROFILS = {"Idéal": "#16A34A", "Peu mais dangereux": "#D97706", "Beaucoup mais peu dangereux": "#94A3B8",
           "Beaucoup et dangereux": "#DC2626"}


def avec_contexte(df):
    """Ajoute aux tableaux WhoScored (Ligue 1) les colonnes FotMob utiles : système, possession, tirs, xG par tir."""
    cols = ["equipe", "ligue", "pct_def4", "systeme", "possession_m", "ppda_approx", "tirs_contre_m", "xga_par_tir",
            "tirs_surface_contre_m", "centres_adv_tentes_m", "xg_contre_m"]
    d = df.drop(columns=[c for c in cols[1:] if c in df.columns])
    return d.merge(EQ[cols], on="equipe", how="left")


def a_possession_egale(df, colonnes):
    """Volume ramené à une possession 50/50 : on divise par la part de ballon laissée à l'adversaire."""
    d = df.copy()
    for c in colonnes:
        d[c] = d[c] * 50 / (100 - d["possession_m"])
    return d


def selection_profil(df, volume, qualite, axe_vol, axe_qual, def4=True, poids_vol=0.6, etiquette="equipe",
                     k_min=2, k_max=6, unite="actions"):
    """
    Références au profil recherché : PEU de volume concédé d'abord, PEU de danger ensuite.
    1. Carré idéal : volume ≤ médiane ET danger ≤ médiane (les équipes qui défendent bien mais subissent
       beaucoup — bloc bas, défense à 5 — sont écartées volontairement).
    2. Option : défense à 4 (2 centraux) sur au moins la moitié des matchs.
    3. Score = 60 % volume + 40 % qualité (en écarts-types), coupe au plus grand écart entre la 2e et la 6e place.
    """
    d = df.dropna(subset=list(volume) + list(qualite)).copy()

    def z(crit):
        return pd.DataFrame({c: (d[c] - d[c].mean()) / (d[c].std() or 1) * s for c, s in crit.items()}).mean(axis=1)
    d["score_volume"], d["score_qualite"] = z(volume), z(qualite)
    d["score"] = poids_vol * d["score_volume"] + (1 - poids_vol) * d["score_qualite"]
    mv, mq = d[axe_vol].median(), d[axe_qual].median()
    peu, faible = d[axe_vol] <= mv, d[axe_qual] <= mq
    d["profil"] = np.select([peu & faible, peu & ~faible, ~peu & faible],
                            ["Idéal", "Peu mais dangereux", "Beaucoup mais peu dangereux"], "Beaucoup et dangereux")
    d["def4"] = d["pct_def4"].fillna(0) >= 50
    d = d.sort_values("score", ascending=False).reset_index(drop=True)
    ok = d[(d["profil"] == "Idéal") & (d["def4"] | (not def4))]
    if len(ok) <= k_min:
        refs, coupe = ok[etiquette].tolist(), None
    else:
        sc = ok["score"].tolist()
        ecarts = {k: sc[k - 1] - sc[k] for k in range(k_min, min(k_max, len(sc) - 1) + 1)}
        k = max(ecarts, key=ecarts.get)
        refs, coupe = ok.head(k)[etiquette].tolist(), (k, ecarts)
    nous = d[d[etiquette].isin([EQUIPE, NOM_WS])]
    texte = (f"**{int((d['profil'] == 'Idéal').sum())} clubs sur {len(d)}** sont dans le carré idéal (peu de {unite} "
             f"**et** peu de danger)" + (f", dont **{len(d[(d['profil'] == 'Idéal') & d['def4']])} à 4 défenseurs**"
                                          if def4 else "") + ". ")
    if coupe:
        k, ecarts = coupe
        texte += (f"On garde les **{k} premiers** au score (60 % volume, 40 % danger) : le plus grand écart de score se "
                  f"situe après le {ordinal(k)} ({fmt(ecarts[k], 2)}).")
    if len(nous):
        texte += f" {EQUIPE} : profil « {nous['profil'].iloc[0]} », {ordinal(int(nous.index[0]) + 1)} / {len(d)} au score."
    ecartes = {
        "volume": d[(d["profil"] == "Beaucoup mais peu dangereux")].sort_values("score_qualite", ascending=False)
                   .head(4)[etiquette].tolist(),
        "systeme": d[(d["profil"] == "Idéal") & ~d["def4"]].head(4)[etiquette].tolist() if def4 else [],
    }
    return d, refs, texte, ecartes, (mv, mq)


def encadre_ecartes(ecartes, d, quoi, pourquoi, etiquette="equipe"):
    """Ceux qu'on écarte volontairement, et pourquoi."""
    morceaux = []
    if ecartes["volume"]:
        noms = ", ".join(f"<b>{e}</b> ({sans_zero(d.loc[d[etiquette] == e, 'systeme'])})" for e in ecartes["volume"])
        morceaux.append(f"{noms} : peu de danger, mais <b>{quoi}</b>. {pourquoi} : pas le modèle recherché.")
    if ecartes["systeme"]:
        noms = ", ".join(f"<b>{e}</b> ({sans_zero(d.loc[d[etiquette] == e, 'systeme'])})" for e in ecartes["systeme"])
        morceaux.append(f"{noms} : bon profil mais <b>défense à 3 / 5</b> la plupart du temps (désactiver le filtre pour "
                        "les inclure).")
    if morceaux:
        st.markdown('<div class="creuser" style="border-left-color:#94A3B8;background:#F8FAFC"><b>✖ Écartés '
                    'volontairement</b><br><span style="font-size:12.5px">' + "<br>".join(morceaux) + "</span></div>",
                    unsafe_allow_html=True)


def sans_zero(serie):
    v = serie.iloc[0] if len(serie) else ""
    return "système ?" if pd.isna(v) or v == "" else str(v).split(",")[0].split(" (")[0]


def matrice_profil(d, x, y, lib_x, lib_y, refs, medianes, libelles, etiquette="equipe", ligue_col=None,
                   taille=(6.6, 4.8), noms=False):
    """Matrice volume × danger : carré idéal en vert (en haut à droite), défenses à 3/5 en creux."""
    mv, mq = medianes
    fig, ax = graphique(taille)
    pad_x, pad_y = (d[x].max() - d[x].min()) * 0.06, (d[y].max() - d[y].min()) * 0.08
    x0, x1, y0, y1 = d[x].min() - pad_x, d[x].max() + pad_x, d[y].min() - pad_y, d[y].max() + pad_y
    ax.add_patch(plt.Rectangle((x0, y0), mv - x0, mq - y0, color="#DCFCE7", zorder=0))
    est_nous = d[etiquette].isin([EQUIPE, NOM_WS])
    est_ref = d[etiquette].isin(refs)
    for plein, masque in ((True, d["def4"]), (False, ~d["def4"])):
        a = d[~est_nous & ~est_ref & masque]
        ax.scatter(a[x], a[y], s=22, facecolors="#B8C0B3" if plein else "none", edgecolors="#9AA394", linewidths=0.9)
    ax.scatter(d.loc[est_ref, x], d.loc[est_ref, y], s=80, color=VERT, edgecolors="white", zorder=3)
    ax.scatter(d.loc[est_nous, x], d.loc[est_nous, y], s=160, color=BLEU_OM, edgecolors="white", zorder=4)
    # références numérotées (la liste est dans l'encadré vert) : pas de chevauchement de noms
    for i, nom in enumerate(refs, 1):
        r = d[d[etiquette] == nom].iloc[0]
        ax.annotate(str(i), (r[x], r[y]), xytext=(0, 0), textcoords="offset points", fontsize=7, fontweight="bold",
                    color="white", ha="center", va="center", zorder=5)
    for _, r in d[est_nous].iterrows():
        ax.annotate(r[etiquette], (r[x], r[y]), xytext=(7, 4), textcoords="offset points", fontsize=8.5,
                    fontweight="bold", color=BLEU_OM, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    if noms:      # tous les clubs nommés (championnat à 18)
        for _, r in d[~est_nous].iterrows():
            ref = r[etiquette] in refs
            ax.annotate(r[etiquette], (r[x], r[y]), xytext=(6, -3 if ref else 3), textcoords="offset points",
                        fontsize=7.2 if ref else 6.6, fontweight="bold" if ref else "normal", color=VERT if ref else GRIS,
                        path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
    ax.axvline(mv, color=GRIS, lw=0.8, ls=":")
    ax.axhline(mq, color=GRIS, lw=0.8, ls=":")
    ax.set_xlim(x1, x0)
    ax.set_ylim(y1, y0)
    ax.set_xlabel(lib_x, color=GRIS, fontsize=9)
    ax.set_ylabel(lib_y, color=GRIS, fontsize=9)
    style = dict(transform=ax.transAxes, fontsize=7.5, style="italic")
    ax.text(1.0, 1.02, libelles[0], ha="right", va="bottom", color="#166534", fontweight="bold", **style)
    ax.text(0.0, 1.02, libelles[1].replace("\n", " "), ha="left", va="bottom", color=GRIS, **style)
    ax.text(0.98, 0.03, libelles[2], ha="right", va="bottom", color="#B45309", **style)
    ax.text(0.02, 0.03, libelles[3], ha="left", va="bottom", color="#B91C1C", **style)
    ax.scatter([], [], s=22, facecolors="none", edgecolors="#9AA394", label="défense à 3 / 5")
    ax.legend(loc="upper left", fontsize=7, frameon=False, bbox_to_anchor=(0, -0.12))
    afficher(fig)


def profil_refs(refs, colonnes, ws_cols=None):
    """Comment ils y arrivent : système, ballon, pressing et volumes, références vs nous."""
    noms = list(dict.fromkeys(refs + [EQUIPE]))
    t = EQ[EQ["equipe"].isin(noms)].copy()
    t["ordre"] = t["equipe"].map({n: i for i, n in enumerate(noms)})
    t = t.sort_values("ordre")
    if ws_cols and WS_OK:
        w = WS.set_index("equipe")
        for c, lib in ws_cols.items():
            t[lib] = t["equipe"].map(lambda e: w[c].get(NOM_WS if e == EQUIPE else e, np.nan))
    base = {"equipe": "Club", "ligue": "Ligue", "systeme": "Systèmes les plus utilisés", "possession_m": "Possession %",
            "ppda_approx": "PPDA (approx.)"}
    t = t[list(base) + list(colonnes) + (list(ws_cols.values()) if ws_cols and WS_OK else [])]
    t = t.rename(columns={**base, **colonnes})
    for c in t.columns[3:]:
        f = "{:.0f}" if c.startswith("%") or c.startswith("Possession") else ("{:.1f}" if "/match" in c else "{:.2f}")
        t[c] = ["–" if pd.isna(v) else f.format(v).replace(".", ",") for v in t[c]]
    st.dataframe(t.style.apply(lambda r: ["background-color:#E0ECF8;font-weight:600" if r["Club"] == EQUIPE
                                          else "background-color:#F0FDF4"] * len(r), axis=1), hide_index=True)


def tableau_classement(d, refs, colonnes, etiquette="equipe", n=10):
    """Classement : références en vert, nous en bleu (toujours affichés)."""
    t = pd.concat([d.head(n), d[d[etiquette].isin([EQUIPE, NOM_WS])]]).drop_duplicates(etiquette)
    t = t.assign(Rang=[int(i) + 1 for i in t.index])
    cols = ["Rang", etiquette] + [c for c in colonnes if c in t.columns] + ["score"]
    noms = {etiquette: "Club", "score": "Score", **colonnes}
    t = t[cols].rename(columns=noms)
    num = [v for v in list(colonnes.values()) + ["Score"] if pd.api.types.is_numeric_dtype(t[v])]
    fmt_ = {v: "{:.2f}" for v in num}
    fmt_.update({v: "{:.1f}" for v in num if v.startswith("%") or "/match" in v and "xG" not in v})

    def couleur(r):
        if r["Club"] in (EQUIPE, NOM_WS):
            return ["background-color:#E0ECF8;font-weight:600"] * len(r)
        if r["Club"] in refs:
            return ["background-color:#DCFCE7"] * len(r)
        return [""] * len(r)
    st.dataframe(t.style.format(fmt_).apply(couleur, axis=1), hide_index=True, height=38 + 35 * len(t))


def nuage_refs(df, x, y, lib_x, lib_y, refs, etiquette="equipe", inverser_x=False, inverser_y=False, quadrants=None,
               ligue_col=None, taille=(6.6, 4.6)):
    """Nuage : toutes les équipes en gris, références en vert (nommées), nous en bleu."""
    fig, ax = graphique(taille)
    est_nous = df[etiquette].isin([EQUIPE, NOM_WS])
    est_ref = df[etiquette].isin(refs)
    autres = df[~est_nous & ~est_ref]
    ax.scatter(autres[x], autres[y], s=18, color="#C9CFC4")
    ax.scatter(df.loc[est_ref, x], df.loc[est_ref, y], s=70, color=VERT, edgecolors="white", zorder=3)
    ax.scatter(df.loc[est_nous, x], df.loc[est_nous, y], s=150, color=BLEU_OM, edgecolors="white", zorder=4)
    for _, r in df[est_ref | est_nous].iterrows():
        lib = r[etiquette] + (f" ({r[ligue_col]})" if ligue_col and r[etiquette] not in (EQUIPE, NOM_WS) else "")
        ax.annotate(lib, (r[x], r[y]), xytext=(5, 4), textcoords="offset points", fontsize=8,
                    fontweight="bold", color=BLEU_OM if r[etiquette] in (EQUIPE, NOM_WS) else VERT,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.axvline(df[x].mean(), color=GRIS, lw=0.7, ls=":")
    ax.axhline(df[y].mean(), color=GRIS, lw=0.7, ls=":")
    ax.set_xlabel(lib_x, color=GRIS, fontsize=9)
    ax.set_ylabel(lib_y, color=GRIS, fontsize=9)
    if inverser_x:
        ax.invert_xaxis()
    if inverser_y:
        ax.invert_yaxis()
    ax.text(0.99, 0.01, "en haut à droite = mieux", transform=ax.transAxes, fontsize=7.5, color=GRIS, style="italic",
            ha="right", va="bottom")
    afficher(fig)


def encadre_refs(titre_, refs, texte, couleur=VERT):
    st.markdown(f'<div class="creuser" style="border-left-color:{couleur};background:#F0FDF4"><b>✔ {titre_}</b> : '
                + ", ".join(f"<b>{i}. {r}</b>" for i, r in enumerate(refs, 1)) + f"<br><span style='font-size:12.5px'>{gras(texte)}</span></div>",
                unsafe_allow_html=True)


def comparatif_joueurs(club, postes, colonnes_fm, colonnes_ws, minutes_min=300):
    """Joueurs d'un club de référence et nos joueurs aux mêmes postes, avec la médiane européenne du poste."""
    lignes = []
    ws_club = sans_accents(club)
    for poste in postes:
        for qui, masque in ((club, JOUEURS["equipe"] == club),
                            (EQUIPE, (JOUEURS["equipe_id"] == str(META["equipe_id"])) & JOUEURS["au_club"])):
            j = JOUEURS[masque & (JOUEURS["poste"] == poste) & (JOUEURS["minutes"] >= minutes_min)]
            for _, r in j.sort_values("minutes", ascending=False).iterrows():
                ligne = {"Club": qui, "Joueur": r["joueur"], "Poste": poste, "Min.": int(r["minutes"])}
                ligne.update({lib: r[col] for col, lib in colonnes_fm.items()})
                if WS_JOUEURS is not None and colonnes_ws:
                    eq_ws = NOM_WS if qui == EQUIPE else qui
                    w = WS_JOUEURS[(WS_JOUEURS["equipe"].map(sans_accents) == sans_accents(eq_ws))
                                   & (pd.to_numeric(WS_JOUEURS["joueur_id"], errors="coerce") ==
                                      pd.to_numeric(r["joueur_id"], errors="coerce"))]
                    for col, lib in colonnes_ws.items():
                        ligne[lib] = w[col].iloc[0] if len(w) else np.nan
                lignes.append(ligne)
        pop = population(poste)
        med = {"Club": "Médiane 5 champ.", "Joueur": f"({len(pop)} joueurs)", "Poste": poste, "Min.": np.nan}
        med.update({lib: pop[col].median() for col, lib in colonnes_fm.items()})
        if WS_JOUEURS is not None and colonnes_ws:
            pws = population_ws(poste)
            med.update({lib: pws[col].median() if len(pws) else np.nan for col, lib in colonnes_ws.items()})
        lignes.append(med)
    t = pd.DataFrame(lignes)
    if not len(t):
        st.info("Pas de joueur avec assez de minutes à ces postes.")
        return
    num = [c for c in t.columns if c not in ("Club", "Joueur", "Poste")]
    for c in num:
        f = "{:.0f}" if (c == "Min." or c.startswith("%")) else "{:.2f}"
        t[c] = ["–" if pd.isna(v) else f.format(v).replace(".", ",") for v in t[c]]

    def couleur(r):
        if r["Club"] == EQUIPE:
            return ["background-color:#E0ECF8"] * len(r)
        if r["Club"].startswith("Médiane"):
            return ["background-color:#F3F5F1;font-style:italic"] * len(r)
        return ["background-color:#F0FDF4"] * len(r)
    st.dataframe(t.style.apply(couleur, axis=1), hide_index=True, height=38 + 35 * min(len(t), 16))


def exemples(theme, refs_l1, refs_europe, choisir_match, lib_match):
    """Séquences vidéo : à reproduire (références, Ligue 1 avec minutes ; Europe : match à visionner) et à corriger (nous)."""
    large = {"Action": st.column_config.TextColumn(width="large"), "Séquence": st.column_config.TextColumn(width="large"),
             "Pourquoi": st.column_config.TextColumn(width="large")}
    with st.container():
        st.markdown("**✔ À reproduire — chez les références**")
        if WS_EXEMPLES is not None and refs_l1:
            club = st.selectbox("Club de référence (Ligue 1, avec minutes)", refs_l1, key=f"ex_{theme}")
            t = WS_EXEMPLES[(WS_EXEMPLES["equipe"] == club) & (WS_EXEMPLES["theme"] == theme)
                            & (WS_EXEMPLES["type"] == "À reproduire")]
            if len(t):
                st.caption(f"Match à visionner : **{club} – {t['adversaire'].iloc[0]}** ({t['date'].iloc[0]}) — "
                           f"{t['match_resume'].iloc[0]}.")
                st.dataframe(t[["minute", "joueur", "description"]].rename(
                    columns={"minute": "Min.", "joueur": "Joueur", "description": "Action"}), hide_index=True,
                    column_config=large)
        if refs_europe:
            st.markdown("Références européennes (sans minutes : match à visionner)")
            lignes = []
            for club in refs_europe:
                m = EM[EM["equipe"] == club]
                if len(m):
                    r = choisir_match(m)
                    lignes.append({"Club": club, "Match": f"{club} – {r['adversaire']} ({r['date']}, {r['score']})",
                                   "Pourquoi": lib_match(r)})
            st.dataframe(pd.DataFrame(lignes), hide_index=True, column_config=large)
    with st.container():
        st.markdown(f"**✖ À corriger — chez {EQUIPE}** (les plus dangereuses)")
        if WS_EXEMPLES is not None:
            t = WS_EXEMPLES[(WS_EXEMPLES["equipe"] == NOM_WS) & (WS_EXEMPLES["theme"] == theme)
                            & (WS_EXEMPLES["type"] == "À corriger")]
            st.dataframe(t[["adversaire", "date", "minute", "description"]].rename(
                columns={"adversaire": "Adversaire", "date": "Date", "minute": "Min.", "description": "Séquence"}),
                hide_index=True, column_config=large)
        else:
            message_whoscored()


def match_peu_de_centres(m):
    """Match contre une attaque au-dessus de la moyenne où l'adversaire a le moins centré."""
    force = dict(zip(EQ["equipe"], EQ["xg_m"]))
    m = m.assign(force_adv=m["adversaire"].map(force))
    fort = m[m["force_adv"] >= EQ["xg_m"].median()]
    return (fort if len(fort) else m).assign(s=lambda x: x["centres_adv"] + 25 * x["xga_tete"]).sort_values("s").iloc[0]


def match_zone_parlant(m):
    """Match contre une attaque au-dessus de la moyenne où l'on a concédé le moins de tirs dans la surface et de xG."""
    force = dict(zip(EQ["equipe"], EQ["xg_m"]))
    m = m.assign(force_adv=m["adversaire"].map(force))
    fort = m[m["force_adv"] >= EQ["xg_m"].median()]
    return (fort if len(fort) else m).assign(s=lambda x: x["tirs_surface_contre"] + 10 * x["xga"]).sort_values("s").iloc[0]


def consignes(titre_, lignes):
    items = "".join(f"<li>{gras(l)}</li>" for l in lignes)
    st.markdown(f'<div class="creuser" style="border-left-color:{ORANGE};background:#FFF7ED"><b>⚽ {titre_}</b>'
                f'<ul style="margin:4px 0 0 0">{items}</ul></div>', unsafe_allow_html=True)


def rang_txt(df, col, sens, nom=None):
    """« 17e / 18 » pour notre équipe dans df (sens -1 = plus bas = mieux)."""
    nom = nom or (EQUIPE if "equipe_id" in df.columns else NOM_WS)
    v = df.loc[df["equipe"] == nom, col]
    if not len(v):
        return "–"
    v = v.iloc[0]
    r = int((df[col] < v).sum() + 1) if sens < 0 else int((df[col] > v).sum() + 1)
    return f"{ordinal(r)} / {len(df)}"


# ------------------------------------------------------------------ RADARS JOUEURS
COULEURS_RADAR = ["#0A60A8", "#16A34A", "#D97706", "#9333EA"]


def dessiner_radar(series, libelles, taille=(5.6, 5.6)):
    """series : [(nom, [percentiles 0-100])]. Plus loin du centre = mieux (indicateurs « bas = bien » retournés)."""
    n = len(libelles)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    fig = plt.figure(figsize=taille)
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], fontsize=7, color=GRIS)
    ax.set_xticks(ang)
    ax.set_xticklabels(libelles, fontsize=8, color=TEXTE)
    ax.tick_params(axis="x", pad=12)
    ax.grid(color="#D5DAD0", lw=0.7)
    ax.spines["polar"].set_color("#D5DAD0")
    ax.fill(ang + ang[:1], [50] * (n + 1), color="#F3F5F1", zorder=0)
    for i, (nom, vals) in enumerate(series):
        v = [0 if pd.isna(x) else x for x in vals]
        c = COULEURS_RADAR[i % len(COULEURS_RADAR)]
        ax.plot(ang + ang[:1], v + v[:1], color=c, lw=2, label=nom)
        ax.fill(ang + ang[:1], v + v[:1], color=c, alpha=0.10)
        ax.scatter(ang, v, color=c, s=16, zorder=3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=2, fontsize=8, frameon=False)
    afficher(fig)


def radar_joueurs(cle, postes, ind_ws, ind_fm, clubs_defaut, minutes_min=300):
    """
    Jusqu'à 4 joueurs sur un radar à 6 indicateurs. Chaque valeur = percentile parmi les joueurs du même poste
    (Ligue 1 pour les indicateurs WhoScored, 5 championnats pour FotMob). 50 = médiane du poste.
    ind_* : [(colonne, libellé, sens)] avec sens -1 si « plus bas = mieux ».
    """
    sources = (["Ligue 1 : détail des événements (WhoScored)"] if WS_OK else []) + ["5 championnats (FotMob)"]
    src = st.radio("Indicateurs", sources, horizontal=True, key=f"{cle}_src")
    if src.startswith("Ligue 1"):
        pool = WS_JOUEURS[WS_JOUEURS["poste"].isin(postes) & (WS_JOUEURS["minutes_ws"] >= minutes_min)].copy()
        if "Latéral / piston" in postes:          # un « latéral » qui joue dans l'axe ne subit pas de centres de son côté
            pool = pool[pool["cote"] != "Axe"]
        pool["lib"] = pool["joueur"] + " (" + pool["equipe"] + ")"
        pool["nous"] = (pool["equipe"] == NOM_WS) & pool["au_club"].fillna(True).astype(bool)
        ind, mins = ind_ws, "minutes_ws"
    else:
        pool = JOUEURS[JOUEURS["poste"].isin(postes) & (JOUEURS["minutes"] >= minutes_min)].copy()
        pool["lib"] = pool["joueur"] + " (" + pool["equipe"] + ")"
        pool["nous"] = (pool["equipe_id"] == str(META["equipe_id"])) & pool["au_club"].astype(bool)
        ind, mins = ind_fm, "minutes"
    if not len(pool):
        st.info("Pas de joueur avec assez de minutes à ces postes.")
        return
    pool = pool.sort_values(mins, ascending=False).drop_duplicates("lib")
    defaut = pool[pool["nous"]].head(2)["lib"].tolist()
    for c in clubs_defaut:
        j = pool[pool["equipe"].map(sans_accents) == sans_accents(c)].head(1)["lib"].tolist()
        defaut += j
        if len(defaut) >= 4:
            break
    choix = st.multiselect("Joueurs (4 au maximum)", pool["lib"].tolist(), default=defaut[:4], max_selections=4,
                           key=f"{cle}_{src[:3]}")
    if not choix:
        return
    series, lignes = [], []
    for lib in choix:
        r = pool[pool["lib"] == lib].iloc[0]
        ref = pool[pool["poste"] == r["poste"]]
        series.append((lib, [percentile_serie(ref[c], r[c], s) for c, _, s in ind]))
        lignes.append({"Joueur": lib, "Poste": r["poste"], "Min.": int(r[mins]),
                       **{l: r[c] for c, l, _ in ind}})
    med = {"Joueur": "Médiane du poste", "Poste": "", "Min.": np.nan,
           **{l: pool.loc[pool["poste"] == postes[0], c].median() for c, l, _ in ind}}
    g, d = st.columns([1.1, 1])
    with g:
        dessiner_radar(series, [l.replace(" (", "\n(") if len(l) > 18 else l for _, l, _ in ind])
    with d:
        t = pd.DataFrame(lignes + [med])
        for c in t.columns[3:]:
            t[c] = ["–" if pd.isna(v) else (f"{v:.0f}" if c.startswith("%") else f"{v:.2f}").replace(".", ",")
                    for v in t[c]]
        t["Min."] = ["–" if pd.isna(v) else str(int(v)) for v in t["Min."]]
        st.dataframe(t.set_index("Joueur").T, height=38 + 35 * (len(ind) + 2))
        st.caption("Radar : percentile parmi les joueurs du même poste (" +
                   ("Ligue 1" if src.startswith("Ligue 1") else "5 championnats") +
                   f", ≥ {minutes_min} min). Plus loin du centre = mieux ; les indicateurs où « bas = bien » sont retournés. "
                   "Le cercle gris = médiane.")


# ------------------------------------------------------------------ INDICATEURS DISCRIMINANTS
def correlations(df, cols, cible):
    return pd.Series({c: df[[c, cible]].dropna().corr().iloc[0, 1] for c in cols})


def barres_correlations(r, libelles, titre_x):
    r = r.dropna().sort_values()
    fig, ax = graphique((6.4, 0.38 * len(r) + 0.9))
    couleurs = [ROUGE if v > 0.3 else VERT if v < -0.3 else "#B8C0B3" for v in r]
    ax.barh([libelles[c] for c in r.index], r.values, color=couleurs)
    ax.axvline(0, color=GRIS, lw=0.8)
    for x in (-0.3, 0.3):
        ax.axvline(x, color=GRIS, lw=0.6, ls=":")
    for i, v in enumerate(r.values):
        ax.text(v + (0.02 if v >= 0 else -0.02), i, fmt(v, 2), va="center", ha="left" if v >= 0 else "right",
                fontsize=7.5, color=GRIS)
    ax.set_xlim(-1, 1)
    ax.set_xlabel(titre_x, color=GRIS, fontsize=8.5)
    ax.tick_params(axis="y", labelsize=8)
    afficher(fig)


def tableau_indicateurs(df, clubs, indicateurs, cible, etiquette="equipe"):
    """Lignes = indicateurs ; colonnes = clubs choisis, moyenne, lien avec la cible (r)."""
    r = correlations(df, [c for c, _, _ in indicateurs], cible)
    lignes = []
    for c, lib, d in indicateurs:
        ligne = {"Indicateur": lib}
        for club in clubs:
            v = df.loc[df[etiquette] == club, c]
            ligne[club] = "–" if not len(v) or pd.isna(v.iloc[0]) else fmt(v.iloc[0], d)
        ligne["Moyenne"] = fmt(df[c].mean(), d)
        ligne["Lien avec le danger (r)"] = fmt(r[c], 2)
        lignes.append(ligne)
    t = pd.DataFrame(lignes)

    def couleur(row):
        try:
            v = float(row["Lien avec le danger (r)"].replace(",", "."))
        except ValueError:
            v = 0
        fond = "#FEE2E2" if v >= 0.3 else "#DCFCE7" if v <= -0.3 else ""
        return [f"background-color:{fond}" if col == "Lien avec le danger (r)" else "" for col in row.index]
    st.dataframe(t.style.apply(couleur, axis=1), hide_index=True, height=38 + 35 * len(t))
    return r


def ecarts_qui_comptent(df, nous, autre, indicateurs, r, etiquette="equipe", seuil=0.3, n=3):
    """Les indicateurs liés au danger (|r| ≥ 0,3) où l'écart entre deux clubs est le plus grand (en écarts-types)."""
    out = []
    for c, lib, d in indicateurs:
        if pd.isna(r.get(c)) or abs(r[c]) < seuil:
            continue
        a = df.loc[df[etiquette] == nous, c]
        b = df.loc[df[etiquette] == autre, c]
        if not len(a) or not len(b):
            continue
        z = (a.iloc[0] - b.iloc[0]) / (df[c].std() or 1)
        out.append((abs(z) * abs(r[c]), lib, a.iloc[0], b.iloc[0], d, r[c]))
    return sorted(out, reverse=True)[:n]


def nuage_iso(df, x, y, lib_x, lib_y, refs, etiquette="equipe"):
    """Entrées × % suivies d'un tir, avec les courbes « même nombre de tirs par match » (x × y / 100 = constante)."""
    fig, ax = graphique((6.6, 4.8))
    xs = np.linspace(df[x].min() * 0.9, df[x].max() * 1.05, 100)
    for k in (4, 6, 8, 10):
        ax.plot(xs, 100 * k / xs, color="#D5DAD0", lw=1, zorder=0)
        xa = xs[-1]
        ya = 100 * k / xa
        if df[y].min() * 0.85 <= ya <= df[y].max() * 1.1:
            ax.text(xa, ya, f" {k} tirs/match", fontsize=7, color=GRIS, va="center")
    est_nous = df[etiquette].isin([EQUIPE, NOM_WS])
    for _, r in df.iterrows():
        ref, nous = r[etiquette] in refs, r[etiquette] in (EQUIPE, NOM_WS)
        c = BLEU_OM if nous else VERT if ref else "#B8C0B3"
        ax.scatter(r[x], r[y], s=150 if nous else 70 if ref else 30, color=c, edgecolors="white", zorder=3)
        ax.annotate(r[etiquette], (r[x], r[y]), xytext=(6, 3), textcoords="offset points",
                    fontsize=8 if nous or ref else 6.6, fontweight="bold" if nous or ref else "normal", color=c if nous or ref else GRIS,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
    ax.set_ylim(df[y].min() * 0.85, df[y].max() * 1.1)
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.set_xlabel(lib_x, color=GRIS, fontsize=9)
    ax.set_ylabel(lib_y, color=GRIS, fontsize=9)
    ax.text(0.99, 0.01, "en haut à droite = mieux ; courbes grises = même nombre de tirs après une entrée", transform=ax.transAxes,
            fontsize=7, color=GRIS, style="italic", ha="right", va="bottom")
    afficher(fig)


def encadre_limite(titre_, texte):
    st.markdown(f'<div class="creuser" style="border-left-color:{NAVY};background:#F1F5F9"><b>ⓘ {titre_}</b><br>'
                f'<span style="font-size:12.5px">{gras(texte)}</span></div>', unsafe_allow_html=True)


TEXTE_STATSBOMB = (
    "WhoScored (données Opta) n'enregistre que les actions **sur le ballon** : une pression sans contact, la distance du "
    "défenseur le plus proche, une prise à deux ou un milieu qui redescend sans toucher le ballon sont **invisibles**. "
    "Nos indicateurs de « pression » ne captent donc que les contacts (tacle, duel, faute, contre). "
    "**Hudl StatsBomb** comblerait ce manque : chaque événement porte un indicateur **« sous pression »**, chaque "
    "pression est un événement (qui presse, où, combien de temps), et l'offre **StatsBomb 360** donne la position de tous "
    "les joueurs visibles à chaque événement (distance au centreur ou au tireur, nombre de défenseurs dans la surface, "
    "défenseurs entre le ballon et le but). Couverture Ligue 1 en 360 et tarif : à confirmer avec Hudl (offre sur devis). "
    "Alternative : SkillCorner (données de suivi issues des images TV, intensité de la pression).")


# ------------------------------------------------------------------ PISTE 2 : sections
CRIT_ZONE = {"entrees_surface_match": ("Entrées /match", -1), "tirs_apres_entrees_match": ("Tirs après entrée /match", -1),
             "pct_entrees_suivies_tir": ("% entrées → tir", -1), "pct_z14_suivies_tir": ("% zone 14 → tir", -1),
             "pct_duels_gagnes_30m": ("% duels gagnés (30 m)", 1), "dribble_subi_30m_match": ("Dribblé (30 m) /match", -1)}


def section_zone_score(refs_l1):
    w = avec_contexte(WS)
    g, d = st.columns(2)
    with g:
        bloc(f"{LIGUE} : entrées dans notre surface et part qui finit en tir",
             lambda: nuage_iso(w, "entrees_surface_match", "pct_entrees_suivies_tir",
                               "← entrées adverses dans notre surface /match (passe ou balle au pied)",
                               "← % suivies d'un tir en 10 s", refs_l1), "")
    with d:
        crit = {c: s_ for c, (_, s_) in CRIT_ZONE.items()}
        d_ws, _, _ = selection_references(w, crit)
        st.markdown(f"**{LIGUE} : la zone de vérité, club par club** (références de A en vert)")
        tableau_classement(d_ws, refs_l1, {c: l for c, (l, _) in CRIT_ZONE.items()}, n=18)
    nous = w[w["equipe"] == NOM_WS].iloc[0]
    lecture(f"On concède **{fmt(nous['entrees_surface_match'], 1)} entrées** par match ({rang_txt(w, 'entrees_surface_match', -1)}) "
            f"et **{fmt(nous['pct_entrees_suivies_tir'], 0)} %** finissent en tir : **{fmt(nous['tirs_apres_entrees_match'], 1)} "
            f"tirs par match après une entrée**, {rang_txt(w, 'tirs_apres_entrees_match', -1)} (moyenne "
            f"{fmt(w['tirs_apres_entrees_match'].mean(), 1)}). Les courbes grises du graphique relient les clubs qui "
            "concèdent le même nombre de tirs après une entrée : un club à 55 % avec 10 entrées et un club à 37 % avec 15 "
            "entrées concèdent autant.")
    with st.expander("Le détail du score, et ce qui pèse vraiment sur le danger", expanded=True):
        z = pd.DataFrame({l: (w[c] - w[c].mean()) / (w[c].std() or 1) * s_ for c, (l, s_) in CRIT_ZONE.items()})
        z.insert(0, "Club", w["equipe"].values)
        z["Score"] = z.drop(columns="Club").mean(axis=1)
        z = z.sort_values("Score", ascending=False)
        cols_num = [c for c in z.columns if c != "Club"]
        st.dataframe(z.style.format({c: "{:+.2f}" for c in cols_num})
                     .background_gradient(subset=cols_num, cmap="RdYlGn", vmin=-2, vmax=2)
                     .apply(lambda r: ["font-weight:700" if r["Club"] in (NOM_WS, *refs_l1) else ""] * len(r), axis=1),
                     hide_index=True, height=38 + 35 * len(z))
        st.caption("Chaque case = écart à la moyenne du championnat en écarts-types, orienté pour que + = mieux "
                   "(vert). Score = moyenne des six cases : chaque critère pèse autant.")
        r = correlations(w, list(CRIT_ZONE), "xg_contre_m")
        g, _ = st.columns([1.6, 1])
        with g:
            barres_correlations(r, {c: l for c, (l, _) in CRIT_ZONE.items()},
                                "lien avec les xG concédés par match (r) — rouge : plus il y en a, plus on concède")
        tri = r.abs().sort_values(ascending=False)
        lib = {c: l for c, (l, _) in CRIT_ZONE.items()}
        psg = w[w["equipe"] == "Paris Saint-Germain"]
        texte = (f"Ce qui pèse le plus sur les xG concédés : **{lib[tri.index[0]]}** (r = {fmt(r[tri.index[0]], 2)}) et "
                 f"**{lib[tri.index[1]]}** (r = {fmt(r[tri.index[1]], 2)}) : **le volume d'entrées compte plus que le % "
                 f"qui finit en tir** (r = {fmt(r['pct_entrees_suivies_tir'], 2)}). Le score met les six critères au même "
                 "niveau : il sert à classer, le graphique dit sur quoi travailler en premier.")
        if len(psg):
            p = psg.iloc[0]
            texte += (f" **Pourquoi le PSG gagne peu de duels près de sa surface sans en souffrir ?** Il n'en dispute que "
                      f"**{fmt(p['duels_30m_match'], 1)} par match** (moyenne {fmt(w['duels_30m_match'].mean(), 1)}) parce "
                      f"que l'adversaire y arrive peu ({fmt(p['entrees_surface_match'], 1)} entrées par match, le moins de la "
                      "ligue) : sur si peu de duels, le % varie beaucoup, et un duel perdu y arrive souvent quand le danger "
                      "est déjà là (dernier défenseur). Le % de duels gagnés ne compte que **rapporté au nombre de duels**.")
        lecture(texte)


def section_discriminants(refs_l1, refs_eu):
    w = avec_contexte(WS)
    tp = [c for c in w.columns if c.startswith("tirs_passe_") and "Penalty" not in c and "Coup de pied" not in c]
    tot = w[tp].sum(axis=1).replace(0, np.nan)
    w["pct_tirs_remise"] = w["tirs_passe_Remise en retrait_match"] / tot * 100
    w["pct_tirs_profondeur"] = w["tirs_passe_Passe en profondeur_match"] / tot * 100
    w["pct_tirs_rebond"] = w["tirs_passe_2e ballon : rebond après arrêt ou tir contré_match"] / tot * 100
    mil = WS_JOUEURS[WS_JOUEURS["poste"].astype(str).str.startswith("Milieu")].groupby("equipe")["interventions_surface"].sum()
    w["milieux_surface_match"] = w["equipe"].map(mil) / w["matchs"]
    inds = [("dist_tirs_m", "Distance moyenne du tir (m)", 1),
            ("pct_grosses_occasions", "% de grosses occasions (définition Opta)", 0),
            ("pct_tirs_contre_attaque", "% tirs en contre-attaque", 0),
            ("pct_tirs_1re_intention", "% tirs en 1re intention (tireur libre à la réception)", 0),
            ("pct_tirs_individuels", "% tirs après une action individuelle (sans passe décisive)", 0),
            ("pct_tirs_apres_elimination", "% tirs juste après avoir éliminé un des nôtres", 0),
            ("pct_tirs_remise", "% tirs après une remise en retrait", 0),
            ("pct_tirs_profondeur", "% tirs après une passe en profondeur", 0),
            ("pct_tirs_rebond", "% tirs sur un 2e ballon (rebond)", 0),
            ("pct_tirs_tete_jeu", "% tirs de la tête", 0),
            ("pct_tirs_contres", "% tirs contrés", 0),
            ("pct_tirs_contact", "% tirs avec un contact défensif à ≤ 10 m dans les 3 s", 0),
            ("joueurs_impliques_tir", "Nos joueurs impliqués dans les 10 s avant le tir", 2),
            ("milieux_surface_match", "Interventions de nos milieux dans la surface /match", 1)]
    defaut = [c for c in [NOM_WS, "Brest"] + refs_l1 if c in set(w["equipe"])]
    clubs = st.multiselect("Clubs comparés", sorted(w["equipe"]), default=list(dict.fromkeys(defaut))[:5], key="p2_disc")
    st.markdown(f"xG par tir concédé (dans le jeu) : " + " · ".join(
        f"**{c}** {fmt(w.loc[w['equipe'] == c, 'xg_par_tir_jeu'].iloc[0], 3)}" for c in clubs)
        + f" · moyenne {fmt(w['xg_par_tir_jeu'].mean(), 3)}")
    r = tableau_indicateurs(w, clubs, inds, "xg_par_tir_jeu")
    g, _ = st.columns([2.2, 1])
    with g:
        barres_correlations(r, {c: l.split(" (")[0] for c, l, _ in inds},
                            "lien avec le xG par tir concédé (r) — rouge : plus il y en a, plus les tirs sont dangereux")
    phrases = []
    for autre in [c for c in clubs if c != NOM_WS]:
        e = ecarts_qui_comptent(w, NOM_WS, autre, inds, r)
        if e:
            phrases.append(f"**{EQUIPE} vs {autre}** : " + " ; ".join(
                f"{lib[0].lower() + lib[1:]} {fmt(a_, d_)} contre {fmt(b_, d_)}" for _, lib, a_, b_, d_, _ in e))
    if phrases:
        lecture("Les écarts qui comptent (indicateurs liés au danger, |r| ≥ 0,3, classés par écart × lien) :<br>"
                + "<br>".join(phrases))
    nous = w[w["equipe"] == NOM_WS].iloc[0]
    lecture("Lecture : ce qui rend les tirs adverses dangereux, ce n'est pas le nombre de nos joueurs autour ni les contacts "
            f"(liens faibles : r = {fmt(r['joueurs_impliques_tir'], 2)} et {fmt(r['pct_tirs_contact'], 2)}), c'est **d'où et "
            f"comment l'adversaire tire** : de près (r = {fmt(r['dist_tirs_m'], 2)}), en **contre-attaque** "
            f"(r = {fmt(r['pct_tirs_contre_attaque'], 2)}), en **1re intention**, c'est-à-dire libre à la réception "
            f"(r = {fmt(r['pct_tirs_1re_intention'], 2)}), ou **juste après avoir éliminé un des nôtres** "
            f"(r = {fmt(r['pct_tirs_apres_elimination'], 2)}). À l'inverse, les défenses solides obligent l'adversaire à "
            f"**se créer le tir seul** (tirs individuels, r = {fmt(r['pct_tirs_individuels'], 2)}) et leurs **milieux "
            f"interviennent davantage dans la surface** (r = {fmt(r['milieux_surface_match'], 2)}) : c'est la trace "
            f"statistique de la redescente d'un milieu (chez nous {fmt(nous['milieux_surface_match'], 1)} par match, moyenne "
            f"{fmt(w['milieux_surface_match'].mean(), 1)}). Pistes : **un milieu qui redescend dans la surface** sur les "
            "attaques placées, **personne de libre au point de penalty** à la réception, **ne pas se faire éliminer** "
            "près de la surface, **sécuriser la perte** (contre-attaques).")
    with st.expander("Europe (FotMob, 96 clubs) : les mêmes questions avec moins de détail"):
        inds_fm = [("dist_tirs_contre_m", "Distance moyenne du tir (m)", 1),
                   ("pct_tirs_surface_contre", "% tirs dans la surface", 0),
                   ("pct_tirs_axe_contre", "% tirs face au but (entre les poteaux)", 0),
                   ("pct_grosses_occ_contre", "% de grosses occasions", 0),
                   ("pct_tirs_tete_contre", "% tirs de la tête", 0),
                   ("pct_tirs_contres_contre", "% tirs contrés", 0)]
        clubs_fm = list(dict.fromkeys([EQUIPE] + refs_eu + refs_l1))
        r_fm = tableau_indicateurs(EQ, clubs_fm, inds_fm, "xga_par_tir")
        g, _ = st.columns([2.2, 1])
        with g:
            barres_correlations(r_fm, {c: l for c, l, _ in inds_fm}, "lien avec le xG par tir concédé (r, 96 clubs)")
    encadre_limite("Distance au tireur, prise à 2, milieu qui redescend : ce que nos données ne voient pas",
                   "Le % de tirs avec un contact défensif est un indice très partiel (lien faible avec le danger) : la "
                   "plupart des pressions, des prises à 2 et des replacements se font sans toucher le ballon. " + TEXTE_STATSBOMB)


# ------------------------------------------------------------------ PISTE 1 : sections
def tableau_par(c, groupe, ordre):
    """Centres de Ligue 1 et nos centres concédés, regroupés : nombre, % réussis, % suivis d'un tir, xG par centre."""
    lignes = []
    for k in ordre:
        ligne = {groupe: k}
        for nom, d in ((LIGUE, c), (EQUIPE, c[c["equipe"] == NOM_WS])):
            x = d[d[groupe] == k]
            ligne[f"{nom} : centres"] = len(x)
            ligne[f"{nom} : % réussis"] = fmt(x["reussi"].mean() * 100, 0) if len(x) else "–"
            ligne[f"{nom} : xG / centre"] = fmt(x["xg_10s"].mean(), 3) if len(x) else "–"
        lignes.append(ligne)
    st.dataframe(pd.DataFrame(lignes), hide_index=True)


def section_pression_distance():
    c = WS_CENTRES_L1.copy()
    c["Distance du centre"] = pd.cut(c["distance_but_m"], [0, 20, 30, 300], labels=["< 20 m", "20 à 30 m", "> 30 m"]).astype(str)
    c["Temps laissé au centreur"] = pd.cut(c["temps_centreur_s"], [-1, 1, 3, 1e4],
                                           labels=["≤ 1 s (1re intention)", "1 à 3 s", "> 3 s"]).astype(str)
    c["Type de centre"] = np.where(c["long"], "Ballon long (« long ball » Opta)", "Court ou moyen")
    g, d = st.columns(2)
    with g:
        st.markdown("**Selon la distance du centre**")
        tableau_par(c, "Distance du centre", ["< 20 m", "20 à 30 m", "> 30 m"])
        st.markdown("**Selon le type de centre**")
        tableau_par(c, "Type de centre", ["Court ou moyen", "Ballon long (« long ball » Opta)"])
    with d:
        st.markdown("**Selon le temps laissé au centreur** (≈ pression)")
        tableau_par(c, "Temps laissé au centreur", ["≤ 1 s (1re intention)", "1 à 3 s", "> 3 s"])
        st.caption("Temps laissé au centreur = secondes entre la dernière action d'un autre adversaire (la passe qu'il a "
                   "reçue) et son centre. Plus il est long, plus il a eu le temps de contrôler, d'avancer, de lever la tête.")
    nous = c[c["equipe"] == NOM_WS]

    def xg(d, masque):
        return d.loc[masque(d), "xg_10s"].mean()
    l_loin, l_pres = xg(c, lambda d: d["distance_but_m"] > 30), xg(c, lambda d: d["distance_but_m"] <= 30)
    n_loin, n_pres = xg(nous, lambda d: d["distance_but_m"] > 30), xg(nous, lambda d: d["distance_but_m"] <= 30)
    l_long, n_long = xg(c, lambda d: d["long"]), xg(nous, lambda d: d["long"])
    r_long_l = c.loc[c["long"], "reussi"].mean() * 100
    r_long_n = nous.loc[nous["long"], "reussi"].mean() * 100
    l_3, n_3 = xg(c, lambda d: d["temps_centreur_s"] > 3), xg(nous, lambda d: d["temps_centreur_s"] > 3)
    lecture(f"En {LIGUE}, un centre tiré de plus de 30 m vaut **{fmt(l_loin, 3)} xG**, contre {fmt(l_pres, 3)} plus près : "
            f"la distance protège un peu. **Chez nous, c'est l'inverse** : {fmt(n_loin, 3)} xG de loin contre {fmt(n_pres, 3)} "
            f"de près. Ce n'est donc pas la distance qui fait le danger, c'est **ce qui se passe dans la surface sur les centres "
            f"longs** : nos adversaires réussissent **{fmt(r_long_n, 0)} %** de leurs centres longs, contre "
            f"{fmt(r_long_l, 0)} % en moyenne, pour {fmt(n_long, 3)} xG par centre (moyenne {fmt(l_long, 3)}). Quand le centreur "
            f"a eu **plus de 3 s**, ses centres nous coûtent {fmt(n_3, 3)} xG (moyenne {fmt(l_3, 3)}) : le temps laissé au "
            "centreur compte, mais il ne dit pas à lui seul si quelqu'un était sur lui.")
    contact = c["contact"].mean() * 100
    encadre_limite("Peut-on prouver que c'est la pression et pas la distance ? Pas avec nos données",
                   f"Seuls **{fmt(contact, 1)} %** des centres de {LIGUE} ont une action défensive enregistrée à moins de 10 m du "
                   "centreur dans les 3 s avant : la pression sur le centreur est presque toujours **sans contact**, donc "
                   "absente des événements. Le temps laissé au centreur et le type de centre sont les meilleurs indices "
                   "disponibles, pas une preuve. " + TEXTE_STATSBOMB)


def section_systeme_collectif():
    a = WS_AC.copy()
    moy = a.groupby("attaque").agg(c_moy=("centres", "mean"), xg_moy=("xg_apres_centres", "mean"),
                                   arr_moy=("arrivees_couloir", "mean"), pc_moy=("pct_arrivees_centre", "mean"))
    a = a.join(moy, on="attaque")
    a["ratio_centres"] = a["centres"] / a["c_moy"]
    dang = moy[(moy["c_moy"] >= moy["c_moy"].median()) & (moy["xg_moy"] >= moy["xg_moy"].median())].index.tolist()
    a["a4"] = a["systeme_defense"].astype(str).str[0].eq("4")
    ex = a[a["attaque"].isin(dang) & a["a4"] & (a["defense"] != NOM_WS)
           & ((a["ratio_centres"] <= 0.65) | ((a["xg_apres_centres"] <= 0.35 * a["xg_moy"]) & (a["ratio_centres"] <= 0.85)))]
    ex = ex.assign(baisse=(1 - ex["ratio_centres"]) + (1 - ex["xg_apres_centres"] / ex["xg_moy"]).clip(lower=-1))
    ex = ex.sort_values("baisse", ascending=False).head(10)
    st.markdown(f"Attaques **habituellement dangereuses sur centres** (au-dessus de la médiane en centres **et** en xG "
                f"après centre) : {', '.join(dang)}. Matchs où une **défense à 4** les a fait passer bien sous leur habitude :")
    t = pd.DataFrame({
        "Match (défense – attaque)": [f"{r['defense']} – {r['attaque']} ({pd.Timestamp(r['date']).strftime('%d/%m')})"
                                      for _, r in ex.iterrows()],
        "Système défense": ex["systeme_defense"],
        "Centres (habituel)": [f"{int(r['centres'])} ({fmt(r['c_moy'], 1)})" for _, r in ex.iterrows()],
        "xG après centres (habituel)": [f"{fmt(r['xg_apres_centres'], 2)} ({fmt(r['xg_moy'], 2)})" for _, r in ex.iterrows()],
        "Arrivées dans le couloir (habituel)": [f"{int(r['arrivees_couloir'])} ({fmt(r['arr_moy'], 0)})" for _, r in ex.iterrows()],
        "% arrivées → centre (habituel)": [f"{fmt(r['pct_arrivees_centre'], 0)} ({fmt(r['pc_moy'], 0)})" for _, r in ex.iterrows()],
        "% ressorties": [fmt(v, 0) for v in ex["pct_arrivees_ressortie"]],
        "% actions ailier / milieu": [fmt(v, 0) for v in ex["pct_aide"]],
        "Prises à 2": ex["prises_a_2"].astype(int),
    })
    st.dataframe(t, hide_index=True)
    st.caption("Arrivées dans le couloir = possessions adverses qui touchent le ballon dans un couloir des 30 derniers mètres. "
               "Ressortie = passe vers l'arrière (≥ 10 m) depuis le couloir, sans centre. % actions ailier / milieu = part des "
               "actions défensives dans nos couloirs (40 m) faites par un non-défenseur. Prise à 2 = deux de nos joueurs qui "
               "interviennent dans le même couloir en moins de 4 s.")
    r_pc = a[["ratio_centres", "pct_arrivees_centre"]].corr().iloc[0, 1]
    r_arr = a.assign(r_arr=a["arrivees_couloir"] / a["arr_moy"])[["ratio_centres", "r_arr"]].corr().iloc[0, 1]
    r_aide = a[["ratio_centres", "pct_aide"]].corr().iloc[0, 1]
    r_p2 = a[["ratio_centres", "prises_a_2"]].corr().iloc[0, 1]
    nous = a[a["defense"] == NOM_WS]
    lecture(f"Sur les {len(a)} matchs de {LIGUE}, ce qui fait baisser le nombre de centres adverses : d'abord **moins "
            f"d'arrivées dans le couloir** (lien r = {fmt(r_arr, 2)}), puis le fait que, **une fois dans le couloir, "
            f"l'adversaire ne centre pas** (r = {fmt(r_pc, 2)}). La part d'actions faites par un ailier ou un milieu "
            f"(r = {fmt(r_aide, 2)}) et les prises à 2 (r = {fmt(r_p2, 2)}) **ne suffisent pas à l'expliquer** dans les "
            "événements : l'aide qui compte (fermer l'intérieur, se placer à côté du latéral) se fait souvent **sans toucher "
            f"le ballon**. Chez nous : **{fmt(nous['arrivees_couloir'].mean(), 0)} arrivées** adverses dans nos couloirs par "
            f"match (moyenne {fmt(a['arrivees_couloir'].mean(), 0)}), **{fmt(nous['pct_arrivees_centre'].mean(), 0)} %** "
            f"finissent en centre (moyenne {fmt(a['pct_arrivees_centre'].mean(), 0)} %), "
            f"**{fmt(nous['pct_aide'].mean(), 0)} %** de nos actions dans les couloirs faites par un ailier ou un milieu "
            f"(moyenne {fmt(a['pct_aide'].mean(), 0)} %).")
    if len(ex):
        choix = st.selectbox("Voir les prises à 2 d'un match (minutes pour la vidéo)", t["Match (défense – attaque)"].tolist(),
                             key="p1_ac_match")
        r = ex.iloc[t["Match (défense – attaque)"].tolist().index(choix)]
        sq = WS_AC_SEQ[(WS_AC_SEQ["game_id"] == r["game_id"]) & (WS_AC_SEQ["defense"] == r["defense"])]
        if len(sq):
            st.dataframe(sq[["minute", "cote_defense", "joueur_1", "joueur_2", "actions", "suite"]].rename(columns={
                "minute": "Min.", "cote_defense": "Couloir (vu par la défense)", "joueur_1": "1er joueur",
                "joueur_2": "2e joueur", "actions": "Actions", "suite": "Suite"}), hide_index=True)
        else:
            st.caption("Aucune prise à 2 enregistrée dans ce match : l'aide s'est faite sans contact — à regarder en vidéo "
                       "(placement de l'ailier, distance avec le latéral).")


def section_europe_centres():
    """Europe (FotMob) : attaques qui centrent beaucoup, tombées sur une défense à 4 qui les a privées de centres."""
    if "systeme" not in EM.columns:
        return
    att = EQ.set_index("equipe")
    moy_c = att["centres_tentes"] / att["mj"]
    dang = moy_c[moy_c >= moy_c.quantile(0.66)].index
    m = EM[(EM["adversaire"].isin(dang)) & EM["systeme"].astype(str).str[0].eq("4")].copy()
    m["c_moy"] = m["adversaire"].map(moy_c)
    m["ratio"] = m["centres_adv"] / m["c_moy"]
    m["ligue"] = m["equipe"].map(att["ligue"])
    m = m[(m["ratio"] <= 0.5) & (m["ligue"] != LIGUE)].sort_values("ratio").head(8)
    if not len(m):
        return
    st.markdown("**Ailleurs en Europe (FotMob, sans le détail des actions)** : grosses équipes de centreurs privées de "
                "centres par une défense à 4 — matchs à regarder en vidéo")
    st.dataframe(pd.DataFrame({
        "Match (défense – attaque)": [f"{r['equipe']} – {r['adversaire']} ({r['date']}, {r['score']})" for _, r in m.iterrows()],
        "Ligue": m["ligue"], "Système défense": m["systeme"],
        "Centres de l'attaque (habituel)": [f"{int(r['centres_adv'])} ({fmt(r['c_moy'], 1)})" for _, r in m.iterrows()],
        "xG de la tête concédé": [fmt(v, 2) for v in m["xga_tete"]]}), hide_index=True)


def tableau_lateraux(clubs):
    lat = WS_JOUEURS[(WS_JOUEURS["poste"] == "Latéral / piston") & (WS_JOUEURS["minutes_ws"] >= 300)].copy()
    lat = lat[((lat["equipe"] != NOM_WS) | lat["au_club"].fillna(True).astype(bool)) & (lat["cote"] != "Axe")]
    cols = {"centres_adv_cote_90": "Centres subis de son côté /90", "pct_centres_cote_reussis": "% réussis",
            "pct_centres_cote_loin": "% de loin (> 30 m)", "temps_centreur_cote_s": "Temps laissé au centreur (s)",
            "centres_adv_cote_tir_90": "Centres suivis d'un tir /90", "xg_apres_centres_adv_cote_90": "xG après ces centres /90"}
    t = lat[lat["equipe"].isin(clubs)].sort_values(["equipe", "minutes_ws"], ascending=[True, False])
    t = t[["equipe", "joueur", "cote", "minutes_ws"] + list(cols)].rename(
        columns={"equipe": "Club", "joueur": "Joueur", "cote": "Côté", "minutes_ws": "Min.", **cols})
    med = {"Club": f"Médiane {LIGUE}", "Joueur": f"({len(lat)} latéraux)", "Côté": "", "Min.": np.nan,
           **{l: lat[c].median() for c, l in cols.items()}}
    t = pd.concat([t, pd.DataFrame([med])], ignore_index=True)
    for c in list(cols.values()) + ["Min."]:
        t[c] = ["–" if pd.isna(v) else (f"{v:.0f}" if c.startswith("%") or c == "Min." else f"{v:.2f}").replace(".", ",")
                for v in t[c]]

    def couleur(r):
        if r["Club"] == NOM_WS:
            return ["background-color:#E0ECF8"] * len(r)
        if r["Club"].startswith("Médiane"):
            return ["background-color:#F3F5F1;font-style:italic"] * len(r)
        return ["background-color:#F0FDF4"] * len(r)
    st.dataframe(t.style.apply(couleur, axis=1), hide_index=True, height=38 + 35 * min(len(t), 14))
    st.caption("Bas = bien pour toutes les colonnes. Un latéral qui joue beaucoup côté fort adverse subit plus de centres : "
               "à lire avec la qualité (% réussis, xG après).")


# ------------------------------------------------------------------ PISTE 1 : DÉFENDRE LES CENTRES
def page_piste_centres():
    entete(PAGES_TITRES.index("Piste 1 · Défendre les centres"))
    o = NOUS
    lecture(f"Chaque centre adverse nous coûte **{fmt(o['xga_tete_par_centre_adv'] * 100, 1)} centièmes de xG de la tête**, "
            f"contre {fmt(EQ['xga_tete_par_centre_adv'].mean() * 100, 1)} en moyenne "
            f"({rang_txt(EQ, 'xga_tete_par_centre_adv', -1)} des 5 championnats). "
            + (f"En Ligue 1, **{fmt(WS_NOUS['pct_centres_suivis_tir'], 1)} %** des centres adverses sont suivis d'un tir en 10 s "
               f"({rang_txt(WS, 'pct_centres_suivis_tir', -1)}, moyenne {fmt(WS['pct_centres_suivis_tir'].mean(), 1)} %)."
               if WS_OK else ""))
    st.markdown("**Le profil recherché** : une équipe qui **subit peu de centres** (pression sur le porteur, latéral et "
                "ailier qui ferment le couloir, défense à 4) et dont les centres concédés partent **dans de mauvaises "
                "conditions** (de loin, sous pression, rarement reçus). Une équipe qui subit 50 centres et les défend bien "
                "grâce à 5 défenseurs dans la surface **n'est pas** le modèle : elle est écartée.")
    c1, c2 = st.columns(2)
    def4 = c1.toggle("Seulement les équipes à 4 défenseurs (2 centraux)", True, key="p1_def4")
    egal = c2.toggle("Volumes à possession égale (50/50)", False, key="p1_poss",
                     help="Une équipe qui a 65 % du ballon subit mécaniquement moins de centres. Activé : le nombre de "
                          "centres subis est ramené à ce qu'il serait si l'adversaire avait le ballon la moitié du temps.")

    # ---------- A. LA SÉLECTION
    titre("A. Peu de centres d'abord, des centres sans danger ensuite",
          "carré vert = idéal ; ronds creux = défense à 3 / 5 ; pointillés = médianes")
    eu = a_possession_egale(EQ, ["centres_adv_tentes_m"]) if egal else EQ
    d_eu, refs_eu, txt_eu, ec_eu, med_eu = selection_profil(
        eu, {"centres_adv_tentes_m": -1}, {"pct_centres_adv_reussis": -1, "xga_tete_par_centre_adv": -1},
        "centres_adv_tentes_m", "xga_tete_par_centre_adv", def4=def4, unite="centres")
    refs_l1 = []
    lib_quad = ("IDÉAL : peu de centres, sans danger", "beaucoup, mais bien défendus\n(bloc bas, défense à 5)",
                "peu, mais dangereux", "beaucoup et dangereux")
    g, d = st.columns(2)
    with g:
        bloc("Europe (96 clubs) : volume et danger des centres subis",
             lambda: matrice_profil(d_eu, "centres_adv_tentes_m", "xga_tete_par_centre_adv",
                                    "← centres adverses par match" + (" (possession égale)" if egal else ""),
                                    "← xG de la tête concédé par centre", refs_eu, med_eu, lib_quad, ligue_col="ligue"), "")
        encadre_refs("Références Europe", refs_eu, txt_eu)
        encadre_ecartes(ec_eu, d_eu, "beaucoup de centres subis", "Ils absorbent les centres (bloc bas, nombre dans la surface) au lieu de les empêcher")
    with d:
        if WS_OK:
            l1 = avec_contexte(WS)
            l1 = a_possession_egale(l1, ["centres_adv_match"]) if egal else l1
            d_l1, refs_l1, txt_l1, ec_l1, med_l1 = selection_profil(
                l1, {"centres_adv_match": -1},
                {"pct_centres_reussis_adv": -1, "xg_par_centre_adv": -1, "pct_centres_de_loin": 1},
                "centres_adv_match", "xg_par_centre_adv", def4=def4, unite="centres")
            bloc(f"{LIGUE} : volume et danger des centres subis (dans le jeu)",
                 lambda: matrice_profil(d_l1, "centres_adv_match", "xg_par_centre_adv",
                                        "← centres adverses dans le jeu par match" + (" (possession égale)" if egal else ""),
                                        "← xG dans les 10 s, par centre", refs_l1, med_l1, lib_quad, noms=True), "")
            encadre_refs(f"Références {LIGUE}", refs_l1, txt_l1)
            encadre_ecartes(ec_l1, d_l1, "beaucoup de centres subis", "Ils absorbent les centres (bloc bas, nombre dans la surface) au lieu de les empêcher")
        else:
            message_whoscored()
    with st.expander("Le classement complet (score = 60 % volume, 40 % danger)"):
        g, d = st.columns(2)
        with g:
            tableau_classement(d_eu.assign(Profil=d_eu["profil"]), refs_eu, {
                "ligue": "Ligue", "centres_adv_tentes_m": "Centres subis /match", "pct_centres_adv_reussis": "% réussis",
                "xga_tete_par_centre_adv": "xG tête / centre", "Profil": "Profil"}, n=12)
        with d:
            if WS_OK:
                tableau_classement(d_l1.assign(Profil=d_l1["profil"]), refs_l1, {
                    "centres_adv_match": "Centres /match", "pct_centres_reussis_adv": "% réussis",
                    "pct_centres_de_loin": "% de loin (> 30 m)", "xg_par_centre_adv": "xG / centre",
                    "Profil": "Profil"}, n=12)

    # ---------- B. COMMENT ILS Y ARRIVENT
    titre("B. Comment ils y arrivent : système, ballon, pressing",
          "PPDA = passes adverses par action défensive : bas = pression haute")
    profil_refs(list(dict.fromkeys(refs_l1 + refs_eu)),
                {"pct_def4": "% matchs à 4 déf.", "centres_adv_tentes_m": "Centres subis /match",
                 "pct_centres_adv_reussis": "% centres réussis", "xga_tete_par_centre_adv": "xG tête / centre",
                 "tirs_contre_m": "Tirs concédés /match"},
                {"centres_adv_match": "Centres dans le jeu /match (L1)", "pct_centres_de_loin": "% centres de loin (L1)"})
    with st.expander("Pour info : défendre le centre une fois donné (ne sert plus à choisir les références)"):
        if WS_OK:
            duel_ok = WS_NOUS["pct_aeriens_surface_gagnes"] >= WS["pct_aeriens_surface_gagnes"].mean()
            st.markdown(f"{EQUIPE} gagne **{fmt(WS_NOUS['pct_aeriens_surface_gagnes'], 0)} %** de ses duels aériens dans sa "
                        f"surface (moyenne {fmt(WS['pct_aeriens_surface_gagnes'].mean(), 0)} %) : "
                        + ("le premier duel n'est pas le problème. " if duel_ok else "le premier duel est un problème. ")
                        + f"**{fmt(WS_NOUS['pct_interventions_suivies_tir'], 0)} %** de nos interventions dans la surface sont "
                        f"suivies d'un tir adverse ({rang_txt(WS, 'pct_interventions_suivies_tir', -1)}) : le 2e ballon.")
        else:
            message_whoscored()

    # ---------- C. PRESSION OU DISTANCE
    titre("C. Pression sur le centreur ou distance du centre : ce que disent nos données",
          f"centres adverses dans le jeu, {LIGUE} (WhoScored) ; xG = tirs dans les 10 s qui suivent le centre")
    if WS_OK and WS_CENTRES_L1 is not None:
        section_pression_distance()
    else:
        message_whoscored()

    # ---------- D. LE SYSTÈME COLLECTIF
    titre("D. Le système collectif : des attaques dangereuses sur centres, neutralisées par une défense à 4",
          "match par match : ce que l'adversaire fait quand il arrive dans le couloir, ce que fait la défense")
    if WS_OK and WS_AC is not None:
        section_systeme_collectif()
    else:
        message_whoscored()
    section_europe_centres()

    # ---------- LATÉRAUX
    titre("Les latéraux : centres subis de leur côté et qualité de ces centres",
          f"{LIGUE}, ≥ 300 min ; centres adverses partis de son côté pendant qu'il était sur le terrain")
    if WS_OK:
        clubs = st.multiselect("Clubs comparés", sorted(WS["equipe"]), default=list(dict.fromkeys([NOM_WS] + refs_l1)),
                               key="p1_clubs_lat")
        tableau_lateraux(clubs)
    else:
        message_whoscored()
    st.markdown("**Radar : jusqu'à 4 latéraux**")
    radar_joueurs("p1_radar", ["Latéral / piston"],
                  [("centres_adv_cote_90", "Centres subis de son côté /90", -1),
                   ("pct_centres_cote_reussis", "% de ces centres réussis", -1),
                   ("xg_apres_centres_adv_cote_90", "xG après ces centres /90", -1),
                   ("temps_centreur_cote_s", "Temps laissé au centreur (s)", -1),
                   ("pct_duels_30m", "% duels gagnés (30 m)", 1),
                   ("dribble_subi_30m_90", "Dribblé (30 m) /90", -1)],
                  [("% duels au sol gagnés", "% duels au sol gagnés", 1),
                   ("% duels aériens gagnés", "% duels aériens gagnés", 1),
                   ("Dribblé /90", "Dribblé /90", -1),
                   ("Tacles /90 (ajusté poss.)", "Tacles /90 (aj.)", 1),
                   ("Interceptions /90 (ajusté poss.)", "Interceptions /90 (aj.)", 1),
                   ("Duels perdus /90", "Duels perdus /90", -1)],
                  refs_l1 + refs_eu)

    # ---------- VIDÉO
    titre("Exemples à analyser en vidéo", "match et minute ; pour les clubs étrangers, le match le plus parlant")
    exemples("Centres", refs_l1, refs_eu, match_peu_de_centres,
             lambda r: f"{int(r['centres_adv'])} centres subis face à une attaque au-dessus de la moyenne, "
                       f"{fmt(r['xga_tete'], 2)} xG de la tête concédé : regarder la pression sur le porteur côté")

    # ---------- ENTRAÎNEMENT
    consignes("Pistes pour l'entraînement", [
        "**Avant le centre** — duel 1 contre 1 côté : le latéral cadre le porteur en moins de 2 s et ferme l'angle de "
        "centre (pied extérieur) ; l'ailier revient fermer l'intérieur. Mesure : nombre de centres « libres ».",
        "**Centres longs (ballons longs)** : chez nous ils trouvent preneur bien plus souvent qu'ailleurs (partie C) : "
        "travailler la fermeture du 2e poteau et la hauteur de la ligne quand le ballon est loin, pas seulement la sortie "
        "sur le centreur.",
        "**Ne pas laisser de temps au centreur** : sur les centres où le centreur a eu plus de 3 s, nous concédons plus "
        "que la moyenne (partie C) : l'ailier ferme l'intérieur, le latéral sort, on oblige à centrer vite ou à ressortir.",
        "**Dans la surface** — 3 contre 3 + gardien sur centres : marquage du 1er poteau et du point de penalty, "
        "le latéral opposé ferme le 2e poteau, contact avant le saut.",
        "**2e ballon** : sur chaque centre, un milieu fixé à l'entrée de surface (zone de reprise) ; consigne de "
        "dégagement « haut et large », jamais dans l'axe.",
        "**Vidéo** : montrer côte à côte une séquence « à reproduire » d'une référence et une séquence « à corriger » "
        "de chez nous, même type de centre."])
    note("decision_piste_centres", "✎ Décisions et exercices retenus", zone=True, hauteur=90)


# ------------------------------------------------------------------ PISTE 2 : PROTÉGER LA ZONE DE VÉRITÉ
def page_piste_zone():
    entete(PAGES_TITRES.index("Piste 2 · Protéger la zone de vérité"))
    o = NOUS
    lecture(f"On concède **{fmt(o['tirs_contre_m'], 1)} tirs par match** dont **{fmt(o['tirs_surface_contre_m'], 1)} dans la "
            f"surface** ({rang_txt(EQ, 'tirs_surface_contre_m', -1)}) et **{fmt(o['xga_cote_Axe_m'], 2)} xG face au but** "
            f"({rang_txt(EQ, 'xga_cote_Axe_m', -1)}). "
            + (f"En {LIGUE}, l'adversaire entre **{fmt(WS_NOUS['entrees_surface_match'], 1)} fois par match** dans notre "
               f"surface et **{fmt(WS_NOUS['pct_entrees_suivies_tir'], 0)} %** de ces entrées finissent en tir en 10 s "
               f"({rang_txt(WS, 'pct_entrees_suivies_tir', -1)})." if WS_OK else ""))
    st.markdown("**Le profil recherché** : une équipe qui **concède peu de tirs** — on empêche l'adversaire d'arriver en "
                "position de frapper — plutôt qu'une équipe qui en concède beaucoup mais de loin (bloc bas qui laisse frapper). "
                "**L'idéal combine les deux** : peu de frappes et, quand il y en a, peu de xG par frappe.")
    c1, c2 = st.columns(2)
    def4 = c1.toggle("Seulement les équipes à 4 défenseurs (2 centraux)", True, key="p2_def4")
    egal = c2.toggle("Volumes à possession égale (50/50)", False, key="p2_poss",
                     help="Activé : les tirs concédés sont ramenés à ce qu'ils seraient si l'adversaire avait le ballon "
                          "la moitié du temps (neutralise l'effet « on a toujours le ballon »).")

    # ---------- A. LA SÉLECTION
    titre("A. Peu de tirs d'abord, des tirs peu dangereux ensuite",
          "carré vert = idéal ; ronds creux = défense à 3 / 5 ; pointillés = médianes")
    base = a_possession_egale(EQ, ["tirs_contre_m", "tirs_surface_contre_m"]) if egal else EQ
    lib_quad = ("IDÉAL : peu de tirs, peu dangereux", "beaucoup de tirs, mais de loin\n(bloc bas qui laisse frapper)",
                "peu de tirs, mais dangereux", "beaucoup et dangereux")
    vol, qual = {"tirs_contre_m": -1, "tirs_surface_contre_m": -1}, {"xga_par_tir": -1, "xga_pied_surface_par_tir": -1}
    d_eu, refs_eu, txt_eu, ec_eu, med_eu = selection_profil(base, vol, qual, "tirs_contre_m", "xga_par_tir",
                                                            def4=def4, unite="tirs")
    d_l1, refs_l1, txt_l1, ec_l1, med_l1 = selection_profil(base[base["ligue"] == LIGUE], vol, qual, "tirs_contre_m",
                                                            "xga_par_tir", def4=def4, unite="tirs")
    lx = "← tirs concédés par match" + (" (possession égale)" if egal else "")
    g, d = st.columns(2)
    with g:
        bloc("Europe (96 clubs) : nombre et danger des tirs concédés",
             lambda: matrice_profil(d_eu, "tirs_contre_m", "xga_par_tir", lx, "← xG par tir concédé", refs_eu, med_eu,
                                    lib_quad, ligue_col="ligue"), "")
        encadre_refs("Références Europe", refs_eu, txt_eu)
        encadre_ecartes(ec_eu, d_eu, "beaucoup de tirs concédés", "Ils laissent frapper, souvent de loin, au lieu d'empêcher la frappe")
    with d:
        bloc(f"{LIGUE} : nombre et danger des tirs concédés",
             lambda: matrice_profil(d_l1, "tirs_contre_m", "xga_par_tir", lx, "← xG par tir concédé", refs_l1, med_l1,
                                    lib_quad, noms=True), "")
        encadre_refs(f"Références {LIGUE}", refs_l1, txt_l1)
        encadre_ecartes(ec_l1, d_l1, "beaucoup de tirs concédés", "Ils laissent frapper, souvent de loin, au lieu d'empêcher la frappe")
    with st.expander("Le classement complet (score = 60 % volume, 40 % danger)"):
        g, d = st.columns(2)
        for col, dd, rr in ((g, d_eu, refs_eu), (d, d_l1, refs_l1)):
            with col:
                tableau_classement(dd.assign(Profil=dd["profil"]), rr, {
                    "ligue": "Ligue", "tirs_contre_m": "Tirs /match", "tirs_surface_contre_m": "Tirs surface /match",
                    "xga_par_tir": "xG / tir", "Profil": "Profil"}, n=12)

    # ---------- B. COMMENT ILS Y ARRIVENT
    titre("B. Comment ils y arrivent : système, ballon, pressing, accès à la surface",
          "PPDA = passes adverses par action défensive : bas = pression haute")
    profil_refs(list(dict.fromkeys(refs_l1 + refs_eu)),
                {"pct_def4": "% matchs à 4 déf.", "tirs_contre_m": "Tirs concédés /match",
                 "tirs_surface_contre_m": "Tirs surface /match", "xga_par_tir": "xG / tir",
                 "touches_surface_contre_m": "Ballons adv. dans notre surface /match", "xga_cote_Axe_m": "xG face au but /match"},
                {"entrees_surface_match": "Entrées surface /match (L1)", "pct_entrees_suivies_tir": "% entrées → tir (L1)"})

    # ---------- C. LA ZONE DE VÉRITÉ
    titre("C. La zone de vérité : combien d'entrées, et combien finissent en tir",
          f"{LIGUE} ; un % élevé avec peu d'entrées pèse moins qu'un % moyen avec beaucoup d'entrées")
    if WS_OK:
        section_zone_score(refs_l1)
    else:
        message_whoscored()

    # ---------- D. CE QUI REND UN TIR DANGEREUX
    titre("D. Pourquoi leurs tirs sont moins dangereux : les indicateurs qui font la différence",
          "lien avec le danger = corrélation r entre l'indicateur et le xG par tir concédé, sur les clubs du championnat")
    if WS_OK:
        section_discriminants(refs_l1, refs_eu)
    else:
        message_whoscored()

    # ---------- JOUEURS
    titre("Les joueurs : radars jusqu'à 4 joueurs, 6 indicateurs",
          "percentile parmi les joueurs du même poste ; plus loin du centre = mieux")
    st.markdown("**Défenseurs centraux**")
    radar_joueurs("p2_dc", ["Défenseur central"],
                  [("pct_duels_30m", "% duels gagnés (30 m)", 1),
                   ("pct_aeriens_surface", "% aériens gagnés (surface)", 1),
                   ("tirs_contres_90", "Tirs contrés /90", 1),
                   ("interventions_surface_90", "Interventions dans la surface /90", 1),
                   ("dribble_subi_30m_90", "Dribblé (30 m) /90", -1),
                   ("duels_perdus_tir_90", "Duels perdus → tir /90", -1)],
                  [("% duels aériens gagnés", "% duels aériens gagnés", 1),
                   ("% duels au sol gagnés", "% duels au sol gagnés", 1),
                   ("Interceptions /90 (ajusté poss.)", "Interceptions /90 (aj.)", 1),
                   ("Tirs contrés /90", "Tirs contrés /90", 1),
                   ("Dribblé /90", "Dribblé /90", -1),
                   ("Dégagements /90", "Dégagements /90", 1)],
                  refs_l1 + refs_eu)
    st.markdown("**Milieux de terrain**")
    radar_joueurs("p2_mil", ["Milieu défensif / central"],
                  [("actions_z14_90", "Ballons gagnés en zone 14 /90", 1),
                   ("interventions_surface_90", "Redescentes : interventions dans la surface /90", 1),
                   ("recuperations_90", "Récupérations /90", 1),
                   ("pct_duels_30m", "% duels gagnés (30 m)", 1),
                   ("dribble_subi_30m_90", "Dribblé (30 m) /90", -1),
                   ("pertes_punies_90", "Pertes punies d'un tir /90", -1)],
                  [("Récupérations /90 (ajusté poss.)", "Récupérations /90 (aj.)", 1),
                   ("Interceptions /90 (ajusté poss.)", "Interceptions /90 (aj.)", 1),
                   ("Tacles /90 (ajusté poss.)", "Tacles /90 (aj.)", 1),
                   ("% duels au sol gagnés", "% duels au sol gagnés", 1),
                   ("Dribblé /90", "Dribblé /90", -1),
                   ("Duels perdus /90", "Duels perdus /90", -1)],
                  refs_l1 + refs_eu)
    st.caption("Zone 14 = axe devant notre surface (17 à 30 m de notre but). « Redescentes » = interventions défensives dans "
               "notre surface (dégagement, interception, contre, duel gagné) : pour un milieu, c'est la trace d'un retour "
               "dans la surface. Indicateurs Ligue 1 : WhoScored ; 5 championnats : FotMob.")

    # ---------- LES BUTS CITÉS
    if WS_OK:
        titre("Les buts du Havre et du Mans : ce qu'ils montrent")
        e = WS_ENTREES
        cas = e[e["adversaire"].isin(["Le Havre", "Le Mans"]) & e["tir_10s"]].sort_values(["but_10s", "xg_10s"],
                                                                                          ascending=False)
        st.dataframe(cas[["adversaire", "minute", "mode", "joueur", "receveur", "zone_depart", "tireur", "xg_10s", "but_10s"]]
                     .rename(columns={"adversaire": "Adversaire", "minute": "Min.", "mode": "Entrée", "joueur": "Qui entre",
                                      "receveur": "Pour qui", "zone_depart": "Départ", "tireur": "Tireur",
                                      "xg_10s": "xG", "but_10s": "But"}).style.format({"xG": "{:.2f}"}), hide_index=True)
        st.markdown(
            "- **Le Havre, 85'** : combinaison au bord de la surface sur notre droite (Mosengo → Nakamura), **Mizuta "
            "élimine Kamissoko balle au pied dans la surface**, sert Nakamura : arrêt de De Lange, **N'Diaye reprend de la "
            "tête**. Trois problèmes en une séquence : pas de pression sur la combinaison, duel perdu dans la surface, "
            "2e ballon non couvert.\n"
            "- **Le Mans, 94'** : jeu en triangle sur notre gauche jusqu'à la ligne de but (Traoré, Colas, Bretelle), "
            "**remise en retrait de Bamba depuis la surface** pour Vercruysse, seul au point de penalty. Le bloc recule "
            "vers le but au lieu de protéger la zone de remise.\n"
            "- **Le Mans, 83'** : changement d'aile, centre de Calodat depuis notre droite, arrêt de De Lange, **Colas "
            "suit et marque** : 2e ballon.")

    # ---------- VIDÉO
    titre("Exemples à analyser en vidéo", "match et minute ; pour les clubs étrangers, le match le plus parlant")
    exemples("Zone de vérité", refs_l1, refs_eu, match_zone_parlant,
             lambda r: f"face à une attaque au-dessus de la moyenne : {int(r['tirs_surface_contre'])} tirs dans la surface, "
                       f"{fmt(r['xga'], 2)} xG concédés, {int(r['touches_surface_contre'])} ballons touchés dans la surface")

    # ---------- ENTRAÎNEMENT
    consignes("Pistes pour l'entraînement", [
        "**Pression sur la zone 14** : jeu réduit devant la surface (4 contre 4 + 2 appuis) ; dès qu'un adversaire reçoit "
        "dans l'axe face au jeu, le milieu le plus proche sort sur lui en moins de 2 s, le défenseur central ne sort pas.",
        "**Défendre balle au pied dans la surface** : 1 contre 1 en entrée de surface, consigne « pas de tacle, on oriente "
        "vers l'extérieur », couverture du 2e défenseur à 3-4 m.",
        "**Remises en retrait** : quand le ballon arrive à la ligne, un milieu redescend au point de penalty (zone de "
        "remise) au lieu de suivre le porteur. À travailler sur des débordements à 2 contre 2 + 1 milieu.",
        "**Combinaisons au bord de la surface** : sortir sur le passeur et fermer la ligne de passe vers l'intérieur "
        "(les deux buts cités partent de combinaisons non pressées).",
        "**Références à regarder** : la distance entre nos lignes et la sortie des milieux chez les clubs retenus (vidéo "
        "ci-dessus)."])
    note("decision_piste_zone", "✎ Décisions et exercices retenus", zone=True, hauteur=90)


def page_detail():
    entete(10)
    m = MATCHS.copy()
    m["date"] = m["date"].dt.strftime("%d/%m")
    tab = m[["date", "adversaire", "lieu", "bp", "bc", "score_mt", "resultat", "xg", "xga", "xga_1mt", "xga_2mt",
             "xga_76_90", "tirs_contre", "grosses_occ_contre", "possession", "systeme", "systeme_adverse",
             "minutes_changements"]].rename(columns={
        "date": "Date", "adversaire": "Adversaire", "lieu": "Lieu", "bp": "BP", "bc": "BC", "score_mt": "Mi-tps",
        "resultat": "Rés.", "xg": "xG", "xga": "xGA", "xga_1mt": "xGA 1re MT", "xga_2mt": "xGA 2e MT",
        "xga_76_90": "xGA 76-90+", "tirs_contre": "Tirs contre", "grosses_occ_contre": "Grosses occ. contre",
        "possession": "Poss. %", "systeme": "Notre système", "systeme_adverse": "Système adverse",
        "minutes_changements": "Nos changements"})
    style = tab.style.format(precision=2)
    for col, cm in (("xG", "Greens"), ("xGA", "Reds"), ("xGA 2e MT", "Reds"), ("xGA 76-90+", "Reds")):
        style = style.background_gradient(subset=[col], cmap=cm)
    st.dataframe(style, hide_index=True, height=460)
    st.caption("Plus la case est foncée, plus la valeur est marquante.")
    with st.expander(f"Tableau complet des {NB} clubs"):
        cols = ["equipe", "ligue", "mj", "pts_m", "xg_m", "xg_contre_m", "xga_1mt_m", "xga_2mt_m", "part_xga_2mt",
                "xga90_Mène", "tirs_contre_m", "xga_par_tir", "xga_cote_Axe_m", "xga_type_Tête_m", "possession_m"]
        st.dataframe(EQ[cols].sort_values("xg_contre_m", ascending=False).round(2), hide_index=True)
    if WS_OK:
        with st.expander(f"Tableau WhoScored des clubs de {LIGUE}"):
            st.dataframe(WS.round(2), hide_index=True)


# =====================================================================================
# 8. MENU ET AFFICHAGE
# =====================================================================================
with st.sidebar:
    st.markdown(f"### Diagnostic équipe\n**{EQUIPE}** · {LIGUE} {META['saison']}")
    choix = st.radio("Pages", [p[0] for p in PAGES], label_visibility="collapsed")
    st.markdown("---")
    st.markdown('<span class="pill" style="background:#DCFCE7;color:#166534">Point fort</span>'
                '<span class="pill" style="background:#FEE2E2;color:#991B1B">Point faible</span>'
                '<span class="pill">Dans la moyenne</span>', unsafe_allow_html=True)
    st.caption(f"Statut = rang parmi les {NB} clubs des 5 grands championnats (ou les clubs de {LIGUE} pour les "
               f"indicateurs WhoScored), par tiers. Frises : chaque point est un club, à droite = mieux.")
    if not WS_OK:
        st.warning("Événements WhoScored absents : transitions et vrai PPDA indisponibles (voir page 5).")

PAGES_F = [page_synthese, page_1, page_2, page_3, page_piste_centres, page_piste_zone, page_4, page_5, page_6, page_7,
           page_detail]
PAGES_F[[p[0] for p in PAGES].index(choix)]()
