"""Observatoire du parc automobile français : application Streamlit.

Lancement local : streamlit run app/streamlit_app.py
"""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).resolve().parents[1] / "data"

st.set_page_config(page_title="Observatoire du parc automobile", page_icon="🚗", layout="wide")

# Couleurs : une teinte fixe par énergie, identique sur tous les graphiques
COULEURS = {
    "Électrique": "#1baf7a",
    "Hybride rechargeable": "#2a78d6",
    "Hybride non rechargeable": "#4a3aa7",
    "Essence": "#eb6834",
    "Diesel": "#eda100",
    "Autres": "#a8a69f",
}
NAVY, TEAL, GRIS = "#14213D", "#0E7C7B", "#6b6a64"
SCEN_COULEURS = {"Flux figés": "#a8a69f", "Tendance des flux": "#2a78d6", "Électrification forte": "#1baf7a"}


def fr(n, dec=0):
    """Formate un nombre à la française."""
    s = f"{n:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def style(fig, height=420):
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=10, r=10, t=40, b=10),
                      font=dict(family="Source Sans Pro, sans-serif", size=13, color="#1b2433"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      hoverlabel=dict(bgcolor="white"), separators=", ")
    fig.update_xaxes(showgrid=False, linecolor="#d5dce4")
    fig.update_yaxes(gridcolor="#eef1f4", zeroline=False)
    return fig


@st.cache_data
def charger():
    d = {n: pd.read_parquet(DATA / f"{n}.parquet") for n in
         ["national_energie", "national_critair", "dep_energie", "communes", "historique_dep",
          "previsions_dep", "previsions_france", "backtest", "flux_entrees_france"]}
    d["audit"] = json.loads((DATA / "audit.json").read_text())
    d["modeles"] = json.loads((DATA / "modeles.json").read_text())
    d["geo"] = json.loads((DATA / "departements.geojson").read_text())
    return d


D = charger()

ECHELLE = ["#eef7f3", "#8fd0b4", "#1baf7a", "#0b6b4a"]


def carte(df):
    """Carte des départements dessinée en polygones (aucun fond de carte externe à charger)."""
    vmin, vmax = df.part.min(), df.part.max()
    fig = go.Figure()
    valeurs = df.set_index("code_dep")
    for feat in D["geo"]["features"]:
        code = feat["properties"]["code"]
        if code not in valeurs.index:
            continue
        v = valeurs.loc[code]
        t = (v.part - vmin) / (vmax - vmin)
        couleur = px.colors.sample_colorscale(ECHELLE, [t])[0]
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            lon, lat = zip(*poly[0])
            fig.add_trace(go.Scatter(
                x=lon, y=lat, fill="toself", fillcolor=couleur, mode="lines",
                line=dict(color="white", width=0.6), hoveron="fills", showlegend=False,
                text=f"<b>{v.nom_dep}</b><br>Électriques : {fr(v.part, 2)} %<br>+{fr(v.evol, 2)} pt depuis 2021",
                hoverinfo="text"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(colorscale=ECHELLE, cmin=vmin, cmax=vmax, color=[vmin],
                                         colorbar=dict(title="%", thickness=12, len=0.6))))
    fig = style(fig, 560)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1.45)
    return fig

M = D["modeles"]

# ------------------------------------------------------------------ En-tête
st.title("Observatoire du parc automobile français")
st.markdown(
    "Où en est la transition vers l'électrique, territoire par territoire, et à quoi ressemblera le parc "
    "dans 5 et 10 ans ? Données publiques du SDES (ministère de la Transition écologique), "
    "35 000 communes, parc au 1er janvier de 2011 à 2026.  \n"
    "Projet réalisé par **Marie Ange Akoua Kouame**, Data Analyst."
)

onglets = st.tabs(["Vue d'ensemble", "Territoires", "Prévisions 2031 et 2036", "Qualité des données", "Méthode"])

