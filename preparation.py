# -*- coding: utf-8 -*-
"""
=====================================================================================
 PRÉPARATION DES DONNÉES — DIAGNOSTIC DE NOTRE ÉQUIPE (exemple : OM)
=====================================================================================

CE QUE FAIT CE FICHIER
  Lit le fichier brut donnees/fotmob_big5_2026-27.json (545 matchs des 5 grands championnats,
  données Opta via FotMob) et produit les tableaux lus par app.py :

    equipes.csv     1 ligne par club (96) : xG pour/contre, par mi-temps, par tranche de 15 min,
                    selon le score, par situation, volume/qualité des tirs, style, points perdus…
    matchs.csv      1 ligne par match de NOTRE équipe
    tirs.csv        tous les tirs des matchs de NOTRE équipe (pour et contre), avec l'état du score
    joueurs.csv     1 ligne par joueur des 5 championnats (poste, minutes, stats par 90 min)
    on_off.csv      pour NOS joueurs : xG pour / contre quand ils sont sur le terrain ou non
    meta.json       équipe analysée, date d'extraction, nombre de matchs

  Pour changer d'équipe : modifier EQUIPE_ID et EQUIPE_NOM ci-dessous, puis relancer.

LANCEMENT (depuis le dossier OM_diagnostic) :
  & 'C:\\Users\\julie\\AppData\\Local\\Programs\\Python\\Python311\\python.exe' preparation.py
"""

import json
import warnings
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)

# =====================================================================================
# 1. RÉGLAGES
# =====================================================================================
EQUIPE_ID = "8592"            # identifiant FotMob de notre équipe (Marseille)
EQUIPE_NOM = "Marseille"
DOSSIER = Path(__file__).resolve().parent / "donnees"
BRUT = DOSSIER / "fotmob_big5_2026-27.json"

TRANCHES = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]
SITUATIONS = {"RegularPlay": "Jeu placé", "IndividualPlay": "Jeu placé", "FastBreak": "Contre-attaque",
              "FromCorner": "Corner", "SetPiece": "Autre CPA", "FreeKick": "Coup franc direct",
              "ThrowInSetPiece": "Autre CPA", "Penalty": "Penalty"}
ETATS = {1: "Mène", 0: "Nul", -1: "Mené"}
TYPES_TIR = ["Tête", "Pied dans la surface", "Hors surface", "Penalty"]
COTES = ["Gauche", "Axe", "Droite"]
JOUEURS_EXCLUS = []          # noms de joueurs partis à exclure à la main (sinon : détection automatique)
NB_DERNIERS_MATCHS_GROUPE = 3   # un joueur est « encore au club » s'il était dans le groupe d'un de ces matchs


def categorie_tir(situation, type_tir, surface):
    if situation == "Penalty":
        return "Penalty"
    if type_tir == "Header":
        return "Tête"
    return "Pied dans la surface" if surface else "Hors surface"


def cote_attaquant(y):
    """Côté du tir vu par l'équipe qui tire (FotMob : y > 34 = gauche de l'attaquant).
    Axe = face au but, entre les deux poteaux (7,32 m) ; Gauche / Droite = de part et d'autre."""
    return "Gauche" if y > 37.66 else "Droite" if y < 30.34 else "Axe"


INVERSE = {"Gauche": "Droite", "Droite": "Gauche", "Axe": "Axe"}   # côté de l'attaquant → côté du défenseur


def ecrire(df, nom):
    df.to_csv(DOSSIER / nom, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"  {nom:<14} {len(df):>6} lignes")


# =====================================================================================
# 2. POSTES (codes de position FotMob → 7 familles de postes)
#    Le code donne la ligne (dizaine) et la place dans la largeur (unité).
# =====================================================================================
def famille_poste(code, usuel=None):
    if code is None:
        return {0: "Gardien", 1: "Défenseur (?)", 2: "Milieu (?)", 3: "Attaquant"}.get(usuel, "Inconnu")
    c = int(code)
    if c == 11:
        return "Gardien"
    if c in (32, 38, 51, 59, 62, 68):
        return "Latéral / piston"
    if 33 <= c <= 37:
        return "Défenseur central"
    if 55 <= c <= 67 or 73 <= c <= 77:
        return "Milieu défensif / central"
    if c in (71, 72, 78, 79, 82, 83, 87, 88, 103, 107):
        return "Ailier"
    if c in (84, 85, 86, 95):
        return "Milieu offensif"
    if c >= 104:
        return "Attaquant"
    return "Inconnu"


# =====================================================================================
# 3. LECTURE
# =====================================================================================
D = json.loads(BRUT.read_text(encoding="utf-8"))
SK = {k: str(i) for i, k in enumerate(D["statKeys"])}
PK = D["pKeys"]
IDX_CENTRES = str(PK.index("Accurate crosses")) if "Accurate crosses" in PK else "x"


def stat_equipe(m, cle, cote):
    """Valeur d'une stat d'équipe du match (cote 0 = domicile, 1 = extérieur) ; pourcentage pour les ratios."""
    v = m["st"].get(SK.get(cle, "x"))
    if not v:
        return np.nan, np.nan
    val, pct = v[cote], v[cote + 2]
    return (np.nan if val is None else float(val)), (np.nan if pct is None else float(pct))


def tranche(periode, minute):
    if periode == "FirstHalf":
        return 0 if minute <= 15 else 1 if minute <= 30 else 2
    return 3 if minute <= 60 else 4 if minute <= 75 else 5


