Application de consultation des horaires de piscine de la ville de Paris.

L'application est divisée en deux parties :
- Une interface utilisateur pour consulter les horaires publiée sur github pages et basée sur leaflet / openstreetmap.
- Un flow pour récupérer les horaires qui est lancé chaque jour via une github action pour mettre à jour les horaires.

Un repertoire de setup correspond aux scripts/prompts pour créer la base géolocalisée des piscines de Paris.

## Tester localement

Pour tester l'application localement, vous pouvez lancer un serveur HTTP simple avec Python :

```bash
python3 -m http.server
```

Ensuite, ouvrez votre navigateur à l'adresse `http://localhost:8000`. 