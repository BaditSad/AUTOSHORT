<div align="center">
  <h1>AUTOSHORT</h1>
  <p>Pipeline Python qui génère automatiquement des vidéos verticales d'histoires d'horreur, du script à la vidéo finale, en enchaînant plusieurs API d'IA.</p>

<p>
  <img src="https://img.shields.io/github/last-commit/BaditSad/AUTOSHORT" alt="last update" />
  <img src="https://img.shields.io/github/languages/top/BaditSad/AUTOSHORT" alt="top language" />
</p>
</div>

<br />

## Table des matières

- [A propos](#a-propos)
- [Stack technique](#stack-technique)
- [Pipeline](#pipeline)
- [Variables d'environnement](#variables-denvironnement)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Dépôts liés](#depots-lies)
- [Contact](#contact)

## A propos

AUTOSHORT est un script qui produit, de bout en bout, des vidéos verticales d'histoires d'horreur racontées à la première personne. A partir d'un simple lancement, il génère le texte de l'histoire, l'illustre, l'anime, la voix, la sous-titre puis assemble le tout en un fichier vidéo prêt à publier.

Le dossier `horror` contient le script principal (`horror_fr.py`) ainsi qu'un script annexe (`test.py`) qui automatise, via Selenium, la génération d'une image sur un site tiers, utilisé ponctuellement en dehors du pipeline principal.

## Stack technique

<details>
  <summary>IA générative</summary>
  <ul>
    <li><a href="https://platform.openai.com/docs">OpenAI GPT</a> : génération de l'histoire et des métadonnées</li>
    <li><a href="https://platform.openai.com/docs">OpenAI DALL-E 3</a> : génération de l'image de la scène</li>
    <li><a href="https://platform.openai.com/docs">OpenAI Whisper</a> : transcription audio pour les sous-titres</li>
    <li><a href="https://elevenlabs.io/docs">ElevenLabs</a> : synthèse vocale de la narration</li>
    <li><a href="https://docs.runwayml.com">Runway ML (gen4_turbo)</a> : génération vidéo image vers vidéo</li>
  </ul>
</details>

<details>
  <summary>Traitement média et infra</summary>
  <ul>
    <li><a href="https://ffmpeg.org/">ffmpeg</a> : concaténation, sous-titrage, ajustement de durée</li>
    <li><a href="https://github.com/jiaaro/pydub">pydub</a> : mixage narration et musique</li>
    <li><a href="https://developers.cloudflare.com/r2">Cloudflare R2</a> (via boto3) : stockage des fichiers intermédiaires</li>
    <li>Pillow : génération de la miniature</li>
  </ul>
</details>

## Pipeline

Les étapes réellement implémentées dans `horror_fr.py`, dans l'ordre :

1. Génération de l'histoire et des métadonnées (GPT)
2. Génération de l'image de la scène (DALL-E 3)
3. Upload de l'image sur Cloudflare R2
4. Génération de la vidéo à partir de l'image (Runway, image vers vidéo)
5. Synthèse vocale de la narration (ElevenLabs)
6. Transcription de l'audio pour produire les sous-titres (Whisper)
7. Préparation et mixage de la musique de fond avec la narration
8. Concaténation des vidéos de scène
9. Assemblage final (vidéo, voix, sous-titres)
10. Génération de la miniature

Les fichiers produits à chaque étape sont conservés dans `horror/renders`.

## Variables d'environnement

Le script lit un fichier `.env` placé à la racine du dossier `horror`. Clés attendues :

`OPENAI_API_KEY`
`ELEVEN_LABS_API_KEY`
`ELEVEN_LABS_VOICE_ID`
`RUNWAY_API_KEY`
`R2_ACCESS_KEY`
`R2_SECRET_KEY`
`R2_BUCKET`
`R2_ENDPOINT`
`R2_PUBLIC_URL`

## Installation

Prérequis : Python 3, ffmpeg installé sur la machine.

```bash
pip install openai elevenlabs runwayml boto3 pillow pydub ffmpeg-python python-dotenv requests
```

## Utilisation

```bash
cd horror
python horror_fr.py
```

Le script tourne sans interaction et produit `final_horror_story.mp4` ainsi que la miniature associée dans `horror/renders`.

## Dépôts liés

Ce projet est une version antérieure et centrée sur un thème unique (horreur) du pipeline de génération vidéo par IA. Une version plus aboutie, orientée automatisation multi-comptes et publication TikTok, existe dans [TRADSHORT](https://github.com/BaditSad/TRADSHORT), qui reprend une logique similaire (GPT, ElevenLabs, ffmpeg) mais dans une architecture full-stack avec file d'attente et publication automatisée.

## Contact

Brieuc Dumortier, [LinkedIn](https://www.linkedin.com/in/dumortier-brieuc/), dumortier.contact@gmail.com