def cle_temps(mi_temps, minute, ajout):
    return (mi_temps, minute, ajout or 0)


def horloge(minute, mi_temps):
    """Minute « jouée » sans le temps additionnel (pour mesurer le temps passé dans chaque état du score)."""
    return min(minute, 45) if mi_temps == 1 else min(max(minute, 45), 90)


# =====================================================================================
# 4. BOUCLE SUR LES MATCHS
# =====================================================================================
E = defaultdict(lambda: defaultdict(float))       # cumul par équipe
LIGNES_EQ_MATCH = []                               # une ligne par équipe et par match (exemples de matchs à visionner)
NOMS, LIGUES = {}, {}
LIGNES_MATCHS, LIGNES_TIRS = [], []

for m in D["matches"]:
    ids = [m["h"][0], m["a"][0]]
    for i in (0, 1):
        NOMS[ids[i]] = m[("h", "a")[i]][1]
        LIGUES[ids[i]] = m["lg"]
    buts = [int(x) for x in m["score"].split(" - ")]

    # --- chronologie des buts (pour l'état du score) -----------------------------------
    chrono = []
    for t, ot, dom, _, _ in m["goals"]:
        mt = 1 if t <= 45 else 2
        chrono.append((cle_temps(mt, t, ot), 0 if dom else 1))
    chrono.sort()

    def ecart(cote, cle):
        """Écart au score avant l'instant 'cle', vu par l'équipe 'cote'."""
        d = sum(1 if c == cote else -1 for k, c in chrono if k < cle)
        return int(np.sign(d))

    # temps passé dans chaque état (en minutes de jeu, sans temps additionnel)
    temps_etat = [Counter(), Counter()]
    reperes = [0] + [horloge(k[1], k[0]) for k, _ in chrono] + [90]
    for j in range(len(reperes) - 1):
        duree = reperes[j + 1] - reperes[j]
        d = sum(1 if c == 0 else -1 for _, c in chrono[:j])
        temps_etat[0][int(np.sign(d))] += duree
        temps_etat[1][int(np.sign(-d))] += duree
    mene_un_moment = [any(sum(1 if c == cote else -1 for _, c in chrono[:j + 1]) > 0 for j in range(len(chrono)))
                      for cote in (0, 1)]

    # --- tirs -----------------------------------------------------------------------
    xg_tr = [[0.0] * 6, [0.0] * 6]
    xg_etat = [Counter(), Counter()]
    xg_sit = [Counter(), Counter()]
    tirs_n, tirs_surf, gros = [0, 0], [0, 0], [0, 0]
    # contexte des tirs (hors penalty) : distance au but, contrés, de la tête, face au but
    dist_np, n_np, contres_np, tetes_np, axe_np = [0.0, 0.0], [0, 0], [0, 0], [0, 0], [0, 0]
    xg_type, n_type = [Counter(), Counter()], [Counter(), Counter()]
    xg_cote, n_cote = [Counter(), Counter()], [Counter(), Counter()]   # côté vu par l'équipe qui TIRE
    for s in m["shots"]:
        (equipe, joueur, minute, ajout, periode, xg, xgot, situation, type_tir, x, y, evt, csc,
         surface, contre, cadre, nom) = s
        if csc or xg is None:
            continue
        cote = 0 if str(equipe) == ids[0] else 1
        mt = 1 if periode == "FirstHalf" else 2
        tr = tranche(periode, minute)
        et = ecart(cote, cle_temps(mt, minute, ajout))
        xg_tr[cote][tr] += xg
        xg_etat[cote][et] += xg
        xg_sit[cote][SITUATIONS.get(situation, "Jeu placé")] += xg
        tirs_n[cote] += 1
        tirs_surf[cote] += surface
        gros[cote] += xg >= 0.3
        cat = categorie_tir(situation, type_tir, surface)
        xg_type[cote][cat] += xg
        n_type[cote][cat] += 1
        if situation != "Penalty":
            dist_np[cote] += float(np.hypot(105 - x, 34 - y))
            n_np[cote] += 1
            contres_np[cote] += bool(contre)
            tetes_np[cote] += type_tir == "Header"
            axe_np[cote] += cote_attaquant(y) == "Axe"
            c_att = cote_attaquant(y)
            xg_cote[cote][c_att] += xg
            n_cote[cote][c_att] += 1
        if EQUIPE_ID in ids:
            nous = 0 if ids[0] == EQUIPE_ID else 1
            LIGNES_TIRS.append(dict(
                match_id=m["id"], date=m["date"], adversaire=NOMS[ids[1 - nous]],
                camp="pour" if cote == nous else "contre", joueur=nom, joueur_id=joueur,
                equipe=NOMS[ids[cote]], mi_temps=mt, minute=minute, ajout=ajout or 0, tranche=TRANCHES[tr],
                etat_score=ETATS[et] if cote == nous else ETATS[-et], xg=xg, xgot=xgot,
                situation=SITUATIONS.get(situation, "Jeu placé"), type_tir=type_tir, x=x, y=y,
                resultat=evt, dans_surface=bool(surface), contre=bool(contre), cadre=bool(cadre),
                categorie=categorie_tir(situation, type_tir, surface),
                # côté vu par NOUS : notre côté d'attaque (pour) ou notre côté défensif (contre)
                cote_nous=cote_attaquant(y) if cote == nous else INVERSE[cote_attaquant(y)]))

    # --- centres tentés / réussis par équipe (somme des statistiques joueurs du match) --------------
    cr_ok, cr_tot = Counter(), Counter()
    for _pid, _nom, _eq, _code, _us, _gk, _st in m["players"]:
        _v = _st.get(IDX_CENTRES)
        if isinstance(_v, list):
            cr_ok[str(_eq)] += _v[0] or 0
            cr_tot[str(_eq)] += _v[1] or 0

    # --- cumul par équipe -------------------------------------------------------------
    for cote in (0, 1):
        t, adv = ids[cote], 1 - cote
        e = E[t]
        pts = 3 if buts[cote] > buts[adv] else 1 if buts[cote] == buts[adv] else 0
        e["mj"] += 1
        e["pts"] += pts
        e["bp"] += buts[cote]
        e["bc"] += buts[adv]
        e["victoires"] += pts == 3
        e["defaites"] += pts == 0
        if mene_un_moment[cote] and pts < 3:
            e["pts_perdus_en_menant"] += 3 - pts
            e["matchs_menes_non_gagnes"] += 1
        for k, nom in (("expected_goals", "xg"), ("expected_goals_open_play", "xg_jeu"),
                       ("expected_goals_set_play", "xg_cpa"), ("expected_goals_non_penalty", "npxg"),
                       ("total_shots", "tirs"), ("big_chance", "grosses_occ"), ("touches_opp_box", "touches_surface"),
                       ("corners", "corners")):
            pour, _ = stat_equipe(m, k, cote)
            contre, _ = stat_equipe(m, k, adv)
            e[nom] += np.nan_to_num(pour)
            e[nom + "_contre"] += np.nan_to_num(contre)
        for k, nom in (("BallPossesion", "possession"), ("passes", "passes"),
                       ("matchstats.headers.tackles", "tacles"), ("interceptions", "interceptions"),
                       ("fouls", "fautes"), ("clearances", "degagements")):
            v, _ = stat_equipe(m, k, cote)
            e[nom] += np.nan_to_num(v)
        for k, nom in (("accurate_passes", "passes_reussies"), ("ground_duels_won", "duels_sol"),
                       ("aerials_won", "duels_aeriens"), ("long_balls_accurate", "longs_ballons"),
                       ("accurate_crosses", "centres")):
            v, pct = stat_equipe(m, k, cote)
            e[nom] += np.nan_to_num(v)
            e[nom + "_pct_somme"] += np.nan_to_num(pct)
        passes_adv, _ = stat_equipe(m, "own_half_passes", adv)
        e["passes_adv_camp_adverse"] += np.nan_to_num(passes_adv)    # passes de l'adversaire dans SA moitié (pour le pressing)
        for i in range(6):
            e[f"xg_{TRANCHES[i]}"] += xg_tr[cote][i]
            e[f"xga_{TRANCHES[i]}"] += xg_tr[adv][i]
        for et, lib in ETATS.items():
            e[f"min_{lib}"] += temps_etat[cote][et]
            e[f"xg_{lib}"] += xg_etat[cote][et]
            e[f"xga_{lib}"] += xg_etat[adv][-et]
        for lib in set(SITUATIONS.values()):
            e[f"xg_sit_{lib}"] += xg_sit[cote][lib]
            e[f"xga_sit_{lib}"] += xg_sit[adv][lib]
        for cat in TYPES_TIR:
            e[f"xg_type_{cat}"] += xg_type[cote][cat]
            e[f"xga_type_{cat}"] += xg_type[adv][cat]
            e[f"tirs_type_{cat}"] += n_type[cote][cat]
            e[f"tirsc_type_{cat}"] += n_type[adv][cat]
        for c in COTES:
            e[f"xg_cote_{c}"] += xg_cote[cote][c]                  # notre côté d'attaque
            e[f"xga_cote_{c}"] += xg_cote[adv][INVERSE[c]]         # notre côté défensif
            e[f"tirsc_cote_{c}"] += n_cote[adv][INVERSE[c]]
        LIGNES_EQ_MATCH.append(dict(
            equipe_id=t, adversaire=m[("h", "a")[adv]][1], date=m["date"], lieu="Dom." if cote == 0 else "Ext.",
            score=f"{buts[cote]}-{buts[adv]}", centres_adv=cr_tot[ids[adv]], centres_adv_reussis=cr_ok[ids[adv]],
            xga=sum(xg_tr[adv]), xga_tete=xg_type[adv]["Tête"], tetes_contre=n_type[adv]["Tête"],
            tirs_surface_contre=tirs_surf[adv], xga_face_au_but=xg_cote[adv]["Axe"],
            touches_surface_contre=np.nan_to_num(stat_equipe(m, "touches_opp_box", adv)[0]),
            tirs_contre=tirs_n[adv], centres=cr_tot[t],
            systeme=(m["lineup"][("h", "a")[cote]] or {}).get("f"), systeme_adv=(m["lineup"][("h", "a")[adv]] or {}).get("f")))
        e["centres_tentes"] += cr_tot[t]
        e["centres_reussis"] += cr_ok[t]
        e["centres_tentes_contre"] += cr_tot[ids[adv]]
        e["centres_reussis_contre"] += cr_ok[ids[adv]]
        e["tirs_shotmap"] += tirs_n[cote]
        e["tirs_shotmap_contre"] += tirs_n[adv]
        e["tirs_surface_contre"] += tirs_surf[adv]
        e["dist_tirs_contre"] += dist_np[adv]
        e["tirs_np_contre"] += n_np[adv]
        e["contres_contre"] += contres_np[adv]
        e["tetes_np_contre"] += tetes_np[adv]
        e["axe_np_contre"] += axe_np[adv]
        e["occ_xg03_contre"] += gros[adv]
        e["occ_xg03"] += gros[cote]
        e["xg_shotmap"] += sum(xg_tr[cote])
        e["xga_shotmap"] += sum(xg_tr[adv])

    # --- ligne match pour NOTRE équipe ------------------------------------------------
    if EQUIPE_ID in ids:
        n = 0 if ids[0] == EQUIPE_ID else 1
        a = 1 - n
        mt_buts = [[0, 0], [0, 0]]
        for k, c in chrono:
            mt_buts[k[0] - 1][0 if c == n else 1] += 1
        poss, _ = stat_equipe(m, "BallPossesion", n)
        LIGNES_MATCHS.append(dict(
            match_id=m["id"], date=pd.to_datetime(m["date"].replace(" UTC", ""), format="%a, %b %d, %Y, %H:%M"),
            journee=m.get("round"), adversaire=NOMS[ids[a]], lieu="Dom." if n == 0 else "Ext.",
            bp=buts[n], bc=buts[a], score_mt=f"{mt_buts[0][0]}-{mt_buts[0][1]}",
            resultat="V" if buts[n] > buts[a] else "N" if buts[n] == buts[a] else "D",
            xg=stat_equipe(m, "expected_goals", n)[0], xga=stat_equipe(m, "expected_goals", a)[0],
            xg_1mt=sum(xg_tr[n][:3]), xg_2mt=sum(xg_tr[n][3:]), xga_1mt=sum(xg_tr[a][:3]), xga_2mt=sum(xg_tr[a][3:]),
            xga_76_90=xg_tr[a][5], tirs=tirs_n[n], tirs_contre=tirs_n[a], possession=poss,
            grosses_occ_contre=stat_equipe(m, "big_chance", a)[0], a_mene=mene_un_moment[n],
            systeme=(m["lineup"][("h", "a")[n]] or {}).get("f"),
            systeme_adverse=(m["lineup"][("h", "a")[a]] or {}).get("f"),
            entraineur=(m["lineup"][("h", "a")[n]] or {}).get("coach")))

