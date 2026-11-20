"""The denoisers. Fetched once per computer and checked byte for byte (SHA-256) before use.

    deep-filter 0.5.6   DeepFilterNet3, the official standalone build (Rust + tract, CPU only,
                        no Python, no GPU). MIT/Apache-2.0, Hendrik Schröter.
                        https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6
    std.rnnn            RNNoise's original model for ffmpeg's `arnndn` filter (the fallback,
                        and the baseline it was measured against). BSD, Xiph / Paul B Mahol.

Why the binary and not `pip install deepfilternet`: its compiled part (DeepFilterLib 0.5.6)
only has Windows wheels for Python 3.8-3.11 and pins numpy < 2, so pip cannot install it on
the Python 3.12 the package's Windows guide installs. The binary is the same model, already
built for Windows x64, macOS (Apple silicon and Intel) and Linux.

They go to ~/.studio-video/models/audio-clean/ (AUDIO_CLEAN_MODELS overrides it)."""
import hashlib
import os
import platform
import stat
import urllib.request
from pathlib import Path

from .util import Stop, T, ffmpeg, run, say, tilde, user_dir

DF = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/"
BINARIES = {
    ("windows", "x86_64"): dict(name="deep-filter-0.5.6-x86_64-pc-windows-msvc.exe", size=26912256,
                                sha256="75e11fa16445f560cb6b021521ddb89e89270d13b83089705d98776f58fd7915"),
    ("darwin", "arm64"): dict(name="deep-filter-0.5.6-aarch64-apple-darwin", size=27877081,
                              sha256="4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081"),
    ("darwin", "x86_64"): dict(name="deep-filter-0.5.6-x86_64-apple-darwin", size=29933512,
                               sha256="d3be84003acb7c23e738ad7f70a158ec779a8d233a82e7fa3e717d112eb5b50f"),
    ("linux", "x86_64"): dict(name="deep-filter-0.5.6-x86_64-unknown-linux-musl", size=36417296,
                              sha256="70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da"),
    ("linux", "arm64"): dict(name="deep-filter-0.5.6-aarch64-unknown-linux-gnu", size=39238496,
                             sha256="14e02a1c0028f3ca0bdf83b62b3336e56ba0556894ef295a95e8573f06557166"),
}
RNNOISE = dict(name="std.rnnn", size=302903,
               sha256="6b8943dc4a9b6b24425873992a44f29c0577503276456af46a8854774faeb294",
               urls=["https://raw.githubusercontent.com/richardpl/arnndn-models/master/std.rnnn"])
_ok = {}


def cache_dir():
    env = os.environ.get("AUDIO_CLEAN_MODELS", "").strip()
    return Path(os.path.expanduser(env)) if env else user_dir() / "models" / "audio-clean"


def platform_key():
    sysname = platform.system().lower()
    mach = platform.machine().lower()
    mach = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(mach, mach)
    if sysname == "windows" and mach == "arm64":
        mach = "x86_64"                     # Windows on ARM runs the x64 build under emulation
    return sysname, mach


def deep_filter_spec():
    spec = BINARIES.get(platform_key())
    if spec and "urls" not in spec:
        spec = dict(spec, urls=[DF + spec["name"]])
    return spec


def _sha256(f):
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _good(f, spec):
    key = (str(f), spec["sha256"])
    if key not in _ok:
        _ok[key] = f.is_file() and f.stat().st_size == spec["size"] and _sha256(f) == spec["sha256"]
    return _ok[key]


def find(spec):
    if not spec:
        return None
    f = cache_dir() / spec["name"]
    return f if _good(f, spec) else None


def fetch(spec, what):
    """Download once, check the SHA-256, keep it. Returns the path or stops with plain words."""
    have = find(spec)
    if have:
        return have
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / spec["name"]
    part = dest.with_name(dest.name + ".part")
    errors = []
    for url in spec["urls"]:
        try:
            say(T("· bajando %s (%.1f MB, una sola vez)…" % (what, spec["size"] / 1e6),
                  "· downloading %s (%.1f MB, once)…" % (what, spec["size"] / 1e6)))
            req = urllib.request.Request(url, headers={"User-Agent": "podcast-audio-clean (python urllib)"})
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as out:
                for b in iter(lambda: r.read(1 << 20), b""):
                    out.write(b)
            if _sha256(part) != spec["sha256"]:
                errors.append(T("%s: el archivo que llegó no es el esperado (SHA-256)" % url,
                                "%s: the file that arrived is not the expected one (SHA-256)" % url))
                part.unlink()
                continue
            os.replace(part, dest)
            if not dest.name.endswith(".exe"):
                dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            _ok.pop((str(dest), spec["sha256"]), None)
            return dest
        except OSError as e:
            errors.append("%s: %s" % (url, e))
            if part.exists():
                part.unlink()
    raise Stop(T("No pude bajar %s. Sin internet o bloqueado. Bajalo a mano de\n  %s\ny ponelo en %s como %s.\n  %s",
                 "Could not download %s. No internet, or blocked. Download it by hand from\n  %s\nand put it in %s as %s.\n  %s")
               % (what, spec["urls"][0], tilde(folder), spec["name"], "\n  ".join(errors)))


def deep_filter_path(download=True):
    spec = deep_filter_spec()
    if not spec:
        return None
    return fetch(spec, "DeepFilterNet (deep-filter 0.5.6)") if download else find(spec)


def rnnoise_path(download=True):
    return fetch(RNNOISE, "RNNoise (std.rnnn)") if download else find(RNNOISE)


def run_deep_filter(binary, in_wav, out_dir, atten_db):
    """DeepFilterNet3 on a 48 kHz WAV. -D compensates the STFT + lookahead delay (output starts
    exactly with the input); the build drops the last 30 ms, the caller pads them back."""
    args = [binary, "-D", "-o", out_dir]
    if atten_db is not None:
        args += ["-a", "%g" % atten_db]
    run(args + [in_wav])
    out = Path(out_dir) / Path(in_wav).name
    if not out.is_file():
        raise Stop(T("DeepFilterNet no escribió %s" % out, "DeepFilterNet wrote no %s" % out))
    return out


def run_rnnoise(model, in_wav, out_wav):
    """RNNoise through ffmpeg's arnndn. Runs in the model's folder so the filter argument is a
    bare file name (a Windows path inside a filter string needs escaping)."""
    ffmpeg("-y", "-i", str(in_wav), "-af", "arnndn=m=%s" % Path(model).name, "-c:a", "pcm_f32le", str(out_wav),
           cwd=str(Path(model).parent))
    return Path(out_wav)
