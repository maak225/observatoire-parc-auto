# Observatoire du parc automobile français

**Où en est la transition vers l'électrique, territoire par territoire, et à quoi ressemblera le parc dans 5 à 10 ans ?**

Projet de bout en bout sur données publiques : audit de qualité, modélisation SQL, tableau de bord et prévisions par machine learning.

🔗 **Application en ligne : [lien à ajouter après déploiement](#)**

Réalisé par **Marie Ange Akoua Kouame**, Data Analyst · [LinkedIn](#)

---

## Les chiffres clés

| | |
|---|---|
| Voitures particulières en circulation au 1er janvier 2026 | **39,9 millions** |
| Voitures 100 % électriques | **1,41 million** (3,5 % du parc), contre 0,25 million en 2021 |
| Part des électriques chez les particuliers | **2,8 %**, de 0,5 % en Guyane à 4,2 % dans les Alpes-Maritimes |
| Prévision 2031 (particuliers) | **11 %**, fourchette à 80 % de 5,7 à 16,1 % |
| Scénarios 2036 (particuliers) | **7 % à 36 %** selon l'évolution des achats |

**Le constat principal :** la part d'électriques parmi les voitures qui entrent dans le parc des particuliers a bondi d'environ 1 % en 2019 à 10 % en 2023, puis plafonne depuis. Les modèles qui prolongent simplement la courbe passée surestiment l'avenir ; tenir compte de ce palier change fortement la vision à 10 ans.

## Ce que montre le projet

1. **Audit de la qualité des données** : 14 contrôles selon les dimensions DAMA-DMBOK (complétude, unicité, validité, cohérence, exactitude, actualité), chacun associé à une décision. Exemple : les flottes des loueurs sont immatriculées au siège et déplacent des dizaines de milliers de voitures d'une commune à l'autre d'une année sur l'autre ; les comparaisons territoriales portent donc sur les voitures des particuliers. Rapport complet : [`reports/audit_qualite.md`](reports/audit_qualite.md).
2. **Modélisation SQL** avec DuckDB : 2,1 millions de lignes × 16 années passées en format long (21 millions de lignes non nulles), familles d'énergie, agrégats national, départemental et communal, contrôle de réconciliation avec le fichier brut. Code : [`src/modele.sql`](src/modele.sql).
3. **Prévisions** : six modèles comparés par backtest à origines glissantes (entraînés en 2018, …, 2023 puis confrontés aux années observées ensuite) :
   - tendance linéaire (référence) ;
   - courbe en S (diffusion logistique) ;
   - XGBoost sur panel de 100 départements, prévision récursive ;
   - modèle stock-flux, qui simule le renouvellement du parc ;
   - moyenne courbe en S + XGBoost, et **consensus** avec le stock-flux, retenu (erreur moyenne de 0,36 point, 0,08 point à un an).
4. **Restitution** : application Streamlit avec carte, classements, recherche par commune, prévisions par département et page qualité des données.

## Méthode de prévision

| Horizon | Approche | Pourquoi |
|---|---|---|
| 2027–2031 | Modèle consensus, fourchette issue des erreurs du backtest | Le backtest permet de mesurer la fiabilité jusqu'à 5 ans |
| 2032–2036 | Trois scénarios du modèle stock-flux | Aucun modèle ne peut être validé à 10 ans sur 16 ans d'historique ; le stock-flux respecte la vitesse de renouvellement du parc |

Scénarios sur la part d'électriques parmi les voitures entrant dans le parc : **flux figés** (niveau 2023-2025), **tendance des flux** (progression moyenne depuis 2019), **électrification forte** (100 % en 2035).

## Structure du dépôt

```
├── app/streamlit_app.py      application
├── src/
│   ├── referentiels.py       départements, régions, familles d'énergie
│   ├── 01_audit.py           audit de qualité → data/audit.json, reports/audit_qualite.md
│   ├── modele.sql            modèle de données DuckDB
│   ├── 02_transform.py       exécute le SQL, exporte les agrégats en Parquet
│   └── 03_previsions.py      modèles, backtest, prévisions
├── data/                     agrégats légers utilisés par l'application
├── reports/audit_qualite.md
└── requirements.txt
```

## Reproduire

```bash
pip install -r requirements.txt
# Télécharger le CSV communal du jeu « Parc de véhicules routiers » (data.gouv.fr)
# et l'enregistrer sous data/raw/parc_communal.csv (230 Mo, non versionné)
python src/01_audit.py
python src/02_transform.py
python src/03_previsions.py
streamlit run app/streamlit_app.py
```

## Limites

- Les millésimes 2025 et 2026 sont provisoires selon le SDES et seront révisés.
- Le taux de sortie du parc (5 % par an, 1 % pour les électriques) est une hypothèse, le fichier ne contenant pas l'âge des véhicules.
- Les prévisions n'intègrent pas les évolutions futures de prix, d'aides ou de réglementation.
- Mayotte est exclue des modèles (couverture incomplète en début de période).

## Sources

- SDES, [Parc de véhicules routiers](https://www.data.gouv.fr/datasets/parc-de-vehicules-routiers), données communales au 1er janvier, Licence Ouverte.
- SDES, *Méthodologie pour l'estimation des parcs de véhicules et des distances parcourues*, document de travail n° 67, mars 2024.
- Contours des départements : [france-geojson](https://github.com/gregoiredavid/france-geojson) (version simplifiée).

**Outils :** Python, DuckDB (SQL), pandas, scikit-learn, XGBoost, Plotly, Streamlit.
