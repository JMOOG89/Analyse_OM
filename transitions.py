# -*- coding: utf-8 -*-
"""
=====================================================================================
 TRANSITIONS, PRESSING ET ORIGINE DU DANGER — à partir des événements WhoScored
=====================================================================================

Utilisé par preparation.py quand le fichier donnees/whoscored_ligue1.csv existe
(produit par export_whoscored.py). Calcule, pour chaque club de Ligue 1 :

  PERTES DE BALLE (dans le jeu)
    Une perte = une possession à nous suivie d'une VRAIE possession adverse (au moins une passe
    réussie ou deux ballons touchés), hors remise en jeu (touche, 6 m, coup franc, corner)
    et hors possession terminée par un tir.
      - contre-pressing réussi : on récupère le ballon dans les 5 secondes
      - transition concédée     : l'adversaire tire dans les 15 secondes, avant qu'on ait
                                  récupéré le ballon
  RÉCUPÉRATIONS (même définition, dans l'autre sens)
      - récupération haute      : à 40 m ou moins du but adverse
      - récupération → tir      : on tire dans les 15 secondes
  PPDA
      passes adverses dans leurs 60 % ÷ nos tacles, interceptions, duels et fautes dans les
      60 % adverses — au total et par tranche de 15 minutes.
  ORIGINE DU DANGER CONCÉDÉ
      pour chaque tir adverse : couloir et type de la dernière passe (centre, profondeur,
      remise en retrait…), partie du corps, xG (modèle maison du script Auxerre).

Coordonnées WhoScored : x de 0 (but défendu) à 100 (but attaqué), du point de vue de l'équipe
qui fait l'action ; y de 0 (droite de l'attaquant) à 100 (gauche de l'attaquant).
"""

import unicodedata

import numpy as np
import pandas as pd

FENETRE_CONTRE_PRESSING_S = 5
FENETRE_TRANSITION_S = 15
X_RECUP_HAUTE = (1 - 40 / 105) * 100          # 40 derniers mètres
TRANCHES = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]
REMISES = ("ThrowIn", "GoalKick", "FreekickTaken", "CornerTaken", "IndirectFreekickTaken", "KeeperThrow")
TYPES_DEF = ["Tackle", "Interception", "Challenge"]
COULOIRS_3 = [(63.2, 100.1, "Gauche"), (36.8, 63.2, "Axe"), (-0.1, 36.8, "Droite")]   # vus par l'attaquant
INVERSE = {"Gauche": "Droite", "Droite": "Gauche", "Axe": "Axe"}


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).lower().strip()


def qual(df, nom):
    return df["quals"].fillna("").str.contains(rf"(?:^|\|){nom}(?:\||$)", regex=True)


def couloir3(y):
    for bas, haut, nom in COULOIRS_3:
        if bas <= y < haut:
            return nom
    return np.nan


def tranche(periode, minute):
    if periode == "FirstHalf":
        return TRANCHES[0] if minute < 15 else TRANCHES[1] if minute < 30 else TRANCHES[2]
    return TRANCHES[3] if minute < 60 else TRANCHES[4] if minute < 75 else TRANCHES[5]


def xg_simple(t):
    """xG maison du script Auxerre (même modèle) : distance, angle, tête, CPA, contre."""
    dx = (100 - t["x"]) * 1.05
    dy = (50 - t["y"]) * 0.68
    dist = np.sqrt(dx ** 2 + dy ** 2).clip(lower=1)
    angle = np.arctan2(7.32 * dx, dx ** 2 + dy ** 2 - (7.32 / 2) ** 2)
    angle = np.where(angle < 0, angle + np.pi, angle)
    z = (2.2553 - 1.7977 * np.log(dist) + 0.7527 * angle - 1.1163 * qual(t, "Head")
         - 0.7495 * qual(t, "FromCorner") - 0.1741 * (qual(t, "SetPiece") | qual(t, "ThrowinSetPiece"))
         + 0.7033 * qual(t, "DirectFreekick") + 0.5299 * qual(t, "FastBreak"))
    xg = 1 / (1 + np.exp(-z))
    return np.where(qual(t, "Penalty"), 0.76, xg)


