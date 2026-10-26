"""Update check against GitHub Releases (network mocked)."""
import hashlib
import io
import json
import threading

import pytest

from lrxe8 import updater
from lrxe8.core import Cancelled, MediaError


class Response(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def release(tag, assets):
    return json.dumps({'tag_name': tag, 'name': f'LRXe8 {tag}', 'body': 'notlar', 'html_url': 'https://example/rel',
                       'assets': assets}).encode()


def test_version_order():
    assert updater.version_tuple('v2.2.1') > updater.version_tuple('2.2.0')
    assert updater.version_tuple('v2.10.0') > updater.version_tuple('2.9.9')
    assert updater.version_tuple('2.2') == (2, 2, 0)


def test_newer_release_with_windows_installer(monkeypatch):
    monkeypatch.setattr(updater, '__version__', '2.2.0')
    monkeypatch.setattr(updater.os, 'name', 'nt')
    assets = [{'name': 'LRXe8-Media-Optimizer-2.3.0-win64.zip', 'browser_download_url': 'z', 'size': 1},
              {'name': 'LRXe8-Media-Optimizer-2.3.0-Kurulum.exe', 'browser_download_url': 'https://x/setup.exe',
               'size': 4, 'digest': 'sha256:abc'}]
    monkeypatch.setattr(updater.urllib.request, 'urlopen', lambda *a, **k: Response(release('v2.3.0', assets)))
    info = updater.check()
    assert info['newer'] and info['version'] == '2.3.0'
    assert info['asset']['url'] == 'https://x/setup.exe' and info['asset']['sha256'] == 'abc'


def test_same_version_is_not_offered(monkeypatch):
    monkeypatch.setattr(updater, '__version__', '2.3.0')
    monkeypatch.setattr(updater.urllib.request, 'urlopen', lambda *a, **k: Response(release('v2.3.0', [])))
    assert updater.check()['newer'] is False


def test_offline_is_a_readable_error(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('ağ yok')
    monkeypatch.setattr(updater.urllib.request, 'urlopen', fail)
    with pytest.raises(MediaError, match='GitHub'):
        updater.check()


def test_download_verifies_digest_and_size(monkeypatch, tmp_path):
    payload = b'kurulum dosyasi'
    good = {'name': 'setup.exe', 'url': 'https://example.com/setup.exe', 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    monkeypatch.setattr(updater.urllib.request, 'urlopen', lambda *a, **k: Response(payload))
    path = updater.download(good, threading.Event())
    assert path.read_bytes() == payload
    with pytest.raises(MediaError, match='SHA-256'):
        updater.download({**good, 'sha256': '0' * 64}, threading.Event())
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        updater.download(good, cancel)
