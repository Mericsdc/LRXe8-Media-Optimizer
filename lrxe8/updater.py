"""In-app updates from GitHub Releases. Only runs when the user presses the
button: one HTTPS request to the GitHub API, then (if accepted) the installer
download. Media files never leave the computer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request

from . import __version__
from .core import Cancelled, MediaError

REPOSITORY = 'Mericsdc/LRXe8-Media-Optimizer'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases/latest'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
DONATE_URL = 'https://www.buymeacoffee.com/Lurexa'


def version_tuple(text: str):
    numbers = re.findall(r'\d+', text or '')
    return tuple(int(number) for number in numbers[:3]) + (0,) * (3 - len(numbers[:3]))


def context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def request(url: str, accept='application/vnd.github+json'):
    return urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': f'LRXe8-Media-Optimizer/{__version__}'})


def pick_asset(assets):
    """The installer for this platform: Windows setup, or the macOS DMG for this CPU."""
    if os.name == 'nt':
        wanted = [a for a in assets if a['name'].lower().endswith('-kurulum.exe')]
    elif sys.platform == 'darwin':
        arch = 'arm64' if platform.machine() == 'arm64' else 'x86_64'
        wanted = [a for a in assets if a['name'].endswith('.dmg') and arch in a['name']]
    else:
        wanted = []
    return wanted[0] if wanted else None


def check(timeout: float = 15):
    """Latest release info; raises MediaError with a readable reason on failure."""
    try:
        with urllib.request.urlopen(request(API), timeout=timeout, context=context()) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as error:  # offline, DNS, rate limit, TLS...
        raise MediaError(f'GitHub\'a ulaşılamadı: {error}')
    tag = data.get('tag_name', '')
    asset = pick_asset(data.get('assets', []))
    return {'version': '.'.join(map(str, version_tuple(tag))), 'tag': tag, 'name': data.get('name') or tag,
            'notes': data.get('body') or '', 'page': data.get('html_url') or RELEASES_PAGE,
            'newer': version_tuple(tag) > version_tuple(__version__),
            'asset': None if asset is None else {
                'name': asset['name'], 'url': asset['browser_download_url'], 'size': asset.get('size', 0),
                'sha256': (asset.get('digest') or '').removeprefix('sha256:') or None}}


def download(asset: dict, cancel: threading.Event, progress=lambda done, total: None) -> Path:
    """Stream the installer to a temp folder; verify size and (when GitHub
    publishes it) the SHA-256 digest before anything is run."""
    folder = Path(tempfile.mkdtemp(prefix='lrxe8-update-'))
    target = folder / asset['name']
    digest = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(request(asset['url'], 'application/octet-stream'), timeout=60,
                                context=context()) as response, target.open('wb') as stream:
        total = int(response.headers.get('Content-Length') or asset.get('size') or 0)
        while block := response.read(1024 * 1024):
            if cancel.is_set():
                stream.close()
                target.unlink(missing_ok=True)
                raise Cancelled('Güncelleme indirmesi iptal edildi')
            stream.write(block)
            digest.update(block)
            done += len(block)
            progress(done, total)
    if asset.get('size') and done != asset['size']:
        raise MediaError('İndirilen dosya eksik; güncelleme kurulmadı')
    if asset.get('sha256') and digest.hexdigest() != asset['sha256']:
        raise MediaError('İndirilen dosyanın SHA-256 değeri tutmuyor; güncelleme kurulmadı')
    return target


def install(installer: Path):
    """Start the installer; the caller quits the app right after."""
    if os.name == 'nt':
        # Inno Setup: small progress window, closes the running app, reopens it afterwards.
        subprocess.Popen([str(installer), '/SILENT', '/SUPPRESSMSGBOXES', '/CLOSEAPPLICATIONS', '/NORESTART'],
                         close_fds=True)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(installer)])
    else:
        raise MediaError('Bu sistem için otomatik güncelleme yok')