# =====================================================================================
# 5. TABLEAU DES ÉQUIPES
# =====================================================================================
eq = pd.DataFrame(E).T
eq.index.name = "equipe_id"
eq = eq.reset_index()
eq.insert(1, "equipe", eq["equipe_id"].map(NOMS))
eq.insert(2, "ligue", eq["equipe_id"].map(LIGUES))
mj = eq["mj"]
par_match = ["pts", "bp", "bc", "xg", "xg_contre", "xg_jeu", "xg_jeu_contre", "xg_cpa", "xg_cpa_contre", "npxg",
             "npxg_contre", "tirs", "tirs_contre", "grosses_occ", "grosses_occ_contre", "touches_surface",
             "touches_surface_contre", "corners", "corners_contre", "possession", "passes", "tacles",
             "interceptions", "fautes", "degagements", "passes_reussies", "occ_xg03_contre", "occ_xg03",
             "passes_adv_camp_adverse"] + [c for c in eq.columns if c.startswith(("xg_", "xga_")) and
                                           not c.startswith(("xg_Mène", "xg_Nul", "xg_Mené", "xga_Mène", "xga_Nul", "xga_Mené"))]
for c in dict.fromkeys(par_match):
    if c in eq.columns and c not in ("xg_shotmap",):
        eq[c + "_m"] = eq[c] / mj
