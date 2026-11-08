"""Request bounds are checked without loading optional model dependencies."""
import contextlib
from http.server import ThreadingHTTPServer
import io
import json
import threading
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_translation import handler_for, Translator


class LocalServiceTests(unittest.TestCase):
    def translator(self, token_count=None, output_count=None):
        translator = Translator.__new__(Translator)
        translator.lock = threading.Lock()
        translator.languages = {'en': 'English', 'vi': 'Vietnamese'}

        def encode(text):
            return text.split() if token_count is None else ['x'] * token_count

        class Engine:
            def translate_batch(self, texts, **kwargs):
                return [SimpleNamespace(hypotheses=[tokens if output_count is None else ['x'] * output_count]) for tokens in texts]

        package = SimpleNamespace(tokenizer=SimpleNamespace(encode=encode, decode=lambda tokens: ' '.join(tokens)), target_prefix='')
        translator.pairs = {('en', 'vi'): (package, Engine())}
        return translator

    def test_scalar_and_batch_preserve_shape_and_empty_lines(self):
        translator = self.translator()
        self.assertEqual(translator.translate({'q': 'One line', 'source': 'en', 'target': 'vi'}), {'translatedText': 'One line'})
        self.assertEqual(translator.translate({'q': ['One line', '  '], 'source': 'en', 'target': 'vi'}), {'translatedText': ['One line', '  ']})

    def test_rejects_unknown_pair_html_and_non_text_queries(self):
        base = {'q': 'Text', 'source': 'en', 'target': 'vi'}
        for changes in ({'target': 'fr'}, {'source': []}, {'format': 'html'}, {'q': []}, {'q': [3]}, {'q': None}, {'q': '\0'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.translator().translate(base | changes)

    def test_batch_and_character_limits(self):
        for query in (['x'] * 51, ['x' * 20001]):
            with self.assertRaises(ValueError):
                self.translator().translate({'q': query, 'source': 'en', 'target': 'vi'})

    def test_does_not_silently_truncate_model_input_or_output(self):
        for translator in (self.translator(token_count=513), self.translator(output_count=1024)):
            with self.assertRaises(ValueError):
                translator.translate({'q': 'Text', 'source': 'en', 'target': 'vi'})

    def test_language_capabilities_report_only_installed_directions(self):
        self.assertEqual(self.translator().language_list(), [{'code': 'en', 'name': 'English', 'targets': ['vi']}])

    def test_http_contract_and_privacy_headers(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.translator()))
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                body = json.dumps({'q': ['Text'], 'source': 'en', 'target': 'vi'}).encode()
                with urlopen(Request(base + '/translate', data=body, headers={'Content-Type': 'application/json'}), timeout=3) as response:
                    self.assertEqual(json.load(response), {'translatedText': ['Text']})
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                    self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + '/translate', data=body, headers={'Content-Type': 'text/plain'}), timeout=3)
                self.assertEqual(error.exception.code, 415)
                error.exception.close()
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + '/unknown?private_subtitle_text', timeout=3)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
            self.assertNotIn('private_subtitle_text', output.getvalue())
            self.assertNotIn('Text', output.getvalue())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
