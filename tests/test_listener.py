import numpy as np

from jarvis import listener
from jarvis.listener import FRAME, FRAME_SECONDS, record_command


def frames(*parts):
    """parts: (segundos, amplitud). Devuelve una función que entrega cuadros de 80 ms."""
    queue = []
    for seconds, amplitude in parts:
        for _ in range(round(seconds / FRAME_SECONDS)):
            queue.append(np.full(FRAME, amplitude, dtype=np.int16))
    queue.reverse()
    return lambda: queue.pop() if queue else np.zeros(FRAME, dtype=np.int16)


def test_sends_after_speech_then_silence():
    audio = record_command(frames((0.4, 20), (1.2, 4000), (3.0, 20)), no_speech_timeout=5)
    assert audio is not None
    seconds = len(audio) / listener.RATE
    assert 1.6 + listener.SILENCE_TO_SEND - 0.2 <= seconds <= 1.6 + listener.SILENCE_TO_SEND + 0.2
    assert audio.dtype == np.float32 and np.abs(audio).max() <= 1


def test_gives_up_when_nobody_speaks():
    assert record_command(frames((20, 20)), no_speech_timeout=2) is None


def test_activation_beep_is_not_taken_as_speech():
    assert record_command(frames((0.2, 6000), (20, 20)), no_speech_timeout=2) is None


def test_command_said_right_after_wake_word_is_heard():
    audio = record_command(frames((2.0, 4000), (3.0, 20)), no_speech_timeout=5, noise=20)
    assert audio is not None


def test_command_said_right_away_is_heard_without_room_measurement():
    assert record_command(frames((2.0, 4000), (3.0, 20)), no_speech_timeout=5) is not None


def test_long_command_is_cut():
    audio = record_command(frames((30, 4000)), no_speech_timeout=5)
    assert len(audio) / listener.RATE <= listener.MAX_COMMAND + FRAME_SECONDS


def test_noisy_room_raises_the_threshold():
    assert record_command(frames((20, 900)), no_speech_timeout=2, noise=900) is None
