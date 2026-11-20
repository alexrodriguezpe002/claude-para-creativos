"""The quality check: does the cleaned voice reach the bar, or is Descript's Studio Sound the
better tool for this recording? Measured on the output against its own input (no reference
file needed), with the limits set on the user's Adobe Podcast versions (references/measured.md).

Every number is taken with the voice at -16 LUFS, so files at any level compare."""
import numpy as np

from .dsp import FRAME, HOP, SR, frame_power, lag, loudness

# The bar. Set on 13 snippets (CLB ep2/ep3, CLA ep4, CLC ep1/ep3, CLE ep1/ep2) where the user's
# Adobe Podcast version exists — see references/measured.md for what each one means and why.
LIMITS = dict(
    noise_floor_max=-47.0,       # dBFS in the gaps, voice at -16 LUFS (Adobe Podcast: -47.8 to -60.5)
    floor_unsteady_max=12.0,     # dB, spread of the gap level (gating / pumping)...
    floor_audible=-50.0,         # ...counted only if the louder gaps (90th pct) pass this, dBFS
    dropouts_per_min_max=2.0,    # syllables pushed down >= 10 dB for >= 60 ms, per minute of voice
    echo_tail_max=-20.0,         # dB, 50-150 ms after a phrase ends vs its last 100 ms (Adobe: up to -23)
    bandwidth_min_hz=10000,      # the input's voice must reach 10 kHz (a 16 kHz call stops at 8)
    clip_events_max=20,          # runs of >= 3 samples stuck at full scale in the input
    stretch_snr_min=8.0,         # dB, the worst 3 s of the input (a snippet joins mics of different quality)
    input_snr_min=25.0,          # dB, voice over the gaps in the input: below it the cleaner removes the
                                 # noise but the voice stays a call voice (CLA ep4: NISQA 3.1-3.3 vs 4.5-4.7)
)


