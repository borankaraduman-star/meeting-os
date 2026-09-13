"""Report retention and transfer budgets without sockets or real user data."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os import team_cloud as TC


class OfflineFiles:
    def __init__(self, *, sizes=True):
        self.blobs = {f'reports/other/2026-09-0{day}_m{day}.json': b' ' * 18 + b'{}'
                      for day in range(1, 6)}
        self.sizes = sizes
        self.downloads = []
        self.fail_path = None
        self.updated = {}

    def index(self):
        files = {}
        for path, blob in self.blobs.items():
            files[path] = {'sha256': hashlib.sha256(blob).hexdigest(),
                           'updated': self.updated.get(path, '2026-09-13T12:00:00Z')}
            if self.sizes: files[path]['size'] = len(blob)
        return files, ['other']

    def left(self): return 20

    def get(self, path, etag=None):
        if path == self.fail_path: raise TC._OutOfTime()
        blob = self.blobs[path]
        if etag == hashlib.sha256(blob).hexdigest(): return None
        self.downloads.append(path)
        return blob


class ReportCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.mirror = self.data / 'mirror'
        self.mirror.mkdir()
        self.server = OfflineFiles()
        self.state = {}

    def run_pass(self, *, budget=45, keep=300):
        result = {'pushed': 0, 'pulled': 0, 'deleted': 0, 'removed': 0, 'pruned': 0}
        with patch.object(TC, '_own_files', return_value={}), \
             patch.object(TC, 'PULL_REPORT_BYTES', budget), patch.object(TC, 'PULL_REPORTS', keep):
            error = TC._run(self.data, {}, self.server, self.mirror, 'self', self.state, result)
        return result, error

    def cached_names(self):
        return sorted(p.name for p in (self.mirror / 'reports' / 'other').glob('*.json'))

    def test_size_limited_reports_are_not_downloaded_and_discarded_each_pass(self):
        first, _ = self.run_pass()
        self.assertEqual((first['pulled'], first['pruned']), (2, 0))
        self.assertEqual(self.cached_names(), ['2026-09-04_m4.json', '2026-09-05_m5.json'])
        again, _ = self.run_pass()
        self.assertEqual((again['pulled'], again['pruned']), (0, 0))

    def test_previously_pruned_report_is_skipped_but_missing_kept_file_is_repaired(self):
        self.run_pass(budget=200)
        self.run_pass()
        (self.mirror / 'reports/other/2026-09-05_m5.json').unlink()
        self.server.downloads.clear()
        self.run_pass()
        self.assertEqual(self.server.downloads, ['reports/other/2026-09-05_m5.json'])
        self.assertEqual(self.cached_names(), ['2026-09-04_m4.json', '2026-09-05_m5.json'])

    def test_changed_content_that_now_fits_is_downloaded(self):
        self.run_pass()
        path = 'reports/other/2026-09-04_m4.json'
        self.server.blobs[path] = b' ' * 23 + b'{}'
        result, _ = self.run_pass()
        self.assertEqual(result['pulled'], 1)
        self.assertEqual((self.mirror / path).read_bytes(), self.server.blobs[path])

    def test_server_deletion_makes_room_for_older_report_and_forgets_deleted_digest(self):
        self.run_pass(budget=200)
        self.run_pass()
        # The oldest report has already been evicted locally, so sweeping only files misses its digest.
        del self.server.blobs['reports/other/2026-09-01_m1.json']
        del self.server.blobs['reports/other/2026-09-05_m5.json']
        self.run_pass()
        self.assertEqual(self.cached_names(), ['2026-09-03_m3.json', '2026-09-04_m4.json'])
        self.assertNotIn('reports/other/2026-09-01_m1.json', self.state['pulled'])
        self.assertNotIn('reports/other/2026-09-05_m5.json', self.state['pulled'])

    def test_report_age_not_latest_upload_time_decides_which_reports_fit(self):
        self.server.updated['reports/other/2026-09-01_m1.json'] = '9999'
        self.run_pass(keep=2)
        self.assertEqual(self.cached_names(), ['2026-09-04_m4.json', '2026-09-05_m5.json'])

    def test_offline_teammate_heartbeat_survives_the_report_limit(self):
        self.server.blobs['reports/other/heartbeat.json'] = b'{"host":"other"}'
        self.server.blobs['reports/other/recording-heartbeat.json'] = b'{}'
        self.server.updated['reports/other/heartbeat.json'] = '0000'
        self.server.updated['reports/other/recording-heartbeat.json'] = '0000'
        self.run_pass(keep=1)
        self.assertEqual(self.cached_names(), ['2026-09-05_m5.json', 'heartbeat.json', 'recording-heartbeat.json'])

    def test_budget_expiration_still_prunes_old_cached_reports(self):
        self.run_pass(budget=200)
        path = 'reports/other/2026-09-05_m5.json'
        self.server.blobs[path] = b'{' + b' ' * 18 + b'}'
        self.server.fail_path = path
        result, error = self.run_pass()
        self.assertEqual(error, 'budget')
        self.assertEqual(result['pruned'], 3)
        self.assertLessEqual(sum(p.stat().st_size for p in self.mirror.rglob('*.json')), 45)

    def test_failed_refresh_keeps_existing_reports_until_replacements_arrive(self):
        self.run_pass(keep=2)
        self.server.blobs['reports/other/2026-09-06_m6.json'] = b' ' * 18 + b'{}'
        self.server.blobs['reports/other/2026-09-07_m7.json'] = b' ' * 18 + b'{}'
        self.server.fail_path = 'reports/other/2026-09-07_m7.json'
        _, error = self.run_pass(keep=2)
        self.assertEqual(error, 'budget')
        self.assertEqual(self.cached_names(), ['2026-09-04_m4.json', '2026-09-05_m5.json'])

    def test_missing_remote_sizes_do_not_repeat_evicted_downloads(self):
        self.server.sizes = False
        self.run_pass()
        self.server.downloads.clear()
        self.run_pass()
        self.assertEqual(self.server.downloads, [])
        self.assertEqual(self.cached_names(), ['2026-09-04_m4.json', '2026-09-05_m5.json'])
        # A larger budget can reclaim an intentionally evicted report; it is not a permanent tombstone.
        self.run_pass(budget=60)
        self.assertEqual(self.cached_names(), ['2026-09-03_m3.json', '2026-09-04_m4.json', '2026-09-05_m5.json'])

    def test_changed_unknown_size_report_is_reconsidered_after_eviction(self):
        self.server.sizes = False
        self.run_pass()
        path = 'reports/other/2026-09-03_m3.json'
        self.server.blobs[path] = b'{}'   # now the two newest and this report fit in 45 bytes
        self.run_pass()
        self.assertEqual((self.mirror / path).read_bytes(), b'{}')

    def test_size_fallback_state_is_bounded_and_removed_with_server_reports(self):
        self.server.sizes = False
        self.run_pass(budget=200)
        self.run_pass(budget=200, keep=2)
        self.assertLessEqual(len(self.state['report_sizes']), 2)
        self.server.blobs.clear()
        self.run_pass()
        self.assertEqual(self.state['report_sizes'], {})
        self.assertEqual(self.state['pulled'], {})

    def test_a_changed_report_too_large_to_retain_does_not_leave_stale_cached_bytes(self):
        self.run_pass()
        path = 'reports/other/2026-09-04_m4.json'
        self.server.blobs[path] = b' ' * 100 + b'{}'
        self.server.downloads.clear()
        self.run_pass()
        self.assertFalse((self.mirror / path).exists())
        self.assertEqual(self.cached_names(), ['2026-09-05_m5.json'])
        self.assertEqual(self.server.downloads, [])


if __name__ == '__main__': unittest.main()
