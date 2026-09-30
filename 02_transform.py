"""Étape 2 : transformation et modélisation SQL avec DuckDB.

Exécute src/modele.sql puis exporte les tables agrégées en Parquet dans data/.
Ces fichiers légers (quelques Mo) sont ceux qu'utilise l'application.
"""
from pathlib import Path

import duckdb

from referentiels import DEP_TO_REGION, DEPARTEMENTS, ENERGIE_SQL

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "parc_communal.csv"
OUT = ROOT / "data"


def main():
    con = duckdb.connect(str(ROOT / "data" / "raw" / "parc.duckdb"))
    sql = (ROOT / "src" / "modele.sql").read_text().format(raw=RAW, energie=ENERGIE_SQL.strip())
    con.execute(sql)

    ref = [(c, DEPARTEMENTS.get(c, c), DEP_TO_REGION.get(c, "Autre")) for c in DEPARTEMENTS]
    con.execute("CREATE OR REPLACE TABLE ref_dep (code_dep VARCHAR, nom_dep VARCHAR, region VARCHAR)")
    con.executemany("INSERT INTO ref_dep VALUES (?, ?, ?)", ref)

    exports = {
        "national_energie": "SELECT * FROM national_energie ORDER BY annee, statut, energie",
        "national_critair": "SELECT * FROM national_critair ORDER BY annee, crit_air",
        "dep_energie": """SELECT d.*, r.nom_dep, r.region FROM dep_energie d
                          JOIN ref_dep r USING (code_dep) ORDER BY code_dep, annee""",
        "communes": """SELECT c.*, r.nom_dep, r.region FROM communes c
                       JOIN ref_dep r USING (code_dep) ORDER BY code_commune""",
    }
    for name, query in exports.items():
        path = OUT / f"{name}.parquet"
        con.execute(f"COPY ({query}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        n = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()[0]
        print(f"{name:18s} {n:>8} lignes  {path.stat().st_size / 1e6:.2f} Mo")

    # Contrôle de réconciliation : le total national doit égaler le fichier brut
    brut = con.execute(f"SELECT sum(PARC_2026) FROM read_csv('{RAW}', delim=';', header=true) WHERE GROUPE = 'VP'").fetchone()[0]
    modele = con.execute("SELECT sum(parc) FROM national_energie WHERE annee = 2026").fetchone()[0]
    assert brut == modele, (brut, modele)
    print(f"Réconciliation OK : {modele:,} voitures au 1er janvier 2026".replace(",", " "))


if __name__ == "__main__":
    main()
