#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Montage AI — version simple.

Un seul script pour :
1. parcourir les vidéos du NAS ;
2. détecter quelques passages intéressants avec FFmpeg ;
3. analyser ces passages avec Ollama Vision ;
4. enregistrer la progression dans SQLite ;
5. générer un CSV et un script JSX pour After Effects.

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


@dataclass
class VideoInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    size: int
    mtime_ns: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyse les vidéos et prépare After Effects.")
    parser.add_argument("source", nargs="?", default=r"P:\Montage-EVENT\ALL_MONTAGE")
    parser.add_argument("--output", default="resultats")
    parser.add_argument("--max-videos", type=int, default=50)
    parser.add_argument("--model", default="gemma3")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--event-name", default="MySelfieBooth")
    parser.add_argument("--references", default="machine_references")
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--top-moments", type=int, default=3)
    parser.add_argument("--min-score", type=int, default=58)
    return parser.parse_args()


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
                UNIQUE(video_path, timestamp)
            );
        """)
        self.connection.commit()

    def upsert_video(self, video: VideoInfo) -> None:
        previous = self.connection.execute(
            "SELECT size, mtime_ns FROM videos WHERE path = ?", (str(video.path),)
        ).fetchone()
        changed = previous and (
            previous["size"] != video.size or previous["mtime_ns"] != video.mtime_ns
        )
        status = "new" if changed or previous is None else None
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
                status=CASE WHEN videos.size != excluded.size OR videos.mtime_ns != excluded.mtime_ns
                            THEN 'new' ELSE videos.status END
        """, (
            str(video.path), video.size, video.mtime_ns, video.duration,
            video.width, video.height, video.fps
        ))
        if status == "new" and previous:
            self.connection.execute("DELETE FROM moments WHERE video_path = ?", (str(video.path),))
        self.connection.commit()

    def next_videos(self, limit: int) -> list[sqlite3.Row]:
        query = "SELECT * FROM videos WHERE status != 'done' ORDER BY mtime_ns DESC"
        if limit > 0:
            query += " LIMIT ?"
            return list(self.connection.execute(query, (limit,)))
        return list(self.connection.execute(query))

    def save_moments(self, video_path: str, moments: list[dict]) -> None:
        self.connection.execute("DELETE FROM moments WHERE video_path = ?", (video_path,))
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
            "UPDATE videos SET status='done', error='' WHERE path=?", (video_path,)
        )
        self.connection.commit()

    def mark_error(self, video_path: str, message: str) -> None:
        self.connection.execute(
            "UPDATE videos SET status='error', error=? WHERE path=?",
            (message[:500], video_path),
        )
        self.connection.commit()

    def all_moments(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("""
            SELECT moments.*, videos.width, videos.height
            FROM moments JOIN videos ON videos.path = moments.video_path
            ORDER BY score DESC, video_path, timestamp
        """))

    def close(self) -> None:
        self.connection.close()