for lib in ETATS.values():   # xG concédés par 90 minutes passées dans chaque état du score
    eq[f"xga90_{lib}"] = eq[f"xga_{lib}"] / eq[f"min_{lib}"].replace(0, np.nan) * 90
    eq[f"xg90_{lib}"] = eq[f"xg_{lib}"] / eq[f"min_{lib}"].replace(0, np.nan) * 90
    eq[f"part_temps_{lib}"] = eq[f"min_{lib}"] / (mj * 90) * 100
for nom in ("duels_sol", "duels_aeriens", "longs_ballons", "centres"):
    eq[f"pct_{nom}"] = eq[f"{nom}_pct_somme"] / mj
eq["pct_passes"] = eq["passes_reussies_pct_somme"] / mj
for c in [c for c in eq.columns if c.startswith(("tirs_type_", "tirsc_type_", "tirsc_cote_"))]:
    eq[c + "_m"] = eq[c] / mj
for cat in TYPES_TIR:   # danger moyen d'un tir concédé de chaque type
    eq[f"xga_par_tir_{cat}"] = eq[f"xga_type_{cat}"] / eq[f"tirsc_type_{cat}"].replace(0, np.nan)
nc = sum(eq[f"xga_cote_{c}"] for c in COTES)
for c in COTES:
    eq[f"part_xga_cote_{c}"] = eq[f"xga_cote_{c}"] / nc * 100
