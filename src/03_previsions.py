"""Étape 3 : prévision de la part de voitures électriques par département (2027-2036).

Cible : part des voitures 100 % électriques (y compris hydrogène) dans le parc des particuliers,
au 1er janvier. Les voitures des professionnels sont exclues car les flottes changent de commune
en bloc (voir l'audit).

Trois modèles sont comparés sur la même échelle (logit de la part) :
  1. Tendance linéaire     : prolonge la pente des cinq dernières années (modèle de référence).
  2. Courbe en S           : logit(part) linéaire dans le temps, ajusté par département
                             depuis 2016 (modèle de diffusion logistique).
  3. XGBoost               : apprend, sur tous les départements, la variation annuelle du logit
                             à partir du niveau atteint, de la dynamique récente et de la
                             structure du parc ; prévision récursive année par année.

  4. Stock-flux            : modèle structurel. Le parc se renouvelle lentement : chaque année
                             une part du parc sort (hypothèse 5 %, 1 % pour les électriques,
                             plus récentes) et de nouvelles voitures entrent. On mesure la part
                             d'électriques parmi ces entrées, puis on simule le parc.

Validation : backtest à origines glissantes (2018 à 2023), horizons de 1 à 5 ans, erreur
mesurée en points de pourcentage sur des années réellement observées.
Court terme (2027-2031) : modèle le mieux classé au backtest (un consensus entre l'approche
statistique et l'approche stock-flux, dont les erreurs se compensent), avec intervalle empirique.
Long terme (jusqu'à 2036) : aucun modèle ne peut être validé à 10 ans sur 16 ans d'historique ;
on utilise le modèle stock-flux, qui respecte la vitesse de renouvellement du parc, en trois
scénarios sur la part d'électriques parmi les voitures entrantes.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DERNIERE = 2026
HORIZON_MAX = 10
ORIGINES_BACKTEST = [2018, 2019, 2020, 2021, 2022, 2023]
HORIZON_VALIDE = 5  # au-delà, le backtest ne peut plus juger les modèles
DEBUT_COURBE = 2016
EPS = 1e-5
FEATURES = ["logit", "dlogit_1", "dlogit_3", "part_hr", "part_hnr", "part_diesel", "log_parc", "croissance_parc_3", "drom"]


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def panel():
    d = pd.read_parquet(DATA / "dep_energie.parquet")
    d = d[(d.statut == "Particulier") & (d.energie != "Inconnu") & (d.code_dep != "976")]
    wide = d.pivot_table(index=["code_dep", "nom_dep", "region", "annee"], columns="energie",
                         values="parc", aggfunc="sum", fill_value=0).reset_index()
    wide["parc"] = wide[[c for c in wide.columns if c not in ("code_dep", "nom_dep", "region", "annee")]].sum(axis=1)
    p = pd.DataFrame({
        "code_dep": wide.code_dep, "nom_dep": wide.nom_dep, "region": wide.region, "annee": wide.annee,
        "parc": wide.parc,
        "part": wide["Électrique"] / wide.parc,
        "part_hr": wide["Hybride rechargeable"] / wide.parc,
        "part_hnr": wide["Hybride non rechargeable"] / wide.parc,
        "part_diesel": wide["Diesel"] / wide.parc,
    }).sort_values(["code_dep", "annee"]).reset_index(drop=True)
    p["drom"] = p.code_dep.str.startswith("97").astype(int)
    return p


def ajoute_features(p):
    p = p.sort_values(["code_dep", "annee"]).copy()
    g = p.groupby("code_dep")
    p["logit"] = logit(p.part)
    p["dlogit_1"] = g.logit.diff(1)
    p["dlogit_3"] = g.logit.diff(3) / 3
    p["log_parc"] = np.log(p.parc)
    p["croissance_parc_3"] = g.parc.pct_change(3, fill_method=None)
    p["cible"] = g.logit.shift(-1) - p.logit  # variation du logit l'année suivante
    return p


# ---------- Modèles : chacun renvoie {code_dep: [part prévue à h=1..H]} ----------

def prevoir_tendance(hist, origine, H):
    out = {}
    for dep, s in hist[hist.annee.between(origine - 4, origine)].groupby("code_dep"):
        a, b = np.polyfit(s.annee, s.part, 1)
        out[dep] = np.clip(b + a * np.arange(origine + 1, origine + H + 1), 0, 1)
    return out


def prevoir_courbe_s(hist, origine, H):
    out = {}
    for dep, s in hist[hist.annee.between(DEBUT_COURBE, origine)].groupby("code_dep"):
        w = np.linspace(0.5, 1.5, len(s))  # plus de poids aux années récentes
        a, b = np.polyfit(s.annee, logit(s.part), 1, w=w)
        out[dep] = sigmoid(b + a * np.arange(origine + 1, origine + H + 1))
    return out


def entrainer_xgb(p, origine):
    train = p[(p.annee < origine) & p[FEATURES + ["cible"]].notna().all(axis=1)]
    m = XGBRegressor(n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8,
                     colsample_bytree=0.8, min_child_weight=5, random_state=42)
    m.fit(train[FEATURES], train.cible)
    return m


def prevoir_xgb(p, origine, H, modele=None):
    m = modele or entrainer_xgb(p, origine)
    etat = p[p.annee <= origine].groupby("code_dep").tail(4).copy()
    out = {dep: [] for dep in etat.code_dep.unique()}
    for _ in range(H):
        x = etat.groupby("code_dep").tail(1).copy()
        x["logit_suiv"] = x.logit + m.predict(x[FEATURES])
        nouv = x.copy()
        nouv["annee"] += 1
        nouv["logit"] = nouv.logit_suiv
        nouv["part"] = sigmoid(nouv.logit)
        # Les autres variables de structure sont figées à leur dernier niveau connu.
        etat = pd.concat([etat, nouv.drop(columns="logit_suiv")])
        etat = etat.sort_values(["code_dep", "annee"])
        g = etat.groupby("code_dep")
        etat["dlogit_1"] = g.logit.diff(1)
        etat["dlogit_3"] = g.logit.diff(3) / 3
        for dep, part in zip(nouv.code_dep, nouv.part):
            out[dep].append(part)
    return {k: np.array(v) for k, v in out.items()}, m


def prevoir_ensemble(prev_s, prev_x):
    return {d: (prev_s[d] + prev_x[d]) / 2 for d in prev_s}


DELTA, DELTA_EV = 0.05, 0.01  # taux de sortie annuels du parc (hypothèses)
SCENARIOS = {"Flux figés": "figes", "Tendance des flux": "tendance", "Électrification forte": "forte"}


def flux_entrees(s):
    """Part d'électriques parmi les voitures entrées dans le parc chaque année (série d'un département)."""
    s = s.sort_values("annee")
    ev = s.part.values * s.parc.values
    entrees = s.parc.values[1:] - s.parc.values[:-1] * (1 - DELTA)
    m = (ev[1:] - ev[:-1] * (1 - DELTA_EV)) / entrees
    return pd.Series(np.clip(m, 0, 1), index=s.annee.values[:-1])


def prevoir_stock_flux(hist, origine, H, scenario="figes"):
    out = {}
    for dep, s in hist[hist.annee <= origine].groupby("code_dep"):
        m_hist = flux_entrees(s)
        m0 = m_hist.loc[origine - 3:origine - 1].mean()
        a_parc, b_parc = np.polyfit(s.annee.tail(5), s.parc.tail(5), 1)
        if scenario == "tendance":
            fen = m_hist.loc[origine - 7:origine - 1]
            pente = max(np.polyfit(fen.index, fen.values, 1)[0], 0)
        parc, ev = s.parc.iloc[-1], s.part.iloc[-1] * s.parc.iloc[-1]
        serie = []
        for h in range(1, H + 1):
            if scenario == "figes":
                m = m0
            elif scenario == "tendance":
                m = min(m0 + pente * h, 1)
            else:  # électrification forte : les entrées deviennent électriques à 100 % en 2035
                m = min(m0 + (1 - m0) * h / max(2035 - origine, 1), 1)
            parc_suiv = b_parc + a_parc * (origine + h)
            entrees = parc_suiv - parc * (1 - DELTA)
            ev = ev * (1 - DELTA_EV) + m * entrees
            parc = parc_suiv
            serie.append(min(ev / parc, 1))
        out[dep] = np.array(serie)
    return out


# ---------- Backtest ----------

def backtest(p):
    lignes = []
    for origine in ORIGINES_BACKTEST:
        H = DERNIERE - origine
        hist = p[p.annee <= origine]
        preds = {"Tendance linéaire": prevoir_tendance(hist, origine, H),
                 "Courbe en S": prevoir_courbe_s(hist, origine, H)}
        preds["XGBoost"], _ = prevoir_xgb(p, origine, H)
        preds["Moyenne courbe en S + XGBoost"] = prevoir_ensemble(preds["Courbe en S"], preds["XGBoost"])
        preds["Stock-flux (tendance des flux)"] = prevoir_stock_flux(hist, origine, H, "tendance")
        preds["Consensus"] = prevoir_ensemble(preds["Moyenne courbe en S + XGBoost"], preds["Stock-flux (tendance des flux)"])
        reel = p.set_index(["code_dep", "annee"]).part
        for nom, pr in preds.items():
            for dep, serie in pr.items():
                for h, val in enumerate(serie[:HORIZON_VALIDE], start=1):
                    obs = reel.get((dep, origine + h))
                    if obs is not None:
                        lignes.append(dict(modele=nom, origine=origine, h=h, code_dep=dep,
                                           prevu=val, observe=obs,
                                           err_logit=logit(obs) - logit(val)))
    bt = pd.DataFrame(lignes)
    bt["erreur_pts"] = 100 * (bt.prevu - bt.observe)
    return bt


def predictions(p, origine, H):
    prev = {"Tendance linéaire": prevoir_tendance(p, origine, H), "Courbe en S": prevoir_courbe_s(p, origine, H)}
    prev["XGBoost"], modele = prevoir_xgb(p, origine, H)
    prev["Moyenne courbe en S + XGBoost"] = prevoir_ensemble(prev["Courbe en S"], prev["XGBoost"])
    prev["Stock-flux (tendance des flux)"] = prevoir_stock_flux(p, origine, H, "tendance")
    prev["Consensus"] = prevoir_ensemble(prev["Moyenne courbe en S + XGBoost"], prev["Stock-flux (tendance des flux)"])
    return prev, modele


def main():
    p = ajoute_features(panel())
    bt = backtest(p)
    bt["abs_err"] = bt.erreur_pts.abs()
    bt["err_rel"] = 100 * bt.abs_err / (100 * bt.observe)

    scores = (bt.groupby("modele")
                .agg(mae_pts=("abs_err", "mean"), biais_pts=("erreur_pts", "mean"), err_rel_med=("err_rel", "median"))
                .sort_values("mae_pts"))
    par_h = bt.pivot_table(index="h", columns="modele", values="abs_err", aggfunc="mean")
    meilleur = scores.index[0]
    print(scores.round(3), "\n")
    print("Modèle retenu pour le court terme :", meilleur)

    # Intervalle : dispersion des erreurs du modèle retenu (quantiles 10 % et 90 % en logit, centrés
    # sur la médiane) par horizon. On garde la dispersion sans corriger le biais, car le biais passé
    # vient surtout des années d'accélération 2018-2022, qui ne se sont pas reproduites depuis.
    q = bt[bt.modele == meilleur].groupby("h").err_logit.quantile([0.1, 0.5, 0.9]).unstack()
    q[0.1], q[0.9] = q[0.1] - q[0.5], q[0.9] - q[0.5]

    prev, modele_final = predictions(p, DERNIERE, HORIZON_MAX)
    scen = {nom: prevoir_stock_flux(p, DERNIERE, HORIZON_MAX, code) for nom, code in SCENARIOS.items()}

    parc_prev = {}
    for dep, s in p[p.annee > DERNIERE - 5].groupby("code_dep"):
        a, b = np.polyfit(s.annee, s.parc, 1)
        parc_prev[dep] = b + a * np.arange(DERNIERE + 1, DERNIERE + HORIZON_MAX + 1)

    infos = p[p.annee == DERNIERE].set_index("code_dep")[["nom_dep", "region"]]
    lignes = []
    for dep in prev[meilleur]:
        for h in range(1, HORIZON_MAX + 1):
            ligne = dict(code_dep=dep, nom_dep=infos.loc[dep, "nom_dep"], region=infos.loc[dep, "region"],
                         annee=DERNIERE + h, h=h, parc=parc_prev[dep][h - 1],
                         scen_figes=100 * scen["Flux figés"][dep][h - 1],
                         scen_tendance=100 * scen["Tendance des flux"][dep][h - 1],
                         scen_forte=100 * scen["Électrification forte"][dep][h - 1])
            if h <= HORIZON_VALIDE:
                val = prev[meilleur][dep][h - 1]
                ligne.update(part=100 * val,
                             part_basse=100 * sigmoid(logit(val) + q.loc[h, 0.1]),
                             part_haute=100 * sigmoid(logit(val) + q.loc[h, 0.9]),
                             part_courbe_s=100 * prev["Courbe en S"][dep][h - 1],
                             part_xgboost=100 * prev["XGBoost"][dep][h - 1],
                             part_stock_flux=100 * prev["Stock-flux (tendance des flux)"][dep][h - 1])
            lignes.append(ligne)
    prevs = pd.DataFrame(lignes)
    prevs.to_parquet(DATA / "previsions_dep.parquet", index=False)

    # Agrégat France (hors Mayotte), pondéré par le parc prévu de chaque département
    cols = ["part", "part_basse", "part_haute", "scen_figes", "scen_tendance", "scen_forte"]
    fr = prevs.groupby("annee").apply(
        lambda g: pd.Series({"parc": g.parc.sum(), **{c: np.average(g[c], weights=g.parc) if g[c].notna().all() else np.nan for c in cols}}),
        include_groups=False).reset_index()
    fr.to_parquet(DATA / "previsions_france.parquet", index=False)

    hist = p.assign(part=100 * p.part)[["code_dep", "nom_dep", "region", "annee", "parc", "part"]]
    hist.to_parquet(DATA / "historique_dep.parquet", index=False)
    flux = pd.concat([flux_entrees(s).rename("m").to_frame().assign(code_dep=d) for d, s in p.groupby("code_dep")])
    flux = flux.rename_axis("annee").reset_index()
    nat = p.groupby("annee").apply(lambda g: pd.Series({"parc": g.parc.sum(), "part": np.average(g.part, weights=g.parc)}),
                                   include_groups=False).reset_index()
    flux_fr = flux_entrees(nat.assign(code_dep="FR")).rename("m").rename_axis("annee").reset_index()
    flux_fr.assign(m=100 * flux_fr.m).to_parquet(DATA / "flux_entrees_france.parquet", index=False)
    bt.to_parquet(DATA / "backtest.parquet", index=False)

    f = fr.set_index("annee")
    meta = dict(
        modele_retenu=meilleur, horizon_valide=HORIZON_VALIDE, origines_backtest=ORIGINES_BACKTEST,
        hypotheses=dict(taux_sortie=DELTA, taux_sortie_electriques=DELTA_EV),
        scores={m: {k: float(v) for k, v in r.items()} for m, r in scores.iterrows()},
        mae_par_horizon={int(h): {m: float(v) for m, v in row.items()} for h, row in par_h.iterrows()},
        importance_xgboost=dict(zip(FEATURES, map(float, modele_final.feature_importances_))),
        france_2026=float(np.average(p[p.annee == DERNIERE].part, weights=p[p.annee == DERNIERE].parc) * 100),
        france_2031={c: round(float(f.loc[2031, c]), 1) for c in cols},
        france_2036={c: round(float(f.loc[2036, c]), 1) for c in cols[3:]},
    )
    (DATA / "modeles.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print("\nFrance 2026 :", round(meta["france_2026"], 2))
    print("France 2031 :", meta["france_2031"])
    print("France 2036 :", meta["france_2036"])


if __name__ == "__main__":
    main()