# =====================================================================================
# 1. VUE D'UNE ÉQUIPE
# =====================================================================================
def vue(ev, equipe):
    """Événements des matchs d'une équipe, avec 'nous' (action de l'équipe) et l'adversaire."""
    v = ev[(ev["home_team"] == equipe) | (ev["away_team"] == equipe)].copy()
    v["nous"] = v["team"] == equipe
    v["adversaire"] = np.where(v["home_team"] == equipe, v["away_team"], v["home_team"])
    return v[v["period"].isin(["FirstHalf", "SecondHalf"])].sort_values(["game_id", "temps_s", "ordre"])


# =====================================================================================
# 2. POSSESSIONS : pertes et récupérations
# =====================================================================================
def possessions(v):
    """Une ligne par séquence (suite de ballons touchés par la même équipe)."""
    t = v[v["is_touch"] & v["team"].notna()].copy()
    t["reussie"] = (t["type"] == "Pass") & (t["outcome_type"] == "Successful")
    t["remise"] = False
    for q in REMISES:
        t["remise"] |= qual(t, q)
    g = t.groupby("sequence", sort=False)
    p = pd.DataFrame({
        "game_id": g["game_id"].first(), "adversaire": g["adversaire"].first(), "nous": g["nous"].first(),
        "period": g["period"].first(), "minute": g["minute"].first(),
        "debut_s": g["temps_s"].first(), "fin_s": g["temps_s"].last(),
        "debut_x": g["x"].first(), "debut_y": g["y"].first(), "fin_x": g["x"].last(), "fin_y": g["y"].last(),
        "dernier_joueur": g["player"].last(), "premier_joueur": g["player"].first(),
        "nb_touches": g.size(), "nb_passes_ok": g["reussie"].sum(), "commence_remise": g["remise"].first(),
        "finit_tir": g["is_shot"].last(),
    }).reset_index()
    p["etablie"] = (p["nb_touches"] >= 2) | (p["nb_passes_ok"] >= 1)
    return p.sort_values(["game_id", "debut_s"]).reset_index(drop=True)


def changements_possession(v, pour_nous):
    """
    Pertes (pour_nous=True : NOS pertes) ou récupérations (pour_nous=False : les pertes ADVERSES).
    Pour chacune : récupération par l'équipe qui a perdu en ≤ 5 s, tir de l'équipe qui a gagné
    le ballon en ≤ 15 s (avant que l'autre ne reprenne vraiment le ballon) et son xG.
    """
    p = possessions(v)
    tirs = v[v["is_shot"] & ~qual(v, "OwnGoal")].copy()
    tirs["xg"] = xg_simple(tirs)
    lignes = []
    for gid, pg in p.groupby("game_id", sort=False):
        pg = pg.reset_index(drop=True)
        tg = tirs[tirs["game_id"] == gid]
        for i in range(len(pg) - 1):
            a, b = pg.loc[i], pg.loc[i + 1]
            if a["nous"] != pour_nous or b["nous"] == a["nous"] or a["period"] != b["period"]:
                continue
            if a["finit_tir"] or b["commence_remise"] or not b["etablie"]:
                continue
            t0 = b["debut_s"]
            # prochaine possession ÉTABLIE de l'équipe qui a perdu le ballon
            suite = pg.loc[i + 2:]
            reprise = suite[(suite["nous"] == a["nous"]) & suite["etablie"] & (suite["period"] == a["period"])]
            t_reprise = reprise["debut_s"].iloc[0] if len(reprise) else np.inf
            retour = suite[(suite["nous"] == a["nous"]) & (suite["period"] == a["period"])]
            t_retour = retour["debut_s"].iloc[0] if len(retour) else np.inf
            tir = tg[(tg["nous"] != a["nous"]) & (tg["temps_s"] > t0 - 0.5)
                     & (tg["temps_s"] <= t0 + FENETRE_TRANSITION_S) & (tg["temps_s"] < t_reprise)
                     & (tg["period"] == a["period"])]
            lignes.append({
                "game_id": gid, "adversaire": a["adversaire"], "period": a["period"], "minute": a["minute"],
                "tranche": tranche(a["period"], b["minute"]),
                "joueur_perte": a["dernier_joueur"], "joueur_recup": b["premier_joueur"],
                # lieu de la perte, vu par l'équipe qui PERD (x = 100 : but adverse)
                "x_perte": a["fin_x"], "y_perte": a["fin_y"],
                # lieu de la récupération, vu par l'équipe qui RÉCUPÈRE
                "x_recup": b["debut_x"], "y_recup": b["debut_y"],
                "repris_5s": t_retour - t0 <= FENETRE_CONTRE_PRESSING_S,
                "tir_15s": len(tir) > 0, "xg_15s": tir["xg"].sum(),
                "but_15s": bool(tir["is_goal"].any()), "tireur": tir["player"].iloc[0] if len(tir) else np.nan,
            })
    return pd.DataFrame(lignes)


