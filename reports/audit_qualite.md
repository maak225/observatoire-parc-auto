# Audit de la qualité des données

Fichier : `parc_communal.csv` · 2 128 015 lignes · 35 017 codes commune · 2011–2026

| Dimension | Contrôle | Constat | Impact | Décision |
|---|---|---|---|---|
| Complétude | Noms de commune manquants | 104 lignes sans nom, toutes sur des codes fictifs de DROM (97100, 97200, 97300, 97400, 97600). | Faible : ces codes ne correspondent à aucune commune réelle. | Lignes exclues des analyses communales, conservées dans les totaux nationaux. |
| Complétude | Valeurs de parc manquantes | 0 valeur manquante sur les 16 colonnes annuelles. | Aucun. | Aucune correction nécessaire. |
| Complétude | Lignes entièrement à zéro | 20 486 lignes (1,0 %) valent 0 sur toutes les années. | Aucun sur les totaux, alourdit le fichier. | Supprimées lors du passage en format long. |
| Unicité | Doublons sur la clé métier | 0 doublon sur la clé commune × carburant × Crit'Air × statut × catégorie. | Aucun. | Clé validée. |
| Unicité | Un code, plusieurs noms | 0 code commune associé à plusieurs libellés. | Aucun. | Référentiel cohérent. |
| Validité | Codes commune fictifs | Code 00000 « Inconnu » (1 087 véhicules en 2026) et codes 97x00 sans commune (535 véhicules). | Très faible (< 0,01 % du parc). | Exclus des analyses territoriales. |
| Validité | Codes « ville entière » de Paris, Lyon et Marseille | Les véhicules sont rattachés aux arrondissements, mais les codes de la ville entière subsistent avec un reliquat (Paris : 6 948, Lyon : 262, Marseille : 91 véhicules en 2026). Sur un si petit reliquat, les parts calculées sont aberrantes (12 % d'électriques pour « Paris »). | Fort sur les classements communaux. | Exclus des analyses communales, conservés dans les totaux départementaux. |
| Validité | Effectifs négatifs | 0 valeur négative. | Aucun. | Aucune correction. |
| Validité | Libellé mal orthographié | La modalité « Professionel » (sic) concerne 836 056 lignes. | Cosmétique. | Renommée « Professionnel ». |
| Cohérence | Carburant incompatible avec la vignette Crit'Air | 369 lignes de voitures (ex. électrique non classée Crit'Air E), soit 1 223 véhicules-années sur l'ensemble de la période. | Négligeable (< 0,001 %). | Conservées ; le carburant fait foi pour le regroupement par énergie. |
| Cohérence | Carburant inconnu | 2 058 voitures sans carburant renseigné en 2026. | Négligeable. | Regroupées dans « Inconnu », exclues des parts d'énergie. |
| Exactitude | Sauts annuels de plus de 30 % dans une commune | 602 sauts sur les voitures de professionnels contre 137 sur celles des particuliers. Les flottes de loueurs et de sociétés sont immatriculées au siège et changent de commune en bloc (Beauvais : 61 337 en 2020, 35 216 en 2021, 6 773 en 2026 ; Lesquin : 3 607 en 2020, 3 280 en 2021, 24 255 en 2026). | Fort au niveau communal : fausse les comparaisons de territoires. | Analyses territoriales et prévisions calculées sur les voitures des particuliers. |
| Exactitude | Couverture incomplète à Mayotte | Le parc de voitures de Mayotte passe de 6 645 en 2011 à 29 095 en 2026 : la montée en charge de l'enregistrement se mêle à la croissance réelle. | Série non comparable dans le temps. | Mayotte affichée mais exclue de l'entraînement des modèles. |
| Actualité | Millésimes provisoires | Selon la note méthodologique du SDES, les parcs ne sont définitifs qu'après deux millésimes : 2025 et 2026 sont provisoires et seront révisés. Les années 2019 à 2022 ont aussi été estimées avec une méthode adaptée à la crise sanitaire. | Moyen sur les dernières années. | Années signalées dans l'application ; le backtest en tient compte. |
