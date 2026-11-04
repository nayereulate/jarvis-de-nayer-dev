"""Escucha de fondo en la PC: "Hey Jarvis", la orden, la respuesta por los altavoces y el modo dictado."""
import logging
import os
import re
import threading

import numpy as np

from . import speech, tools
from .brain import BrainError, audit
from .speaker import tone

RATE = 16000
FRAME = 1280  # 80 ms, lo que espera openWakeWord
FRAME_SECONDS = FRAME / RATE
WAKE_THRESHOLD = 0.5
IGNORE_START = 0.25  # El tono de activación no cuenta como voz
SILENCE_TO_SEND = 0.9
NO_SPEECH_TIMEOUT = 5.0
FOLLOW_UP_TIMEOUT = 6.0
MAX_COMMAND = 15.0
MIN_SPEECH_LEVEL = 300
DICTATION_WAIT = 30.0  # en dictado se espera más a que vuelvas a hablar
STOP_DICTATION = re.compile(r"\b(fin|termina\w*|para\w*|det[eé]n\w*|cierra\w*|sal\w*)\s+(del?\s+|el\s+)?dictado\b", re.IGNORECASE)
NEW_LINE = re.compile(r"[,.]?\s*\b(nueva l[ií]nea|punto y aparte)\b[,.]?\s*", re.IGNORECASE)

log = logging.getLogger("jarvis.listener")


def level_of(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))


def record_command(read_frame, no_speech_timeout: float, noise: float | None = None) -> np.ndarray | None:
    """Graba hasta que la persona deja de hablar. None si nunca empezó a hablar.

    noise es el ruido de la habitación medido antes; sin él, la orden dicha de corrido
    tras "Hey Jarvis" se tomaría como ruido de fondo.
    """
    frames = []
    heard = False
    silent = 0.0
    elapsed = 0.0
    while elapsed < MAX_COMMAND:
        frame = read_frame()
        frames.append(frame)
        elapsed += FRAME_SECONDS
        if elapsed <= IGNORE_START:
            continue
        level = level_of(frame)
        if noise is None:
            noise = min(level, MIN_SPEECH_LEVEL / 3)
        loud = level > max(noise * 3, MIN_SPEECH_LEVEL)
        if loud:
            heard = True
            silent = 0.0
        elif heard:
            silent += FRAME_SECONDS
            if silent >= SILENCE_TO_SEND:
                break
        else:
            noise = noise * 0.9 + level * 0.1
            if elapsed >= no_speech_timeout:
                return None
    if not heard:
        return None
    return np.concatenate(frames).astype(np.float32) / 32768


def beep() -> np.ndarray:
    return tone(880, 0.12, 0.25, RATE)


def dictation_text(text: str) -> str:
    """Lo dictado listo para teclear: «nueva línea» salta de línea y se deja un espacio para seguir."""
    text = NEW_LINE.sub("\n", text.strip())
    return text if text.endswith("\n") else text + " "


class Listener:
    def __init__(self, brain, events, speaker):
        self.brain = brain
        self.events = events
        self.speaker = speaker
        self.enabled = True
        self.dictation = False
        self.state = "off"
        self._thread = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="jarvis-listener", daemon=True)
            self._thread.start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        audit("listener", enabled=enabled)

    def set_dictation(self, enabled: bool) -> None:
        if enabled and self._thread is None:
            raise RuntimeError("El dictado necesita la escucha de la PC encendida")
        self.dictation = enabled
        audit("dictation", enabled=enabled)

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.events.publish("listener", state=state)

    def _run(self) -> None:
        import openwakeword.utils
        import sounddevice as sd
        from openwakeword.model import Model

        try:
            openwakeword.utils.download_models(model_names=["hey_jarvis"])
            model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            device = os.environ.get("JARVIS_MIC") or None
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME, device=device) as stream:
                read_frame = lambda: stream.read(FRAME)[0][:, 0]

                def drain():
                    while stream.read_available >= FRAME:
                        read_frame()
                    model.reset()

                follow_up = False
                woken = False
                ambient = None
                while True:
                    frame = read_frame()
                    if not self.enabled:
                        follow_up = woken = self.dictation = False
                        self._set_state("paused")
                        continue
                    if self.dictation:
                        self._dictate(read_frame, ambient)
                        follow_up = woken = False
                        drain()
                        continue
                    if not (follow_up or woken):
                        self._set_state("speaking" if self.speaker.busy() else "wake")
                        level = level_of(frame)
                        # Las subidas fuertes (voz) apenas mueven la estimación del ruido.
                        ambient = level if ambient is None else ambient * 0.97 + min(level, ambient * 2) * 0.03
                        if model.predict(frame)["hey_jarvis"] < WAKE_THRESHOLD:
                            continue
                        self._wake()
                    woken = False
                    self._set_state("listening")
                    timeout = FOLLOW_UP_TIMEOUT if follow_up else NO_SPEECH_TIMEOUT
                    audio = record_command(read_frame, timeout, noise=ambient)
                    follow_up = audio is not None and self._handle(audio)
                    drain()
                    if self.speaker.busy():
                        woken = self._watch_while_speaking(read_frame, model)
                        follow_up = follow_up and not woken
                    # La cola de la voz de Jarvis no debe tomarse como una orden.
                    for _ in range(3):
                        read_frame()
                    model.reset()
        except Exception as error:
            log.exception("La escucha de la PC se detuvo")
            self._set_state("error")
            self.events.publish("error", text=f"La escucha de la PC se detuvo: {error}")

    def _wake(self) -> None:
        audit("wake_word")
        self.speaker.stop()  # si Jarvis estaba hablando, se calla para escucharte
        self.speaker.play(beep(), RATE)

    def _watch_while_speaking(self, read_frame, model) -> bool:
        """Mientras Jarvis habla, sigue atento a «Hey Jarvis» para poder interrumpirlo."""
        self._set_state("speaking")
        model.reset()
        while self.speaker.busy():
            if model.predict(read_frame())["hey_jarvis"] >= WAKE_THRESHOLD:
                self._wake()
                return True
        return False

    def _handle(self, audio: np.ndarray) -> bool:
        """Devuelve True si conviene seguir escuchando sin pedir "Hey Jarvis"."""
        self._set_state("thinking")
        text = speech.transcribe(audio)
        if not text:
            return False
        self.events.publish("user", text=text)
        try:
            reply = self.brain.chat(text)
        except BrainError as error:
            self.events.publish("error", text=str(error))
            self.speaker.say("Lo siento, no pude contactar con Claude.")
            return False
        self.events.publish("jarvis", text=reply["say"], pending=reply["pending"])
        if reply["say"]:
            self.speaker.say(reply["say"])
        return reply["pending"] is None and not self.dictation

    def _dictate(self, read_frame, ambient) -> None:
        """Todo lo que digas se teclea en la ventana activa hasta que digas «fin del dictado»."""
        self.speaker.wait()
        self._set_state("dictating")
        while self.dictation and self.enabled:
            audio = record_command(read_frame, DICTATION_WAIT, noise=ambient)
            if audio is None or not self.dictation:
                continue
            text = speech.transcribe(audio)
            if not text:
                continue
            if STOP_DICTATION.search(text):
                self.dictation = False
                audit("dictation", enabled=False)
                self.events.publish("jarvis", text="Dictado terminado.", pending=None)
                self.speaker.say("Dictado terminado.", wait=True)
                break
            tools.type_text(dictation_text(text))
            self.events.publish("user", text="✎ " + text)