# =====================================================================================
# 3. PPDA (total et par tranche)
# =====================================================================================
def ppda_tranches(v):
    v = v.copy()
    v["tranche"] = [tranche(p, m) for p, m in zip(v["period"], v["minute"])]
    passes_adv = v[~v["nous"] & (v["type"] == "Pass") & (v["x"] <= 60)]
    def_ = v[v["nous"] & (v["x"] >= 40) & (v["type"].isin(TYPES_DEF)
                                         | ((v["type"] == "Foul") & (v["outcome_type"] == "Unsuccessful")))]
    tot = len(passes_adv) / max(len(def_), 1)
    par = (passes_adv.groupby("tranche").size() / def_.groupby("tranche").size()).reindex(TRANCHES)
    return tot, par


# =====================================================================================
# 4. ORIGINE DU DANGER CONCÉDÉ (tirs adverses)
# =====================================================================================
DEDANS = lambda x, y: (x >= 83) & (y >= 21.1) & (y <= 78.9)        # dans la surface attaquée
CPA = ("CornerTaken", "FreekickTaken", "ThrowIn", "IndirectFreekickTaken", "GoalKick")
TYPES_PASSE = ["Centre", "Long ballon aérien dans la surface", "Remise en retrait", "Passe en profondeur",
               "Passe courte / combinaison", "2e ballon : rebond après arrêt ou tir contré",
               "2e ballon : après un dégagement", "2e ballon : après un duel ou un contrôle raté",
               "Ballon perdu par nous", "Récupération ou dribble adverse", "Coup de pied arrêté", "Penalty"]
SECOND_BALLON = [t for t in TYPES_PASSE if t.startswith("2e ballon")]


def est_cpa(quals):
    return any(q in str(quals) for q in CPA)


def est_aerien_long(p):
    """Passe (hors centre, hors CPA) qui finit dans la surface : ballon long, levé, ou de plus de 25 m."""
    if "Cross" in str(p["quals"]) or est_cpa(p["quals"]) or pd.isna(p["end_x"]):
        return False
    if not DEDANS(p["end_x"], p["end_y"]) or DEDANS(p["x"], p["y"]):
        return False
    longueur = np.hypot((p["end_x"] - p["x"]) * 1.05, (p["end_y"] - p["y"]) * 0.68)
    return "Longball" in str(p["quals"]) or "Chipped" in str(p["quals"]) or longueur >= 25


def type_derniere_passe(dp):
    q = str(dp["quals"])
    if est_cpa(q):
        return "Coup de pied arrêté"
    if "Cross" in q:
        return "Centre"
    if est_aerien_long(dp):
        return "Long ballon aérien dans la surface"
    if "Throughball" in q:
        return "Passe en profondeur"
    if dp["x"] >= 83 and dp["end_x"] < dp["x"] and (dp["y"] < 36.8 or dp["y"] > 63.2):
        return "Remise en retrait"
    return "Passe courte / combinaison"


