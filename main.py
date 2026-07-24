#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Montage AI — analyse et sélection de rushs événementiels.

Le programme peut :
1. indexer les vidéos du NAS dans SQLite ;
2. reprendre une base existante sans rescanner le NAS ;
3. détecter des passages intéressants avec FFmpeg ;
4. analyser les images avec Ollama Vision ;
5. générer les CSV de sélection et un script After Effects.

Aucune bibliothèque Python externe n'est nécessaire.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts",
    ".webm", ".wmv", ".mpg", ".mpeg", ".3gp", ".hevc"
}

EXCLUDED_FOLDERS = {
    "$recycle.bin", "@recycle", "#recycle", "recycle", "cache", ".cache",
    "temp", "tmp", "proxy", "proxies", "preview", "previews", "resultats",
    "after_effects", "thumbnails", "miniatures", "renders", "autosave"
}

MACHINES = ["Photobooth", "VogueBooth", "360Booth", "MiroirBooth", "Aucune"]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ANALYSIS_VERSION = 3


@dataclass
class VideoInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    size: int
    mtime_ns: int


@dataclass
class ReferenceImage:
    machine: str
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Indexe, analyse et classe les vidéos pour After Effects."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=r"P:\Montage-EVENT\ALL_MONTAGE",
        help="Dossier contenant les vidéos."
    )
    parser.add_argument("--output", default="resultats", help="Dossier de sortie.")

    index_group = parser.add_argument_group("Indexation")
    index_group.add_argument(
        "--skip-index",
        action="store_true",
        help="Utilise la base SQLite existante sans rescanner le NAS."
    )
    index_group.add_argument(
        "--index-only",
        action="store_true",
        help="Indexe les vidéos puis s'arrête avant l'analyse."
    )
    index_group.add_argument(
        "--max-index",
        type=int,
        default=0,
        help="Nombre maximal de fichiers à parcourir pendant l'indexation. 0 = tous."
    )

    analysis_group = parser.add_argument_group("Analyse")
    analysis_group.add_argument(
        "--max-videos",
        type=int,
        default=50,
        help="Nombre maximal de vidéos à analyser. 0 = toutes les vidéos en attente."
    )
    analysis_group.add_argument(
        "--export-only",
        action="store_true",
        help="Regénère les CSV et le JSX sans indexer ni analyser."
    )
    analysis_group.add_argument(
        "--retry-errors",
        action="store_true",
        help="Réessaie aussi les vidéos précédemment en erreur."
    )
    analysis_group.add_argument(
        "--reanalyze",
        action="store_true",
        help="Réanalyse des vidéos déjà terminées."
    )
    analysis_group.add_argument("--candidates", type=int, default=8)
    analysis_group.add_argument("--top-moments", type=int, default=3)
    analysis_group.add_argument("--min-score", type=int, default=58)

    ai_group = parser.add_argument_group("Ollama")
    ai_group.add_argument("--model", default="gemma3")
    ai_group.add_argument("--ollama-url", default="http://localhost:11434")
    ai_group.add_argument("--references", default="machine_references")

    export_group = parser.add_argument_group("Exports")
    export_group.add_argument("--event-name", default="MySelfieBooth")
    export_group.add_argument(
        "--top-machine",
        choices=MACHINES[:-1],
        default="Photobooth",
        help="Machine utilisée pour le fichier Top."
    )
    export_group.add_argument(
        "--top-limit",
        type=int,
        default=10,
        help="Nombre de moments dans le fichier Top."
    )
    export_group.add_argument(
        "--keep-work",
        action="store_true",
        help="Conserve les planches d'images temporaires."
    )

    args = parser.parse_args()

    if args.max_index < 0 or args.max_videos < 0:
        parser.error("--max-index et --max-videos doivent être positifs ou égaux à 0.")
    if args.candidates < 1:
        parser.error("--candidates doit être supérieur ou égal à 1.")
    if args.top_moments < 1:
        parser.error("--top-moments doit être supérieur ou égal à 1.")
    if not 0 <= args.min_score <= 100:
        parser.error("--min-score doit être compris entre 0 et 100.")
    if args.top_limit < 1:
        parser.error("--top-limit doit être supérieur ou égal à 1.")

    return args


def require_program(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"ERREUR : {name} est introuvable dans le PATH.")
    return path