eq["xga_1mt_m"] = eq[[f"xga_{t}" for t in TRANCHES[:3]]].sum(axis=1) / mj
eq["xga_2mt_m"] = eq[[f"xga_{t}" for t in TRANCHES[3:]]].sum(axis=1) / mj
eq["xg_1mt_m"] = eq[[f"xg_{t}" for t in TRANCHES[:3]]].sum(axis=1) / mj
eq["xg_2mt_m"] = eq[[f"xg_{t}" for t in TRANCHES[3:]]].sum(axis=1) / mj
eq["part_xga_2mt"] = eq["xga_2mt_m"] / (eq["xga_1mt_m"] + eq["xga_2mt_m"]) * 100
eq["xga_par_tir"] = eq["xga_shotmap"] / eq["tirs_shotmap_contre"]
eq["xg_par_tir"] = eq["xg_shotmap"] / eq["tirs_shotmap"]
eq["pct_tirs_surface_contre"] = eq["tirs_surface_contre"] / eq["tirs_shotmap_contre"] * 100
eq["buts_moins_xg"] = (eq["bp"] - eq["xg"]) / mj
eq["buts_contre_moins_xga"] = (eq["bc"] - eq["xg_contre"]) / mj
eq["ppda_approx"] = eq["passes_adv_camp_adverse"] / (eq["tacles"] + eq["interceptions"] + eq["fautes"]).replace(0, np.nan)
eq["pts_perdus_en_menant_m"] = eq["pts_perdus_en_menant"] / mj
eq["xg_diff_m"] = eq["xg_m"] - eq["xg_contre_m"]
# Centres adverses (toutes situations, d'après les statistiques joueurs) : volume, précision, danger de la tête
eq["centres_adv_tentes_m"] = eq["centres_tentes_contre"] / mj
eq["centres_adv_reussis_m"] = eq["centres_reussis_contre"] / mj
eq["pct_centres_adv_reussis"] = eq["centres_reussis_contre"] / eq["centres_tentes_contre"].replace(0, np.nan) * 100
eq["xga_tete_par_centre_adv"] = eq["xga_type_Tête"] / eq["centres_tentes_contre"].replace(0, np.nan)
eq["tirs_surface_contre_m"] = eq["tirs_surface_contre"] / mj
# Contexte des tirs concédés (hors penalty)
eq["dist_tirs_contre_m"] = eq["dist_tirs_contre"] / eq["tirs_np_contre"]
eq["pct_tirs_contres_contre"] = eq["contres_contre"] / eq["tirs_np_contre"] * 100
eq["pct_tirs_tete_contre"] = eq["tetes_np_contre"] / eq["tirs_np_contre"] * 100
eq["pct_tirs_axe_contre"] = eq["axe_np_contre"] / eq["tirs_np_contre"] * 100
eq["pct_tirs_surface_contre"] = eq["tirs_surface_contre"] / eq["tirs_shotmap_contre"] * 100
eq["pct_grosses_occ_contre"] = eq["grosses_occ_contre"] / eq["tirs_contre"] * 100
eq["xga_pied_surface_par_tir"] = eq["xga_type_Pied dans la surface"] / eq["tirsc_type_Pied dans la surface"].replace(0, np.nan)
# Système le plus utilisé (compositions de départ FotMob) : « 4-2-3-1 (7), 4-1-4-1 (3) »
SYSTEMES = defaultdict(Counter)
for m in D["matches"]:
    for c in ("h", "a"):
        if m["lineup"][c] and m["lineup"][c].get("f"):
            SYSTEMES[m[c][0]][m["lineup"][c]["f"]] += 1
eq["systeme"] = eq["equipe_id"].map(lambda i: ", ".join(f"{f} ({n})" for f, n in SYSTEMES[i].most_common(2)))
# Part des matchs avec une défense à 4 (2 défenseurs centraux) — sert à écarter les blocs à 3 / 5
eq["pct_def4"] = eq["equipe_id"].map(lambda i: 100 * sum(n for f, n in SYSTEMES[i].items() if f.split("-")[0] == "4")
                                     / max(sum(SYSTEMES[i].values()), 1))
ecrire(eq.round(4), "equipes.csv")
em = pd.DataFrame(LIGNES_EQ_MATCH)
em.insert(1, "equipe", em["equipe_id"].map(NOMS))
em["date"] = pd.to_datetime(em["date"].str.replace(" UTC", ""), format="%a, %b %d, %Y, %H:%M").dt.strftime("%d/%m/%Y")
ecrire(em.round(3), "equipes_matchs.csv")

# =====================================================================================
# 6. MATCHS ET TIRS DE NOTRE ÉQUIPE
# =====================================================================================
ecrire(pd.DataFrame(LIGNES_TIRS), "tirs.csv")

# =====================================================================================
# 7. JOUEURS (5 championnats)
# =====================================================================================
J = defaultdict(lambda: defaultdict(float))     # clé = (joueur, club) : un joueur transféré a 2 lignes
POSTES = defaultdict(Counter)
INFO = {}
GROUPES = defaultdict(list)    # club → [(date, ids du groupe : titulaires + remplaçants)]
for m in D["matches"]:
    titulaires = set()
    for c in ("h", "a"):
        lu = m["lineup"][c]
        if lu:
            titulaires |= {p[0] for p in lu["st"]}
            GROUPES[m[c][0]].append((m["date"], {p[0] for p in lu["st"]} | {p[0] for p in lu["sub"]}))
    for pid, nom, eq_id, code, usuel, gk, st in m["players"]:
        cle = (pid, str(eq_id))
        mins = st.get(str(PK.index("Minutes played")), 0) or 0
        INFO[cle] = (nom, usuel)
        POSTES[cle][famille_poste(code, usuel) if code else famille_poste(None, usuel)] += mins
        j = J[cle]
        j["matchs"] += 1
        j["titularisations"] += pid in titulaires
        for i, v in st.items():
            k = PK[int(i)]
            if isinstance(v, list):
                j[k] += v[0] or 0
                j[k + " (tentés)"] += v[1] or 0
            elif isinstance(v, (int, float)):
                if k == "FotMob rating":
                    j["note_somme"] += v * mins
                else:
                    j[k] += v


