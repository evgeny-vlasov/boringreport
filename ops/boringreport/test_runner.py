import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('runner', pathlib.Path(__file__).with_name('server_runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class RunnerTest(unittest.TestCase):
    def test_new_package_gets_repaired_after_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            state = root / 'state'
            state.mkdir()
            issue = '2026-11-03'
            package = root / 'data/issues' / issue
            package.mkdir(parents=True)
            (package / 'issue.json').write_text('{}')
            content = dict(issue_json=json.dumps({'issue_id':issue}), report_en='en', report_ru='ru', telegram_ru='tg')
            (state / f'{issue}.package.json').write_text(json.dumps(content))
            outputs = root / 'output' / issue
            outputs.mkdir(parents=True)
            png = b'\x89PNG\r\n\x1a\n' + bytes(8) + (2400).to_bytes(4,'big') + (1350).to_bytes(4,'big')
            for lang in ['en','ru']:
                (outputs / f'boring-report-{lang}.png').write_bytes(png)
                (outputs / f'boring-report-{lang}.svg').write_text('<svg></svg>')
            failed = Mock(returncode=1, stderr='missing schema field', stdout='')
            passed = Mock(returncode=0, stdout='Valid issue', stderr='')
            with patch.object(runner,'ROOT',root), patch.object(runner,'STATE',state), patch.object(runner,'run') as run, patch.object(runner.subprocess,'run',side_effect=[failed,passed]), patch.object(runner.subprocess,'check_output',return_value=b''), patch.object(sys,'argv',['runner','prepare','--issue',issue]):
                runner.main()
            self.assertTrue((state / f'{issue}.ready').exists())
            self.assertTrue(any('exec' in call.args for call in run.call_args_list))

    def test_rejects_wrong_issue_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            package = pathlib.Path(directory) / 'package'
            with self.assertRaises(ValueError):
                runner.write_package({'issue_json': '{"issue_id":"2026-09-29"}'}, '2026-11-03', package)
            self.assertFalse(package.exists())

    def test_recorded_delivery_does_not_send_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            state = root / 'state'
            state.mkdir()
            (state / '2026-11-03.ready').touch()
            with patch.object(runner,'ROOT',root), patch.object(runner,'STATE',state), patch.object(runner,'run'), patch.object(runner.subprocess,'run',return_value=Mock(returncode=0)), patch.object(runner,'send',return_value={'id':'test-id'}) as send, patch.object(sys,'argv',['runner','deliver','--issue','2026-11-03']):
                runner.main()
                runner.main()
                self.assertEqual(send.call_count,1)
            self.assertEqual(json.loads((state/'2026-11-03.sent.json').read_text())['id'],'test-id')

    def test_missing_gmail_id_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / '2026-11-03.ready').touch()
            with patch.object(runner,'ROOT',root), patch.object(runner,'STATE',root), patch.object(runner,'send',return_value={}), patch.object(sys,'argv',['runner','deliver','--issue','2026-11-03']):
                with self.assertRaises(RuntimeError):
                    runner.main()
            self.assertFalse((root/'2026-11-03.sent.json').exists())

if __name__ == '__main__':
    unittest.main()