def _runs(mask):
    """(start, end) index pairs of the True runs."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    d = np.diff(m.astype(np.int8))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _dilate(mask, k):
    if k <= 0:
        return mask
    c = np.convolve(mask.astype(np.int32), np.ones(2 * k + 1, np.int32), mode="same")
    return c > 0


def _band_levels(x, frames_mask, lo, hi):
    """Mean power (dB) of x between lo and hi Hz over the selected 20 ms frames (FFT 4096)."""
    n, hop = 4096, 1024
    if len(x) < n:
        return None
    w = np.hanning(n).astype(np.float32)
    nf = 1 + (len(x) - n) // hop
    t_fft = (np.arange(nf) * hop + n / 2) / SR
    t_fr = (np.arange(len(frames_mask)) * HOP + FRAME / 2) / SR
    sel = np.interp(t_fft, t_fr, frames_mask.astype(float)) > 0.5
    if sel.sum() < 4:
        return None
    idx = np.arange(n)[None, :] + hop * np.where(sel)[0][:, None]
    P = np.abs(np.fft.rfft(x[idx] * w, axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / SR)
    b = (f >= lo) & (f < hi)
    return float(10 * np.log10(P[:, b].mean() + 1e-20))


CENTERS = [1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000]


def _bandwidth(x, voiced, pause):
    """Highest 1/3-octave band (Hz) where the voice still carries energy: within 30 dB of its
    1-4 kHz level and 6 dB over the gaps in that band. A call at 16 kHz stops at 8 kHz."""
    n, hop = 4096, 1024
    if len(x) < n or voiced.sum() < 50:
        return None
    w = np.hanning(n).astype(np.float32)
    nf = 1 + (len(x) - n) // hop
    t_fft = (np.arange(nf) * hop + n / 2) / SR
    t_fr = (np.arange(len(voiced)) * HOP + FRAME / 2) / SR
    sv = np.interp(t_fft, t_fr, voiced.astype(float)) > 0.5
    sp = np.interp(t_fft, t_fr, pause.astype(float)) > 0.5
    if sv.sum() < 4:
        return None
    f = np.fft.rfftfreq(n, 1.0 / SR)

    def ltas(sel):
        idx = np.arange(n)[None, :] + hop * np.where(sel)[0][:, None]
        P = (np.abs(np.fft.rfft(x[idx] * w, axis=1)) ** 2).mean(0)
        return np.array([10 * np.log10(P[(f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))].mean() + 1e-20) for c in CENTERS])
    v = ltas(sv)
    g = ltas(sp) if sp.sum() >= 4 else np.full(len(CENTERS), -200.0)
    ref = 10 * np.log10(np.mean(10 ** (v[:7] / 10)))          # 1-4 kHz
    ok = (v >= ref - 30) & (v >= g + 6)
    top = [c for c, k in zip(CENTERS, ok) if k]
    return float(max(top)) if top else float(CENTERS[0])


INPUT_REASONS = ("input-noisy", "noisy-stretch", "band-limited", "input-clipped")


def analyze(raw, clean, pre=None, limits=None, judge_input=True):
    """raw, clean (and the denoised voice before EQ, when known): mono float arrays, same length.
    Returns dict(metrics=..., verdict='ok'|'studio-sound', reasons=[...], warnings=[...]).
    judge_input=False (checking someone else's result, e.g. a Studio Sound export): what the
    input lacks is only noted as a warning — the verdict is about the result."""
    L = dict(LIMITS, **(limits or {}))
    n = min(len(raw), len(clean))
    raw, clean = np.asarray(raw[:n], np.float32), np.asarray(clean[:n], np.float32)
    seg_src = np.asarray(pre[:n], np.float32) if pre is not None else clean
    Ps = frame_power(seg_src)
    Ls = 10 * np.log10(Ps)
    top = np.sort(Ps)[int(len(Ps) * 0.7):]
    ref = 10 * np.log10(top.mean())
    voiced = Ls > ref - 30
    # the gaps between words and phrases, >= 30 ms from any voice: an edited snippet has almost no
    # long pauses (the silences were cut), so the background is read in these short gaps
    pause = ~_dilate(voiced, 3)
    lr, lc = loudness(raw), loudness(clean)
    Pr, Pc = frame_power(raw), frame_power(clean)
    m = len(Ps)
    Pr, Pc = Pr[:m], Pc[:m]
    Lr, Lc = 10 * np.log10(Pr), 10 * np.log10(Pc)
    norm_r, norm_c = -16 - lr["I"], -16 - lc["I"]
    met = dict(seconds=round(n / SR, 2), voice_seconds=round(float(voiced.sum()) * HOP / SR, 2),
               pause_seconds=round(float(pause.sum()) * HOP / SR, 2),
               input_lufs=round(lr["I"], 2), output_lufs=round(lc["I"], 2), output_true_peak=round(lc["TP"], 2),
               output_lra=round(lc["LRA"], 2), lag_samples=int(lag(raw, clean)))
    reasons, warnings = [], []
    if voiced.sum() * HOP / SR < 2:
        return dict(metrics=met, verdict="no-voice", reasons=["no-voice"], warnings=[])

    def db_mean(p):
        return float(10 * np.log10(np.mean(p)))

    if pause.sum() * HOP / SR >= 0.3:
        nr = db_mean(Pr[pause]) + norm_r
        nc = db_mean(Pc[pause]) + norm_c
        gaps_c = Lc[pause] + norm_c
        met.update(input_noise_floor=round(nr, 1), noise_floor=round(nc, 1), noise_reduction=round(nr - nc, 1),
                   floor_unsteadiness=round(float(np.std(gaps_c)), 1),
                   floor_p90=round(float(np.percentile(gaps_c, 90)), 1))
        met["input_snr"] = round(db_mean(Pr[voiced]) - db_mean(Pr[pause]), 1)
        met["output_snr"] = round(db_mean(Pc[voiced]) - db_mean(Pc[pause]), 1)
        if met["input_snr"] < L["input_snr_min"]:
            reasons.append("input-noisy")
        if nc > L["noise_floor_max"]:
            reasons.append("noise-left")
        # pumping only counts when it can be heard: the louder gaps must reach the audible range
        if met["floor_unsteadiness"] > L["floor_unsteady_max"] and met["floor_p90"] > L["floor_audible"]:
            warnings.append("pumping")      # a warning: Adobe's own versions show it where breaths sit in the gaps
    else:
        warnings.append("few-pauses")
    # the input's noise moment to moment (a snippet joins moments, and mics, of different quality):
    # the 10th percentile of each second, the lowest of its neighbours = the local background
    nb = int(np.ceil(m / 100))
    blk = np.array([np.percentile(Lr[i * 100:(i + 1) * 100], 10) for i in range(nb)])
    loc = np.array([blk[max(0, i - 1):i + 2].min() for i in range(nb)])
    floor_loc = np.repeat(loc, 100)[:m]
    # the worst 3-second stretch of the input: voice over its local background
    worst = None
    for s0 in range(0, max(1, m - 300 + 1), 100):
        v, g = voiced[s0:s0 + 300], pause[s0:s0 + 300]
        if v.sum() >= 50 and g.sum() >= 10:
            snr = db_mean(Pr[s0:s0 + 300][v]) - db_mean(Pr[s0:s0 + 300][g])
            if worst is None or snr < worst[0]:
                worst = (snr, s0 * HOP / SR)
    if worst:
        met["input_snr_worst"] = round(worst[0], 1)
        met["input_snr_worst_at"] = round(worst[1], 1)
        if worst[0] < L["stretch_snr_min"]:
            reasons.append("noisy-stretch")
    # dropouts: in voice frames the input carries clearly (>= 20 dB over its LOCAL background, so a
    # noisy stretch's hum is not mistaken for voice), where the output falls >= 10 dB below its usual
    # relation to the input for >= 60 ms
    strong = voiced & (Lr >= floor_loc + 20)
    if strong.sum() * HOP / SR >= 10:
        diff = Lr - Lc
        dev = diff - np.median(diff[strong])
        bad = strong & (dev >= 10)
        ev = [r for r in _runs(bad) if r[1] - r[0] >= 6]
        vmin = strong.sum() * HOP / SR / 60
        met.update(dropouts=len(ev), dropouts_per_min=round(len(ev) / vmin, 2),
                   dropouts_at=[round(a * HOP / SR, 2) for a, _ in ev[:10]],
                   voice_change_p95=round(float(np.percentile(dev[strong], 95)), 1))
        if met["dropouts_per_min"] > L["dropouts_per_min_max"]:
            reasons.append("voice-damaged")
    else:
        warnings.append("little-clear-voice")
    # echo: how fast the voice dies after a phrase ends (cleaned signal, before EQ when known)
    tails = []
    vr = _runs(voiced)
    for i, (s, e) in enumerate(vr):
        if e - s < 20:
            continue
        gap = (vr[i + 1][0] if i + 1 < len(vr) else m) - e
        if gap < 20 or e + 15 > m:
            continue
        pre_p, post_p = Ps[e - 12:e - 2].mean(), Ps[e + 5:e + 15].mean()
        tails.append(10 * np.log10(post_p / pre_p))
    if len(tails) >= 3:
        met["echo_tail"] = round(float(np.median(tails)), 1)
        met["echo_tail_n"] = len(tails)
        if met["echo_tail"] > L["echo_tail_max"]:
            reasons.append("echo-left")
    # the input itself: a band-limited source (a call sampled at 16 kHz, a phone line) and clipping
    # are what Studio Sound / Adobe re-synthesise and a denoiser cannot
    bw = _bandwidth(raw, voiced, pause)
    if bw is not None:
        met["input_bandwidth_khz"] = round(bw / 1000, 1)
        if bw < L["bandwidth_min_hz"]:
            reasons.append("band-limited")
    stuck = np.abs(raw) >= 0.999
    clip_ev = [r for r in _runs(stuck) if r[1] - r[0] >= 3]
    met["input_clip_events"] = len(clip_ev)
    if len(clip_ev) > L["clip_events_max"]:
        reasons.append("input-clipped")
    if abs(met["lag_samples"]) > 1:
        warnings.append("shifted")
    if not judge_input:
        warnings += [r for r in reasons if r in INPUT_REASONS]
        reasons = [r for r in reasons if r not in INPUT_REASONS]
        return dict(metrics=met, verdict="ok" if not reasons else "review", reasons=reasons, warnings=warnings)
    return dict(metrics=met, verdict="ok" if not reasons else "studio-sound", reasons=reasons, warnings=warnings)


def explain(code, T):
    """One plain line per reason code (the codes are the same in both languages)."""
    return {
        "noise-left": T("queda ruido de fondo audible en las pausas",
                        "background noise is still audible in the pauses"),
        "pumping": T("el fondo sube y baja entre frases (bombeo)",
                     "the background comes and goes between phrases (pumping)"),
        "input-noisy": T("la grabación original tiene mucho ruido (llamada, sala): el limpiador saca el ruido pero la voz "
                         "sigue sonando a llamada; Studio Sound la reconstruye",
                         "the original is noisy (a call, a room): the cleaner removes the noise but the voice still "
                         "sounds like a call; Studio Sound rebuilds it"),
        "noisy-stretch": T("hay un tramo con muchísimo ruido", "one stretch is very noisy"),
        "voice-damaged": T("el limpiador se comió partes de la voz", "the cleaner ate parts of the voice"),
        "echo-left": T("queda eco de la sala después de cada frase", "room echo remains after each phrase"),
        "band-limited": T("la grabación no tiene agudos (llamada o teléfono): Studio Sound los reconstruye",
                          "the recording has no highs (a call or phone line): Studio Sound rebuilds them"),
        "input-clipped": T("la grabación original está saturada", "the original recording is clipped"),
        "no-voice": T("no encontré voz para medir", "found no voice to measure"),
        "little-clear-voice": T("hay poca voz clara para juzgar si se comió sílabas",
                                "too little clear voice to judge dropouts"),
        "few-pauses": T("casi no hay pausas: el ruido de fondo no se pudo medir",
                        "almost no pauses: the background could not be measured"),
        "shifted": T("la salida quedó corrida respecto de la entrada", "the output is shifted against the input"),
    }.get(code, code)