def type_sans_passe(derniere_nous, derniere_eux):
    """Le tireur n'a reçu aucune passe : que s'est-il passé juste avant ?"""
    if derniere_nous is not None:
        t = derniere_nous["type"]
        if t in ("Save", "Smother"):
            return "2e ballon : rebond après arrêt ou tir contré"
        if t in ("Clearance", "Punch"):
            return "2e ballon : après un dégagement"
        if t in ("Aerial", "Challenge", "Tackle", "Interception", "BlockedPass", "BallTouch", "Claim"):
            return "2e ballon : après un duel ou un contrôle raté"
        return "Ballon perdu par nous"      # passe ratée, dépossédé, erreur…
    return "Récupération ou dribble adverse"


def tirs_concedes(v):
    """
    Tirs adverses classés selon ce qui les amène, vus par NOUS :
      - dernière passe de la même possession adverse (centre, long ballon aérien, remise…)
      - sinon (aucune passe) : 2e ballon après notre intervention (arrêt, dégagement, duel), ballon perdu
        par nous, ou récupération / dribble adverse
      - ballon_aerien_10s : un centre ou un long ballon aérien adverse dans notre surface dans les 10 s
        avant le tir, même si on l'a repoussé (c'est ce qui mesure « les ballons aériens dans la surface »)
    """
    v = v.reset_index(drop=True)
    t = v[~v["nous"] & v["is_shot"] & ~qual(v, "OwnGoal")].copy()
    t["xg"] = xg_simple(t)
    passes_ok = v[~v["nous"] & (v["type"] == "Pass") & (v["outcome_type"] == "Successful")]
    passes_adv = v[~v["nous"] & (v["type"] == "Pass")]
    lignes = []
    for _, s in t.iterrows():
        meme_match = (v["game_id"] == s["game_id"]) & (v["period"] == s["period"]) & (v["ordre"] < s["ordre"])
        pp = passes_ok[(passes_ok["game_id"] == s["game_id"]) & (passes_ok["sequence"] == s["sequence"])
                       & (passes_ok["ordre"] < s["ordre"])]
        dp = pp.iloc[-1] if len(pp) else None
        fen = v[meme_match & (v["temps_s"] >= s["temps_s"] - 10)]
        nous_avant = fen[fen["nous"] & fen["team"].notna()]
        eux_avant = fen[~fen["nous"] & fen["team"].notna()]
        if "Penalty" in str(s["quals"]):
            tp = "Penalty"
        elif dp is not None:
            tp = type_derniere_passe(dp)
        else:
            tp = type_sans_passe(nous_avant.iloc[-1] if len(nous_avant) else None,
                                 eux_avant.iloc[-1] if len(eux_avant) else None)
        # ballon aérien adverse dans notre surface dans les 10 s (centre ou long ballon), hors CPA
        pa = passes_adv[(passes_adv["game_id"] == s["game_id"]) & (passes_adv["period"] == s["period"])
                        & (passes_adv["ordre"] < s["ordre"]) & (passes_adv["temps_s"] >= s["temps_s"] - 10)]
        aeriens = pa[[("Cross" in str(q) and not est_cpa(q)) or est_aerien_long(r) for q, (_, r) in
                      zip(pa["quals"], pa.iterrows())]] if len(pa) else pa
        a = aeriens.iloc[-1] if len(aeriens) else None
        origine = couloir3(dp["y"]) if dp is not None else (couloir3(a["y"]) if a is not None else couloir3(s["y"]))
        lignes.append({
            "game_id": s["game_id"], "adversaire": s["adversaire"], "minute": s["minute"],
            "tranche": tranche(s["period"], s["minute"]), "tireur": s["player"], "x": s["x"], "y": s["y"],
            "xg": s["xg"], "but": bool(s["is_goal"]), "partie_corps": "Tête" if "Head" in str(s["quals"]) else "Pied",
            "type_passe": tp, "passeur": dp["player"] if dp is not None else np.nan,
            "passe_x": dp["x"] if dp is not None else np.nan, "passe_y": dp["y"] if dp is not None else np.nan,
            "cote_origine_nous": INVERSE.get(origine, np.nan),
            "ballon_aerien_10s": a is not None,
            "aerien_type": (("Centre" if "Cross" in str(a["quals"]) else "Long ballon") if a is not None else np.nan),
            "aerien_cote_nous": INVERSE.get(couloir3(a["y"]), np.nan) if a is not None else np.nan,
            "aerien_distance_but_m": (np.hypot((100 - a["x"]) * 1.05, (50 - a["y"]) * 0.68) if a is not None else np.nan),
            "intervention_nous": (f"{nous_avant.iloc[-1]['player']} ({nous_avant.iloc[-1]['type']})"
                                  if len(nous_avant) and dp is None else np.nan),
        })
    return pd.DataFrame(lignes)