def dans_le_groupe_recent(pid, eq_id):
    """Vrai si le joueur figurait (titulaire ou remplaçant) sur une des dernières feuilles de match du club."""
    derniers = sorted(GROUPES[eq_id], key=lambda t: pd.to_datetime(t[0].replace(" UTC", ""),
                                                                  format="%a, %b %d, %Y, %H:%M"))[-NB_DERNIERS_MATCHS_GROUPE:]
    return any(pid in ids for _, ids in derniers)


def poste_principal(cle):
    """Poste où le joueur a passé le plus de minutes (on ignore les postes « (?) » si un poste précis existe)."""
    precis = [(p, n) for p, n in POSTES[cle].most_common() if "(?)" not in p and p != "Inconnu"]
    return precis[0][0] if precis else POSTES[cle].most_common(1)[0][0]


jo = pd.DataFrame(J).T.fillna(0)
jo.index.names = ["joueur_id", "equipe_id"]
jo = jo.reset_index()
cles = list(zip(jo["joueur_id"], jo["equipe_id"]))
jo.insert(2, "joueur", [INFO[c][0] for c in cles])
jo.insert(3, "equipe", jo["equipe_id"].map(NOMS))
jo.insert(4, "ligue", jo["equipe_id"].map(LIGUES))
jo.insert(5, "poste", [poste_principal(c) for c in cles])
jo.insert(6, "minutes", jo["Minutes played"])
jo.insert(7, "au_club", [dans_le_groupe_recent(p, e) and INFO[(p, e)][0] not in JOUEURS_EXCLUS for p, e in cles])
jo["note"] = jo["note_somme"] / jo["minutes"].replace(0, np.nan)
# possession moyenne de son club : sert à « ajuster » les volumes défensifs (une équipe qui a le ballon
# défend moins souvent, ses joueurs font donc mécaniquement moins de tacles / interceptions)
poss = jo["equipe_id"].map(eq.set_index("equipe_id")["possession_m"])
ajust = 50 / (100 - poss).clip(lower=20)


def p90(col):
    return jo[col] / jo["minutes"].replace(0, np.nan) * 90 if col in jo.columns else np.nan


def pct(col):
    return jo[col] / jo[col + " (tentés)"].replace(0, np.nan) * 100 if col in jo.columns else np.nan


METRIQUES = {
    # nom affiché : série
    "Buts /90": p90("Goals"), "xG /90": p90("Expected goals (xG)"), "xG hors penalty /90": p90("xG Non-penalty"),
    "Tirs /90": p90("Total shots"), "Finition (xGOT − xG) /90": (p90("Expected goals on target (xGOT)") - p90("Expected goals (xG)")),
    "Passes déc. /90": p90("Assists"), "xA /90": p90("Expected assists (xA)"), "Occasions créées /90": p90("Chances created"),
    "Grosses occasions créées /90": p90("Big chances created"), "Touches dans la surface /90": p90("Touches in opposition box"),
    "Dribbles réussis /90": p90("Successful dribbles"), "% dribbles réussis": pct("Successful dribbles"),
    "Pertes de balle (dépossédé) /90": p90("Dispossessed"), "Ballons touchés /90": p90("Touches"),
    "Passes dernier tiers /90": p90("Passes into final third"), "Passes qui cassent une ligne /90": p90("Line breaking passes"),
    "Longs ballons réussis /90": p90("Accurate long balls"), "% longs ballons": pct("Accurate long balls"),
    "Centres réussis /90": p90("Accurate crosses"), "% centres réussis": pct("Accurate crosses"),
    "Tacles /90 (ajusté poss.)": p90("Tackles") * ajust, "Interceptions /90 (ajusté poss.)": p90("Interceptions") * ajust,
    "Récupérations /90 (ajusté poss.)": p90("Recoveries") * ajust, "Dégagements /90": p90("Clearances"),
    "Tirs contrés /90": p90("Blocks"), "Dribblé /90": p90("Dribbled past"), "% duels au sol gagnés": pct("Ground duels won"),
    "% duels aériens gagnés": pct("Aerial duels won"), "Duels aériens gagnés /90": p90("Aerial duels won"),
    "Duels perdus /90": p90("Duels lost"), "Fautes commises /90": p90("Fouls committed"),
    "Erreurs menant à un but": jo.get("Error led to goal", 0), "Penaltys concédés": jo.get("Conceded penalty", 0),
    "Arrêts /90": p90("Saves"), "Buts évités (xGOT − buts) /90": p90("Goals prevented"),
    "% arrêts": jo["Saves"] / (jo["Saves"] + jo["Goals conceded"]).replace(0, np.nan) * 100 if "Saves" in jo else np.nan,
    "Sorties aériennes /90": p90("High claim"), "Sorties hors surface /90": p90("Acted as sweeper"),
    "Note FotMob": jo["note"],
}
METRIQUES["xG + xA /90"] = METRIQUES["xG /90"] + METRIQUES["xA /90"]
for k, v in METRIQUES.items():
    jo[k] = v
garder = ["joueur_id", "equipe_id", "joueur", "equipe", "ligue", "poste", "minutes", "au_club", "matchs",
          "titularisations", "Goals", "Assists"] + list(METRIQUES)
ecrire(jo[garder].rename(columns={"Goals": "buts", "Assists": "passes_dec"}).round(4), "joueurs.csv")

