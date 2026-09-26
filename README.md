<div align="center">
  <img src=".github/assets/banner.png" alt="AUTOSHORT banner" width="100%" />

  <h1>AUTOSHORT</h1>
  <p>Python pipeline that automatically generates vertical horror-story videos, from script to final video, by chaining several AI APIs.</p>

<p>
  <img src="https://img.shields.io/github/last-commit/BaditSad/AUTOSHORT" alt="last update" />
  <img src="https://img.shields.io/github/languages/top/BaditSad/AUTOSHORT" alt="top language" />
</p>
</div>

<br />

## :notebook_with_decorative_cover: Table of Contents

- [About](#star2-about)
  * [Screenshots](#camera-screenshots)
- [Tech Stack](#space_invader-tech-stack)
- [Pipeline](#gear-pipeline)
- [Environment Variables](#key-environment-variables)
- [Installation](#toolbox-installation)
- [Usage](#eyes-usage)
- [Related Repositories](#link-related-repositories)
- [Contact](#handshake-contact)

## :star2: About

AUTOSHORT is a script that produces, end to end, vertical videos of horror stories told in the first person.
From a single run, it generates the story text, illustrates it, animates it, voices it, subtitles it, then
assembles everything into a video file ready to publish.

The `horror` folder holds the main script (`horror_fr.py`) plus a side script (`test.py`) that automates,
through Selenium, image generation on a third-party site, used occasionally outside the main pipeline.

### :camera: Screenshots

<div align="center">
  <img src=".github/assets/banner.png" alt="AUTOSHORT sample output" width="100%" />
</div>

## :space_invader: Tech Stack

<details>
  <summary>Generative AI</summary>
  <ul>
    <li><a href="https://platform.openai.com/docs">OpenAI GPT</a>: story and metadata generation</li>
    <li><a href="https://platform.openai.com/docs">OpenAI DALL-E 3</a>: scene image generation</li>
    <li><a href="https://platform.openai.com/docs">OpenAI Whisper</a>: audio transcription for subtitles</li>
    <li><a href="https://elevenlabs.io/docs">ElevenLabs</a>: narration voice synthesis</li>
    <li><a href="https://docs.runwayml.com">Runway ML (gen4_turbo)</a>: image-to-video generation</li>
  </ul>
</details>

<details>
  <summary>Media processing and infra</summary>
  <ul>
    <li><a href="https://ffmpeg.org/">ffmpeg</a>: concatenation, subtitling, duration adjustment</li>
    <li><a href="https://github.com/jiaaro/pydub">pydub</a>: narration and music mixing</li>
    <li><a href="https://developers.cloudflare.com/r2">Cloudflare R2</a> (via boto3): intermediate file storage</li>
    <li>Pillow: thumbnail generation</li>
  </ul>
</details>

## :gear: Pipeline

The steps actually implemented in `horror_fr.py`, in order:

1. Story and metadata generation (GPT)
2. Scene image generation (DALL-E 3)
3. Image upload to Cloudflare R2
4. Video generation from the image (Runway, image to video)
5. Narration voice synthesis (ElevenLabs)
6. Audio transcription to produce subtitles (Whisper)
7. Background music preparation and mixing with narration
8. Scene video concatenation
9. Final assembly (video, voice, subtitles)
10. Thumbnail generation

Files produced at each step are kept in `horror/renders`.

## :key: Environment Variables

The script reads a `.env` file placed at the root of the `horror` folder. Expected keys:

`OPENAI_API_KEY`
`ELEVEN_LABS_API_KEY`
`ELEVEN_LABS_VOICE_ID`
`RUNWAY_API_KEY`
`R2_ACCESS_KEY`
`R2_SECRET_KEY`
`R2_BUCKET`
`R2_ENDPOINT`
`R2_PUBLIC_URL`

## :toolbox: Installation

Prerequisites: Python 3, ffmpeg installed on the machine.

```bash
pip install openai elevenlabs runwayml boto3 pillow pydub ffmpeg-python python-dotenv requests
```

## :eyes: Usage

```bash
cd horror
python horror_fr.py
```

The script runs without interaction and produces `final_horror_story.mp4` along with its thumbnail in
`horror/renders`.

## :link: Related Repositories

This project is an earlier, single-theme (horror) version of the AI video generation pipeline. A more
advanced version, focused on multi-account automation and TikTok publishing, lives in
[TRADSHORT](https://github.com/BaditSad/TRADSHORT), which reuses a similar logic (GPT, ElevenLabs, ffmpeg) but
within a full-stack architecture with a job queue and automated publishing.

## :handshake: Contact

Brieuc Dumortier, [LinkedIn](https://www.linkedin.com/in/dumortier-brieuc/), dumortier.contact@gmail.com