def entrees_surface_concedees(v):
    """Passes adverses réussies qui entrent dans notre surface, par couloir de départ (vu par nous)."""
    p = v[~v["nous"] & (v["type"] == "Pass") & (v["outcome_type"] == "Successful")]
    p = p[[not est_cpa(q) for q in p["quals"]]]
    p = p[~DEDANS(p["x"], p["y"]) & DEDANS(p["end_x"], p["end_y"])].copy()
    p["cote_nous"] = [INVERSE.get(couloir3(y), np.nan) for y in p["y"]]
    p["centre"] = qual(p, "Cross")
    return p


def suivi_de_tir(evenements, tirs, fenetre=10):
    """Pour chaque événement : tir adverse dans les N secondes (même mi-temps) ? et xG de ces tirs."""
    tir, xg = [], []
    for _, r in evenements.iterrows():
        t = tirs[(tirs["game_id"] == r["game_id"]) & (tirs["period"] == r["period"]) & (tirs["temps_s"] >= r["temps_s"])
                 & (tirs["temps_s"] <= r["temps_s"] + fenetre)]
        tir.append(len(t) > 0)
        xg.append(t["xg"].sum())
    return np.array(tir, dtype=bool), np.array(xg, dtype=float)


def defense_centres_et_seconds_ballons(v):
    """
    Rapporte le danger au nombre de situations :
      - centres adverses dans le jeu : combien, combien réussis, combien suivis d'un tir en 10 s ;
      - nos interventions dans notre surface (dégagement, arrêt, duel aérien gagné, contre, interception) :
        combien sont suivies d'un tir adverse en 10 s (= 2e ballon non sécurisé).
    """
    nb = max(v["game_id"].nunique(), 1)
    tirs = v[~v["nous"] & v["is_shot"] & ~qual(v, "OwnGoal")].copy()
    tirs["xg"] = xg_simple(tirs)
    cr = v[~v["nous"] & (v["type"] == "Pass") & qual(v, "Cross")]
    cr = cr[[not est_cpa(q) for q in cr["quals"]]]
    s_cr, x_cr = suivi_de_tir(cr, tirs)
    it = v[v["nous"] & v["type"].isin(["Clearance", "Save", "Punch", "Aerial", "BlockedPass", "Interception"])
           & (v["x"] <= 17) & v["y"].between(21.1, 78.9)]
    it = it[(it["type"] != "Aerial") | (it["outcome_type"] == "Successful")]
    s_it, x_it = suivi_de_tir(it, tirs)
    return {
        "centres_adv_match": len(cr) / nb,
        "pct_centres_reussis_adv": (cr["outcome_type"] == "Successful").mean() * 100 if len(cr) else np.nan,
        "pct_centres_suivis_tir": s_cr.mean() * 100 if len(cr) else np.nan,
        "xg_par_centre_adv": x_cr.mean() if len(cr) else np.nan,
        "xg_apres_centres_match": x_cr.sum() / nb,
        "interventions_surface_match": len(it) / nb,
        "pct_interventions_suivies_tir": s_it.mean() * 100 if len(it) else np.nan,
        "xg_apres_interventions_match": x_it.sum() / nb,
    }


