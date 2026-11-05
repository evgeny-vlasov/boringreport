"""Regression checks for sourced regional references and empty-map rejection."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'data/issues/2026-11-03/issue.json'

class MapTest(unittest.TestCase):
    def validate(self, issue):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'issue.json'
            path.write_text(json.dumps(issue), encoding='utf-8')
            return subprocess.run(['Rscript', 'scripts/validate_issue.R', str(path)], cwd=ROOT, capture_output=True, text=True)

    def test_valid_sourced_regions(self):
        issue = json.loads(FIXTURE.read_text())
        self.assertTrue(all(e['location']['type'] == 'region' for e in issue['events']))
        result = self.validate(issue)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_reference_coordinate_rejected(self):
        issue = json.loads(FIXTURE.read_text())
        issue['events'][0]['location']['map_reference']['lat'] = 100
        result = self.validate(issue)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('map_reference.lat', result.stderr)

    def test_reference_requires_provenance(self):
        issue = json.loads(FIXTURE.read_text())
        del issue['events'][0]['location']['map_reference']['source_url']
        result = self.validate(issue)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('source_url', result.stderr)

    def test_empty_map_cannot_render(self):
        issue = json.loads(FIXTURE.read_text())
        for event in issue['events']:
            event['location'].pop('map_reference')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'issue.json'
            path.write_text(json.dumps(issue), encoding='utf-8')
            result = subprocess.run(['Rscript','scripts/render_report.R',str(path),str(Path(directory)/'output')], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No mappable events', result.stderr)
            self.assertFalse(list((Path(directory)/'output').glob('*.png')))

if __name__ == '__main__':
    unittest.main()
