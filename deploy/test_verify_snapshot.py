import hashlib
from pathlib import Path
import tempfile
import unittest
from verify_snapshot import verify


class VerificationTests(unittest.TestCase):
    def test_lfs_corruption_rejected_even_at_correct_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'weight').write_bytes(b'bad')
            entry = {'rfilename': 'weight', 'size': 3,
                     'lfs': {'sha256': hashlib.sha256(b'yes').hexdigest()}}
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                verify(root, entry)
            (root / 'weight').write_bytes(b'yes')
            verify(root, entry)

    def test_git_blob_verified_with_header(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').write_bytes(b'{}')
            verify(root, {'rfilename': 'config', 'size': 2,
                          'blobId': hashlib.sha1(b'blob 2\0{}').hexdigest()})

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'escapes'):
                verify(Path(folder), {'rfilename': '../outside'})


if __name__ == '__main__':
    unittest.main()
