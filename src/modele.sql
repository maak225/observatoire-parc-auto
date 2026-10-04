-- Étape 2 : modèle de données (DuckDB)
-- Source : parc communal du SDES au 1er janvier, 2011-2026.
-- Le chemin du fichier brut et la règle de regroupement des énergies sont injectés par 02_transform.py.

-- 1. Table de faits en format long, lignes vides retirées, libellés corrigés
CREATE OR REPLACE TABLE fait_parc AS
SELECT
    COMMUNE_CODE                                            AS code_commune,
    COMMUNE_NOM                                             AS nom_commune,
    CASE WHEN COMMUNE_CODE LIKE '97%' THEN substr(COMMUNE_CODE, 1, 3)
         ELSE substr(COMMUNE_CODE, 1, 2) END                AS code_dep,
    CASE WHEN STATUT_UTILISATEUR = 'Professionel' THEN 'Professionnel'
         ELSE STATUT_UTILISATEUR END                        AS statut,
    GROUPE                                                  AS groupe,
    CATEGORIE                                               AS categorie,
    CARBURANT                                               AS carburant,
    {energie}                                               AS energie,
    CRIT_AIR                                                AS crit_air,
    CAST(replace(annee, 'PARC_', '') AS INTEGER)            AS annee,
    parc
FROM (
    UNPIVOT (SELECT * FROM read_csv('{raw}', delim=';', header=true, types={{'COMMUNE_CODE': 'VARCHAR'}}))
    ON COLUMNS('PARC_.*') INTO NAME annee VALUE parc
)
WHERE parc > 0;

-- 2. Validité territoriale : codes fictifs et codes « ville entière » de Paris, Lyon et Marseille
--    (résiduels, les véhicules étant rattachés aux arrondissements) exclus des analyses communales
CREATE OR REPLACE VIEW fait_vp_valide AS
SELECT * FROM fait_parc
WHERE groupe = 'VP'
  AND code_commune <> '00000'
  AND code_commune NOT IN ('97100', '97200', '97300', '97400', '97600');

CREATE OR REPLACE VIEW fait_vp_commune AS
SELECT * FROM fait_vp_valide
WHERE code_commune NOT IN ('75056', '69123', '13055');

-- 3. Agrégats nationaux (toutes communes, y compris codes inconnus)
CREATE OR REPLACE TABLE national_energie AS
SELECT annee, statut, energie, sum(parc)::BIGINT AS parc
FROM fait_parc WHERE groupe = 'VP'
GROUP BY ALL;

CREATE OR REPLACE TABLE national_critair AS
SELECT annee, crit_air, sum(parc)::BIGINT AS parc
FROM fait_parc WHERE groupe = 'VP'
GROUP BY ALL;

-- 4. Agrégats départementaux par énergie et statut
CREATE OR REPLACE TABLE dep_energie AS
SELECT code_dep, annee, statut, energie, sum(parc)::BIGINT AS parc
FROM fait_vp_valide
GROUP BY ALL;

-- 5. Profil des communes (voitures des particuliers) : 2021 et 2026
CREATE OR REPLACE TABLE communes AS
WITH base AS (
    SELECT code_commune, any_value(nom_commune) AS nom_commune, any_value(code_dep) AS code_dep,
        sum(parc) FILTER (annee = 2026)                                                   AS parc_2026,
        sum(parc) FILTER (annee = 2026 AND energie = 'Électrique')                        AS elec_2026,
        sum(parc) FILTER (annee = 2026 AND energie IN ('Électrique', 'Hybride rechargeable')) AS rech_2026,
        sum(parc) FILTER (annee = 2026 AND crit_air IN ('Crit''Air 3', 'Crit''Air 4', 'Crit''Air 5', 'Non classé')) AS ancien_2026,
        sum(parc) FILTER (annee = 2021)                                                   AS parc_2021,
        sum(parc) FILTER (annee = 2021 AND energie = 'Électrique')                        AS elec_2021
    FROM fait_vp_commune
    WHERE statut = 'Particulier'
    GROUP BY code_commune
)
SELECT code_commune, nom_commune, code_dep,
    coalesce(parc_2026, 0)::BIGINT                                AS parc_2026,
    coalesce(elec_2026, 0)::BIGINT                                AS elec_2026,
    round(100.0 * coalesce(elec_2026, 0) / nullif(parc_2026, 0), 2)   AS part_elec_2026,
    round(100.0 * coalesce(rech_2026, 0) / nullif(parc_2026, 0), 2)   AS part_rechargeable_2026,
    round(100.0 * coalesce(ancien_2026, 0) / nullif(parc_2026, 0), 2) AS part_crit3plus_2026,
    round(100.0 * coalesce(elec_2021, 0) / nullif(parc_2021, 0), 2)   AS part_elec_2021
FROM base
WHERE coalesce(parc_2026, 0) > 0;