# =====================================================================================
# 5. TOUT POUR UNE ÉQUIPE
# =====================================================================================
def analyser(v):
    nb = max(v["game_id"].nunique(), 1)
    pertes = changements_possession(v, True)
    recups = changements_possession(v, False)
    tot, par = ppda_tranches(v)
    tc = tirs_concedes(v)
    ent = entrees_surface_concedees(v)
    haut_perte = pertes["x_perte"] >= 50 if len(pertes) else pd.Series(dtype=bool)
    hautes = recups[recups["x_recup"] >= X_RECUP_HAUTE] if len(recups) else recups
    hp = tc[tc["type_passe"] != "Penalty"]
    m = {
        "matchs": nb, "ppda": tot,
        "pertes_match": len(pertes) / nb,
        "pertes_punies_match": pertes["tir_15s"].sum() / nb if len(pertes) else np.nan,
        "contre_pressing_pct": pertes["repris_5s"].mean() * 100 if len(pertes) else np.nan,
        "contre_pressing_camp_adverse_pct": pertes.loc[haut_perte, "repris_5s"].mean() * 100 if len(pertes) else np.nan,
        "transitions_concedees_match": pertes["tir_15s"].sum() / nb,
        "xg_transitions_concedees_match": pertes["xg_15s"].sum() / nb,
        "pct_pertes_tir_adverse": pertes["tir_15s"].mean() * 100 if len(pertes) else np.nan,
        "recup_match": len(recups) / nb,
        "recup_hautes_match": len(hautes) / nb,
        "recup_tir_match": recups["tir_15s"].sum() / nb,
        "xg_recup_tir_match": recups["xg_15s"].sum() / nb,
        "pct_recup_hautes_tir": hautes["tir_15s"].mean() * 100 if len(hautes) else np.nan,
        "entrees_surface_concedees_match": len(ent) / nb,
        "centres_concedes_surface_match": ent["centre"].sum() / nb,
        "xga_ws_match": tc["xg"].sum() / nb,
        "xga_aerien_10s_match": hp.loc[hp["ballon_aerien_10s"], "xg"].sum() / nb,
        "tirs_aerien_10s_match": hp["ballon_aerien_10s"].sum() / nb,
        "xga_tete_aerien_match": hp.loc[hp["ballon_aerien_10s"] & (hp["partie_corps"] == "Tête"), "xg"].sum() / nb,
        "xga_second_ballon_match": hp.loc[hp["type_passe"].isin(SECOND_BALLON), "xg"].sum() / nb,
        "tirs_second_ballon_match": hp["type_passe"].isin(SECOND_BALLON).sum() / nb,
    }
    m.update(defense_centres_et_seconds_ballons(v))
    for tr_, val in par.items():
        m[f"ppda_{tr_}"] = val
    for c in ("Gauche", "Axe", "Droite"):
        m[f"pct_entrees_{c}"] = (ent["cote_nous"] == c).mean() * 100 if len(ent) else np.nan
        m[f"xga_origine_{c}_match"] = hp.loc[hp["cote_origine_nous"] == c, "xg"].sum() / nb
        m[f"xga_aerien_{c}_match"] = hp.loc[hp["ballon_aerien_10s"] & (hp["aerien_cote_nous"] == c), "xg"].sum() / nb
    for tp in TYPES_PASSE:
        m[f"xga_passe_{tp}_match"] = tc.loc[tc["type_passe"] == tp, "xg"].sum() / nb
        m[f"tirs_passe_{tp}_match"] = (tc["type_passe"] == tp).sum() / nb
    return m, {"pertes": pertes, "recups": recups, "tirs_concedes": tc, "entrees": ent}


# =====================================================================================
# 6. JOUEURS : les actions qui coûtent (pour TOUS les joueurs de Ligue 1)
# =====================================================================================
def temps_de_jeu(v):
    """Minutes jouées par joueur de l'équipe (titulaire = pas d'entrée en jeu ; sortie, carton rouge)."""
    lignes = []
    for gid, g in v[v["nous"]].groupby("game_id"):
        fin = v.loc[v["game_id"] == gid, "minute"].max()
        entrees = g[g["type"] == "SubstitutionOn"].set_index("player")["minute"]
        sorties = g[g["type"] == "SubstitutionOff"].set_index("player")["minute"]
        rouges = g[(g["type"] == "Card") & (qual(g, "Red") | qual(g, "SecondYellow"))].set_index("player")["minute"]
        for p in g["player"].dropna().unique():
            debut = entrees.get(p, 0)
            stop = min(sorties.get(p, fin), rouges.get(p, fin))
            lignes.append({"game_id": gid, "joueur": p, "debut": float(debut), "fin": float(stop)})
    return pd.DataFrame(lignes)


