import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import publisher as p

class PublisherTest(unittest.TestCase):
    def test_album_success_and_uncertain_timeout_are_recorded(self):
        for fail in [False,True]:
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root/'output/2026-11-03'
                output.mkdir(parents=True)
                for lang in ['ru','en']:
                    (output/f'boring-report-{lang}.png').write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(16))
                config = {'channel':'@dots_and_lines','channel_id':-1001,'enabled':True,'mode':'auto'}
                record = {'articles':{},'preview':{'caption_ru':'RU','caption_en':'EN'}}
                messages = [{'message_id':11,'chat':{'id':-1001}},{'message_id':12,'chat':{'id':-1001}}]
                with patch.object(p,'ROOT',root),patch.object(p,'STATE',root),patch.object(p,'prepare',return_value=record),patch.object(p,'check_bot',return_value=({'id':7},{'id':-1001})),patch.object(p,'telegram',side_effect=p.UncertainRequest('timeout') if fail else None,return_value=messages) as send:
                    if fail:
                        with self.assertRaises(p.UncertainRequest):
                            p.publish('2026-11-03',config,scheduled=True)
                    else:
                        p.publish('2026-11-03',config,scheduled=True)
                    self.assertEqual(send.call_args.args[0],'sendMediaGroup')
                    self.assertEqual(set(send.call_args.args[2]),{'photo_ru','photo_en'})
                saved = json.loads((root/'2026-11-03.publication.json').read_text())
                self.assertEqual(saved['telegram']['status'],'uncertain' if fail else 'sent')

    def test_converter_preserves_text_and_links_without_scripts(self):
        nodes = p.article_nodes('<article><h1>Title</h1><p>A <strong>claim</strong> &amp; <a href="https://example.com/source">source</a>.</p><script>secret()</script><style>bad</style><p><a href="javascript:alert(1)">unsafe link</a></p></article>','https://example.com/plot.png','en')
        encoded = json.dumps(nodes)
        self.assertIn('https://example.com/source',encoded)
        self.assertIn('https://example.com/plot.png',encoded)
        self.assertIn('claim',encoded)
        self.assertNotIn('secret()',encoded)
        self.assertNotIn('javascript:',encoded)
        self.assertNotIn('"tag": "h1"',encoded)

    def test_provider_ids_and_merged_whitespace_do_not_fail_verification(self):
        original = ['\n ','\n',{'tag':'h3','children':['A title']}]
        live = ['\n \n',{'tag':'h3','attrs':{'id':'A-title'},'children':['A title']}]
        self.assertEqual(p.canonical_nodes(original),p.canonical_nodes(live))
        live[1]['children'] = ['Changed title']
        self.assertNotEqual(p.canonical_nodes(original),p.canonical_nodes(live))

    def test_already_sent_never_posts_again(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            p.save(state/'2026-11-03.publication.json',{'telegram':{'status':'sent'}})
            with patch.object(p,'STATE',state),patch.object(p,'telegram') as send:
                p.publish('2026-11-03',{'channel':'@dots_and_lines'})
                send.assert_not_called()

    def test_uncertain_delivery_cannot_be_retried_blindly(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            p.save(state/'2026-11-03.publication.json',{'telegram':{'status':'in_flight'}})
            with patch.object(p,'STATE',state),patch.object(p,'telegram') as send:
                with self.assertRaises(p.UncertainRequest):
                    p.publish('2026-11-03',{'channel':'@dots_and_lines'})
                send.assert_not_called()

    def test_read_only_permission_checks_reject_wrong_destination(self):
        responses = [{'id':1,'username':'reportbot'}, {'id':-1001,'type':'channel','username':'some_other_channel'}]
        with patch.object(p,'telegram',side_effect=responses):
            with self.assertRaises(p.APIError):
                p.check_bot({'channel':'@dots_and_lines'})

    def test_posting_permission_required(self):
        responses = [{'id':1,'username':'reportbot'}, {'id':-1001,'type':'channel','username':'dots_and_lines'}, {'status':'administrator','can_post_messages':False}]
        with patch.object(p,'telegram',side_effect=responses):
            with self.assertRaises(p.APIError):
                p.check_bot({'channel':'@dots_and_lines'})

    def test_image_and_article_links_do_not_disappear_in_conversion(self):
        for lang in ['ru','en']:
            source = p.ROOT/'data/issues/2026-11-03'/f'report-{lang}.html'
            if not source.exists():
                self.skipTest('Requires archived server fixture')
            parser = p.ArticleParser()
            parser.feed(source.read_text())
            nodes = p.article_nodes(source.read_text(),'https://example.com/image.png',lang)
            self.assertEqual(p.canonical_nodes(nodes[1:]),p.canonical_nodes(parser.nodes))

if __name__ == '__main__':
    unittest.main()