# ------------------------------------------------------------------ 1. Vue d'ensemble
with onglets[0]:
    ne = D["national_energie"].copy()
    ne["energie"] = ne.energie.where(ne.energie.isin(COULEURS), "Autres")
    tot = ne.groupby(["annee", "energie"], as_index=False).parc.sum()
    pivot = tot.pivot(index="annee", columns="energie", values="parc").fillna(0)
    parts = 100 * pivot.div(pivot.sum(axis=1), axis=0)

    p26, p21 = parts.loc[2026], parts.loc[2021]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Voitures en circulation (2026)", f"{fr(pivot.loc[2026].sum() / 1e6, 1)} M",
              f"+{fr(100 * (pivot.loc[2026].sum() / pivot.loc[2021].sum() - 1), 1)} % depuis 2021")
    c2.metric("Part des électriques", f"{fr(p26['Électrique'], 1)} %",
              f"+{fr(p26['Électrique'] - p21['Électrique'], 1)} pt depuis 2021")
    c3.metric("Part des hybrides rechargeables", f"{fr(p26['Hybride rechargeable'], 1)} %",
              f"+{fr(p26['Hybride rechargeable'] - p21['Hybride rechargeable'], 1)} pt depuis 2021")
    c4.metric("Part du diesel", f"{fr(p26['Diesel'], 1)} %",
              f"{fr(p26['Diesel'] - p21['Diesel'], 1)} pt depuis 2021", delta_color="inverse")

    st.subheader("Composition du parc par énergie")
    ordre = ["Diesel", "Essence", "Hybride non rechargeable", "Hybride rechargeable", "Électrique", "Autres"]
    long = parts.reset_index().melt(id_vars="annee", var_name="energie", value_name="part")
    fig = px.area(long, x="annee", y="part", color="energie", category_orders={"energie": ordre},
                  color_discrete_map=COULEURS, labels={"annee": "", "part": "Part du parc (%)", "energie": ""})
    fig.update_traces(hovertemplate="%{fullData.name} : %{y:.1f} %<extra></extra>", line=dict(width=0.5))
    fig.update_layout(hovermode="x unified", yaxis_range=[0, 100])
    fig.add_vline(x=2024.5, line_width=1, line_dash="dash", line_color="#ffffff")
    fig.add_annotation(x=2025.5, y=50, text="2025-2026<br>provisoires", showarrow=False, font=dict(size=11, color="#1b2433"))
    st.plotly_chart(style(fig), width="stretch")
    st.caption("Toutes voitures particulières, particuliers et professionnels. Les millésimes 2025 et 2026 "
               "sont provisoires selon le SDES.")

    st.subheader("La montée des motorisations électrifiées")
    elec = long[long.energie.isin(["Hybride non rechargeable", "Hybride rechargeable", "Électrique"])]
    fig = px.line(elec, x="annee", y="part", color="energie", color_discrete_map=COULEURS, markers=True,
                  labels={"annee": "", "part": "Part du parc (%)", "energie": ""})
    fig.update_traces(line=dict(width=2.5), marker=dict(size=7),
                      hovertemplate="%{fullData.name} : %{y:.2f} %<extra></extra>")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style(fig, 380), width="stretch")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Voitures électriques en circulation")
        ev = pivot["Électrique"].reset_index()
        fig = px.bar(ev, x="annee", y="Électrique", labels={"annee": "", "Électrique": "Voitures"},
                     color_discrete_sequence=[COULEURS["Électrique"]])
        fig.update_traces(hovertemplate="%{x} : %{y:,.0f} voitures<extra></extra>", marker_line_width=0)
        st.plotly_chart(style(fig, 360), width="stretch")
    with col_b:
        st.subheader("Vignettes Crit'Air en 2026")
        ca = D["national_critair"].query("annee == 2026").copy()
        ordre_ca = ["Crit'Air E", "Crit'Air 1", "Crit'Air 2", "Crit'Air 3", "Crit'Air 4", "Crit'Air 5", "Non classé", "Inconnu"]
        ca = ca[ca.crit_air != "Inconnu"]
        ca["part"] = 100 * ca.parc / ca.parc.sum()
        ca["crit_air"] = pd.Categorical(ca.crit_air, ordre_ca, ordered=True)
        ca = ca.sort_values("crit_air")
        seq = ["#1baf7a", "#8fd0b4", "#c9c7bf", "#e0a370", "#d97a45", "#b8532a", "#7a4a3a"]
        ordre_aff = [c for c in ordre_ca if c != "Inconnu"]
        fig = px.bar(ca, x="part", y="crit_air", orientation="h", color="crit_air",
                     category_orders={"crit_air": ordre_aff}, color_discrete_sequence=seq,
                     labels={"part": "Part du parc (%)", "crit_air": ""})
        fig.update_traces(hovertemplate="%{y} : %{x:.1f} %<extra></extra>", marker_line_width=0)
        fig.update_layout(showlegend=False, yaxis_autorange="reversed")
        st.plotly_chart(style(fig, 360), width="stretch")
        st.caption("Les vignettes 3 à 5 et les voitures non classées désignent les modèles les plus anciens "
                   "et les plus émetteurs, visés par les zones à faibles émissions.")

