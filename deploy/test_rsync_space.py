from pathlib import Path
import re
import subprocess
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'start.sh').read_text()
FUNCTION = re.search(r'rsync_required_bytes\(\) \{.*?\n\}', SOURCE, re.S).group()


class SpaceTests(unittest.TestCase):
    def run_estimate(self, output, status=0):
        script = (f'rsync() {{ printf "%s\\n" "{output}"; return {status}; }}\n'
                  + FUNCTION + '\nWORKER_SSH=fixture\nrsync_required_bytes /src /dest')
        return subprocess.run(['bash', '-c', script], text=True, capture_output=True)

    def test_completed_copy_needs_no_weight_space(self):
        result = self.run_estimate('Total transferred file size: 0 bytes')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0'))

    def test_changed_files_reserve_full_replacement_sizes(self):
        result = self.run_estimate('Total transferred file size: 101,535,150,936 bytes')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '101535150936'))

    def test_failed_probe_is_not_zero(self):
        self.assertNotEqual(self.run_estimate('Total transferred file size: 0 bytes', 12).returncode, 0)

    def test_unknown_stats_are_not_zero(self):
        self.assertNotEqual(self.run_estimate('unrecognized output').returncode, 0)


if __name__ == '__main__':
    unittest.main()
