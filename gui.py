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
        self.geometry("980x840")
        self.minsize(820, 680)

        self.process: subprocess.Popen[str] | None = None
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()

        self.source = tk.StringVar(value=r"P:\Montage-EVENT\ALL_MONTAGE")
        self.output = tk.StringVar(value=str(Path(__file__).parent / "resultats"))
        self.references = tk.StringVar(value=str(Path(__file__).parent / "machine_references"))
        self.provider = tk.StringVar(value="Cloud Ollama (Free)")
        self.model = tk.StringVar(value="gemma4:31b-cloud")
        self.ollama_url = tk.StringVar(value="http://localhost:11434")
        self.max_index = tk.IntVar(value=5)
        self.max_videos = tk.IntVar(value=5)
        self.candidates = tk.IntVar(value=3)
        self.top_moments = tk.IntVar(value=2)
        self.min_score = tk.IntVar(value=58)
        self.skip_index = tk.BooleanVar(value=False)
        self.reset_index = tk.BooleanVar(value=False)
        self.retry_errors = tk.BooleanVar(value=False)
        self.reanalyze = tk.BooleanVar(value=False)
        self.keep_work = tk.BooleanVar(value=False)
        self.search_query = tk.StringVar()
        self.status = tk.StringVar(value="Prêt")

        self._build_ui()
        self.after(100, self._drain_messages)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

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

        ttk.Label(settings, text="Mode IA").grid(row=0, column=5, sticky="w", padx=3)
        provider_box = ttk.Combobox(
            settings,
            textvariable=self.provider,
            values=("Cloud Ollama (Free)", "Local"),
            state="readonly",
            width=18,
        )
        provider_box.grid(row=1, column=5, sticky="ew", padx=3)
        provider_box.bind("<<ComboboxSelected>>", self._provider_changed)

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
        ttk.Checkbutton(
            settings,
            text="Réinitialiser complètement l'indexation",
            variable=self.reset_index,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        presets = ttk.Frame(settings)
        presets.grid(row=3, column=3, columnspan=3, sticky="e", pady=(6, 0))
        ttk.Label(presets, text="Préréglage :").pack(side="left", padx=(0, 5))
        ttk.Button(
            presets, text="Rapide", command=lambda: self._apply_preset("fast")
        ).pack(side="left", padx=2)
        ttk.Button(
            presets, text="Équilibré", command=lambda: self._apply_preset("balanced")
        ).pack(side="left", padx=2)
        ttk.Button(
            presets, text="Qualité", command=lambda: self._apply_preset("quality")
        ).pack(side="left", padx=2)

        ttk.Label(settings, text="Modèle").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.model).grid(
            row=5, column=1, columnspan=3, sticky="ew", padx=3, pady=(8, 0)
        )
        ttk.Label(
            settings,
            text="Cloud Free : connexion Ollama obligatoire",
        ).grid(row=5, column=4, columnspan=2, sticky="e", pady=(8, 0))

        help_frame = ttk.LabelFrame(outer, text="À quoi servent les réglages ?", padding=9)
        help_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        help_text = (
            "Indexer = ajouter les fichiers du NAS à SQLite.  Vidéos à analyser = taille du lot "
            "(0 signifie toutes).  Candidats/vidéo = passages testés : plus ce nombre est grand, "
            "plus l'analyse est précise mais lente.  Moments/vidéo = extraits finalement gardés.\n"
            "Score minimum = sévérité de la sélection.  Réessayer les erreurs reprend les échecs "
            "sans toucher aux réussites.  Réanalyser ignore le cache et recalcule aussi les vidéos "
            "terminées. Réinitialiser vide l'index et les analyses, puis rescannera le dossier choisi "
            "sans supprimer les vidéos originales. "
            "Cloud Ollama utilise Gemma 4 sur les serveurs Ollama ; Local utilise "
            "Gemma3 sur ce PC. Seules les grilles JPEG sont envoyées au cloud, jamais les vidéos.\n"
            "Le CSV détaille maintenant le nombre de personnes, l'action, l'expression, le cadrage, "
            "la confiance de description et les preuves de reconnaissance de la machine. "
            "Une valeur « Indéterminée » signifie que l'IA n'a pas assez d'indices visibles."
        )
        ttk.Label(help_frame, text=help_text, wraplength=910, justify="left").pack(fill="x")

        search_frame = ttk.LabelFrame(outer, text="Retrouver des rushs avec une phrase", padding=9)
        search_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        search_frame.columnconfigure(0, weight=1)
        ttk.Entry(
            search_frame,
            textvariable=self.search_query,
            font=("Segoe UI", 11),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_button = ttk.Button(
            search_frame,
            text="Rechercher dans l'index",
            command=self._search,
        )
        self.search_button.grid(row=0, column=1)
        ttk.Label(
            search_frame,
            text="Exemple : des gens au Photobooth qui rigolent beaucoup",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        console_frame = ttk.LabelFrame(outer, text="Journal", padding=8)
        console_frame.grid(row=4, column=0, sticky="nsew")
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
        actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
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

    def _provider_changed(self, _event=None) -> None:
        if self.provider.get().startswith("Cloud"):
            self.model.set("gemma4:31b-cloud")
            self.status.set("Cloud Ollama Free : vérifie que 'ollama signin' a été exécuté.")
        else:
            self.model.set("gemma3")
            self.status.set("Mode local : l'analyse utilise les ressources de ce PC.")

    def _apply_preset(self, name: str) -> None:
        presets = {
            "fast": (3, 1, 65, "Rapide : moins d'appels Ollama, sélection stricte."),
            "balanced": (5, 2, 60, "Équilibré : recommandé pour les traitements courants."),
            "quality": (8, 3, 58, "Qualité : davantage de passages testés, analyse plus lente."),
        }
        candidates, moments, score, description = presets[name]
        self.candidates.set(candidates)
        self.top_moments.set(moments)
        self.min_score.set(score)
        self.status.set(description)

    def _command(self) -> list[str]:
        command = [
            sys.executable,
            "-u",
            str(Path(__file__).with_name("main.py")),
            self.source.get().strip(),
            "--output", self.output.get().strip(),
            "--references", self.references.get().strip(),
            "--provider", "cloud" if self.provider.get().startswith("Cloud") else "local",
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
        if self.reset_index.get():
            command.append("--reset-index")
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
        if self.reset_index.get():
            if self.skip_index.get():
                messagebox.showerror(
                    "Montage AI",
                    "Décochez « Ignorer l'indexation » pour réinitialiser l'index.",
                )
                return
            confirmed = messagebox.askyesno(
                "Réinitialiser l'indexation",
                "Vider l'index SQLite et toutes les analyses enregistrées ?\n\n"
                "Les vidéos originales ne seront pas supprimées.",
            )
            if not confirmed:
                return

        self._append("\n=== Nouvelle analyse ===\n")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.start(12)
        self.status.set("Analyse en cours…")
        threading.Thread(target=self._run_process, args=(self._command(),), daemon=True).start()

    def _search(self) -> None:
        if self.process is not None:
            return
        query = self.search_query.get().strip()
        if not query:
            messagebox.showerror("Montage AI", "Écrivez la phrase décrivant le rush recherché.")
            return
        command = [
            sys.executable, "-u", str(Path(__file__).with_name("main.py")),
            "--output", self.output.get().strip(), "--export-only",
            "--search", query, "--search-limit", "30",
            "--model", self.model.get().strip(),
        ]
        self._append(f"\n=== Recherche : {query} ===\n")
        self.start_button.configure(state="disabled")
        self.search_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.start(12)
        self.status.set("Recherche dans l'index…")
        threading.Thread(target=self._run_process, args=(command,), daemon=True).start()

    def _run_process(self, command: list[str]) -> None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                command,
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
        self.search_button.configure(state="normal")
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
