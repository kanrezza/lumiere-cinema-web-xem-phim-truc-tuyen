"""Loopback-only Argos service implementing the LibreTranslate text API subset.

Create a separate Python 3.12 virtual environment with requirements-translation.txt.
Run once with --install-models to obtain en/vi models from the official Argos index.
Subsequent translation uses installed models locally; it never calls a remote API.
"""
from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading


MAX_BODY_BYTES = 128 * 1024
MAX_BATCH = 50
MAX_TEXT_CHARACTERS = 20000
ALLOWED_PAIRS = (('en', 'vi'), ('vi', 'en'))
MODEL_VERSION = '1.9'


def configure_data_directory(directory):
    directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('ARGOS_PACKAGES_DIR', str(directory / 'packages'))
    os.environ.setdefault('XDG_DATA_HOME', str(directory / 'data'))
    os.environ.setdefault('XDG_CACHE_HOME', str(directory / 'cache'))
    os.environ.setdefault('XDG_CONFIG_HOME', str(directory / 'config'))
    os.environ.setdefault('ARGOS_DEVICE_TYPE', 'cpu')
    os.environ.setdefault('ARGOS_COMPUTE_TYPE', 'int8')
    os.environ.setdefault('ARGOS_INTER_THREADS', '1')
    os.environ.setdefault('ARGOS_INTRA_THREADS', '2')
    os.environ.setdefault('OMP_NUM_THREADS', '2')


def install_models():
    import argostranslate.package

    installed = {(package.from_code, package.to_code) for package in argostranslate.package.get_installed_packages() if package.package_version == MODEL_VERSION}
    missing = [pair for pair in ALLOWED_PAIRS if pair not in installed]
    if not missing:
        print('English/Vietnamese translation models are already installed.', flush=True)
        return
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    for source, target in missing:
        package = next((item for item in available if (item.from_code, item.to_code) == (source, target) and item.package_version == MODEL_VERSION), None)
        if package is None:
            raise RuntimeError(f'Official Argos index has no {source} -> {target} model.')
        print(f'Installing official Argos model {source} -> {target} ({package.package_version}).', flush=True)
        argostranslate.package.install_from_path(package.download())


class Translator:
    def __init__(self):
        import argostranslate.package
        import ctranslate2

        self.lock = threading.Lock()
        self.languages = {}
        self.pairs = {}
        for package in argostranslate.package.get_installed_packages():
            source, target = package.from_code, package.to_code
            if (source, target) not in ALLOWED_PAIRS or package.package_version != MODEL_VERSION:
                continue
            self.languages.update({source: package.from_name, target: package.to_name})
            engine = ctranslate2.Translator(
                str(package.package_path / 'model'), device='cpu',
                inter_threads=1, intra_threads=2, compute_type='int8',
            )
            self.pairs[(source, target)] = (package, engine)
        if not self.pairs:
            raise RuntimeError('No en/vi model installed. Run this service once with --install-models.')

    def language_list(self):
        return [
            {'code': code, 'name': self.languages[code],
             'targets': sorted(target for source, target in self.pairs if source == code)}
            for code in sorted({source for source, _target in self.pairs})
        ]

    def translate(self, payload):
        source, target = payload.get('source'), payload.get('target')
        if payload.get('format', 'text') != 'text':
            raise ValueError('Only plain-text translation is supported.')
        if not isinstance(source, str) or not isinstance(target, str) or (source, target) not in self.pairs:
            raise ValueError('Only installed English/Vietnamese language pairs are supported.')
        query = payload.get('q')
        is_list = isinstance(query, list)
        texts = query if is_list else [query]
        if not 1 <= len(texts) <= MAX_BATCH or any(not isinstance(text, str) for text in texts):
            raise ValueError('q must be text or an array of up to 50 texts.')
        if sum(len(text) for text in texts) > MAX_TEXT_CHARACTERS:
            raise ValueError('The batch exceeds 20,000 characters.')
        if any('\x00' in text for text in texts):
            raise ValueError('Text contains an invalid control character.')
        package, engine = self.pairs[(source, target)]
        with self.lock:
            translated = list(texts)
            indexes = [index for index, text in enumerate(texts) if text.strip()]
            tokenized = [package.tokenizer.encode(texts[index]) for index in indexes]
            if any(len(tokens) > 512 for tokens in tokenized):
                raise ValueError('A subtitle cue exceeds the local model token limit.')
            if tokenized:
                # Each subtitle cue is already a bounded unit. Use the official
                # Argos tokenizer/model directly, without a sentence detector.
                prefix = [[package.target_prefix]] * len(tokenized) if package.target_prefix else None
                results = engine.translate_batch(
                    tokenized, target_prefix=prefix, replace_unknowns=True,
                    beam_size=4, num_hypotheses=1, length_penalty=0.2,
                    max_input_length=512, max_decoding_length=1024,
                )
                for index, result in zip(indexes, results):
                    if len(result.hypotheses[0]) >= 1024:
                        raise ValueError('The local model reached its output token limit.')
                    value = package.tokenizer.decode(result.hypotheses[0])
                    if package.target_prefix and value.startswith(package.target_prefix):
                        value = value[len(package.target_prefix):]
                    translated[index] = value.lstrip(' ')
        return {'translatedText': translated if is_list else translated[0]}


def handler_for(translator):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'LumiereLocalTranslate/1'

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def json_response(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/languages':
                self.json_response(200, translator.language_list())
            elif self.path == '/health':
                self.json_response(200, {'status': 'ok', 'engine': 'argos-local', 'modelVersion': MODEL_VERSION, 'pairs': len(translator.pairs)})
            else:
                self.json_response(404, {'error': 'Endpoint not found.'})

        def do_POST(self):
            if self.path != '/translate':
                return self.json_response(404, {'error': 'Endpoint not found.'})
            if self.headers.get_content_type() != 'application/json':
                return self.json_response(415, {'error': 'Send application/json.'})
            if self.headers.get('Transfer-Encoding'):
                return self.json_response(400, {'error': 'Chunked requests are not accepted.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY_BYTES:
                    return self.json_response(413, {'error': 'Request is empty or too large.'})
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('Expected a JSON object.')
                result = translator.translate(payload)
            except (ValueError, UnicodeDecodeError):
                return self.json_response(400, {'error': 'Invalid translation request or unsupported language pair.'})
            except Exception:
                # Do not log user subtitle text, request bodies or provider internals.
                return self.json_response(503, {'error': 'Local translation failed; check installed language models.'})
            self.json_response(200, result)

        def log_message(self, format, *args):
            # Even an invalid URL might contain subtitle text in its query.
            # Log only method/status, never paths, bodies, headers or API keys.
            status = args[1] if len(args) > 1 and str(args[1]).isdigit() else '-'
            print(f'local-translate {self.command} {status}', flush=True)

    return Handler


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5001)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / '.translation-data')
    parser.add_argument('--install-models', action='store_true')
    args = parser.parse_args()
    configure_data_directory(args.data_dir.resolve())
    if args.install_models:
        install_models()
    translator = Translator()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(translator))
    server.daemon_threads = True
    print(f'Local translation ready at http://127.0.0.1:{args.port}; subtitle text stays on this machine.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
