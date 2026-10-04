"""Étape 1 : audit de la qualité des données du parc communal (SDES).

Chaque contrôle est rattaché à une dimension de la qualité des données (DAMA-DMBOK) :
complétude, unicité, validité, cohérence, exactitude (plausibilité), actualité.
Sorties : data/audit.json (lu par l'application) et reports/audit_qualite.md.
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "parc_communal.csv"
YEARS = [f"PARC_{y}" for y in range(2011, 2027)]
TOTAL = " + ".join(YEARS)


def pct(a, b):
    return f"{100 * a / b:.1f}".replace(".", ",")


def fmt(n):
    """Nombre au format français : espace comme séparateur de milliers."""
    return f"{n:,.0f}".replace(",", "\u202f")


def main():
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE brut AS
        SELECT * FROM read_csv('{RAW}', delim=';', header=true, types={{'COMMUNE_CODE': 'VARCHAR'}})
    """)
    one = lambda sql: con.execute(sql).fetchone()[0]

    n_lignes = one("SELECT count(*) FROM brut")
    n_communes = one("SELECT count(DISTINCT COMMUNE_CODE) FROM brut")
    parc_2026 = one("SELECT sum(PARC_2026) FROM brut")

    controles = []

    def ajoute(dimension, nom, constat, valeur, impact, decision):
        controles.append(dict(dimension=dimension, controle=nom, constat=constat,
                              valeur=valeur, impact=impact, decision=decision))

    # Complétude
    noms_vides = one("SELECT count(*) FROM brut WHERE COMMUNE_NOM IS NULL")
    codes_noms_vides = [r[0] for r in con.execute(
        "SELECT DISTINCT COMMUNE_CODE FROM brut WHERE COMMUNE_NOM IS NULL ORDER BY 1").fetchall()]
    ajoute("Complétude", "Noms de commune manquants",
           f"{noms_vides} lignes sans nom, toutes sur des codes fictifs de DROM ({', '.join(codes_noms_vides)}).",
           noms_vides, "Faible : ces codes ne correspondent à aucune commune réelle.",
           "Lignes exclues des analyses communales, conservées dans les totaux nationaux.")
    nulls_parc = one("SELECT " + " + ".join([f"(count(*) - count({c}))" for c in YEARS]) + " FROM brut")
    ajoute("Complétude", "Valeurs de parc manquantes",
           f"{nulls_parc} valeur manquante sur les 16 colonnes annuelles.",
           nulls_parc, "Aucun.", "Aucune correction nécessaire.")
    vides = one(f"SELECT count(*) FROM brut WHERE ({TOTAL}) = 0")
    ajoute("Complétude", "Lignes entièrement à zéro",
           f"{fmt(vides)} lignes ({pct(vides, n_lignes)} %) valent 0 sur toutes les années.",
           vides, "Aucun sur les totaux, alourdit le fichier.",
           "Supprimées lors du passage en format long.")

    # Unicité
    doublons = one("""SELECT count(*) FROM (SELECT 1 FROM brut
        GROUP BY COMMUNE_CODE, CARBURANT, CRIT_AIR, STATUT_UTILISATEUR, GROUPE, CATEGORIE HAVING count(*) > 1)""")
    ajoute("Unicité", "Doublons sur la clé métier",
           f"{doublons} doublon sur la clé commune × carburant × Crit'Air × statut × catégorie.",
           doublons, "Aucun.", "Clé validée.")
    multi_noms = one("SELECT count(*) FROM (SELECT COMMUNE_CODE FROM brut GROUP BY 1 HAVING count(DISTINCT COMMUNE_NOM) > 1)")
    ajoute("Unicité", "Un code, plusieurs noms",
           f"{multi_noms} code commune associé à plusieurs libellés.", multi_noms, "Aucun.", "Référentiel cohérent.")

    # Validité
    inconnu = one("SELECT sum(PARC_2026) FROM brut WHERE COMMUNE_CODE = '00000'")
    pseudo_drom = one("SELECT sum(PARC_2026) FROM brut WHERE COMMUNE_CODE IN ('97100','97200','97300','97400','97600')")
    ajoute("Validité", "Codes commune fictifs",
           f"Code 00000 « Inconnu » ({fmt(inconnu)} véhicules en 2026) et codes 97x00 sans commune "
           f"({fmt(pseudo_drom)} véhicules).",
           int(inconnu + pseudo_drom), "Très faible (< 0,01 % du parc).",
           "Exclus des analyses territoriales.")
    residuels = con.execute("""SELECT COMMUNE_NOM, sum(PARC_2026)::int FROM brut
        WHERE COMMUNE_CODE IN ('75056', '69123', '13055') GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    ajoute("Validité", "Codes « ville entière » de Paris, Lyon et Marseille",
           "Les véhicules sont rattachés aux arrondissements, mais les codes de la ville entière subsistent avec "
           "un reliquat (" + ", ".join(f"{n} : {fmt(v)}" for n, v in residuels) + " véhicules en 2026). "
           "Sur un si petit reliquat, les parts calculées sont aberrantes (12 % d'électriques pour « Paris »).",
           sum(v for _, v in residuels), "Fort sur les classements communaux.",
           "Exclus des analyses communales, conservés dans les totaux départementaux.")
    negatifs = one("SELECT " + " + ".join([f"sum(({c} < 0)::int)" for c in YEARS]) + " FROM brut")
    ajoute("Validité", "Effectifs négatifs", f"{negatifs} valeur négative.", negatifs, "Aucun.", "Aucune correction.")
    typo = one("SELECT count(*) FROM brut WHERE STATUT_UTILISATEUR = 'Professionel'")
    ajoute("Validité", "Libellé mal orthographié",
           f"La modalité « Professionel » (sic) concerne {fmt(typo)} lignes.",
           typo, "Cosmétique.", "Renommée « Professionnel ».")

    # Cohérence
    incoh = con.execute(f"""
        SELECT count(*), sum({TOTAL}) FROM brut WHERE GROUPE = 'VP' AND (
          (CARBURANT IN ('Electrique','Hydrogène et autre ZE') AND CRIT_AIR <> 'Crit''Air E')
          OR (CARBURANT NOT IN ('Electrique','Hydrogène et autre ZE') AND CRIT_AIR = 'Crit''Air E')
          OR (CARBURANT LIKE '% HR' AND CRIT_AIR <> 'Crit''Air 1')
          OR (CARBURANT = 'Essence' AND CRIT_AIR IN ('Crit''Air 4','Crit''Air 5')))
    """).fetchone()
    ajoute("Cohérence", "Carburant incompatible avec la vignette Crit'Air",
           f"{incoh[0]} lignes de voitures (ex. électrique non classée Crit'Air E), "
           f"soit {fmt(incoh[1])} véhicules-années sur l'ensemble de la période.",
           int(incoh[0]), "Négligeable (< 0,001 %).",
           "Conservées ; le carburant fait foi pour le regroupement par énergie.")
    carb_inconnu = one("SELECT sum(PARC_2026) FROM brut WHERE GROUPE = 'VP' AND CARBURANT = 'Inconnu'")
    ajoute("Cohérence", "Carburant inconnu",
           f"{fmt(carb_inconnu)} voitures sans carburant renseigné en 2026.",
           int(carb_inconnu), "Négligeable.", "Regroupées dans « Inconnu », exclues des parts d'énergie.")

    # Exactitude / plausibilité
    sauts = con.execute("""
        WITH vp AS (
          SELECT COMMUNE_CODE code, STATUT_UTILISATEUR statut, cast(replace(annee, 'PARC_', '') AS int) annee, sum(parc) parc
          FROM (UNPIVOT (SELECT * FROM brut WHERE GROUPE = 'VP') ON COLUMNS('PARC_.*') INTO NAME annee VALUE parc)
          GROUP BY ALL),
        t AS (SELECT *, lag(parc) OVER (PARTITION BY code, statut ORDER BY annee) prev FROM vp)
        SELECT statut, count(*) FROM t WHERE prev >= 200 AND abs(parc - prev) / prev > 0.3 GROUP BY 1
    """).fetchall()
    sauts = {s: n for s, n in sauts}
    exemples = con.execute("""
        SELECT COMMUNE_NOM, sum(PARC_2020)::int, sum(PARC_2021)::int, sum(PARC_2026)::int FROM brut
        WHERE GROUPE = 'VP' AND STATUT_UTILISATEUR = 'Professionel' AND COMMUNE_CODE IN ('60057', '59343')
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    ex_txt = " ; ".join(f"{n} : {fmt(a)} en 2020, {fmt(b)} en 2021, {fmt(c)} en 2026" for n, a, b, c in exemples)
    ajoute("Exactitude", "Sauts annuels de plus de 30 % dans une commune",
           f"{sauts.get('Professionel', 0)} sauts sur les voitures de professionnels contre "
           f"{sauts.get('Particulier', 0)} sur celles des particuliers. Les flottes de loueurs et de "
           f"sociétés sont immatriculées au siège et changent de commune en bloc ({ex_txt}).",
           int(sum(sauts.values())), "Fort au niveau communal : fausse les comparaisons de territoires.",
           "Analyses territoriales et prévisions calculées sur les voitures des particuliers.")
    mayotte = con.execute("SELECT sum(PARC_2011)::int, sum(PARC_2026)::int FROM brut WHERE GROUPE = 'VP' AND COMMUNE_CODE LIKE '976%'").fetchone()
    ajoute("Exactitude", "Couverture incomplète à Mayotte",
           f"Le parc de voitures de Mayotte passe de {fmt(mayotte[0])} en 2011 à {fmt(mayotte[1])} en 2026 : "
           f"la montée en charge de l'enregistrement se mêle à la croissance réelle.",
           mayotte[0], "Série non comparable dans le temps.",
           "Mayotte affichée mais exclue de l'entraînement des modèles.")

    # Actualité
    ajoute("Actualité", "Millésimes provisoires",
           "Selon la note méthodologique du SDES, les parcs ne sont définitifs qu'après deux millésimes : "
           "2025 et 2026 sont provisoires et seront révisés. Les années 2019 à 2022 ont aussi été "
           "estimées avec une méthode adaptée à la crise sanitaire.",
           2, "Moyen sur les dernières années.",
           "Années signalées dans l'application ; le backtest en tient compte.")

    resume = dict(fichier=RAW.name, lignes=n_lignes, communes=n_communes, parc_2026=int(parc_2026),
                  colonnes=7 + len(YEARS), annees="2011–2026", controles=controles)
    (ROOT / "data" / "audit.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2))

    md = ["# Audit de la qualité des données", "",
          f"Fichier : `{RAW.name}` · {fmt(n_lignes)} lignes · {fmt(n_communes)} codes commune · 2011–2026", "",
          "| Dimension | Contrôle | Constat | Impact | Décision |", "|---|---|---|---|---|"]
    for c in controles:
        md.append(f"| {c['dimension']} | {c['controle']} | {c['constat']} | {c['impact']} | {c['decision']} |")
    (ROOT / "reports" / "audit_qualite.md").write_text("\n".join(md) + "\n")
    print(f"{len(controles)} contrôles écrits.")


if __name__ == "__main__":
    main()
