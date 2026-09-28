"""Simple Music Station - lightweight desktop music project manager.

The application intentionally uses only Python's standard library. Optional
audio backends (pygame and sounddevice) are detected at runtime when available.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import threading
import uuid
import wave
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_NAME = "Simple Music Station"
ROOT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)
SUPPORTED_TYPES = ("WAV", "MP3", "MIDI")

try:
    import pygame  # type: ignore
except ImportError:
    pygame = None

try:
    import sounddevice as sd  # type: ignore
except ImportError:
    sd = None


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in value).strip()
    return cleaned or "Proyecto sin nombre"


class ProjectStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def list_projects(self) -> list[dict]:
        result = []
        for path in sorted(self.base_dir.iterdir()):
            metadata = path / "project.json"
            if path.is_dir() and metadata.exists():
                try:
                    data = json.loads(metadata.read_text(encoding="utf-8"))
                    data["folder"] = str(path)
                    result.append(data)
                except (OSError, json.JSONDecodeError):
                    continue
        return result

    def create(self, name: str) -> dict:
        project_id = uuid.uuid4().hex[:10]
        folder = self.base_dir / f"{safe_name(name)}_{project_id}"
        (folder / "assets").mkdir(parents=True)
        data = {"id": project_id, "name": name.strip() or "Proyecto sin nombre", "created": now(), "updated": now(), "tracks": []}
        self.save(folder, data)
        data["folder"] = str(folder)
        return data

    def save(self, folder: Path, data: dict) -> None:
        data["updated"] = now()
        (folder / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def delete(self, project: dict) -> None:
        shutil.rmtree(project["folder"])

    def import_project(self, source: str) -> dict:
        source_path = Path(source)
        metadata = source_path / "project.json"
        if not metadata.exists():
            raise ValueError("La carpeta seleccionada no contiene project.json.")
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data["id"] = uuid.uuid4().hex[:10]
        folder = self.base_dir / f"{safe_name(data.get('name', 'Proyecto importado'))}_{data['id']}"
        shutil.copytree(source_path, folder)
        self.save(folder, data)
        data["folder"] = str(folder)
        return data


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x650")
        self.minsize(760, 500)
        self.configure(bg="#141821")
        self.store = ProjectStore(PROJECTS_DIR)
        self.editor = None
        self.player_ready = False
        self.current_sound = None
        self._init_audio()
        self._styles()
        self._build_project_screen()

    def _init_audio(self):
        if pygame:
            try:
                pygame.mixer.init()
                pygame.mixer.set_num_channels(32)
                self.player_ready = True
            except pygame.error:
                pass

    def _styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#141821")
        style.configure("Card.TFrame", background="#202633")
        style.configure("TLabel", background="#141821", foreground="#e8edf5", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), foreground="#ffffff")
        style.configure("Subtitle.TLabel", foreground="#9da8bb")
        style.configure("CardTitle.TLabel", background="#202633", foreground="#ffffff", font=("Segoe UI", 12, "bold"))
        style.configure("CardText.TLabel", background="#202633", foreground="#aeb8c9")
        style.configure("Accent.TButton", background="#6c5ce7", foreground="white", padding=(14, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#8174f0")])
        style.configure("Small.TButton", padding=(8, 4))

    def _clear(self):
        for child in self.winfo_children():
            child.destroy()

    def _build_project_screen(self):
        self._clear()
        header = ttk.Frame(self, padding=(32, 28, 32, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Simple Music Station", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="＋ Nuevo proyecto", style="Accent.TButton", command=self.create_project).pack(side="right")
        ttk.Label(self, text="Tus proyectos de música", style="Subtitle.TLabel").pack(anchor="w", padx=34)

        toolbar = ttk.Frame(self, padding=(32, 18, 32, 8))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Importar proyecto", command=self.import_project).pack(side="left")
        ttk.Button(toolbar, text="Actualizar", command=self._build_project_screen).pack(side="left", padx=8)

        body = ttk.Frame(self, padding=(32, 8))
        body.pack(fill="both", expand=True)
        projects = self.store.list_projects()
        if not projects:
            ttk.Label(body, text="Todavía no hay proyectos. Crea uno para empezar a organizar tus pistas.", style="Subtitle.TLabel").pack(pady=70)
            return
        canvas = tk.Canvas(body, bg="#141821", highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        cards = ttk.Frame(canvas)
        cards.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=cards, anchor="nw", width=850)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for project in projects:
            self._project_card(cards, project)

    def _project_card(self, parent, project):
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.pack(fill="x", pady=6)
        info = ttk.Frame(card, style="Card.TFrame")
        info.pack(side="left", fill="x", expand=True)
        ttk.Label(info, text=project.get("name", "Sin nombre"), style="CardTitle.TLabel").pack(anchor="w")
        count = len(project.get("tracks", []))
        ttk.Label(info, text=f"{count} pista(s)  •  {project.get('folder', '')}", style="CardText.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Button(card, text="Editar", style="Accent.TButton", command=lambda p=project: self.open_editor(p)).pack(side="right", padx=(8, 0))
        ttk.Button(card, text="Eliminar", style="Small.TButton", command=lambda p=project: self.delete_project(p)).pack(side="right")

    def create_project(self):
        name = simpledialog.askstring("Nuevo proyecto", "Nombre del proyecto:", parent=self)
        if name and name.strip():
            self.open_editor(self.store.create(name.strip()))

    def import_project(self):
        source = filedialog.askdirectory(title="Selecciona la carpeta del proyecto")
        if not source:
            return
        try:
            project = self.store.import_project(source)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("No se pudo importar", str(exc), parent=self)
            return
        self.open_editor(project)

    def delete_project(self, project):
        if messagebox.askyesno("Eliminar proyecto", f"¿Eliminar '{project.get('name')}' y todos sus assets?", parent=self):
            try:
                self.store.delete(project)
                self._build_project_screen()
            except OSError as exc:
                messagebox.showerror("Error", str(exc), parent=self)

    def open_editor(self, project):
        if self.editor:
            self.editor.destroy()
        self.editor = Editor(self, project, self.store)

    def stop_audio(self):
        if self.player_ready:
            pygame.mixer.music.stop()
            pygame.mixer.stop()


class Editor(tk.Toplevel):
    def __init__(self, app: App, project: dict, store: ProjectStore):
        super().__init__(app)
        self.app, self.project, self.store = app, project, store
        self.folder = Path(project["folder"])
        self.play_queue = []
        self.play_index = 0
        self.playing_all = False
        self.play_started_at = None
        self.active_channels = []
        self.play_plan = []
        self.pending_segments = []
        self.recording_events = {}
        self.record_after_id = None
        self.record_started_at = None
        self.record_start_position = 0
        self.recording_segments = {}
        self.record_dialog = None
        self.selected_segment = None
        self.dragging_segment = None
        self.volume_labels = {}
        self.volume_texts = {}
        self.waveform_canvases = {}
        self.timeline_scale = None
        self.continuous_playhead = None
        self.queue_after_id = None
        self.timeline_after_id = None
        self.timeline_duration = tk.IntVar(value=int(self.project.get("duration", 300)))
        self.timeline_position = tk.DoubleVar(value=0)
        self.title(f"{APP_NAME} · {project['name']}")
        self.geometry("980x680")
        self.configure(bg="#141821")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._build()

    def _build(self):
        top = ttk.Frame(self, padding=(24, 18, 24, 10))
        top.pack(fill="x")
        ttk.Button(top, text="‹", width=3, command=self.close).pack(side="left")
        ttk.Label(top, text=f"  {self.project['name']}", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="▣", width=3, style="Accent.TButton", command=self.save).pack(side="right")

        menu = ttk.Frame(self, padding=(24, 4, 24, 16))
        menu.pack(fill="x")
        for text, command in (("▶", self.play_all), ("⏸", self.pause), ("■", self.stop)):
            ttk.Button(menu, text=text, width=3, style="Small.TButton", command=command).pack(side="left", padx=(0, 4))
        ttk.Label(menu, text="Pistas", style="Subtitle.TLabel").pack(side="right")

        body = ttk.Frame(self, padding=(24, 0))
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#141821", highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.track_frame = ttk.Frame(self.canvas)
        self.track_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.track_frame, anchor="nw", width=880)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.render_tracks()
        footer = ttk.Frame(self, padding=(24, 10, 24, 18))
        footer.pack(fill="x")
        ttk.Button(footer, text="＋", width=3, style="Accent.TButton", command=self.add_track).pack(side="left")
        ttk.Button(footer, text="✕", width=3, style="Small.TButton", command=self.delete_selected_segment).pack(side="left", padx=(5, 0))
        timeline_box = ttk.Frame(footer)
        timeline_box.pack(side="left", fill="x", expand=True, padx=(18, 0))
        timeline_row = ttk.Frame(timeline_box)
        timeline_row.pack(fill="x")
        ttk.Label(timeline_row, text="Línea de tiempo").pack(side="left")
        self.timeline_scale = ttk.Scale(timeline_row, from_=0, to=self.timeline_duration.get(), variable=self.timeline_position, command=self._timeline_changed)
        self.timeline_scale.pack(side="left", fill="x", expand=True, padx=10)
        self.timeline_scale.bind("<Button-1>", self.select_timeline_position)
        self.timeline_scale.bind("<B1-Motion>", self.select_timeline_position)
        ttk.Label(timeline_row, text="Duración (seg)").pack(side="left")
        duration_spin = tk.Spinbox(timeline_row, from_=60, to=3600, width=6, textvariable=self.timeline_duration, command=self._duration_changed)
        duration_spin.pack(side="left", padx=(5, 0))
        duration_spin.bind("<Return>", lambda _event: self._duration_changed())
        duration_spin.bind("<FocusOut>", lambda _event: self._duration_changed())
        self.timeline_label = ttk.Label(timeline_box, text="00:00 / 05:00", style="Subtitle.TLabel")
        self.timeline_label.pack(anchor="e")
        self.continuous_playhead = tk.Frame(self, bg="#ffcf5c", width=2, height=2)
        self.after_idle(self._update_continuous_playhead)

    def render_tracks(self):
        self.waveform_canvases = {}
        self.volume_texts = {}
        for child in self.track_frame.winfo_children():
            child.destroy()
        if not self.project.get("tracks"):
            ttk.Label(self.track_frame, text="No hay pistas todavía. Crea una pista vacía para comenzar.", style="Subtitle.TLabel").pack(pady=75)
        for track in self.project.get("tracks", []):
            self.normalize_track(track)
            self.track_card(track)
        if self.continuous_playhead:
            self.after_idle(self._update_continuous_playhead)

    def normalize_track(self, track):
        """Migrate projects created before tracks supported multiple segments."""
        if "segments" not in track:
            track["segments"] = []
            if track.get("file"):
                track["segments"].append({
                    "id": uuid.uuid4().hex[:8],
                    "file": track["file"],
                    "offset": float(track.get("offset", 0)),
                })

    def segments_for(self, track):
        self.normalize_track(track)
        return track["segments"]

    def track_card(self, track):
        card = ttk.Frame(self.track_frame, style="Card.TFrame", padding=14, width=880, height=260)
        card.pack(fill="x", pady=5)
        card.pack_propagate(False)
        controls = ttk.Frame(card, style="Card.TFrame", width=125, height=232)
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        controls.grid_propagate(False)
        ttk.Label(controls, text=track["name"], style="CardTitle.TLabel", wraplength=120).pack(anchor="w")
        ttk.Label(controls, text=track["type"], style="CardText.TLabel").pack(anchor="w", pady=(2, 6))
        tk.Button(controls, text="▶", width=3, height=1, bg="#6c5ce7", fg="white", activebackground="#8174f0", activeforeground="white", relief="flat", bd=0, font=("Segoe UI", 11, "bold"), command=lambda t=track: self.play_track(t)).pack(fill="x", pady=2)
        tk.Button(controls, text="●", width=3, height=1, bg="#2d8f83", fg="white", activebackground="#43b5a5", activeforeground="white", relief="flat", bd=0, font=("Segoe UI", 11, "bold"), command=lambda t=track: self.record_track(t)).pack(fill="x", pady=2)
        tk.Button(controls, text="✕", width=3, height=1, bg="#b64b5b", fg="white", activebackground="#d26170", activeforeground="white", relief="flat", bd=0, font=("Segoe UI", 11, "bold"), command=lambda t=track: self.remove_track(t)).pack(fill="x", pady=2)
        ttk.Label(controls, text="Volumen", style="CardText.TLabel").pack(pady=(8, 0))
        volume_value = tk.IntVar(value=max(1, min(100, int(track.get("volume", 100)))))
        volume_scale = tk.Scale(controls, from_=1, to=100, orient="horizontal", length=105, width=10, showvalue=True, highlightthickness=0, bg="#202633", fg="#e8edf5", troughcolor="#3b4353", command=lambda value, t=track, v=volume_value: self.set_volume(t, v, value))
        volume_scale.set(volume_value.get())
        volume_scale.pack()
        volume_text = tk.StringVar(value=f"Volumen: {volume_value.get()}%")
        volume_label = ttk.Label(controls, textvariable=volume_text, style="CardText.TLabel")
        volume_label.pack()
        self.volume_labels[track["id"]] = volume_scale
        self.volume_texts[track["id"]] = volume_text

        visual = ttk.Frame(card, style="Card.TFrame")
        visual.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(1, weight=1)
        card.rowconfigure(0, weight=1)
        filenames = ", ".join(s["file"] for s in self.segments_for(track) if s.get("file"))
        if filenames:
            ttk.Label(visual, text=filenames, style="CardText.TLabel").pack(anchor="w")
        self.draw_track_visual(visual, track)

    def draw_track_visual(self, parent, track):
        width, height = 650, 105
        canvas = tk.Canvas(parent, width=width, height=height, bg="#171c27", highlightthickness=0)
        canvas.pack(fill="x", expand=True, pady=(5, 0))
        canvas.bind("<Button-1>", lambda event, c=canvas, t=track: self.select_track_segment(event, c, t))
        canvas.bind("<B1-Motion>", lambda event, c=canvas, t=track: self.move_selected_segment(event, c, t))
        canvas.bind("<ButtonRelease-1>", lambda _event: self.finish_segment_move())
        project_duration = max(1, self.timeline_duration.get())
        self.waveform_canvases[track["id"]] = (canvas, width, height, width, 0)
        segments = self.segments_for(track)
        if not segments:
            canvas.create_text(width // 2, height // 2, text="Pista vacía — graba o importa un segmento", fill="#8995aa")
            return
        for segment in segments:
            segment_track = {"type": track["type"], "file": segment.get("file")}
            samples, caption = self.audio_samples(segment_track)
            length = self.segment_duration(track, segment)
            start_x = min(width, int(width * float(segment.get("offset", 0)) / project_duration))
            segment_width = max(12, min(width - start_x, int(width * length / project_duration))) if length else 12
            if not samples:
                canvas.create_rectangle(start_x, 12, start_x + segment_width, height - 12, outline="#8174f0", tags=f"segment_{segment['id']}")
                continue
            center = height // 2
            for relative_x in range(segment_width):
                index = min(len(samples) - 1, int(relative_x * len(samples) / segment_width))
                amplitude = max(2, int(samples[index] * (height * 0.42)))
                x = start_x + relative_x
                color = "#ffcf5c" if self.selected_segment and self.selected_segment[1] is segment else "#8174f0"
                canvas.create_line(x, center - amplitude, x, center + amplitude, fill=color, tags=f"segment_{segment['id']}")
            canvas.create_line(start_x, center, start_x + segment_width, center, fill="#3e4657", tags=f"segment_{segment['id']}")
            canvas.create_rectangle(start_x, 3, start_x + segment_width, height - 3, outline="#ffcf5c" if self.selected_segment and self.selected_segment[1] is segment else "#333b4b", tags=f"segment_{segment['id']}")

    def segment_duration(self, track, segment):
        if not segment.get("file"):
            return 0
        return self.track_duration({"type": track["type"], "file": segment["file"]})

    def track_duration(self, track):
        path = self.folder / "assets" / track["file"] if track.get("file") else None
        if not path or not path.exists():
            return 0
        try:
            if track["type"] == "WAV":
                with wave.open(str(path), "rb") as source:
                    return source.getnframes() / max(1, source.getframerate())
            if track["type"] == "MP3" and self.app.player_ready:
                return pygame.mixer.Sound(str(path)).get_length()
        except Exception:
            pass
        return 0

    def audio_samples(self, track):
        path = self.folder / "assets" / track["file"] if track.get("file") else None
        if not path or not path.exists():
            return [], "Pista vacía — sin señal todavía"
        if track["type"] == "MIDI":
            try:
                data = path.read_bytes()
                events = [1.0 if (data[i] & 0xF0) == 0x90 and i + 2 < len(data) and data[i + 2] else 0.15 for i in range(len(data) - 2)]
                return events[-180:] or [0.15], "MIDI — actividad de notas"
            except OSError:
                return [], "No se pudo leer el MIDI"
        try:
            if track["type"] == "WAV":
                with wave.open(str(path), "rb") as source:
                    frames = source.readframes(source.getnframes())
                    width = source.getsampwidth()
                step = max(width, len(frames) // 180 or 1)
                samples = []
                for offset in range(0, len(frames), step):
                    block = frames[offset:offset + step]
                    if width == 2:
                        values = [abs(int.from_bytes(block[i:i + 2], "little", signed=True)) / 32768 for i in range(0, len(block) - 1, 2)]
                    else:
                        values = [abs(value - 128) / 128 for value in block]
                    samples.append(min(1.0, max(values or [0])))
                return samples[:180], ""
            if self.app.player_ready:
                sound = pygame.mixer.Sound(str(path))
                raw = sound.get_raw()
                step = max(1, len(raw) // 180)
                values = [sum(abs(value - 128) for value in raw[i:i + step:2]) / max(1, step * 128) for i in range(0, len(raw), step)]
                return [min(1.0, value) for value in values[:180]], ""
        except Exception:
            pass
        return [], "Archivo de audio — señal no disponible"

    def add_track(self):
        """Show one form for all track creation choices."""
        dialog = tk.Toplevel(self)
        dialog.title("Crear pista")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        track_type = tk.StringVar(value="WAV")
        default_name = f"Pista {len(self.project['tracks']) + 1}"
        track_name = tk.StringVar(value=default_name)
        selected_file = {"path": None}
        file_label = tk.StringVar(value="Sin archivo: pista vacía")

        form = ttk.Frame(dialog, padding=22)
        form.pack(fill="both", expand=True)
        ttk.Label(form, text="Nueva pista", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))
        ttk.Label(form, text="Nombre").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 14))
        ttk.Entry(form, textvariable=track_name, width=36).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Tipo de pista").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 14))
        type_combo = ttk.Combobox(form, textvariable=track_type, values=SUPPORTED_TYPES, state="readonly", width=33)
        type_combo.grid(row=2, column=1, sticky="ew", pady=6)

        def choose_file():
            extension = track_type.get().lower()
            source = filedialog.askopenfilename(
                parent=dialog,
                title=f"Importar archivo {track_type.get()}",
                filetypes=[(f"Archivos {track_type.get()}", f"*.{extension}")],
            )
            if source:
                selected_file["path"] = Path(source)
                file_label.set(f"Archivo: {selected_file['path'].name}")
                if not track_name.get().strip() or track_name.get() == default_name:
                    track_name.set(selected_file["path"].stem)

        def update_file_filter(*_):
            selected_file["path"] = None
            file_label.set("Sin archivo: pista vacía")

        type_combo.bind("<<ComboboxSelected>>", update_file_filter)
        import_box = ttk.Frame(form)
        import_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 4))
        ttk.Button(import_box, text="Importar desde archivo...", command=choose_file).pack(side="left")
        ttk.Label(import_box, textvariable=file_label, style="Subtitle.TLabel").pack(side="left", padx=10)

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="right", padx=(8, 0))

        def create():
            name = track_name.get().strip()
            if not name:
                messagebox.showwarning("Falta el nombre", "Escribe un nombre para la pista.", parent=dialog)
                return
            source = selected_file["path"]
            filename = None
            if source:
                expected_suffix = f".{track_type.get().lower()}"
                if source.suffix.lower() != expected_suffix:
                    messagebox.showerror("Tipo incorrecto", f"El archivo debe ser de tipo {track_type.get()}.", parent=dialog)
                    return
                filename = f"{uuid.uuid4().hex[:8]}{expected_suffix}"
                try:
                    shutil.copy2(source, self.folder / "assets" / filename)
                except OSError as exc:
                    messagebox.showerror("No se pudo importar", str(exc), parent=dialog)
                    return
            self.project.setdefault("tracks", []).append({"id": uuid.uuid4().hex[:8], "name": name, "type": track_type.get(), "file": None, "segments": ([{"id": uuid.uuid4().hex[:8], "file": filename, "offset": 0}] if filename else [])})
            self.save()
            self.render_tracks()
            dialog.destroy()

        ttk.Button(buttons, text="Crear pista", style="Accent.TButton", command=create).pack(side="right")
        dialog.bind("<Return>", lambda _event: create())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.wait_window()

    def remove_track(self, track):
        if not messagebox.askyesno("Eliminar pista", f"¿Eliminar '{track['name']}'?", parent=self):
            return
        for segment in self.segments_for(track):
            if segment.get("file"):
                try:
                    (self.folder / "assets" / segment["file"]).unlink(missing_ok=True)
                except OSError:
                    pass
        self.project["tracks"].remove(track)
        self.save()
        self.render_tracks()

    def play_track(self, track):
        start_position = max(0, float(self.timeline_position.get()))
        plan = [(track, segment) for segment in self.segments_for(track) if segment.get("file")]
        if not plan:
            messagebox.showinfo("Pista vacía", "Esta pista todavía no tiene un archivo de audio.", parent=self)
        elif not self.app.player_ready:
            messagebox.showinfo("Reproducción", "Instala pygame para reproducir WAV/MP3: pip install pygame", parent=self)
        elif track["type"] == "MIDI":
            messagebox.showinfo("MIDI", "La reproducción MIDI estará disponible en una próxima versión.", parent=self)
        else:
            self.start_playback_plan(plan, start_position)

    def sound_from_position(self, path, position):
        """Load audio and return a Sound containing only the requested tail."""
        source = pygame.mixer.Sound(str(path))
        if position <= 0:
            return source
        frequency, sample_format, channels = pygame.mixer.get_init()
        bytes_per_sample = max(1, abs(sample_format) // 8)
        bytes_per_frame = bytes_per_sample * channels
        raw = source.get_raw()
        offset = int(position * frequency) * bytes_per_frame
        if offset >= len(raw):
            return None
        return pygame.mixer.Sound(buffer=raw[offset:])

    def play_all(self):
        tracks = [(t, s) for t in self.project.get("tracks", []) for s in self.segments_for(t) if s.get("file") and t["type"] in ("WAV", "MP3") and (self.folder / "assets" / s["file"]).exists()]
        if tracks and self.app.player_ready:
            start_position = max(0, float(self.timeline_position.get()))
            pygame.mixer.set_num_channels(max(32, len(tracks) + 4))
            self.start_playback_plan(tracks, start_position)
        elif tracks:
            messagebox.showinfo("Reproducir todo", "Instala pygame para reproducir WAV/MP3: pip install pygame", parent=self)
        else:
            messagebox.showinfo("Reproducir todo", "No hay pistas WAV o MP3 con archivos para reproducir.", parent=self)

    def start_playback_plan(self, plan, start_position):
        self._stop_channels(reset_timeline=False)
        self.play_plan = list(plan)
        self.pending_segments = list(plan)
        self.active_channels = []
        self.playing_all = True
        self.play_started_at = time.monotonic() - start_position
        self.timeline_position.set(start_position)
        self._poll_playback()

    def _poll_playback(self):
        if not self.active_channels and not self.pending_segments:
            return
        if self.play_started_at is not None:
            elapsed = min(self.timeline_duration.get(), time.monotonic() - self.play_started_at)
            self.timeline_position.set(elapsed)
            self._timeline_changed(elapsed)
            self._move_playheads(elapsed)
            if elapsed >= self.timeline_duration.get():
                self.pending_segments = []
            still_pending = []
            if elapsed < self.timeline_duration.get():
                for track, segment in self.pending_segments:
                    if float(segment.get("offset", 0)) > elapsed:
                        still_pending.append((track, segment))
                        continue
                    try:
                        local_position = max(0, elapsed - float(segment.get("offset", 0)))
                        sound = self.sound_from_position(self.folder / "assets" / segment["file"], local_position)
                        if sound is None:
                            continue
                        channel = pygame.mixer.find_channel(True)
                        channel.set_volume(track.get("volume", 100) / 100)
                        channel.play(sound)
                        self.active_channels.append((track, segment, channel, sound))
                    except Exception:
                        continue
            self.pending_segments = still_pending
        self.active_channels = [item for item in self.active_channels if item[2].get_busy()]
        if self.active_channels or self.pending_segments:
            self.queue_after_id = self.after(80, self._poll_playback)
        else:
            self.playing_all = False

    def _stop_channels(self, reset_timeline=True):
        self.playing_all = False
        self.play_started_at = None
        if self.queue_after_id:
            self.after_cancel(self.queue_after_id)
            self.queue_after_id = None
        if self.app.player_ready:
            pygame.mixer.stop()
        self.active_channels = []
        self.pending_segments = []
        self.play_plan = []
        if reset_timeline:
            self.timeline_position.set(0)
            self._move_playheads(0)

    def _move_playheads(self, elapsed):
        duration = max(1, self.timeline_duration.get())
        x_ratio = min(1, max(0, elapsed / duration))
        self._update_continuous_playhead()

    def _update_continuous_playhead(self):
        """Extend the playhead from the timeline down to the first track."""
        if not self.continuous_playhead or not self.timeline_scale or not self.waveform_canvases:
            return
        first = next(iter(self.waveform_canvases.values()))[0]
        if not first.winfo_ismapped() or not self.timeline_scale.winfo_ismapped():
            return
        duration = max(1, self.timeline_duration.get())
        ratio = min(1, max(0, self.timeline_position.get() / duration))
        active_width = next(iter(self.waveform_canvases.values()))[3]
        start_x = next(iter(self.waveform_canvases.values()))[4]
        x = first.winfo_rootx() - self.winfo_rootx() + start_x + max(0, min(active_width, int(first.winfo_width() * ratio) - start_x))
        first_top = first.winfo_rooty() - self.winfo_rooty()
        timeline_top = self.timeline_scale.winfo_rooty() - self.winfo_rooty()
        top = min(first_top, timeline_top)
        height = max(2, abs(timeline_top - first_top))
        self.continuous_playhead.place(x=x, y=top, width=2, height=height)

    def set_volume(self, track, value_var, value):
        value = max(1, min(100, int(float(value))))
        value_var.set(value)
        track["volume"] = value
        if track["id"] in self.volume_texts:
            self.volume_texts[track["id"]].set(f"Volumen: {value}%")
        for active_track, _segment, channel, _sound in self.active_channels:
            if active_track is track:
                channel.set_volume(value / 100)
        self.save()

    def _duration_changed(self):
        try:
            duration = max(60, min(3600, int(self.timeline_duration.get())))
        except (ValueError, tk.TclError):
            duration = 300
        self.timeline_duration.set(duration)
        self.project["duration"] = duration
        self.save()
        self.timeline_position.set(min(self.timeline_position.get(), duration))
        self.timeline_label.configure(text=f"{self._clock(self.timeline_position.get())} / {self._clock(duration)}")

    def _timeline_changed(self, value):
        duration = max(1, self.timeline_duration.get())
        position = min(duration, max(0, float(value)))
        self.timeline_position.set(position)
        self.timeline_label.configure(text=f"{self._clock(position)} / {self._clock(duration)}")
        self._update_continuous_playhead()

    def select_track_segment(self, event, canvas, track):
        project_duration = max(1, self.timeline_duration.get())
        click_position = max(0, min(project_duration, event.x / max(1, canvas.winfo_width()) * project_duration))
        selected = None
        for segment in self.segments_for(track):
            start = float(segment.get("offset", 0))
            end = start + self.segment_duration(track, segment)
            if start <= click_position <= end:
                selected = segment
                break
        if selected:
            self.selected_segment = (track, selected)
            self.dragging_segment = [track, selected, click_position - float(selected.get("offset", 0))]
            self.timeline_position.set(click_position)
            self._timeline_changed(click_position)
            self.seek_active_playback(click_position)

    def move_selected_segment(self, event, canvas, track):
        if not self.dragging_segment or self.dragging_segment[0] is not track:
            return
        _, segment, grab_offset = self.dragging_segment
        project_duration = max(1, self.timeline_duration.get())
        position = max(0, min(project_duration, event.x / max(1, canvas.winfo_width()) * project_duration))
        length = self.segment_duration(track, segment)
        new_offset = max(0, min(max(0, project_duration - length), position - grab_offset))
        old_offset = float(segment.get("offset", 0))
        dx = int((new_offset - old_offset) / project_duration * canvas.winfo_width())
        if dx:
            canvas.move(f"segment_{segment['id']}", dx, 0)
            segment["offset"] = new_offset
            self.timeline_position.set(new_offset)
            self._timeline_changed(new_offset)

    def finish_segment_move(self):
        if self.dragging_segment:
            self.save()
            self.dragging_segment = None
            if self.play_plan and not self.recording_events:
                self.seek_active_playback(self.timeline_position.get())

    def delete_selected_segment(self):
        if not self.selected_segment:
            return
        track, segment = self.selected_segment
        if segment.get("file"):
            try:
                (self.folder / "assets" / segment["file"]).unlink(missing_ok=True)
            except OSError:
                pass
        self.segments_for(track).remove(segment)
        self.selected_segment = None
        self.dragging_segment = None
        self.save()
        self.render_tracks()

    def select_timeline_position(self, event):
        if not self.timeline_scale:
            return
        width = max(1, self.timeline_scale.winfo_width())
        position = max(0, min(1, event.x / width)) * self.timeline_duration.get()
        self.timeline_position.set(position)
        self._timeline_changed(position)
        self.seek_active_playback(position)

    def select_track_position(self, event, canvas, track):
        active_width = self.waveform_canvases.get(track["id"], (canvas, 1, 1, 1))[3]
        track_length = self.track_duration(track)
        if not track_length:
            return
        position = max(0, min(active_width, event.x)) / max(1, active_width) * track_length
        position = min(self.timeline_duration.get(), position)
        self.timeline_position.set(position)
        self._timeline_changed(position)
        self.seek_active_playback(position)

    def seek_active_playback(self, position):
        """Restart currently playing channels at the newly selected position."""
        if not self.play_plan or self.recording_events:
            return
        self.start_playback_plan(self.play_plan, position)

    @staticmethod
    def _clock(seconds):
        seconds = int(seconds)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def pause(self):
        if self.app.player_ready:
            pygame.mixer.pause()

    def stop(self):
        self._stop_channels()
        self.app.stop_audio()

    def record_track(self, track):
        if track["type"] != "WAV":
            messagebox.showinfo("Grabación", "La grabación directa está disponible para pistas WAV.", parent=self)
            return
        if sd is None:
            messagebox.showinfo("Grabación", "Instala sounddevice y numpy para grabar: pip install sounddevice numpy", parent=self)
            return
        try:
            sd.query_devices(kind="input")
        except Exception as exc:
            messagebox.showerror("Micrófono no disponible", f"No se pudo abrir un dispositivo de entrada.\n\n{exc}", parent=self)
            return
        if self.recording_events:
            messagebox.showinfo("Grabación en curso", "Detén la grabación actual desde su ventana flotante antes de iniciar otra.", parent=self)
            return
        start_position = max(0, float(self.timeline_position.get()))
        dialog = tk.Toplevel(self)
        dialog.title("Grabación")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        self.record_dialog = dialog
        status = tk.StringVar(value=f"Listo para grabar desde {self._clock(start_position)}")
        content = ttk.Frame(dialog, padding=22)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Nueva grabación", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(content, text="Se creará un segmento WAV nuevo. No se sobrescribirá ningún segmento existente.", wraplength=330).pack(anchor="w", pady=(10, 8))
        ttk.Label(content, textvariable=status, style="Subtitle.TLabel").pack(anchor="w", pady=(0, 16))
        buttons = ttk.Frame(content)
        buttons.pack(fill="x")
        start_button = ttk.Button(buttons, text="Comenzar a grabar", style="Accent.TButton")
        start_button.pack(side="left")
        stop_button = ttk.Button(buttons, text="Detener grabación", state="disabled")
        stop_button.pack(side="right")

        def start():
            track_id = track["id"]
            stop_event = threading.Event()
            segment = {"id": uuid.uuid4().hex[:8], "file": None, "offset": start_position}
            self.recording_events[track_id] = stop_event
            self.recording_segments[track_id] = segment
            self.record_start_position = start_position
            self.record_started_at = time.monotonic()
            status.set("● Grabando... pulsa Detener grabación para finalizar")
            start_button.configure(state="disabled")
            stop_button.configure(state="normal")
            threading.Thread(target=self._record_worker, args=(track, segment, stop_event), daemon=True).start()
            self._poll_recording()

        def stop():
            event = self.recording_events.get(track["id"])
            if event:
                status.set("Guardando el segmento...")
                stop_button.configure(state="disabled")
                event.set()

        def close_without_recording():
            if not self.recording_events:
                self.record_dialog = None
                dialog.destroy()

        start_button.configure(command=start)
        stop_button.configure(command=stop)
        dialog.protocol("WM_DELETE_WINDOW", close_without_recording)
        dialog.bind("<Escape>", lambda _event: close_without_recording())

    def _set_recording_state(self, track, recording):
        track["recording"] = recording
        self.render_tracks()

    def _poll_recording(self):
        if not self.recording_events or self.record_started_at is None:
            self.record_after_id = None
            return
        elapsed = self.record_start_position + (time.monotonic() - self.record_started_at)
        elapsed = min(self.timeline_duration.get(), elapsed)
        self.timeline_position.set(elapsed)
        self._timeline_changed(elapsed)
        self._move_playheads(elapsed)
        if elapsed >= self.timeline_duration.get():
            for event in self.recording_events.values():
                event.set()
        self.record_after_id = self.after(80, self._poll_recording)

    def _record_worker(self, track, segment, stop_event):
        try:
            import numpy as np  # type: ignore
            sample_rate, channels = 44100, 1
            chunks = []

            def callback(indata, _frames, _time_info, _status):
                chunks.append(indata.copy())

            with sd.InputStream(samplerate=sample_rate, channels=channels, dtype="int16", callback=callback):
                while not stop_event.wait(0.1):
                    pass
            if not chunks:
                raise RuntimeError("No se recibieron datos del micrófono.")
            data = np.concatenate(chunks, axis=0)
            filename = f"{segment['id']}.wav"
            with wave.open(str(self.folder / "assets" / filename), "wb") as output:
                output.setnchannels(channels)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                output.writeframes(np.asarray(data).tobytes())
            self.after(0, lambda: self._finish_recording(track, segment, filename))
        except Exception as exc:
            self.after(0, lambda: self._finish_recording(track, segment, None, exc))

    def _finish_recording(self, track, segment, filename=None, error=None):
        self.recording_events.pop(track["id"], None)
        self.recording_segments.pop(track["id"], None)
        if not self.recording_events:
            self.record_started_at = None
            if self.record_after_id:
                self.after_cancel(self.record_after_id)
                self.record_after_id = None
        track.pop("recording", None)
        if filename:
            segment["file"] = filename
            self.segments_for(track).append(segment)
        elif segment in self.segments_for(track):
            self.segments_for(track).remove(segment)
        self.save()
        self.render_tracks()
        if self.record_dialog:
            self.record_dialog.grab_release()
            self.record_dialog.destroy()
            self.record_dialog = None
        if error:
            messagebox.showerror("Error de grabación", str(error), parent=self)

    def save(self):
        self.store.save(self.folder, self.project)

    def close(self):
        self.save()
        self.destroy()
        self.app.editor = None
        self.app._build_project_screen()


if __name__ == "__main__":
    App().mainloop()
