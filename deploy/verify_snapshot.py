"""Verify local Hub files against an immutable revision without loading weights."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def verify(root, entry):
    path = (root / entry['rfilename']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('path escapes model directory')
    if path.stat().st_size != entry['size']:
        raise ValueError(f'wrong size: {path}')
    lfs = entry.get('lfs')
    digest = hashlib.sha256() if lfs else hashlib.sha1()
    if not lfs:
        digest.update(f'blob {entry["size"]}\0'.encode())
    with path.open('rb') as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
    expected = lfs['sha256'] if lfs else entry['blobId']
    if digest.hexdigest() != expected:
        raise ValueError(f'hash mismatch: {path}')
    print(json.dumps({'file': entry['rfilename'], 'bytes': entry['size'],
                      'digest': digest.hexdigest(), 'verified': True}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('repo')
    parser.add_argument('revision')
    parser.add_argument('--files', nargs='+')
    args = parser.parse_args()
    if len(args.revision) != 40 or any(c not in '0123456789abcdef' for c in args.revision):
        parser.error('revision must be an immutable commit')
    url = f'https://huggingface.co/api/models/{args.repo}/revision/{args.revision}?blobs=true'
    with urllib.request.urlopen(url, timeout=60) as response:
        manifest = json.load(response)
    if manifest['sha'] != args.revision:
        raise ValueError('Hub returned a different revision')
    entries = {e['rfilename']: e for e in manifest['siblings']}
    for name in args.files or entries:
        verify(args.root, entries[name])
    print(json.dumps({'revision': args.revision, 'complete': True}), flush=True)


if __name__ == '__main__':
    main()
