import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import publisher as p

class PublisherTest(unittest.TestCase):
    def publication_fixture(self,root):
        output = root/'output/2026-11-03'
        output.mkdir(parents=True)
        for lang in ['ru','en']:
            (output/f'boring-report-{lang}.png').write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(16))
        config = {'channel':'@dots_and_lines','channel_id':-1001,'enabled':True,'mode':'auto'}
        record = {'articles':{'ru':{'url':'https://telegra.ph/RU'},'en':{'url':'https://telegra.ph/EN'}}}
        data = {'issue_id':'2026-11-03','issue_number':5}
        record['preview'] = p.preview(data,record,'<p><strong>Summary</strong><br>Text &amp; <a href="https://example.com">source</a>.</p>')
        def prepare(issue):
            state = root/f'{issue}.publication.json'
            return json.loads(state.read_text()) if state.exists() else record
        return config,prepare

    def response(self,message_id):
        return {'message_id':message_id,'chat':{'id':-1001}}

    def test_four_posts_in_order_with_only_ru_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config,prepare = self.publication_fixture(root)
            with patch.object(p,'ROOT',root),patch.object(p,'STATE',root),patch.object(p,'prepare',side_effect=prepare),patch.object(p,'check_bot',return_value=({'id':7},{'id':-1001})),patch.object(p.time,'sleep'),patch.object(p,'telegram',side_effect=[self.response(n) for n in [11,12,13,14]]) as send:
                p.publish('2026-11-03',config,scheduled=True)
                self.assertEqual([call.args[0] for call in send.call_args_list],['sendPhoto','sendMessage','sendMessage','sendMessage'])
                calls = send.call_args_list
                self.assertEqual(set(calls[0].args[2]),{'photo'})
                self.assertEqual(calls[0].args[2]['photo'].name,'boring-report-ru.png')
                self.assertEqual(calls[0].args[1]['caption'],'Boring Report №05 — 03.11.2026')
                self.assertEqual(calls[1].args[1]['text'],'<strong>Summary</strong>\nText &amp; <a href="https://example.com">source</a>.')
                for call in calls[1:]:
                    self.assertIsNone(call.args[2])
                    self.assertFalse(call.args[1]['link_preview_options']['is_disabled'])
                self.assertIn('<b><a href="https://telegra.ph/RU">',calls[2].args[1]['text'])
                self.assertIn('<b><a href="https://telegra.ph/EN">',calls[3].args[1]['text'])
                p.publish('2026-11-03',config,scheduled=True)
                self.assertEqual(send.call_count,4)
            state = json.loads((root/'2026-11-03.publication.json').read_text())['telegram']
            self.assertEqual(state['status'],'sent')
            self.assertEqual(state['message_ids'],[11,12,13,14])

    def test_definitive_rejection_resumes_without_repeating_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config,prepare = self.publication_fixture(root)
            responses = [self.response(11),p.APIError('rate limit'),self.response(12),self.response(13),self.response(14)]
            with patch.object(p,'ROOT',root),patch.object(p,'STATE',root),patch.object(p,'prepare',side_effect=prepare),patch.object(p,'check_bot',return_value=({'id':7},{'id':-1001})),patch.object(p.time,'sleep'),patch.object(p,'telegram',side_effect=responses) as send:
                with self.assertRaises(p.APIError):
                    p.publish('2026-11-03',config,scheduled=True)
                p.publish('2026-11-03',config,scheduled=True)
                self.assertEqual([c.args[0] for c in send.call_args_list].count('sendPhoto'),1)
            state = json.loads((root/'2026-11-03.publication.json').read_text())['telegram']
            self.assertEqual(state['message_ids'],[11,12,13,14])

    def test_uncertain_second_post_blocks_blind_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config,prepare = self.publication_fixture(root)
            with patch.object(p,'ROOT',root),patch.object(p,'STATE',root),patch.object(p,'prepare',side_effect=prepare),patch.object(p,'check_bot',return_value=({'id':7},{'id':-1001})),patch.object(p.time,'sleep'),patch.object(p,'telegram',side_effect=[self.response(11),p.UncertainRequest('timeout')]) as send:
                with self.assertRaises(p.UncertainRequest):
                    p.publish('2026-11-03',config,scheduled=True)
                with self.assertRaises(p.UncertainRequest):
                    p.publish('2026-11-03',config,scheduled=True)
                self.assertEqual(send.call_count,2)
            state = json.loads((root/'2026-11-03.publication.json').read_text())['telegram']
            self.assertEqual(state['posts']['ru_image']['message_id'],11)
            self.assertEqual(state['posts']['ru_message']['status'],'uncertain')

    def test_oversized_second_post_is_not_truncated_or_split(self):
        record = {'articles':{'ru':{'url':'https://telegra.ph/RU'},'en':{'url':'https://telegra.ph/EN'}}}
        with self.assertRaises(ValueError):
            p.preview({'issue_id':'2026-11-03','issue_number':5},record,'<p>'+('x'*4097)+'</p>')

    def test_owner_removed_batch_stays_suppressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p.save(root/'2026-11-03.publication.json',{'telegram':{'status':'sent','removed_by_owner_request':True,'message_ids':[2113,2114]}})
            with patch.object(p,'STATE',root),patch.object(p,'telegram') as send:
                p.publish('2026-11-03',{'channel':'@dots_and_lines'})
                send.assert_not_called()

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