def run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_score(value: object) -> int:
    return max(0, min(100, int(round(safe_float(value)))))


def parse_rate(value: str) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    if "/" in value:
        left, right = value.split("/", 1)
        denominator = safe_float(right)
        return safe_float(left) / denominator if denominator else 0.0
    return safe_float(value)


def timecode(seconds: float) -> str:
    total_ms = int(max(0.0, seconds) * 1000)
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    return cleaned.strip("_") or "selection"


def discover_videos(root: Path) -> Iterable[Path]:
    for current, directories, files in os.walk(root):
        directories[:] = [
            name for name in directories
            if not name.startswith(".") and name.lower() not in EXCLUDED_FOLDERS
        ]
        for filename in files:
            path = Path(current) / filename
            if path.suffix.lower() in VIDEO_EXTENSIONS:
                yield path


def probe_video(ffprobe: str, path: Path) -> VideoInfo | None:
    result = run([
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ], timeout=45)
    if not result or result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
        stream = next(
            item for item in data.get("streams", [])
            if item.get("codec_type") == "video"
        )
        stat = path.stat()
        return VideoInfo(
            path=path,
            duration=safe_float(data.get("format", {}).get("duration")),
            width=int(stream.get("width") or 0),
            height=int(stream.get("height") or 0),
            fps=parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or ""),
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )
    except (StopIteration, OSError, ValueError, json.JSONDecodeError):
        return None


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS videos (
                path TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                duration REAL NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                fps REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS moments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT NOT NULL,
                timestamp REAL NOT NULL,
                start REAL NOT NULL,
                end REAL NOT NULL,
                score INTEGER NOT NULL,
                machine TEXT NOT NULL,
                smile INTEGER NOT NULL,
                reaction INTEGER NOT NULL,
                energy INTEGER NOT NULL,
                quality INTEGER NOT NULL,
                description TEXT NOT NULL,
                UNIQUE(video_path, timestamp),
                FOREIGN KEY(video_path) REFERENCES videos(path) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS analysis_cache (
                video_path TEXT NOT NULL,
                timestamp REAL NOT NULL,
                model TEXT NOT NULL,
                version INTEGER NOT NULL,
                analysis_json TEXT NOT NULL,
                PRIMARY KEY(video_path, timestamp, model, version),
                FOREIGN KEY(video_path) REFERENCES videos(path) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_videos_status
            ON videos(status, mtime_ns DESC);

            CREATE INDEX IF NOT EXISTS idx_moments_machine_score
            ON moments(machine, score DESC);
        """)
        self.connection.commit()

    def get_signature(self, video_path: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT size, mtime_ns FROM videos WHERE path = ?",
            (video_path,)
        ).fetchone()

    def upsert_video(self, video: VideoInfo) -> str:
        video_path = str(video.path)
        previous = self.connection.execute(
            "SELECT size, mtime_ns FROM videos WHERE path = ?",
            (video_path,)
        ).fetchone()

        state = "new"
        if previous is not None:
            changed = (
                previous["size"] != video.size
                or previous["mtime_ns"] != video.mtime_ns
            )
            state = "updated" if changed else "unchanged"

        self.connection.execute("""
            INSERT INTO videos(path, size, mtime_ns, duration, width, height, fps, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
            ON CONFLICT(path) DO UPDATE SET
                size=excluded.size,
                mtime_ns=excluded.mtime_ns,
                duration=excluded.duration,
                width=excluded.width,
                height=excluded.height,
                fps=excluded.fps,
                status=CASE
                    WHEN videos.size != excluded.size
                      OR videos.mtime_ns != excluded.mtime_ns
                    THEN 'new'
                    ELSE videos.status
                END,
                error=CASE
                    WHEN videos.size != excluded.size
                      OR videos.mtime_ns != excluded.mtime_ns
                    THEN ''
                    ELSE videos.error
                END
        """, (
            video_path, video.size, video.mtime_ns, video.duration,
            video.width, video.height, video.fps
        ))

        if state == "updated":
            self.connection.execute(
                "DELETE FROM moments WHERE video_path = ?",
                (video_path,)
            )
            self.connection.execute(
                "DELETE FROM analysis_cache WHERE video_path = ?",
                (video_path,)
            )
        return state

    def cached_analysis(
        self,
        video_path: str,
        timestamp: float,
        model: str,
    ) -> dict | None:
        row = self.connection.execute("""
            SELECT analysis_json FROM analysis_cache
            WHERE video_path=? AND timestamp=? AND model=? AND version=?
        """, (video_path, timestamp, model, ANALYSIS_VERSION)).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["analysis_json"])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None

    def save_cached_analysis(
        self,
        video_path: str,
        timestamp: float,
        model: str,
        analysis: dict,
    ) -> None:
        self.connection.execute("""
            INSERT OR REPLACE INTO analysis_cache(
                video_path, timestamp, model, version, analysis_json
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            video_path,
            timestamp,
            model,
            ANALYSIS_VERSION,
            json.dumps(analysis, ensure_ascii=False),
        ))
        self.connection.commit()

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def has_videos(self) -> bool:
        row = self.connection.execute("SELECT 1 FROM videos LIMIT 1").fetchone()
        return row is not None

    def next_videos(
        self,
        limit: int,
        retry_errors: bool = False,
        reanalyze: bool = False,
    ) -> list[sqlite3.Row]:
        if reanalyze:
            query = "SELECT * FROM videos ORDER BY mtime_ns DESC"
            parameters: tuple[object, ...] = ()
        elif retry_errors:
            query = "SELECT * FROM videos WHERE status IN ('new', 'error') ORDER BY mtime_ns DESC"
            parameters = ()
        else:
            query = "SELECT * FROM videos WHERE status = 'new' ORDER BY mtime_ns DESC"
            parameters = ()

        if limit > 0:
            query += " LIMIT ?"
            parameters = (*parameters, limit)

        return list(self.connection.execute(query, parameters))

    def save_moments(self, video_path: str, moments: list[dict]) -> None:
        self.connection.execute(
            "DELETE FROM moments WHERE video_path = ?",
            (video_path,)
        )
        for item in moments:
            self.connection.execute("""
                INSERT OR REPLACE INTO moments(
                    video_path, timestamp, start, end, score, machine,
                    smile, reaction, energy, quality, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_path, item["timestamp"], item["start"], item["end"],
                item["score"], item["machine"], item["smile"], item["reaction"],
                item["energy"], item["quality"], item["description"]
            ))
        self.connection.execute(
            "UPDATE videos SET status='done', error='' WHERE path=?",
            (video_path,)
        )
        self.connection.commit()

    def mark_error(self, video_path: str, message: str) -> None:
        self.connection.execute(
            "UPDATE videos SET status='error', error=? WHERE path=?",
            (message[:500], video_path),
        )
        self.connection.commit()

    def all_moments(
        self,
        machine: str | None = None,
        limit: int = 0,
    ) -> list[sqlite3.Row]:
        query = """
            SELECT moments.*, videos.width, videos.height, videos.duration
            FROM moments
            JOIN videos ON videos.path = moments.video_path
        """
        parameters: list[object] = []

        if machine:
            query += " WHERE moments.machine = ?"
            parameters.append(machine)

        query += " ORDER BY moments.score DESC, moments.video_path, moments.timestamp"

        if limit > 0:
            query += " LIMIT ?"
            parameters.append(limit)

        return list(self.connection.execute(query, parameters))

    def status_counts(self) -> dict[str, int]:
        counts = {"new": 0, "done": 0, "error": 0}
        for row in self.connection.execute(
            "SELECT status, COUNT(*) AS total FROM videos GROUP BY status"
        ):
            counts[str(row["status"])] = int(row["total"])
        return counts

    def close(self) -> None:
        self.connection.close()


def index_videos(
    database: Database,
    ffprobe: str,
    source: Path,
    maximum: int,
) -> dict[str, int]:
    counters = {
        "discovered": 0,
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "invalid": 0,
    }

    print(f"Indexation : {source}")
    print("Ctrl+C permet d'arrêter proprement. La progression déjà enregistrée sera conservée.")

    try:
        for path in discover_videos(source):
            if maximum > 0 and counters["discovered"] >= maximum:
                break

            counters["discovered"] += 1

            try:
                stat = path.stat()
            except OSError:
                counters["invalid"] += 1
                continue

            previous = database.get_signature(str(path))
            if (
                previous is not None
                and previous["size"] == stat.st_size
                and previous["mtime_ns"] == stat.st_mtime_ns
            ):
                counters["unchanged"] += 1
            else:
                info = probe_video(ffprobe, path)
                if info is None or info.duration < 2:
                    counters["invalid"] += 1
                else:
                    state = database.upsert_video(info)
                    counters[state] += 1

            if counters["discovered"] % 25 == 0:
                database.commit()
                print(
                    f"  {counters['discovered']} parcourues | "
                    f"{counters['new']} nouvelles | "
                    f"{counters['updated']} modifiées | "
                    f"{counters['unchanged']} déjà connues"
                )

        database.commit()
        return counters

    except KeyboardInterrupt:
        database.commit()
        print("\nIndexation interrompue proprement. La progression SQLite est conservée.")
        raise


def detect_scene_times(
    ffmpeg: str,
    video: Path,
    duration: float,
    maximum: int,
) -> list[float]:
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(video),
        "-vf", "fps=2,scale=256:-2,select='gt(scene,0.28)',showinfo",
        "-an", "-f", "null", "-"
    ], timeout=max(90, int(duration * 0.75)))

    values: list[float] = []
    if result:
        for match in re.finditer(r"pts_time:([0-9.]+)", result.stderr):
            value = safe_float(match.group(1))
            if 0.5 < value < duration - 0.5:
                values.append(value)

    if len(values) < min(3, maximum):
        fallback_count = min(maximum, max(3, int(duration // 12) + 1))
        values.extend(
            duration * (index + 1) / (fallback_count + 1)
            for index in range(fallback_count)
        )

    unique: list[float] = []
    for value in sorted(values):
        if all(abs(value - existing) >= 3.0 for existing in unique):
            unique.append(round(value, 3))
        if len(unique) >= maximum:
            break
    return unique


def extract_candidate_frames(
    ffmpeg: str,
    video: Path,
    timestamp: float,
    duration: float,
    folder: Path,
    prefix: str,
) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    times = [
        max(0.05, min(duration - 0.05, timestamp + offset))
        for offset in (-1.2, -0.6, 0.0, 0.6, 1.2)
    ]

    inputs: list[str] = []
    outputs: list[str] = []
    destinations: list[Path] = []
    for index, value in enumerate(times):
        inputs.extend(["-ss", f"{value:.3f}", "-i", str(video)])
        destination = folder / f"{prefix}_{index + 1}.jpg"
        destinations.append(destination)
        outputs.extend([
            "-map", f"{index}:v:0", "-frames:v", "1",
            "-vf", "scale=768:-2", str(destination),
        ])

    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
        *outputs,
    ], timeout=90)

    if not result or result.returncode != 0:
        return []
    return [path for path in destinations if path.exists()]


def create_image_grid(
    ffmpeg: str,
    images: list[Path],
    destination: Path,
    columns: int = 3,
) -> bool:
    if not images:
        return False
    inputs: list[str] = []
    filters: list[str] = []
    positions: list[str] = []
    for index, path in enumerate(images):
        inputs.extend(["-i", str(path)])
        filters.append(
            f"[{index}:v]scale=512:384:force_original_aspect_ratio=decrease,"
            f"pad=512:384:(ow-iw)/2:(oh-ih)/2[img{index}]"
        )
        positions.append(f"{(index % columns) * 512}_{(index // columns) * 384}")

    labels = "".join(f"[img{index}]" for index in range(len(images)))
    filter_complex = (
        ";".join(filters)
        + f";{labels}xstack=inputs={len(images)}:layout={'|'.join(positions)}[grid]"
    )
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[grid]", "-frames:v", "1", str(destination),
    ], timeout=90)
    return bool(result and result.returncode == 0 and destination.exists())


def reference_images(folder: Path) -> list[ReferenceImage]:
    references: list[ReferenceImage] = []

    for machine in MACHINES[:-1]:
        machine_folder = folder / machine
        if not machine_folder.exists():
            continue

        image = next(
            (
                path for path in sorted(machine_folder.iterdir())
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ),
            None,
        )
        if image:
            references.append(ReferenceImage(machine=machine, path=image))

    return references


def image_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def check_ollama(url: str, model: str) -> None:
    tags_url = f"{url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "ERREUR : Ollama ne répond pas. Lance Ollama puis réessaie.\n"
            f"Détail : {exc}"
        ) from exc

    installed_names = {
        str(item.get("name", ""))
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    model_is_present = any(
        name == model or name.startswith(f"{model}:")
        for name in installed_names
    )
    if not model_is_present:
        raise SystemExit(
            f"ERREUR : le modèle Ollama '{model}' n'est pas installé.\n"
            f"Commande : ollama pull {model}"
        )


def ollama_request(url: str, payload: dict, timeout: int = 180) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(
            f"Ollama a refusé la requête (HTTP {exc.code}) : {detail}"
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ollama ne répond pas correctement : {exc}") from exc


def parse_ollama_json(value: object) -> dict:
    if isinstance(value, dict):
        return value

    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("Ollama a renvoyé une réponse d'analyse vide.")

    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        object_start = raw.find("{")
        if object_start >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(raw[object_start:])
            except json.JSONDecodeError:
                data = None
        else:
            data = None
        if data is None:
            preview = raw[:200].replace("\n", " ")
            raise RuntimeError(
                f"Ollama a renvoyé un JSON d'analyse invalide : {preview!r}"
            ) from exc

    if not isinstance(data, dict):
        raise RuntimeError("Ollama a renvoyé un JSON qui n'est pas un objet.")
    return data


def normalize_machine(value: object) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "photobooth": "Photobooth",
        "photo booth": "Photobooth",
        "borne photo": "Photobooth",
        "voguebooth": "VogueBooth",
        "vogue booth": "VogueBooth",
        "360booth": "360Booth",
        "360 booth": "360Booth",
        "miroirbooth": "MiroirBooth",
        "miroir booth": "MiroirBooth",
        "miroir": "MiroirBooth",
        "aucune": "Aucune",
        "none": "Aucune",
    }
    return aliases.get(text, "Aucune")


def ollama_json_with_retry(args: argparse.Namespace, prompt: str, images: list[str]) -> dict:
    payload = {
        "model": args.model,
        "prompt": prompt,
        "images": images,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 512},
    }
    last_error: RuntimeError | None = None
    for attempt in range(1, 4):
        try:
            attempt_payload = dict(payload)
            if attempt == 3:
                attempt_payload.pop("format", None)
            response = ollama_request(
                f"{args.ollama_url.rstrip('/')}/api/generate",
                attempt_payload,
            )
            raw = response.get("response") or response.get("thinking")
            if not raw:
                raise RuntimeError(
                    "Ollama a renvoyé une réponse incomplète "
                    f"(model={response.get('model')!r}, done={response.get('done')!r}, "
                    f"done_reason={response.get('done_reason')!r})."
                )
            data = parse_ollama_json(raw)
            return data
        except RuntimeError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 if attempt == 1 else 5)

    restart_hint = (
        " Ferme puis relance Ollama avant de réessayer."
        if last_error and "réponse incomplète" in str(last_error)
        else ""
    )
    raise RuntimeError(
        f"Analyse Ollama impossible après 3 tentatives : {last_error}.{restart_hint}"
    ) from last_error


def analyze_grids(
    args: argparse.Namespace,
    candidate_grid: Path,
    reference_grid: Path | None,
    references: list[ReferenceImage],
) -> dict:
    candidate_image = image_base64(candidate_grid)
    reference_description = ", ".join(
        f"référence {index + 1} = {reference.machine}"
        for index, reference in enumerate(references[:4])
    ) or "aucune référence fournie"
    machine_images = [candidate_image]
    if reference_grid is not None:
        machine_images.append(image_base64(reference_grid))

    data = ollama_json_with_retry(args, """
Tu notes une grille montrant cinq instants successifs d'un passage événementiel.
Décris seulement ce qui est directement visible. N'identifie aucune marque ni
machine.

Évalue séparément smile, reaction, energy et quality de 0 à 100. Barème global :
0-39 faible ou inexploitable, 40-59 ordinaire, 60-74 bon, 75-89 excellent avec
réaction évidente, 90-100 exceptionnel et rare. Propose une durée de 2 à 10
secondes. Réponds uniquement en JSON avec : score, smile, reaction, energy,
quality, duration, description.
""".strip(), [candidate_image])

    smile = clamp_score(data.get("smile"))
    reaction = clamp_score(data.get("reaction"))
    energy = clamp_score(data.get("energy"))
    quality = clamp_score(data.get("quality"))
    ai_score = clamp_score(data.get("score"))

    calculated_score = round(
        ai_score * 0.15
        + smile * 0.25
        + reaction * 0.25
        + energy * 0.15
        + quality * 0.20
    )
    final_score = clamp_score(calculated_score)

    machine = "Aucune"
    if final_score >= args.min_score and quality >= 35:
        machine_data = ollama_json_with_retry(args, f"""
L'image 1 est une grille de cinq instants successifs d'un même passage, dans
l'ordre de lecture. L'image 2, si présente, est une grille de références dans
l'ordre de lecture : {reference_description}.

Identifie uniquement la machine réellement visible parmi Photobooth,
VogueBooth, 360Booth, MiroirBooth ou Aucune. Une décoration, un téléphone, un
miroir ordinaire ou des invités ne sont pas des preuves. La structure doit être
visible sur au moins deux des cinq images et correspondre à une référence.
En cas de doute, réponds Aucune.

Réponds uniquement en JSON avec : machine, confidence, visible_evidence,
supporting_frames. confidence vaut 0 à 100 et supporting_frames est le nombre
d'images du passage qui montrent réellement la machine.
""".strip(), machine_images)

        machine = normalize_machine(machine_data.get("machine"))
        confidence = clamp_score(machine_data.get("confidence"))
        evidence = str(machine_data.get("visible_evidence", "")).strip()
        supporting_frames = int(safe_float(machine_data.get("supporting_frames")))
        if machine != "Aucune" and (
            confidence < 75 or supporting_frames < 2 or len(evidence) < 8
        ):
            machine = "Aucune"

    return {
        "score": final_score,
        "machine": machine,
        "smile": smile,
        "reaction": reaction,
        "energy": energy,
        "quality": quality,
        "duration": max(2.0, min(10.0, safe_float(data.get("duration"), 5.0))),
        "description": str(data.get("description", "Moment événementiel"))[:300],
    }


def analyze_video(
    args: argparse.Namespace,
    database: Database,
    ffmpeg: str,
    row: sqlite3.Row,
    work: Path,
    references: list[ReferenceImage],
) -> list[dict]:
    path = Path(row["path"])
    duration = safe_float(row["duration"])

    if not path.exists():
        raise RuntimeError("Fichier vidéo introuvable ou lecteur réseau déconnecté.")
    if duration < 2:
        return []

    candidates = detect_scene_times(
        ffmpeg,
        path,
        duration,
        args.candidates,
    )
    results: list[dict] = []
    analysis_errors: list[str] = []
    analyzed_candidates = 0

    for index, timestamp in enumerate(candidates, start=1):
        analysis = None if args.reanalyze else database.cached_analysis(
            str(path), timestamp, args.model
        )
        if analysis is not None:
            analyzed_candidates += 1
            print(f"    candidat {index} : cache SQLite")
        else:
            prefix = f"{abs(hash(str(path))) % 10**10}_{index}"
            frames = extract_candidate_frames(
                ffmpeg, path, timestamp, duration, work, prefix
            )
            if len(frames) < 3:
                continue

            candidate_grid = work / f"{prefix}_grid.jpg"
            if not create_image_grid(ffmpeg, frames, candidate_grid):
                continue
            reference_grid: Path | None = None
            if references:
                reference_grid = work / "machine_references_grid.jpg"
                if not reference_grid.exists() and not create_image_grid(
                    ffmpeg,
                    [reference.path for reference in references[:4]],
                    reference_grid,
                    columns=2,
                ):
                    reference_grid = None

            try:
                analysis = analyze_grids(
                    args, candidate_grid, reference_grid, references
                )
                database.save_cached_analysis(
                    str(path), timestamp, args.model, analysis
                )
                analyzed_candidates += 1
            except RuntimeError as exc:
                analysis_errors.append(str(exc))
                print(f"    AVERTISSEMENT : candidat {index} ignoré ({exc})")
                continue
        if analysis["score"] < args.min_score or analysis["quality"] < 35:
            continue

        clip_duration = analysis["duration"]
        start = max(0.0, timestamp - clip_duration * 0.4)
        end = min(duration, start + clip_duration)
        results.append({
            **analysis,
            "timestamp": timestamp,
            "start": start,
            "end": end,
        })

    if analysis_errors and analyzed_candidates == 0:
        raise RuntimeError(
            "Tous les candidats ont échoué pendant l'analyse Ollama. "
            f"Dernière erreur : {analysis_errors[-1]}"
        )

    selected: list[dict] = []
    for item in sorted(results, key=lambda value: value["score"], reverse=True):
        if all(abs(item["timestamp"] - kept["timestamp"]) >= 6.0 for kept in selected):
            selected.append(item)
        if len(selected) >= args.top_moments:
            break

    return selected


def write_csv(rows: list[sqlite3.Row], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "video_path", "start", "end", "start_timecode", "end_timecode",
        "score", "machine", "smile", "reaction", "energy", "quality",
        "description"
    ]

    with destination.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "video_path": row["video_path"],
                "start": round(safe_float(row["start"]), 3),
                "end": round(safe_float(row["end"]), 3),
                "start_timecode": timecode(safe_float(row["start"])),
                "end_timecode": timecode(safe_float(row["end"])),
                "score": row["score"],
                "machine": row["machine"],
                "smile": row["smile"],
                "reaction": row["reaction"],
                "energy": row["energy"],
                "quality": row["quality"],
                "description": row["description"],
            })


def jsx_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def generate_after_effects(
    rows: list[sqlite3.Row],
    destination: Path,
    event_name: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    clips = [dict(row) for row in rows[:30]]
    payload = json.dumps(clips, ensure_ascii=False)

    script = f'''// Montage AI — projet After Effects généré automatiquement
(function () {{
    app.beginUndoGroup("Montage AI");
    var clips = {payload};
    var project = app.project || app.newProject();
    var folder = project.items.addFolder("MONTAGE AI - RUSHS");
    var comp = project.items.addComp({jsx_string(event_name + " - REEL 30S")}, 1080, 1920, 1, 30, 25);
    var reviewDuration = Math.max(30, clips.length * 10);
    var review = project.items.addComp("SELECTS_REVIEW", 1920, 1080, 1, reviewDuration, 25);
    var cursor = 0;
    var reviewCursor = 0;

    function fit(layer, width, height) {{
        var source = layer.source;
        var scale = Math.max(width / source.width, height / source.height) * 100;
        layer.property("Scale").setValue([scale, scale]);
        layer.property("Position").setValue([width / 2, height / 2]);
    }}

    for (var i = 0; i < clips.length; i++) {{
        var clip = clips[i];
        var file = new File(clip.video_path);
        if (!file.exists) continue;

        var footage = project.importFile(new ImportOptions(file));
        footage.parentFolder = folder;
        var duration = Math.max(1, clip.end - clip.start);

        if (cursor < comp.duration) {{
            var layer = comp.layers.add(footage);
            layer.startTime = cursor - clip.start;
            layer.inPoint = cursor;
            layer.outPoint = Math.min(comp.duration, cursor + duration);
            fit(layer, comp.width, comp.height);
            var marker = new MarkerValue(
                "Score " + clip.score + " | " + clip.machine + " | " + clip.description
            );
            layer.property("Marker").setValueAtTime(cursor, marker);
            cursor += duration;
        }}

        var reviewLayer = review.layers.add(footage);
        reviewLayer.startTime = reviewCursor - clip.start;
        reviewLayer.inPoint = reviewCursor;
        reviewLayer.outPoint = Math.min(review.duration, reviewCursor + duration);
        fit(reviewLayer, review.width, review.height);
        reviewCursor += duration;
    }}

    alert("Projet créé : " + comp.name + " et SELECTS_REVIEW");
    app.endUndoGroup();
}})();
'''
    destination.write_text(script, encoding="utf-8")


def print_top(rows: list[sqlite3.Row], machine: str) -> None:
    print(f"\nTop {len(rows)} — {machine}")
    if not rows:
        print("  Aucun moment correspondant dans la base.")
        return

    for rank, row in enumerate(rows, start=1):
        filename = Path(row["video_path"]).name
        print(
            f"  {rank:>2}. Score {row['score']:>3} | "
            f"{timecode(row['start'])} → {timecode(row['end'])} | {filename}"
        )


def export_results(
    database: Database,
    output: Path,
    args: argparse.Namespace,
) -> None:
    all_rows = database.all_moments()
    top_rows = database.all_moments(
        machine=args.top_machine,
        limit=args.top_limit,
    )

    all_csv = output / "moments.csv"
    top_name = safe_filename(args.top_machine.lower())
    top_csv = output / f"top_{args.top_limit}_{top_name}.csv"
    jsx_file = output / "MSB_Creer_Projet_After_Effects.jsx"

    write_csv(all_rows, all_csv)
    write_csv(top_rows, top_csv)
    generate_after_effects(all_rows, jsx_file, args.event_name)
    print_top(top_rows, args.top_machine)

    print("\nExports :")
    print(f"  Tous les moments : {all_csv}")
    print(f"  Top {args.top_limit} {args.top_machine} : {top_csv}")
    print(f"  After Effects : {jsx_file}")


def print_database_status(database: Database) -> None:
    counts = database.status_counts()
    total = sum(counts.values())
    print("\nÉtat de la base SQLite :")
    print(f"  Total : {total}")
    print(f"  À analyser : {counts.get('new', 0)}")
    print(f"  Terminées : {counts.get('done', 0)}")
    print(f"  En erreur : {counts.get('error', 0)}")


def main() -> int:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output).resolve()
    work = output / "work"
    database_path = output / "video_index.sqlite3"
    output.mkdir(parents=True, exist_ok=True)

    database = Database(database_path)

    try:
        if args.export_only:
            export_results(database, output, args)
            print_database_status(database)
            print(f"\nBase SQLite : {database_path}")
            return 0

        if not args.skip_index:
            if not source.exists():
                raise SystemExit(f"ERREUR : dossier introuvable : {source}")
            ffprobe = require_program("ffprobe")

            start_time = time.monotonic()
            try:
                counters = index_videos(
                    database,
                    ffprobe,
                    source,
                    args.max_index,
                )
            except KeyboardInterrupt:
                print_database_status(database)
                print(f"Base SQLite : {database_path}")
                return 130

            elapsed = time.monotonic() - start_time
            print("\nIndexation terminée :")
            print(f"  Fichiers parcourus : {counters['discovered']}")
            print(f"  Nouvelles vidéos : {counters['new']}")
            print(f"  Vidéos modifiées : {counters['updated']}")
            print(f"  Déjà connues : {counters['unchanged']}")
            print(f"  Illisibles ou trop courtes : {counters['invalid']}")
            print(f"  Durée : {elapsed / 60:.1f} minute(s)")
        else:
            print("Indexation ignorée : utilisation de la base SQLite existante.")
            if not database.has_videos():
                raise SystemExit(
                    "ERREUR : la base SQLite ne contient aucune vidéo. "
                    "Lance d'abord une indexation sans --skip-index."
                )

        print_database_status(database)

        if args.index_only:
            print(f"\nBase SQLite : {database_path}")
            return 0

        ffmpeg = require_program("ffmpeg")
        check_ollama(args.ollama_url, args.model)

        todo = database.next_videos(
            limit=args.max_videos,
            retry_errors=args.retry_errors,
            reanalyze=args.reanalyze,
        )
        print(f"\nAnalyse de {len(todo)} vidéo(s).")

        references = reference_images(Path(args.references))
        if references:
            names = ", ".join(reference.machine for reference in references)
            print(f"Références machines chargées : {names}")
        else:
            print("Aucune référence machine trouvée. La reconnaissance sera moins fiable.")

        work.mkdir(parents=True, exist_ok=True)
        analysis_start = time.monotonic()

        for index, row in enumerate(todo, start=1):
            video_path = str(row["path"])
            print(f"[{index}/{len(todo)}] {Path(video_path).name}")
            try:
                moments = analyze_video(
                    args,
                    database,
                    ffmpeg,
                    row,
                    work,
                    references,
                )
                database.save_moments(video_path, moments)
                print(f"  {len(moments)} moment(s) retenu(s)")
            except KeyboardInterrupt:
                print("\nAnalyse interrompue. Les vidéos déjà terminées restent enregistrées.")
                return 130
            except Exception as exc:
                database.mark_error(video_path, str(exc))
                print(f"  ERREUR : {exc}")

        elapsed = time.monotonic() - analysis_start
        export_results(database, output, args)
        print_database_status(database)

        print("\nTerminé.")
        print(f"Base SQLite : {database_path}")
        print(f"Durée de l'analyse : {elapsed / 60:.1f} minute(s)")
        return 0

    finally:
        database.close()
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
