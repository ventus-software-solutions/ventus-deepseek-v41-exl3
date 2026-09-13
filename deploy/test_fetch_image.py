import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import fetch_image


class Response(io.BytesIO):
    status = 206

    def __init__(self, data, content_range=''):
        super().__init__(data)
        self.headers = {'Content-Range': content_range}


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.config = json.dumps({'architecture': 'arm64', 'os': 'linux'}).encode()
        self.layer = b'x' * (16 * 1024 * 1024 + 13)
        self.blobs = {}
        for data in (self.config, self.layer):
            self.blobs['sha256:' + hashlib.sha256(data).hexdigest()] = data
        self.config_id, self.layer_id = self.blobs
        self.manifest = json.dumps({
            'schemaVersion': 2,
            'config': {'digest': self.config_id, 'size': len(self.config)},
            'layers': [{'digest': self.layer_id, 'size': len(self.layer)}] * 2,
        }).encode()
        self.pin = 'sha256:' + hashlib.sha256(self.manifest).hexdigest()
        self.ranges = []
        self.bad_range = False

    def open(self, request, **_kwargs):
        url = request if isinstance(request, str) else request.full_url
        if '/token?' in url:
            return Response(b'{"token":"fixture"}')
        if '/manifests/' in url:
            return Response(self.manifest)
        digest = url.rsplit('/', 1)[1]
        data = self.blobs[digest]
        start, end = map(int, request.headers['Range'][6:].split('-'))
        self.ranges.append((digest, start, end))
        header = 'wrong' if self.bad_range else f'bytes {start}-{end}/{len(data)}'
        return Response(data[start:end + 1], header)

    def invoke(self, root):
        with patch('sys.argv', ['fetch_image', 'fixture/image', self.pin, str(root),
                               '--tag', 'fixture/image:test', '--workers', '2']), \
             patch('fetch_image.urllib.request.urlopen', self.open), \
             patch('fetch_image.subprocess.run') as run, \
             patch('fetch_image.subprocess.check_output', return_value=self.config_id), \
             patch('fetch_image.time.sleep'), patch('sys.stdout', io.StringIO()):
            fetch_image.main()
            return run

    def test_ranges_digest_archive_and_duplicate_layers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = self.invoke(root)
            self.assertEqual(fetch_image.digest_file(root / self.layer_id[7:]), self.layer_id)
            self.assertEqual(len(self.ranges), 3)  # config + two ranges, no duplicate fetch
            with tarfile.open(root / 'image.tar') as archive:
                manifest = json.load(archive.extractfile('manifest.json'))
                self.assertEqual(manifest[0]['Layers'], [self.layer_id[7:]] * 2)
                self.assertEqual(archive.getnames().count(self.layer_id[7:]), 1)
            self.assertEqual(run.call_args_list[0].args[0][:2], ['docker', 'load'])
            self.assertEqual(run.call_args_list[1].args[0],
                             ['docker', 'pull', 'ghcr.io/fixture/image@' + self.pin])

    def test_wrong_manifest_rejected_before_download(self):
        self.pin = 'sha256:' + '0' * 64
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'manifest digest mismatch'):
                self.invoke(Path(folder))
            self.assertFalse(self.ranges)

    def test_wrong_range_rejected(self):
        self.bad_range = True
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'byte range'):
                self.invoke(Path(folder))
            self.assertFalse((Path(folder) / 'image.tar').exists())


if __name__ == '__main__':
    unittest.main()
