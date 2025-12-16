import os
import time
import logging
import requests
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import base64
from openai import OpenAI
import shutil
import boto3
from botocore.client import Config
from runwayml import RunwayML, TaskFailedError
from PIL import Image, ImageDraw, ImageFont
import re
import ffmpeg
import random
import math

# ======================
# LOGGING
# ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")
logging.getLogger("httpx").setLevel(logging.WARNING)

def log_step(name):
    """Décorateur pour logger début/fin/erreur d'une étape."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            log.info(f"▶️  {name} | DÉBUT")
            try:
                result = fn(*args, **kwargs)
                log.info(f"✅ {name} | OK")
                return result
            except Exception as e:
                log.exception(f"❌ {name} | ÉCHEC : {e}")
                raise
        return wrapper
    return decorator

# ======================
# 0. CONFIG
# ======================
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
ELEVEN_LABS_API_KEY= os.getenv("ELEVEN_LABS_API_KEY")
RUNWAY_API_KEY     = os.getenv("RUNWAY_API_KEY")

R2_ACCESS_KEY  = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY  = os.getenv("R2_SECRET_KEY")
R2_BUCKET      = os.getenv("R2_BUCKET")
R2_ENDPOINT    = os.getenv("R2_ENDPOINT")
R2_PUBLIC_URL  = os.getenv("R2_PUBLIC_URL", "https://pub-9279aa534411405f9ce46f24a059516a.r2.dev").rstrip("/")

ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID", "EiNlNiXeDU1pqqOPrYMO")

for key, val in [
    ("OPENAI_API_KEY", OPENAI_API_KEY),
    ("ELEVEN_LABS_API_KEY", ELEVEN_LABS_API_KEY),
    ("RUNWAY_API_KEY", RUNWAY_API_KEY),
    ("R2_ACCESS_KEY", R2_ACCESS_KEY),
    ("R2_SECRET_KEY", R2_SECRET_KEY),
    ("R2_BUCKET", R2_BUCKET),
    ("R2_ENDPOINT", R2_ENDPOINT),
    ("R2_PUBLIC_URL", R2_PUBLIC_URL),
]:
    if not val:
        raise ValueError(f"❌ Config manquante: {key}")

client = OpenAI(api_key=OPENAI_API_KEY)
runway_client = RunwayML(api_key=RUNWAY_API_KEY)

s3_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=Config(signature_version="s3v4"),
)

RENDERS_DIR = Path(__file__).resolve().parent / "renders"
RENDERS_DIR.mkdir(exist_ok=True)

def clean_renders():
    log.info("🧹 Nettoyage du dossier 'renders'")
    for file in RENDERS_DIR.iterdir():
        if file.is_file():
            file.unlink()
        elif file.is_dir():
            shutil.rmtree(file)

# ======================
# UTILS
# ======================
def http_get_bytes(url, timeout=30, retries=3, backoff=2):
    for attempt in range(1, retries+1):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.content
            log.warning(f"GET {url} -> {resp.status_code} (tentative {attempt}/{retries})")
        except Exception as e:
            log.warning(f"GET {url} échoué ({e}) (tentative {attempt}/{retries})")
        time.sleep(backoff * attempt)
    raise RuntimeError(f"Échec téléchargement après {retries} tentatives")

def verify_url_ok(url, retries=5, delay=2):
    for i in range(retries):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return True
            log.warning(f"URL non prête (HTTP {r.status_code}) | retry {i+1}/{retries}")
        except Exception as e:
            log.warning(f"URL inaccessible ({e}) | retry {i+1}/{retries}")
        time.sleep(delay)
    return False

def adjust_video_duration(input_path: str, output_path: str, target_duration: int):
    """Ajuste une vidéo Runway (5 ou 10s) à la durée souhaitée."""
    probe = ffmpeg.probe(input_path)
    duration = float(probe["format"]["duration"])

    if abs(duration - target_duration) < 0.1:
        shutil.copy(input_path, output_path)
        return output_path

    if duration > target_duration:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-t", str(target_duration),
            "-c", "copy", output_path
        ], check=True)
    else:
        speed = duration / target_duration
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-filter:v", f"setpts={1/speed}*PTS",
            "-an", output_path
        ], check=True)

    return output_path

def split_text_into_chunks(text, max_words=5):
    words = text.split()
    return [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]

def random_zoompan():
    speed = round(random.uniform(0.0008, 0.0018), 4)
    max_zoom = round(random.uniform(1.2, 1.6), 2)
    direction = random.choice(["in", "out"])
    if direction == "out":
        return f"zoompan=z='if(lte(zoom,{max_zoom}),zoom-{speed},zoom)':d=125,scale=720:1280"
    else:
        return f"zoompan=z='min(zoom+{speed},{max_zoom})':d=125,scale=720:1280"

def prepare_background_music(music_path, narration_duration, output_path):
    """Prend un extrait aléatoire de la musique avec la durée exacte de la narration"""
    # Durée totale de la musique
    probe = ffmpeg.probe(str(music_path))
    music_duration = float(probe["format"]["duration"])

    if narration_duration > music_duration:
        raise RuntimeError("La musique est plus courte que la narration.")

    # Point de départ aléatoire
    start_time = random.uniform(0, music_duration - narration_duration)
    log.info(f"🎵 Musique de fond : extrait {narration_duration:.2f}s à partir de {start_time:.2f}s")

    # Découper et baisser le volume (0.3 = 30%)
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-t", str(narration_duration),
        "-i", str(music_path),
        "-filter:a", "volume=0.3",
        str(output_path)
    ], check=True)

    return output_path

@log_step("Mixage narration + musique de fond")
def mix_audio(narration_path, music_path, output_path):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(narration_path),
        "-i", str(music_path),
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2:weights=1 1.5",
        "-c:a", "aac",
        str(output_path)
    ], check=True)
    return output_path

# ======================
# 1. Génération histoire + métadonnées
# ======================
@log_step("Génération histoire + métadonnées")
def generate_story_and_meta():
    prompt = (
        "Donne-moi :\n"
        "1️⃣ Une histoire VRAIE, troublante, mystérieuse et actuelle en france d’environ 1 minute de narration (~120-150 mots). "
        "Style : narration peusante, comme un documentaire. "
        "⚠️ Évite absolument les mots sang, gore, violence, sexe explicite.\n\n"
        "2️⃣ Un titre accrocheur pour TikTok/YouTube Shorts.\n"
        "3️⃣ Une description optimisée (2 phrases).\n"
        "4️⃣ 10 hashtags pertinents.\n\n"
        "⚠️ Formate ta réponse EXACTEMENT ainsi :\n"
        "HISTOIRE:\n"
        "<ton histoire>\n\n"
        "TITRE:\n"
        "<ton titre>\n\n"
        "DESCRIPTION:\n"
        "<ta description>\n\n"
        "HASHTAGS:\n"
        "#tag1 #tag2 #tag3 ..."
    )
    
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.8,
    )
    text = resp.choices[0].message.content.strip()

    parts = re.split(r"(HISTOIRE:|TITRE:|DESCRIPTION:|HASHTAGS:)", text)
    meta = {}
    current = None
    for p in parts:
        p = p.strip()
        if p in ["HISTOIRE:", "TITRE:", "DESCRIPTION:", "HASHTAGS:"]:
            current = p[:-1].lower()
            meta[current] = ""
        elif current:
            meta[current] += p + " "

    for k in meta:
        meta[k] = meta[k].strip()

    return meta

# ======================
# 2. Synthèse vocale
# ======================
@log_step("Synthèse vocale")
def generate_voice(story_text, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_LABS_VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_LABS_API_KEY, "Content-Type": "application/json"}
    data = {"text": story_text, "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}}

    resp = requests.post(url, headers=headers, json=data, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Erreur ElevenLabs: {resp.text}")

    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path

# ======================
# 3. Transcription Whisper (durées réelles + sous-titres)
# ======================
@log_step("Transcription audio (Whisper)")
def transcribe_audio(audio_path):
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    # Segments bruts (pour vidéos/images)
    scene_segments = []
    # Segments découpés en petits morceaux (pour sous-titres)
    subtitle_segments = []

    for seg in resp.segments:
        start = seg.start
        end = seg.end
        text = seg.text.strip()
        scene_segments.append((start, end, text))  # une scène entière

        # Sous-titres (chunks de 5 mots)
        text_chunks = split_text_into_chunks(text, max_words=5)
        duration = (end - start) / len(text_chunks)
        for i, chunk in enumerate(text_chunks):
            chunk_start = start + i * duration
            chunk_end = chunk_start + duration
            subtitle_segments.append((chunk_start, chunk_end, chunk))

    log.info(f"Transcription ok → {len(scene_segments)} scènes, {len(subtitle_segments)} sous-titres")
    return scene_segments, subtitle_segments


# ======================
# 4. Génération image
# ======================
@log_step("Génération image (DALL·E 3 via OpenAI)")
def generate_image(prompt, output_path):
    full_prompt = (
        f"Illustration réaliste et cinématographique de la scène suivante : {prompt}. "
        f"Style dérangeant, ambiance peusante, atmosphère cinématique. "
        f"⚠️ Sans texte, sans sous-titres par dessus l'image."
    )
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=full_prompt,
        size="1024x1536",
    )

    if not resp.data:
        raise RuntimeError("❌ L’API OpenAI n’a rien renvoyé.")

    if hasattr(resp.data[0], "url") and resp.data[0].url:
        img_url = resp.data[0].url
        img_data = requests.get(img_url, timeout=60).content
    elif hasattr(resp.data[0], "b64_json") and resp.data[0].b64_json:
        img_data = base64.b64decode(resp.data[0].b64_json)
    else:
        raise RuntimeError("❌ L’API OpenAI n’a pas fourni d’image utilisable.")

    with open(output_path, "wb") as f:
        f.write(img_data)

    return output_path

# ======================
# 5. Upload image
# ======================
@log_step("Upload image sur R2")
def upload_to_r2(file_path, object_name):
    s3_client.upload_file(str(file_path), R2_BUCKET, object_name)
    url = f"{R2_PUBLIC_URL}/{object_name}"
    if not verify_url_ok(url, retries=5, delay=2):
        raise RuntimeError(f"Fichier non accessible publiquement: {url}")
    return url

# ======================
# 6. Génération vidéo Runway
# ======================
@log_step("Génération vidéo (Runway image→video)")
def generate_video_from_image(image_url, prompt, duration, output_path):
    runway_duration = 5 if duration <= 5 else 10
    try:
        task = runway_client.image_to_video.create(
            model="gen4_turbo",
            prompt_image=image_url,
            prompt_text=f"{prompt}, style mystérieux, atmosphère peusante, cinématique, beaucoup d'animations",
            ratio="720:1280",
            duration=runway_duration,
        ).wait_for_task_output()

        if isinstance(task.output, list) and len(task.output) > 0:
            video_url = task.output[0]
        elif isinstance(task.output, dict) and "video" in task.output:
            video_url = task.output["video"]
        else:
            raise RuntimeError(f"❌ Sortie Runway inattendue: {task.output}")

        raw_path = str(output_path).replace(".mp4", "_raw.mp4")
        video_data = http_get_bytes(video_url, timeout=300, retries=3, backoff=3)
        with open(raw_path, "wb") as f:
            f.write(video_data)

        return adjust_video_duration(raw_path, output_path, duration)

    except Exception as e:
        log.warning(f"⚠️ Runway a échoué ({e}) → fallback zoom/pan ffmpeg")
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1",
            "-i", str(Path(output_path).with_suffix(".png")),
            "-t", str(duration),
            "-vf", random_zoompan(),
            "-c:v", "libx264", "-c:a", "aac",
            str(output_path)
        ], check=True)
        return output_path

# ======================
# 7. Concat vidéos
# ======================
@log_step("Concat vidéos")
def concat_videos(video_files, output_path):
    list_file = RENDERS_DIR / "file_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{vf}'\n")

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0",
         "-i", str(list_file),
         "-c:v", "libx264", "-c:a", "aac",
         str(output_path), "-y"],
        check=True,
    )

# ======================
# 8. Assemblage final
# ======================
@log_step("Assemblage final (vidéo + voix + sous-titres AI)")
def assemble_video(video_path, audio_path, segments, output_path):
    srt_path = RENDERS_DIR / "subtitles.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(segments, 1):
            def format_time(t):
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int((t * 1000) % 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            f.write(f"{i}\n")
            f.write(f"{format_time(start)} --> {format_time(end)}\n")
            f.write(text + "\n\n")

    # ✅ Fix chemin Windows pour FFmpeg
    srt_fixed = str(srt_path.resolve()).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", srt_fixed):  # ex: C:/Users/...
        srt_fixed = srt_fixed[0] + "\\:" + srt_fixed[2:]

    # 🎨 Style des sous-titres
    vf_filter = (
        f"subtitles='{srt_fixed}':force_style='FontName=Macondo,"
        f"FontSize=12,PrimaryColour=&H0000A5FF,MarginV=60',scale=720:1280"
    )

    log.info(f"🔎 FFMPEG FILTER = {vf_filter}")

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(video_path),     # vidéo concat
            "-i", str(audio_path),     # audio mixé (narration + musique)
            "-vf", vf_filter,
            "-map", "0:v:0",           # vidéo du premier input
            "-map", "1:a:0",           # audio du deuxième input
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            str(output_path), "-y",
        ],
        check=True,
    )

# ======================
# 9. Génération miniature
# ======================
@log_step("Génération miniature")
def generate_thumbnail(image_path, title, output_path):
    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    # Charger l'image
    img = Image.open(image_path).convert("RGBA")

    # Overlay sombre
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 120))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    # Police stylisée (Impact > Arial Black > défaut)
    try:
        font = ImageFont.truetype("impact.ttf", 90)
    except:
        try:
            font = ImageFont.truetype("arialbd.ttf", 90)
        except:
            font = ImageFont.load_default()

    # Texte en majuscules et wrap automatique
    text = title.upper()
    wrapped_text = textwrap.fill(text, width=15)

    # Taille texte
    if hasattr(draw, "multiline_textbbox"):
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=10)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        text_width, text_height = draw.multiline_textsize(wrapped_text, font=font, spacing=10)

    # Position centrée
    position = ((img.width - text_width) // 2, (img.height - text_height) // 2)

    # Fond rectangulaire semi-transparent
    padding = 40
    rect_x0 = position[0] - padding
    rect_y0 = position[1] - padding
    rect_x1 = position[0] + text_width + padding
    rect_y1 = position[1] + text_height + padding
    draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill=(0, 0, 0, 180))

    # Ombre autour du texte
    outline_range = 4
    for x in range(-outline_range, outline_range + 1):
        for y in range(-outline_range, outline_range + 1):
            draw.multiline_text(
                (position[0] + x, position[1] + y),
                wrapped_text,
                font=font,
                fill="black",
                spacing=10,
                align="center"
            )

    # Texte principal (rouge/orange)
    draw.multiline_text(
        position,
        wrapped_text,
        font=font,
        fill=(255, 80, 50),
        spacing=10,
        align="center"
    )

    # Sauvegarde
    img.convert("RGB").save(output_path, "PNG")
    log.info(f"✅ Miniature générée : {output_path}")


# ======================
# MAIN
# ======================
if __name__ == "__main__":
    log.info("🚀 LANCEMENT DU PROCESS")
    try:
        clean_renders()
        meta = generate_story_and_meta()
        story = meta.get("histoire", "")
        title = meta.get("titre", "")
        description = meta.get("description", "")
        hashtags = meta.get("hashtags", "")

        # Ajout d'une intro obligatoire
        story = "Ceci est une histoire vraie. " + story

        log.info(f"🎬 Titre : {title}")
        log.info(f"📝 Description : {description}")
        log.info(f"🏷️ Hashtags : {hashtags}")

        # Génération narration
        audio_file = RENDERS_DIR / "narration.mp3"
        generate_voice(story, audio_file)

        # Durée de la narration (en secondes)
        probe_audio = ffmpeg.probe(str(audio_file))
        narration_duration = float(probe_audio["format"]["duration"])
        log.info(f"🔊 Durée narration = {narration_duration:.2f}s")

        # 🎵 Préparer musique de fond
        music_file = Path(__file__).resolve().parent / "assets" / "music_1.mp3"
        music_clip = RENDERS_DIR / "music_clip.mp3"
        final_audio = RENDERS_DIR / "audio_mix.m4a"

        prepare_background_music(music_file, narration_duration, music_clip)
        mix_audio(audio_file, music_clip, final_audio)

        # Transcription → renvoie 2 listes : scènes + sous-titres
        scene_segments, subtitle_segments = transcribe_audio(audio_file)

        # Vidéos → basées sur les scènes uniquement
        video_clips = []
        total_video_duration = 0.0

        for i, (start, end, seg) in enumerate(scene_segments, 1):
            dur = end - start
            log.info(f"--- SCÈNE {i} | Durée {dur:.2f}s ---")
            img_path = RENDERS_DIR / f"scene_{i}.png"
            vid_path = RENDERS_DIR / f"scene_{i}.mp4"
            generate_image(seg, img_path)
            image_url = upload_to_r2(img_path, img_path.name)
            final_vid = generate_video_from_image(image_url, seg, dur, vid_path)
            video_clips.append(final_vid)

            # Mesurer durée réelle du clip généré
            probe = ffmpeg.probe(str(final_vid))
            total_video_duration += float(probe["format"]["duration"])

        # 🔧 Ajuster la dernière scène si besoin
        if total_video_duration < narration_duration:
            diff = narration_duration - total_video_duration
            log.info(f"⏱️ Allongement de la dernière scène de {diff:.2f}s pour égaler la narration")
            last_clip = video_clips[-1]
            adjusted_last_clip = str(last_clip).replace(".mp4", "_adjusted.mp4")

            subprocess.run([
                "ffmpeg", "-y", "-i", str(last_clip),
                "-vf", f"tpad=stop_mode=clone:stop_duration={math.ceil(diff)}",
                "-c:v", "libx264", "-c:a", "aac",
                adjusted_last_clip
            ], check=True)

            video_clips[-1] = adjusted_last_clip

        # Concat
        temp_video = RENDERS_DIR / "temp_concat.mp4"
        concat_videos(video_clips, temp_video)

        # Assemblage final avec sous-titres découpés (5 mots max)
        final_file = RENDERS_DIR / "final_horror_story.mp4"
        assemble_video(temp_video, final_audio, subtitle_segments, final_file)
        
        thumbnail_file = RENDERS_DIR / "thumbnail.png"
        generate_thumbnail(RENDERS_DIR / "scene_1.png", title, thumbnail_file)

        log.info(f"🎉 PROCESS TERMINÉ | Sortie: {final_file}")

    except Exception:
        log.exception("💥 PROCESS ÉCHOUÉ")
        raise