# ------------------------------------------------------------------ 2. Territoires
with onglets[1]:
    st.markdown("Les comparaisons territoriales portent sur les **voitures des particuliers** : les flottes des "
                "entreprises et des loueurs sont immatriculées au siège et faussent la géographie "
                "(voir l'onglet Qualité des données).")
    h = D["historique_dep"]
    dep26 = h[h.annee == 2026].copy()
    dep21 = h[h.annee == 2021].set_index("code_dep").part
    dep26["evol"] = dep26.part - dep26.code_dep.map(dep21)

    col_m, col_r = st.columns([3, 2])
    with col_m:
        st.subheader("Part de voitures électriques par département, 2026")
        st.plotly_chart(carte(dep26[~dep26.code_dep.str.startswith("97")]), width="stretch")
    with col_r:
        st.subheader("Classement")
        niveau = st.radio("Niveau", ["Départements", "Régions"], horizontal=True, key="niveau")
        if niveau == "Régions":
            reg = (h[h.annee == 2026].assign(ev=lambda x: x.part * x.parc)
                   .groupby("region", as_index=False).agg(ev=("ev", "sum"), parc=("parc", "sum")))
            reg["part"] = reg.ev / reg.parc
            tab = reg.sort_values("part", ascending=False)[["region", "part", "parc"]]
            tab.columns = ["Région", "Part électrique (%)", "Voitures des particuliers"]
        else:
            tab = dep26.sort_values("part", ascending=False)[["code_dep", "nom_dep", "part", "evol"]]
            tab.columns = ["Code", "Département", "Part électrique (%)", "Évolution depuis 2021 (pt)"]
        st.dataframe(tab, hide_index=True, height=500, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in tab.columns if "(%" in c or "(pt" in c}
                     | {"Voitures des particuliers": st.column_config.NumberColumn(format="%d")})

    st.subheader("Trouver une commune")
    com = D["communes"]
    recherche = st.text_input("Nom de commune", placeholder="ex. Brest, Angers, Lyon 3e…", key="recherche")
    seuil = st.slider("Taille minimale du parc des particuliers", 0, 5000, 1000, step=100, key="seuil")
    vue = com[com.parc_2026 >= seuil]
    if recherche:
        vue = vue[vue.nom_commune.str.contains(recherche, case=False, na=False)]
    vue = vue.sort_values("part_elec_2026", ascending=False)[
        ["nom_commune", "nom_dep", "parc_2026", "part_elec_2026", "part_rechargeable_2026", "part_crit3plus_2026", "part_elec_2021"]]
    vue.columns = ["Commune", "Département", "Voitures (2026)", "Électriques (%)", "Électriques + hybrides rech. (%)",
                   "Crit'Air 3 et plus (%)", "Électriques en 2021 (%)"]
    st.dataframe(vue, hide_index=True, height=380, width="stretch",
                 column_config={"Voitures (2026)": st.column_config.NumberColumn(format="%d")}
                 | {c: st.column_config.NumberColumn(format="%.2f") for c in vue.columns if "(%)" in c})
    st.caption(f"{fr(len(vue))} communes affichées. Voitures des particuliers uniquement.")

