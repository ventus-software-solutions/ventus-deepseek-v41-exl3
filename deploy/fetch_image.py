"""Fetch a pinned public GHCR image in checked HTTP ranges, then docker load it."""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import threading
import time
import urllib.request


def digest_file(path):
    with path.open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository')
    parser.add_argument('digest')
    parser.add_argument('directory', type=Path)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--workers', type=int, default=32)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = 'https://ghcr.io/v2/' + args.repository
    token_lock = threading.Lock()
    token, expires = '', 0

    def headers():
        nonlocal token, expires
        with token_lock:
            if time.monotonic() >= expires:
                url = 'https://ghcr.io/token?scope=repository:' + args.repository + ':pull'
                with urllib.request.urlopen(url, timeout=30) as response:
                    token = json.load(response)['token']
                expires = time.monotonic() + 120
            return {'Authorization': 'Bearer ' + token}

    req = urllib.request.Request(base + '/manifests/' + args.digest, headers={
        **headers(), 'Accept': 'application/vnd.docker.distribution.manifest.v2+json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != args.digest:
        raise RuntimeError('manifest digest mismatch')
    manifest = json.loads(raw)
    if manifest.get('schemaVersion') != 2 or 'layers' not in manifest:
        raise RuntimeError('expected a single-platform image manifest')
    (root / 'registry-manifest.json').write_bytes(raw)
    blobs = list({b['digest']: b for b in [manifest['config'], *manifest['layers']]}.values())
    chunk_size = 16 * 1024 * 1024
    started, copied, last_report = time.monotonic(), 0, 0

    def fetch_range(blob, fd, start, end):
        expected = end - start + 1
        for attempt in range(6):
            try:
                req = urllib.request.Request(base + '/blobs/' + blob['digest'], headers={
                    **headers(), 'Range': f'bytes={start}-{end}'})
                with urllib.request.urlopen(req, timeout=45) as response:
                    wanted = f'bytes {start}-{end}/{blob["size"]}'
                    if response.status != 206 or response.headers.get('Content-Range') != wanted:
                        raise RuntimeError('server did not honor the requested byte range')
                    offset = start
                    while offset <= end:
                        data = response.read(min(1024 * 1024, end - offset + 1))
                        if not data:
                            raise RuntimeError('short range response')
                        view = memoryview(data)
                        while view:
                            n = os.pwrite(fd, view, offset)
                            if n <= 0:
                                raise OSError('short disk write')
                            offset += n
                            view = view[n:]
                return expected
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(min(2 ** attempt, 15))

    handles = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = []
            for blob in blobs:
                name = blob['digest'].removeprefix('sha256:')
                if len(name) != 64 or any(c not in '0123456789abcdef' for c in name):
                    raise RuntimeError('invalid blob digest')
                path = root / name
                if path.exists() and path.stat().st_size == blob['size'] and digest_file(path) == blob['digest']:
                    continue
                fd = os.open(str(path) + '.partial', os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)
                handles[name] = fd
                os.ftruncate(fd, blob['size'])
                for start in range(0, blob['size'], chunk_size):
                    futures.append(pool.submit(fetch_range, blob, fd, start,
                                               min(start + chunk_size, blob['size']) - 1))
            for future in concurrent.futures.as_completed(futures):
                copied += future.result()
                now = time.monotonic()
                if now - last_report >= 15:
                    print(json.dumps({'downloaded_GiB': round(copied / 2**30, 3),
                                      'MiB_per_s': round(copied / 2**20 / (now - started), 2)}), flush=True)
                    last_report = now
        for name, fd in handles.items():
            os.fsync(fd)
            path = root / (name + '.partial')
            if digest_file(path) != 'sha256:' + name:
                raise RuntimeError('blob checksum mismatch: ' + name)
            path.replace(root / name)
    finally:
        for fd in handles.values():
            os.close(fd)

    config_name = manifest['config']['digest'].removeprefix('sha256:')
    config = json.loads((root / config_name).read_text())
    if config.get('architecture') != 'arm64' or config.get('os') != 'linux':
        raise RuntimeError('expected linux/arm64 image')
    layout = [{'Config': config_name, 'RepoTags': [args.tag],
               'Layers': [b['digest'].removeprefix('sha256:') for b in manifest['layers']]}]
    archive = root / 'image.tar'
    with tarfile.open(archive, 'w') as tar:
        content = json.dumps(layout).encode()
        info = tarfile.TarInfo('manifest.json')
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
        for blob in blobs:
            name = blob['digest'].removeprefix('sha256:')
            tar.add(root / name, arcname=name, recursive=False)
    subprocess.run(['docker', 'load', '-i', str(archive)], check=True)
    actual = subprocess.check_output(['docker', 'image', 'inspect', args.tag,
                                      '--format', '{{.Id}}'], text=True).strip()
    if actual != manifest['config']['digest']:
        raise RuntimeError('loaded image config ID mismatch')
    # Docker recognizes the loaded config ID; this registers the digest without
    # downloading its layers again.
    pinned = 'ghcr.io/' + args.repository + '@' + args.digest
    subprocess.run(['docker', 'pull', pinned], check=True)
    registered = subprocess.check_output(['docker', 'image', 'inspect', pinned,
                                          '--format', '{{.Id}}'], text=True).strip()
    if registered != actual:
        raise RuntimeError('registered image ID mismatch')
    print(json.dumps({'complete': True, 'source_manifest': args.digest, 'image_id': actual}), flush=True)


if __name__ == '__main__':
    main()