# =====================================================================================
# 8. ON / OFF : xG pour et contre selon que nos joueurs sont sur le terrain
#    (et xG concédés par côté : notre gauche / axe / notre droite)
# =====================================================================================
# Coefficient de difficulté : force offensive de l'adversaire = ses xG créés par match / moyenne de sa ligue
# (1,3 = il crée 30 % de plus qu'une équipe moyenne). On divise les xG concédés par ce coefficient : concéder
# 2 xG contre une attaque à 1,6 « vaut » 1,25 xG contre une attaque moyenne. Idem pour nos xG créés avec la
# force défensive de l'adversaire.
FORCE = eq.set_index("equipe_id")
MOY_LIGUE = eq.groupby("ligue")[["xg_m", "xg_contre_m"]].mean()
COEF_ATT = FORCE["xg_m"] / FORCE["ligue"].map(MOY_LIGUE["xg_m"])
COEF_DEF = FORCE["xg_contre_m"] / FORCE["ligue"].map(MOY_LIGUE["xg_contre_m"])
lignes = []
CHANGEMENTS = {}
for mid, ev in D.get("omEvents", {}).items():
    m = next(x for x in D["matches"] if x["id"] == mid)
    n = "h" if m["h"][0] == EQUIPE_ID else "a"
    nous_id = m[n][0]
    adv_id = m["a" if n == "h" else "h"][0]
    c_att, c_def = float(COEF_ATT.get(adv_id, 1.0)), float(COEF_DEF.get(adv_id, 1.0))
    # minute de fin de match approximative (90 + temps additionnel du dernier tir)
    fin = 90 + max([(s[3] or 0) for s in m["shots"] if s[4] == "SecondHalf" and s[2] >= 90] + [3])
    intervalles = {}
    for pid, nom, titulaire, subs, rouges in ev[n]:
        debut = 0 if titulaire else None
        stop = fin
        for e in subs:
            if e["type"] == "subIn":
                debut = e["time"]
            elif e["type"] == "subOut":
                stop = e["time"]
        for r in rouges:
            stop = min(stop, r.get("time", stop))
        if debut is not None:
            intervalles[pid] = (nom, debut, stop)
    entrees = sorted(e["time"] for _, _, _, subs, _ in ev[n] for e in subs if e["type"] == "subIn")
    CHANGEMENTS[mid] = dict(min_1er_changement=entrees[0] if entrees else np.nan, nb_changements=len(entrees),
                            nb_changements_avant_70=sum(t < 70 for t in entrees),
                            minutes_changements=" ".join(f"{t}'" for t in entrees))
    for pid, (nom, debut, stop) in intervalles.items():
        on = {"xg_pour": 0.0, "xg_contre": 0.0, **{f"xga_{c}": 0.0 for c in COTES}}
        off = {"xg_pour": 0.0, "xg_contre": 0.0, **{f"xga_{c}": 0.0 for c in COTES}}
        for s in m["shots"]:
            if s[12] or s[5] is None:
                continue
            t = s[2] + ((s[3] or 0) if s[4] == "SecondHalf" and s[2] >= 90 else 0)
            camp = "xg_pour" if str(s[0]) == nous_id else "xg_contre"
            cible = on if debut <= t < stop else off
            cible[camp] += s[5]
            if camp == "xg_contre" and s[7] != "Penalty":
                cible[f"xga_{INVERSE[cote_attaquant(s[10])]}"] += s[5]
        lignes.append(dict(match_id=mid, joueur_id=pid, joueur=nom, minutes_on=stop - debut,
                           minutes_off=fin - (stop - debut), **{f"{k}_on": v for k, v in on.items()},
                           **{f"{k}_off": v for k, v in off.items()},
                           xg_contre_on_adj=on["xg_contre"] / c_att, xg_contre_off_adj=off["xg_contre"] / c_att,
                           xg_pour_on_adj=on["xg_pour"] / c_def, xg_pour_off_adj=off["xg_pour"] / c_def,
                           **{f"xga_{c}_on_adj": on[f"xga_{c}"] / c_att for c in COTES},
                           **{f"xga_{c}_off_adj": off[f"xga_{c}"] / c_att for c in COTES},
                           difficulte_x_min=c_att * (stop - debut), adversaires=NOMS[adv_id] + (
                               f" ({stop - debut}')" if (stop - debut) < fin - 5 else "")))
oo = pd.DataFrame(lignes)
if len(oo):
    adv = oo.groupby("joueur_id")["adversaires"].agg(", ".join)
    oo = oo.groupby(["joueur_id", "joueur"], as_index=False).sum(numeric_only=True).drop(columns="match_id", errors="ignore")
    oo["adversaires"] = oo["joueur_id"].map(adv)
    oo["difficulte"] = oo["difficulte_x_min"] / oo["minutes_on"].replace(0, np.nan)   # coefficient moyen des adversaires affrontés
    for suffixe in ("", "_adj"):
        for c in ("pour", "contre"):
            oo[f"xg_{c}_on_90{suffixe}"] = oo[f"xg_{c}_on{suffixe}"] / oo["minutes_on"].replace(0, np.nan) * 90
            oo[f"xg_{c}_off_90{suffixe}"] = oo[f"xg_{c}_off{suffixe}"] / oo["minutes_off"].replace(0, np.nan) * 90
        for c in COTES:
            oo[f"xga_{c}_on_90{suffixe}"] = oo[f"xga_{c}_on{suffixe}"] / oo["minutes_on"].replace(0, np.nan) * 90
            oo[f"xga_{c}_off_90{suffixe}"] = oo[f"xga_{c}_off{suffixe}"] / oo["minutes_off"].replace(0, np.nan) * 90