# ------------------------------------------------------------------ 3. Prévisions
with onglets[2]:
    pf, hdep = D["previsions_france"], D["historique_dep"]
    hist_fr = (hdep.assign(ev=hdep.part * hdep.parc).groupby("annee", as_index=False)
                   .agg(ev=("ev", "sum"), parc=("parc", "sum")))
    hist_fr["part"] = hist_fr.ev / hist_fr.parc
    f31, f36 = M["france_2031"], M["france_2036"]

    st.markdown(
        f"Part des voitures **100 % électriques** dans le parc des particuliers, France hors Mayotte. "
        f"Elle était de **{fr(M['france_2026'], 1)} %** au 1er janvier 2026.")
    c1, c2, c3 = st.columns(3)
    c1.metric("2031 · prévision centrale", f"{fr(f31['part'], 1)} %")
    c1.caption(f"Fourchette à 80 % : {fr(f31['part_basse'], 1)} à {fr(f31['part_haute'], 1)} %")
    c2.metric("2036 · scénario tendance des flux", f"{fr(f36['scen_tendance'], 1)} %")
    c2.caption(f"De {fr(f36['scen_figes'], 1)} à {fr(f36['scen_forte'], 1)} % selon le scénario")
    c3.metric("Erreur moyenne du modèle à 5 ans", f"{fr(M['mae_par_horizon']['5'][M['modele_retenu']], 2)} pt")
    c3.caption("Mesurée sur des années déjà observées (backtest)")

    def graphique_prevision(hist, prev, titre):
        fig = go.Figure()
        court = prev.dropna(subset=["part"])
        fig.add_trace(go.Scatter(x=list(court.annee) + list(court.annee[::-1]),
                                 y=list(court.part_haute) + list(court.part_basse[::-1]),
                                 fill="toself", fillcolor="rgba(20,33,61,0.10)", line=dict(width=0), mode="lines",
                                 name="Fourchette 80 %", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=hist.annee, y=hist.part, name="Observé", mode="lines+markers",
                                 line=dict(color=NAVY, width=2.5), marker=dict(size=6),
                                 hovertemplate="%{x} : %{y:.2f} %<extra>Observé</extra>"))
        x0, y0 = hist.annee.iloc[-1], hist.part.iloc[-1]
        fig.add_trace(go.Scatter(x=[x0] + list(court.annee), y=[y0] + list(court.part), name="Prévision centrale",
                                 line=dict(color=NAVY, width=2.5, dash="dot"),
                                 hovertemplate="%{x} : %{y:.1f} %<extra>Prévision centrale</extra>"))
        for nom, col in [("Flux figés", "scen_figes"), ("Tendance des flux", "scen_tendance"), ("Électrification forte", "scen_forte")]:
            fig.add_trace(go.Scatter(x=[x0] + list(prev.annee), y=[y0] + list(prev[col]), name=f"Scénario : {nom.lower()}",
                                     line=dict(color=SCEN_COULEURS[nom], width=2),
                                     hovertemplate="%{x} : %{y:.1f} %<extra>" + nom + "</extra>"))
        fig.add_vline(x=2026.5, line_width=1, line_dash="dash", line_color="#b8bfc8")
        fig.update_layout(title=titre, yaxis_title="Part des électriques (%)", hovermode="x unified")
        return style(fig, 460)

    st.plotly_chart(graphique_prevision(hist_fr, pf, "France"), width="stretch")

    st.subheader("Par département")
    deps = D["previsions_dep"][["code_dep", "nom_dep"]].drop_duplicates().sort_values("code_dep")
    choix = st.selectbox("Département", deps.code_dep + " – " + deps.nom_dep, index=int((deps.code_dep == "29").argmax()), key="dep")
    code = choix.split(" – ")[0]
    pd_dep = D["previsions_dep"].query("code_dep == @code")
    st.plotly_chart(graphique_prevision(hdep.query("code_dep == @code"), pd_dep, choix), width="stretch")

    p31 = D["previsions_dep"].query("annee == 2031").sort_values("part", ascending=False)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Départements les plus avancés en 2031 (prévision centrale)**")
        st.dataframe(p31.head(10)[["nom_dep", "part", "part_basse", "part_haute"]].rename(columns={
            "nom_dep": "Département", "part": "Centrale (%)", "part_basse": "Basse (%)", "part_haute": "Haute (%)"}),
            hide_index=True, width="stretch", column_config={c: st.column_config.NumberColumn(format="%.1f") for c in ["Centrale (%)", "Basse (%)", "Haute (%)"]})
    with col_b:
        st.markdown("**Départements les moins avancés en 2031**")
        st.dataframe(p31.tail(10).iloc[::-1][["nom_dep", "part", "part_basse", "part_haute"]].rename(columns={
            "nom_dep": "Département", "part": "Centrale (%)", "part_basse": "Basse (%)", "part_haute": "Haute (%)"}),
            hide_index=True, width="stretch", column_config={c: st.column_config.NumberColumn(format="%.1f") for c in ["Centrale (%)", "Basse (%)", "Haute (%)"]})

    st.subheader("Comment les modèles ont été départagés")
    st.markdown(
        "Chaque modèle a été entraîné comme si l'on était en 2018, 2019, … 2023, puis ses prévisions ont été "
        "comparées aux années réellement observées ensuite. Le modèle retenu est celui dont l'erreur moyenne est "
        f"la plus faible : **{M['modele_retenu'].lower()}** entre l'approche statistique (courbe en S + XGBoost) "
        "et l'approche stock-flux. Leurs erreurs vont en sens inverse et se compensent.")
    sc = pd.DataFrame(M["scores"]).T.reset_index().rename(columns={"index": "Modèle", "mae_pts": "Erreur moyenne (pt)",
                                                                    "biais_pts": "Biais (pt)", "err_rel_med": "Écart relatif médian (%)"})
    col_a, col_b = st.columns([2, 3])
    with col_a:
        st.dataframe(sc, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in sc.columns[1:]})
        st.caption("Biais négatif : le modèle a sous-estimé la progression. Erreurs calculées sur 100 départements.")
    with col_b:
        mh = pd.DataFrame(M["mae_par_horizon"]).T
        mh.index = mh.index.astype(int)
        garder = ["Consensus", "Moyenne courbe en S + XGBoost", "Stock-flux (tendance des flux)", "Tendance linéaire"]
        coul = {"Consensus": NAVY, "Moyenne courbe en S + XGBoost": "#2a78d6",
                "Stock-flux (tendance des flux)": "#1baf7a", "Tendance linéaire": "#a8a69f"}
        fig = go.Figure()
        for m in garder:
            fig.add_trace(go.Scatter(x=mh.index, y=mh[m], name=m, mode="lines+markers", line=dict(color=coul[m], width=2),
                                     marker=dict(size=8), hovertemplate="%{x} an(s) : %{y:.2f} pt<extra>" + m + "</extra>"))
        fig.update_layout(xaxis_title="Horizon de prévision (années)", yaxis_title="Erreur absolue moyenne (pt)",
                          hovermode="x unified")
        fig = style(fig, 380)
        fig.update_xaxes(dtick=1)
        fig.update_layout(legend=dict(orientation="h", y=-0.3, yanchor="top"))
        st.plotly_chart(fig, width="stretch")

    ff = D["flux_entrees_france"]
    st.subheader("Le signal que les modèles d'extrapolation ne voient pas")
    st.markdown(
        "Le modèle stock-flux estime chaque année la part d'électriques parmi les voitures qui **entrent** dans le "
        "parc des particuliers. Elle a bondi de 2020 à 2023, puis s'est stabilisée autour de 10 %. "
        "Tant que ce palier dure, le parc ne peut pas s'électrifier au rythme des années d'accélération : "
        "c'est pour cela que les scénarios à 10 ans reposent sur cette variable.")
    fig = px.bar(ff[ff.annee >= 2015], x="annee", y="m", labels={"annee": "", "m": "Part des électriques parmi les entrées (%)"},
                 color_discrete_sequence=[COULEURS["Électrique"]])
    fig.update_traces(hovertemplate="%{x} : %{y:.1f} %<extra></extra>", marker_line_width=0)
    st.plotly_chart(style(fig, 320), width="stretch")
    st.caption(f"Hypothèses : {fr(100 * M['hypotheses']['taux_sortie'])} % du parc sort chaque année, "
               f"{fr(100 * M['hypotheses']['taux_sortie_electriques'])} % pour les électriques, plus récentes.")