def actions_qui_coutent(v, pertes, equipe):
    """Une ligne par joueur de l'équipe : pertes, duels perdus, dribblé, erreurs, fautes, centres de son côté."""
    v = v.reset_index(drop=True)
    tj = temps_de_jeu(v)
    if tj.empty:
        return pd.DataFrame()
    tj["minutes"] = tj["fin"] - tj["debut"]
    tirs_adv = v[~v["nous"] & v["is_shot"] & ~qual(v, "OwnGoal")].copy()
    tirs_adv["xg"] = xg_simple(tirs_adv)

    def danger(ev_, fenetre=10):
        """Pour chaque action : y a-t-il un tir adverse dans les N secondes (et son xG) ?"""
        tir, xg = [], []
        for _, r in ev_.iterrows():
            t = tirs_adv[(tirs_adv["game_id"] == r["game_id"]) & (tirs_adv["period"] == r["period"])
                         & (tirs_adv["temps_s"] >= r["temps_s"]) & (tirs_adv["temps_s"] <= r["temps_s"] + fenetre)]
            tir.append(len(t) > 0)
            xg.append(t["xg"].sum())
        return ev_.assign(tir=tir, xg_suite=xg)

    a = v[v["nous"]]
    duels = a[(a["type"] == "Challenge") | ((a["type"].isin(["Aerial", "Tackle"])) & (a["outcome_type"] == "Unsuccessful"))]
    duels = danger(duels)
    erreurs = a[a["type"] == "Error"]
    fautes = a[(a["type"] == "Foul") & (a["outcome_type"] == "Unsuccessful") & (a["x"] <= 33.3)]
    touches = a[a["is_touch"] & a["x"].notna()]
    pos = touches.groupby("player").agg(x_moyen=("x", "mean"), y_moyen=("y", "mean"))
    pos["cote"] = np.where(pos["y_moyen"] > 60, "Gauche", np.where(pos["y_moyen"] < 40, "Droite", "Axe"))

    # centres adverses (hors CPA) partis du côté du joueur pendant qu'il était sur le terrain
    cr = v[~v["nous"] & (v["type"] == "Pass") & qual(v, "Cross")]
    cr = cr[[not est_cpa(q) for q in cr["quals"]]].copy()
    cr["cote_nous"] = [INVERSE.get(couloir3(y), np.nan) for y in cr["y"]]
    cr = danger(cr)

    lignes = []
    for joueur, t in tj.groupby("joueur"):
        cote = pos["cote"].get(joueur, "Axe")
        c_cote = cr[cr["cote_nous"] == cote] if cote != "Axe" else cr.iloc[0:0]
        sur_terrain = np.zeros(len(c_cote), dtype=bool)
        for _, iv in t.iterrows():
            sur_terrain |= ((c_cote["game_id"] == iv["game_id"]) & (c_cote["minute"] >= iv["debut"])
                            & (c_cote["minute"] < iv["fin"])).to_numpy()
        c_on = c_cote[sur_terrain]
        p = pertes[pertes["joueur_perte"] == joueur] if len(pertes) else pertes
        d = duels[duels["player"] == joueur]
        ch = d[d["type"] == "Challenge"]
        lignes.append({
            "equipe": equipe, "joueur": joueur, "minutes_ws": t["minutes"].sum(), "cote": cote,
            "x_moyen": pos["x_moyen"].get(joueur, np.nan),
            "pertes": len(p), "pertes_punies": int(p["tir_15s"].sum()) if len(p) else 0,
            "xg_apres_pertes": p["xg_15s"].sum() if len(p) else 0.0,
            "pertes_notre_moitie": int((p["x_perte"] < 50).sum()) if len(p) else 0,
            "pertes_notre_moitie_punies": int(((p["x_perte"] < 50) & p["tir_15s"]).sum()) if len(p) else 0,
            "duels_perdus": len(d), "duels_perdus_tir": int(d["tir"].sum()), "xg_apres_duels_perdus": d["xg_suite"].sum(),
            "aeriens_perdus": int((d["type"] == "Aerial").sum()),
            "aeriens_perdus_tir": int(d.loc[d["type"] == "Aerial", "tir"].sum()),
            "dribble_subi": len(ch), "dribble_subi_tir": int(ch["tir"].sum()),
            "erreurs": len(erreurs[erreurs["player"] == joueur]),
            "erreurs_but": int(qual(erreurs[erreurs["player"] == joueur], "LeadingToGoal").sum()),
            "fautes_notre_tiers": len(fautes[fautes["player"] == joueur]),
            "centres_adv_cote": len(c_on), "centres_adv_cote_tir": int(c_on["tir"].sum()),
            "xg_apres_centres_adv_cote": c_on["xg_suite"].sum(),
        })
    j = pd.DataFrame(lignes)
    for c in ("pertes", "pertes_punies", "xg_apres_pertes", "pertes_notre_moitie", "duels_perdus", "duels_perdus_tir",
              "xg_apres_duels_perdus", "aeriens_perdus_tir", "dribble_subi", "dribble_subi_tir", "fautes_notre_tiers",
              "centres_adv_cote", "centres_adv_cote_tir", "xg_apres_centres_adv_cote"):
        j[c + "_90"] = j[c] / j["minutes_ws"].replace(0, np.nan) * 90
    j["pct_pertes_punies"] = j["pertes_punies"] / j["pertes"].replace(0, np.nan) * 100
    j["xg_cout_90"] = j["xg_apres_pertes_90"] + j["xg_apres_duels_perdus_90"]
    return j


