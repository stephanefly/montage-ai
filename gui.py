#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Interface graphique Windows pour Montage AI."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class MontageAIApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Montage AI")
        self.geometry("920x720")
        self.minsize(760, 600)

        self.process: subprocess.Popen[str] | None = None
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()

        self.source = tk.StringVar(value=r"P:\Montage-EVENT\ALL_MONTAGE")
        self.output = tk.StringVar(value=str(Path(__file__).parent / "resultats"))
        self.references = tk.StringVar(value=str(Path(__file__).parent / "machine_references"))
        self.model = tk.StringVar(value="qwen2.5vl:7b")
        self.ollama_url = tk.StringVar(value="http://localhost:11434")
        self.max_index = tk.IntVar(value=5)
        self.max_videos = tk.IntVar(value=5)
        self.candidates = tk.IntVar(value=3)
        self.top_moments = tk.IntVar(value=2)
        self.min_score = tk.IntVar(value=58)
        self.skip_index = tk.BooleanVar(value=False)
        self.retry_errors = tk.BooleanVar(value=False)
        self.reanalyze = tk.BooleanVar(value=False)
        self.keep_work = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Prêt")

        self._build_ui()
        self.after(100, self._drain_messages)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        paths = ttk.LabelFrame(outer, text="Dossiers", padding=10)
        paths.grid(row=0, column=0, sticky="ew")
        paths.columnconfigure(1, weight=1)
        self._path_row(paths, 0, "Vidéos", self.source, self._choose_source)
        self._path_row(paths, 1, "Résultats", self.output, self._choose_output)
        self._path_row(paths, 2, "Références", self.references, self._choose_references)

        settings = ttk.LabelFrame(outer, text="Analyse", padding=10)
        settings.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        for column in range(6):
            settings.columnconfigure(column, weight=1)

        numeric_options = (
            ("Fichiers à indexer", self.max_index),
            ("Vidéos à analyser", self.max_videos),
            ("Candidats / vidéo", self.candidates),
            ("Moments / vidéo", self.top_moments),
            ("Score minimum", self.min_score),
        )
        for column, (label, variable) in enumerate(numeric_options):
            ttk.Label(settings, text=label).grid(row=0, column=column, sticky="w", padx=3)
            ttk.Spinbox(settings, from_=0, to=10000, textvariable=variable, width=10).grid(
                row=1, column=column, sticky="ew", padx=3
            )

        ttk.Label(settings, text="Modèle Ollama").grid(row=0, column=5, sticky="w", padx=3)
        ttk.Entry(settings, textvariable=self.model).grid(row=1, column=5, sticky="ew", padx=3)

        ttk.Checkbutton(settings, text="Ignorer l'indexation", variable=self.skip_index).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Checkbutton(settings, text="Réessayer les erreurs", variable=self.retry_errors).grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Checkbutton(settings, text="Conserver les fichiers temporaires", variable=self.keep_work).grid(
            row=2, column=4, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Checkbutton(
            settings,
            text="Réanalyser sans utiliser le cache",
            variable=self.reanalyze,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        console_frame = ttk.LabelFrame(outer, text="Journal", padding=8)
        console_frame.grid(row=2, column=0, sticky="nsew")
        console_frame.columnconfigure(0, weight=1)
        console_frame.rowconfigure(0, weight=1)
        self.console = tk.Text(
            console_frame,
            wrap="word",
            state="disabled",
            background="#101418",
            foreground="#e8eef2",
            insertbackground="white",
            font=("Consolas", 10),
        )
        scrollbar = ttk.Scrollbar(console_frame, command=self.console.yview)
        self.console.configure(yscrollcommand=scrollbar.set)
        self.console.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        actions.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(actions, text="Lancer", command=self._start)
        self.stop_button = ttk.Button(actions, text="Arrêter", command=self._stop, state="disabled")
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=8)
        self.stop_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(actions, textvariable=self.status).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _path_row(self, parent: ttk.LabelFrame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label, width=12).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(parent, text="Parcourir…", command=command).grid(row=row, column=2, pady=3)

    def _choose_source(self) -> None:
        value = filedialog.askdirectory(title="Choisir le dossier des vidéos")
        if value:
            self.source.set(value)

    def _choose_output(self) -> None:
        value = filedialog.askdirectory(title="Choisir le dossier des résultats")
        if value:
            self.output.set(value)

    def _choose_references(self) -> None:
        value = filedialog.askdirectory(title="Choisir le dossier des références")
        if value:
            self.references.set(value)

    def _command(self) -> list[str]:
        command = [
            sys.executable,
            "-u",
            str(Path(__file__).with_name("main.py")),
            self.source.get().strip(),
            "--output", self.output.get().strip(),
            "--references", self.references.get().strip(),
            "--model", self.model.get().strip(),
            "--ollama-url", self.ollama_url.get().strip(),
            "--max-index", str(self.max_index.get()),
            "--max-videos", str(self.max_videos.get()),
            "--candidates", str(self.candidates.get()),
            "--top-moments", str(self.top_moments.get()),
            "--min-score", str(self.min_score.get()),
        ]
        if self.skip_index.get():
            command.append("--skip-index")
        if self.retry_errors.get():
            command.append("--retry-errors")
        if self.reanalyze.get():
            command.append("--reanalyze")
        if self.keep_work.get():
            command.append("--keep-work")
        return command

    def _start(self) -> None:
        if self.process is not None:
            return
        if not self.source.get().strip() or not self.output.get().strip():
            messagebox.showerror("Montage AI", "Les dossiers vidéos et résultats sont obligatoires.")
            return

        self._append("\n=== Nouvelle analyse ===\n")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.start(12)
        self.status.set("Analyse en cours…")
        threading.Thread(target=self._run_process, daemon=True).start()

    def _run_process(self) -> None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                self._command(),
                cwd=Path(__file__).parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.messages.put(("line", line))
            return_code = self.process.wait()
            self.messages.put(("done", return_code))
        except OSError as exc:
            self.messages.put(("error", str(exc)))

    def _stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.status.set("Arrêt demandé…")
            self.process.terminate()

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "line":
                    self._append(str(value))
                elif kind == "done":
                    self._finish(int(value))
                elif kind == "error":
                    self._append(f"ERREUR : {value}\n")
                    self._finish(1)
        except queue.Empty:
            pass
        self.after(100, self._drain_messages)

    def _append(self, text: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.configure(state="disabled")

    def _finish(self, return_code: int) -> None:
        self.process = None
        self.progress.stop()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status.set("Terminé" if return_code == 0 else f"Arrêté avec le code {return_code}")

    def _on_close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno("Montage AI", "Une analyse est en cours. L'arrêter et fermer ?"):
                return
            self.process.terminate()
        self.destroy()


if __name__ == "__main__":
    MontageAIApp().mainloop()
