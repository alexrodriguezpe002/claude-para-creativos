"""Audio in and out (through ffmpeg, so any video or audio file works), the voice EQ, the
loudness measurement, frame levels. numpy only."""
import json
import re
import tempfile
from pathlib import Path

import numpy as np

from .util import Stop, T, ffmpeg, run, tool

SR = 48000


def probe_audio(path):
    r = run([tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError:
        info = {}
    streams = info.get("streams", [])
    a = [s for s in streams if s.get("codec_type") == "audio"]
    v = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    if not a:
        raise Stop(T("%s no tiene audio." % path, "%s has no audio stream." % path), code=2)
    dur = float((info.get("format") or {}).get("duration") or a[0].get("duration") or 0)
    return dict(channels=int(a[0].get("channels") or 1), sample_rate=int(a[0].get("sample_rate") or 0),
                codec=a[0].get("codec_name"), duration=dur, has_video=bool(v))


def decode(path, channels=None):
    """float32 at 48 kHz, shape (n, ch). Only the first audio stream."""
    info = probe_audio(path)
    ch = channels or min(2, info["channels"])
    r = ffmpeg("-i", str(path), "-map", "0:a:0", "-vn", "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-", data=b"")
    x = np.frombuffer(r.stdout, dtype=np.float32).copy()
    if x.size == 0:
        raise Stop(T("No pude leer el audio de %s." % path, "Could not read the audio of %s." % path), code=2)
    return x.reshape(-1, ch), info


def to_mono(x):
    """Dual mono or a mix -> the average. If one channel is (nearly) silent — a mic recorded on
    one side only — the live channel alone, so the voice does not lose 6 dB."""
    if x.ndim == 1 or x.shape[1] == 1:
        return x.reshape(-1), "mono"
    p = (x.astype(np.float64) ** 2).mean(0) + 1e-20
    lv = 10 * np.log10(p)
    if abs(lv[0] - lv[1]) > 20:
        k = int(np.argmax(lv))
        return x[:, k].copy(), "channel %d only (the other is silent)" % (k + 1)
    return x.mean(1), "L+R average"


def write_wav(path, x, stereo=True, bits=24):
    x = np.clip(np.asarray(x, dtype=np.float32).reshape(-1), -1.0, 1.0)
    codec = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_f32le"}[bits]
    ffmpeg("-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", *(["-ac", "2"] if stereo else []),
           "-c:a", codec, str(path), data=x.tobytes())


def write_float_mono(path, x):
    ffmpeg("-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_f32le", str(path),
           data=np.asarray(x, dtype=np.float32).reshape(-1).tobytes())


def read_wav_mono(path):
    r = ffmpeg("-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-", data=b"")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


# ----------------------------------------------------------------------------- EQ
def eq_response(freqs, centers, gains_db, hp_hz=None):
    """Magnitude of the voice EQ at `freqs`: the curve interpolated on a log axis (flat beyond
    its ends) times a 2nd-order Butterworth high-pass magnitude."""
    f = np.maximum(np.asarray(freqs, float), 1e-3)
    g = np.interp(np.log(f), np.log(np.asarray(centers, float)), np.asarray(gains_db, float))
    mag = 10 ** (g / 20)
    if hp_hz:
        mag = mag / np.sqrt(1 + (hp_hz / f) ** 4)
    return mag


def apply_eq(x, centers, gains_db, hp_hz=70.0, taps=16384):
    """Zero-phase (linear-phase FIR, delay removed) EQ by overlap-add — any length, no shift."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    nfft_design = taps
    f = np.fft.rfftfreq(nfft_design, 1.0 / SR)
    h = np.fft.irfft(eq_response(f, centers, gains_db, hp_hz), nfft_design)
    h = np.roll(h, taps // 2) * np.hanning(taps)            # linear phase, centred at taps//2
    delay = taps // 2
    block = 1 << 18
    nfft = 1 << int(np.ceil(np.log2(block + taps)))
    H = np.fft.rfft(h, nfft)
    y = np.zeros(len(x) + taps + block)
    for s in range(0, len(x), block):
        seg = x[s:s + block]
        y[s:s + nfft] += np.fft.irfft(np.fft.rfft(seg, nfft) * H, nfft)[: len(y) - s]
    return y[delay: delay + len(x)].astype(np.float32)


# ------------------------------------------------------------------------ loudness
def loudness(x):
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBTP) of a mono signal,
    measured by ffmpeg's ebur128 (the same numbers music-bed and the gates use)."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "l.wav"
        write_float_mono(p, x)
        r = run([tool("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(p), "-af", "ebur128=peak=true:framelog=quiet",
                 "-f", "null", "-"], check=False)
    t = r.stderr[r.stderr.rfind("Summary:"):]

    def g(k):
        m = re.search(k + r":\s+(-?[\d.]+|-inf)", t)
        return -120.0 if (not m or m.group(1) == "-inf") else float(m.group(1))
    return dict(I=g(r"\bI"), LRA=g(r"LRA"), TP=g(r"Peak"))


def normalize(x, target_lufs, tp_max=-1.5):
    """One gain for the whole file (no compression, as Adobe Podcast leaves it): to the target
    loudness, or less if the true peak would pass tp_max."""
    m = loudness(x)
    gain = target_lufs - m["I"]
    limited = False
    if m["TP"] + gain > tp_max:
        gain, limited = tp_max - m["TP"], True
    return (x * 10 ** (gain / 20)).astype(np.float32), dict(gain_db=round(gain, 2), peak_limited=limited)


# -------------------------------------------------------------------------- frames
FRAME, HOP = 960, 480          # 20 ms windows every 10 ms at 48 kHz

AUTO_STEPS = (12, 15, 20, 25, 30, 35, 40)


def mix_background(raw, full, atten_db):
    """DeepFilterNet's attenuation limit is exactly this mix (checked against the binary's own
    -a output: identical to 16-bit precision), so the denoiser runs once and the amount of
    background kept is chosen afterwards."""
    lim = 10 ** (-abs(atten_db) / 20)
    return (lim * raw + (1 - lim) * full).astype(np.float32)


def choose_atten(raw, full, tolerance_db=1.0):
    """The mildest attenuation whose background (gaps between words, relative to the voice) is
    within `tolerance_db` of what full suppression reaches. Past that point more suppression
    only gates the gaps (they go dead and come back) without lowering the background — on clean
    recordings that happens at 12 dB, on noisy calls at 40 (references/measured.md)."""
    P = frame_power(full)
    L = 10 * np.log10(P)
    ref = 10 * np.log10(np.sort(P)[int(len(P) * 0.7):].mean())
    voiced = L > ref - 30
    c = np.convolve(voiced.astype(np.int32), np.ones(7, np.int32), mode="same") > 0
    gap = ~c
    if gap.sum() * HOP / SR < 0.3 or voiced.sum() < 100:
        return 30.0, {}

    def rel_floor(y):
        p = frame_power(y)[: len(P)]
        return float(10 * np.log10(p[gap].mean()) - 10 * np.log10(p[voiced].mean()))
    best = rel_floor(full)
    curve = {}
    for a in AUTO_STEPS:
        curve[a] = round(rel_floor(mix_background(raw, full, a)), 1)
        if curve[a] <= best + tolerance_db:
            return float(a), dict(curve, full=round(best, 1))
    return float(AUTO_STEPS[-1]), dict(curve, full=round(best, 1))


def frame_power(x):
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    if len(x) < FRAME:
        return np.array([1e-12])
    nf = 1 + (len(x) - FRAME) // HOP
    sq = np.cumsum(np.concatenate([[0.0], x ** 2]))
    idx = np.arange(nf) * HOP
    return (sq[idx + FRAME] - sq[idx]) / FRAME + 1e-12


def align(ref, x, max_shift=4800):
    """x moved onto ref's clock (same length as ref) when a denoiser delayed or advanced it —
    RNNoise in ffmpeg delays by one 10 ms frame. Returns (aligned x, shift found in samples)."""
    k = lag(ref, x)
    if abs(k) > max_shift:
        k = 0
    if k > 0:
        x = np.concatenate([np.zeros(k, np.float32), x])
    elif k < 0:
        x = x[-k:]
    n = len(ref)
    return np.pad(x, (0, max(0, n - len(x))))[:n].astype(np.float32), int(k)


def lag(a, b, seconds=20):
    """Shift (samples) of b against a, by cross-correlation over the first `seconds`
    (negative: b comes later than a)."""
    n = int(min(len(a), len(b), SR * seconds))
    if n < SR:
        return 0
    A = np.fft.rfft(a[:n], 2 * n)
    B = np.fft.rfft(b[:n], 2 * n)
    cc = np.fft.irfft(A * np.conj(B))
    k = int(np.argmax(np.abs(cc)))
    return k - 2 * n if k > n else k