# =====================================================================================
# 7. TOUT LE FICHIER LIGUE 1 → tableaux lus par l'application
# =====================================================================================
def lire_evenements(chemin):
    ev = pd.read_csv(chemin, sep=";", decimal=",", encoding="utf-8-sig", low_memory=False)
    for c in ("is_touch", "is_shot", "is_goal"):
        ev[c] = ev[c].astype(str).str.lower().eq("true")
    return ev


def preparer_tout(ev, equipe_ws, ecrire):
    """
    ev : événements de toute la Ligue 1 ; equipe_ws : notre équipe (nom WhoScored) ;
    ecrire(df, nom) : fonction d'écriture de preparation.py.
    Écrit ws_equipes.csv, ws_joueurs_l1.csv, et le détail de notre équipe (pertes, récupérations, tirs concédés).
    Renvoie (nombre de matchs de notre équipe, tableau joueurs Ligue 1).
    """
    equipes = sorted(set(ev["home_team"].dropna()) | set(ev["away_team"].dropna()))
    lignes, joueurs, details = [], [], None
    for e in equipes:
        v = vue(ev, e)
        m, det = analyser(v)
        if e == equipe_ws:
            details = det
        lignes.append({"equipe": e, **m})
        joueurs.append(actions_qui_coutent(v, det["pertes"], e))
        print(f"    WhoScored · {e:<22} {m['matchs']} matchs")
    eqs = pd.DataFrame(lignes)
    jl = pd.concat(joueurs, ignore_index=True)
    # par équipe : actions qui coûtent par match (pour comparer)
    tot = jl.groupby("equipe")[["duels_perdus_tir", "dribble_subi_tir", "aeriens_perdus_tir", "erreurs",
                                 "centres_adv_cote"]].sum()
    eqs = eqs.join(tot, on="equipe")
    for c in tot.columns:
        eqs[c + "_match"] = eqs[c] / eqs["matchs"]
    ecrire(eqs.round(4), "ws_equipes.csv")
    if details is None:
        print(f"    ✖ {equipe_ws} introuvable dans les événements WhoScored")
        return 0, jl
    ecrire(details["pertes"], "ws_pertes.csv")
    ecrire(details["recups"], "ws_recups.csv")
    ecrire(details["tirs_concedes"], "ws_tirs_concedes.csv")
    return int(eqs.loc[eqs["equipe"] == equipe_ws, "matchs"].iloc[0]), jl