# ------------------------------------------------------------------ 4. Qualité des données
with onglets[3]:
    a = D["audit"]
    st.markdown(
        f"Avant toute analyse, le fichier brut ({fr(a['lignes'])} lignes, {fr(a['communes'])} codes commune, "
        f"{a['colonnes']} colonnes) a été audité selon les dimensions de la qualité des données du référentiel "
        "DAMA-DMBOK. Chaque constat est associé à une décision de traitement.")
    audit = pd.DataFrame(a["controles"])[["dimension", "controle", "constat", "impact", "decision"]]
    audit.columns = ["Dimension", "Contrôle", "Constat", "Impact", "Décision"]
    st.dataframe(audit, hide_index=True, width="stretch", height=560,
                 column_config={"Constat": st.column_config.TextColumn(width="large"),
                                "Décision": st.column_config.TextColumn(width="medium")})
    st.markdown("**Contrôle de réconciliation** : après transformation, le total national de voitures au 1er janvier "
                "2026 est identique au fichier brut, à l'unité près.")

# ------------------------------------------------------------------ 5. Méthode
with onglets[4]:
    st.markdown(f"""
**Source.** [Parc de véhicules routiers](https://www.data.gouv.fr/datasets/parc-de-vehicules-routiers), SDES, données communales
au 1er janvier 2011-2026, licence ouverte. Note méthodologique du SDES (document de travail n° 67).

**Chaîne de traitement.**
1. *Audit* (Python + DuckDB) : 14 contrôles de qualité, rapport dans `reports/audit_qualite.md`.
2. *Modélisation SQL* (DuckDB) : passage en format long, regroupement des carburants en familles d'énergie,
   agrégats nationaux, départementaux et communaux, contrôle de réconciliation.
3. *Prévisions* (Python, scikit-learn, XGBoost) : six modèles comparés par backtest.
4. *Restitution* : cette application Streamlit.

**Les modèles de prévision.** La cible est la part de voitures électriques dans le parc des particuliers, par département.
- *Tendance linéaire* : prolonge la pente des cinq dernières années. Sert de référence.
- *Courbe en S* : l'adoption d'une technologie suit une courbe logistique ; on ajuste le logit de la part sur le temps depuis 2016.
- *XGBoost* : apprend sur les 100 départements la variation annuelle du logit à partir du niveau atteint, de la dynamique
  récente et de la structure du parc (hybrides, diesel, taille et croissance du parc, DROM). Prévision récursive.
- *Stock-flux* : chaque année, {fr(100 * M['hypotheses']['taux_sortie'])} % du parc sort (hypothèse) et de nouvelles voitures entrent ;
  on mesure la part d'électriques parmi ces entrées, puis on simule le parc.
- *Consensus* : moyenne de l'approche statistique et de l'approche stock-flux. Meilleur score au backtest.

**Court terme et long terme.** Le backtest ne peut juger les modèles que jusqu'à 5 ans. Pour 2036, les prévisions sont
présentées en trois scénarios du modèle stock-flux, qui respecte la vitesse de renouvellement du parc :
- *Flux figés* : la part d'électriques parmi les voitures entrantes reste au niveau de 2023-2025 ;
- *Tendance des flux* : elle prolonge sa progression moyenne depuis 2019 ;
- *Électrification forte* : elle atteint 100 % en 2035.

**Limites.** Les millésimes 2025 et 2026 sont provisoires. Le taux de sortie du parc est une hypothèse, faute de données
d'âge dans ce fichier. Les prévisions ne tiennent pas compte des changements futurs de prix, d'aides ou de réglementation.
Mayotte est exclue des modèles (couverture incomplète en début de période).
""")
    imp = pd.Series(M["importance_xgboost"]).sort_values()
    noms = {"logit": "Niveau atteint (logit)", "dlogit_1": "Dynamique sur 1 an", "dlogit_3": "Dynamique sur 3 ans",
            "part_hr": "Part d'hybrides rechargeables", "part_hnr": "Part d'hybrides non rechargeables",
            "part_diesel": "Part de diesel", "log_parc": "Taille du parc", "croissance_parc_3": "Croissance du parc",
            "drom": "Département d'outre-mer"}
    fig = px.bar(x=imp.values, y=[noms[i] for i in imp.index], orientation="h",
                 labels={"x": "Importance dans le modèle XGBoost", "y": ""}, color_discrete_sequence=[TEAL])
    fig.update_traces(hovertemplate="%{y} : %{x:.2f}<extra></extra>", marker_line_width=0)
    st.plotly_chart(style(fig, 340), width="stretch")
    st.caption("Code source, SQL et rapport d'audit disponibles sur le dépôt GitHub du projet.")