ecrire(oo.round(4), "on_off.csv")
matchs = pd.DataFrame(LIGNES_MATCHS).sort_values("date")
matchs = matchs.join(pd.DataFrame.from_dict(CHANGEMENTS, orient="index"), on="match_id")
ecrire(matchs, "matchs.csv")

# =====================================================================================
# 9. TRANSITIONS ET PRESSING (événements WhoScored de la Ligue 1, si export_whoscored.py a été lancé)
# =====================================================================================
EQUIPE_WHOSCORED = "Marseille"      # nom de notre équipe chez WhoScored
FICHIER_WS = DOSSIER / "whoscored_ligue1.csv"
nb_matchs_ws = 0
if FICHIER_WS.exists():
    import transitions
    print("  Événements WhoScored trouvés : calcul des transitions et du pressing (1 à 2 minutes)…")
    nb_matchs_ws, jl = transitions.preparer_tout(transitions.lire_evenements(FICHIER_WS), EQUIPE_WHOSCORED, ecrire)
    # On rattache chaque joueur WhoScored à sa fiche FotMob (poste, identifiant) par nom et club
    ref = jo[jo["ligue"] == LIGUES[EQUIPE_ID]][["joueur_id", "joueur", "equipe", "poste", "minutes", "au_club"]].copy()
    ref["cle_nom"] = ref["joueur"].map(transitions.sans_accents)
    ref["cle_eq"] = ref["equipe"].map(transitions.sans_accents)
    jl["cle_nom"] = jl["joueur"].map(transitions.sans_accents)
    jl["cle_eq"] = jl["equipe"].map(transitions.sans_accents)
    jl = jl.merge(ref.drop(columns=["joueur", "equipe"]).rename(columns={"minutes": "minutes_fotmob"}),
                  on=["cle_nom", "cle_eq"], how="left")
    # 2e essai : même nom de famille dans le même club (« P. Højbjerg » / « Pierre-Emile Højbjerg »)
    manque = jl["poste"].isna()
    ref["cle_fam"] = ref["cle_nom"].str.split().str[-1] + "|" + ref["cle_eq"]
    uniques = ref.drop_duplicates("cle_fam", keep=False).set_index("cle_fam")
    fam = (jl.loc[manque, "cle_nom"].str.split().str[-1] + "|" + jl.loc[manque, "cle_eq"])
    for col in ("joueur_id", "poste", "au_club"):
        jl.loc[manque, col] = fam.map(uniques[col]).values
    print(f"    joueurs WhoScored rattachés à FotMob : {jl['poste'].notna().mean() * 100:.0f} %")
    ecrire(jl.drop(columns=["cle_nom", "cle_eq"]).round(4), "ws_joueurs_l1.csv")
    # Centres : ce que font les défenses dans leurs couloirs, match par match (système de jeu : FotMob)
    form_l1 = defaultdict(list)
    for m in D["matches"]:
        if m["lg"] == LIGUES[EQUIPE_ID] and m.get("lineup"):
            d_ = pd.to_datetime(m["date"].replace(" UTC", ""), format="%a, %b %d, %Y, %H:%M")
            for c, o in (("h", "a"), ("a", "h")):
                if m["lineup"].get(c):
                    form_l1[(transitions.sans_accents(m[c][1]), transitions.sans_accents(m[o][1]))].append(
                        (d_, m["lineup"][c].get("f")))

    def systeme_match(date, equipe, adversaire):
        cands = form_l1.get((transitions.sans_accents(equipe), transitions.sans_accents(adversaire)), [])
        if not cands:
            return None
        d_ = pd.Timestamp(date)
        return min(cands, key=lambda x: abs((x[0] - d_).total_seconds()))[1]

    postes_ws = {(r["equipe"], r["joueur"]): r["poste"] for _, r in jl.iterrows() if pd.notna(r["poste"])}
    ac, ac_seq = transitions.anti_centres(transitions.lire_evenements(FICHIER_WS), postes_ws, systeme_match)
    print(f"    anti-centres : {len(ac)} lignes match × équipe, systèmes trouvés {ac['systeme_defense'].notna().mean() * 100:.0f} %")
    ecrire(ac.round(3), "ws_anti_centres.csv")
    ecrire(ac_seq, "ws_anti_centres_sequences.csv")
else:
    print("  (pas de donnees/whoscored_ligue1.csv : lance export_whoscored.py pour les transitions et le pressing)")

# =====================================================================================
# 10. MÉTA
# =====================================================================================
meta = dict(equipe_id=EQUIPE_ID, equipe=EQUIPE_NOM, ligue=LIGUES.get(EQUIPE_ID), saison=D["meta"]["saison"],
            source=D["meta"]["source"], extrait_le=D["meta"]["extrait_le"][:10],
            nb_matchs=int(eq.loc[eq["equipe_id"] == EQUIPE_ID, "mj"].iloc[0]), nb_equipes=len(eq),
            nb_matchs_total=len(D["matches"]), nb_matchs_whoscored=nb_matchs_ws, equipe_whoscored=EQUIPE_WHOSCORED,
            maj_whoscored=(pd.Timestamp(FICHIER_WS.stat().st_mtime, unit="s").strftime("%Y-%m-%d")
                           if FICHIER_WS.exists() else None))
(DOSSIER / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print("Terminé :", meta)