def detect_scene_times(ffmpeg: str, video: Path, duration: float, maximum: int) -> list[float]:
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(video),
        "-vf", "scale=256:-2,select='gt(scene,0.32)',showinfo",
        "-an", "-f", "null", "-"
    ], timeout=max(90, int(duration * 1.5)))

    values: list[float] = []
    if result:
        for match in re.finditer(r"pts_time:([0-9.]+)", result.stderr):
            value = safe_float(match.group(1))
            if 0.5 < value < duration - 0.5:
                values.append(value)

    if len(values) < 3:
        count = min(maximum, max(3, int(duration // 12) + 1))
        values.extend(duration * (index + 1) / (count + 1) for index in range(count))

    unique: list[float] = []
    for value in sorted(values):
        if all(abs(value - existing) >= 3.0 for existing in unique):
            unique.append(round(value, 3))
    return unique[:maximum]


def extract_contact_sheet(ffmpeg: str, video: Path, timestamp: float, duration: float, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    times = [max(0.05, min(duration - 0.05, timestamp + offset)) for offset in (-0.8, 0.0, 0.8)]
    filters = []
    inputs = []
    for index, value in enumerate(times):
        inputs.extend(["-ss", f"{value:.3f}", "-i", str(video)])
        filters.append(f"[{index}:v]scale=420:-2,fps=1[img{index}]")
    filter_complex = ";".join(filters) + ";[img0][img1][img2]hstack=inputs=3[out]"
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", filter_complex, "-map", "[out]", "-frames:v", "1", str(destination)
    ], timeout=90)
    return bool(result and result.returncode == 0 and destination.exists())


def reference_images(folder: Path) -> list[Path]:
    result: list[Path] = []
    for machine in MACHINES[:-1]:
        machine_folder = folder / machine
        if not machine_folder.exists():
            continue
        image = next((p for p in machine_folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}), None)
        if image:
            result.append(image)
    return result


def image_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


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
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ollama ne répond pas correctement : {exc}") from exc


def analyze_sheet(args: argparse.Namespace, sheet: Path, refs: list[Path]) -> dict:
    prompt = """
Analyse cette planche de trois images successives d'une vidéo événementielle.
Donne une note globale et repère les sourires, réactions, énergie, qualité visuelle
et la machine visible : Photobooth, VogueBooth, 360Booth, MiroirBooth ou Aucune.
Les éventuelles images suivantes sont des références des vraies machines.
Réponds uniquement en JSON avec les clés : score, machine, smile, reaction,
energy, quality, duration, description. Toutes les notes sont de 0 à 100.
""".strip()
    images = [image_base64(sheet)] + [image_base64(path) for path in refs[:4]]
    payload = {
        "model": args.model,
        "prompt": prompt,
        "images": images,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }
    response = ollama_request(f"{args.ollama_url.rstrip('/')}/api/generate", payload)
    raw = response.get("response", "{}")
    data = raw if isinstance(raw, dict) else json.loads(raw)
    machine = str(data.get("machine", "Aucune"))
    if machine not in MACHINES:
        machine = "Aucune"
    return {
        "score": max(0, min(100, int(safe_float(data.get("score"))))),
        "machine": machine,
        "smile": max(0, min(100, int(safe_float(data.get("smile"))))),
        "reaction": max(0, min(100, int(safe_float(data.get("reaction"))))),
        "energy": max(0, min(100, int(safe_float(data.get("energy"))))),
        "quality": max(0, min(100, int(safe_float(data.get("quality"))))),
        "duration": max(2.0, min(10.0, safe_float(data.get("duration"), 5.0))),
        "description": str(data.get("description", "Moment événementiel"))[:300],
    }


def analyze_video(
    args: argparse.Namespace,
    ffmpeg: str,
    row: sqlite3.Row,
    work: Path,
    refs: list[Path],
) -> list[dict]:
    path = Path(row["path"])
    duration = safe_float(row["duration"])
    candidates = detect_scene_times(ffmpeg, path, duration, args.candidates)
    results: list[dict] = []

    for index, timestamp in enumerate(candidates, start=1):
        sheet = work / f"{abs(hash(str(path))) % 10**10}_{index}.jpg"
        if not extract_contact_sheet(ffmpeg, path, timestamp, duration, sheet):
            continue
        analysis = analyze_sheet(args, sheet, refs)
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
        "video_path", "start", "end", "score", "machine", "smile",
        "reaction", "energy", "quality", "description"
    ]
    with destination.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def jsx_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def generate_after_effects(rows: list[sqlite3.Row], destination: Path, event_name: str) -> None:
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
    var review = project.items.addComp("SELECTS_REVIEW", 1920, 1080, 1, Math.max(30, clips.length * 6), 25);
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
            var marker = new MarkerValue("Score " + clip.score + " | " + clip.machine + " | " + clip.description);
            layer.property("Marker").setValueAtTime(cursor, marker);
            cursor += duration;
        }}

        var reviewLayer = review.layers.add(footage);
        reviewLayer.startTime = reviewCursor - clip.start;
        reviewLayer.inPoint = reviewCursor;
        reviewLayer.outPoint = reviewCursor + duration;
        fit(reviewLayer, review.width, review.height);
        reviewCursor += duration;
    }}

    alert("Projet créé : " + comp.name + " et SELECTS_REVIEW");
    app.endUndoGroup();
}})();
'''
    destination.write_text(script, encoding="utf-8")


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output).resolve()
    work = output / "work"
    database_path = output / "video_index.sqlite3"

    if not source.exists():
        raise SystemExit(f"ERREUR : dossier introuvable : {source}")

    ffmpeg = require_program("ffmpeg")
    ffprobe = require_program("ffprobe")
    database = Database(database_path)

    try:
        print(f"Indexation : {source}")
        count = 0
        for path in discover_videos(source):
            info = probe_video(ffprobe, path)
            if info and info.duration >= 2:
                database.upsert_video(info)
                count += 1
                if count % 100 == 0:
                    print(f"  {count} vidéos indexées")

        todo = database.next_videos(args.max_videos)
        print(f"Analyse de {len(todo)} vidéo(s).")
        refs = reference_images(Path(args.references))
        work.mkdir(parents=True, exist_ok=True)

        for index, row in enumerate(todo, start=1):
            path = row["path"]
            print(f"[{index}/{len(todo)}] {Path(path).name}")
            try:
                moments = analyze_video(args, ffmpeg, row, work, refs)
                database.save_moments(path, moments)
                print(f"  {len(moments)} moment(s) retenu(s)")
            except Exception as exc:
                database.mark_error(path, str(exc))
                print(f"  ERREUR : {exc}")

        rows = database.all_moments()
        write_csv(rows, output / "moments.csv")
        generate_after_effects(
            rows,
            output / "MSB_Creer_Projet_After_Effects.jsx",
            args.event_name,
        )
        print("\nTerminé.")
        print(f"Base SQLite : {database_path}")
        print(f"CSV : {output / 'moments.csv'}")
        print(f"After Effects : {output / 'MSB_Creer_Projet_After_Effects.jsx'}")
    finally:
        database.close()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
