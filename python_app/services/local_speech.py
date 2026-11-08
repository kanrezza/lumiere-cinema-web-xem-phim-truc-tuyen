"""Loopback-only speech recognition. Movie files and audio stay on this host."""
import argparse
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5002)
    parser.add_argument('--model', default='tiny')
    parser.add_argument('--download-model', action='store_true', help='Allow the initial official model download.')
    args = parser.parse_args()
    from faster_whisper import WhisperModel

    app_root = Path(__file__).resolve().parents[1]
    media_root = Path(os.getenv('PRIVATE_MEDIA_ROOT', str(app_root / 'private_media'))).resolve()
    model_root = app_root / '.speech-models'
    token = os.getenv('SPEECH_API_TOKEN', '')
    model = WhisperModel(args.model, device='cpu', compute_type='int8', cpu_threads=4,
                         download_root=str(model_root), local_files_only=not args.download_model)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != '/health':
                return self.respond(404, {'error': 'Not found'})
            self.respond(200, {'status': 'ready', 'model': args.model, 'offline': True})

        def do_POST(self):
            self.connection.settimeout(30)
            if self.path != '/transcribe':
                return self.respond(404, {'error': 'Not found'})
            if token and not compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                return self.respond(403, {'error': 'Unauthorized'})
            try:
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Use application/json')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                source = Path(data['source_path']).resolve(strict=True)
                if not source.is_relative_to(media_root) or not source.is_file() or source.suffix.lower() not in ('.mp4', '.mkv', '.mov', '.webm', '.wav'):
                    raise ValueError('Source must be a private local media file')
                language = data.get('language', 'auto')
                if language not in ('auto', 'en', 'vi'):
                    raise ValueError('Unsupported source language')
                probe = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                        '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(source)],
                                       capture_output=True, text=True, timeout=15, check=True)
                info = json.loads(probe.stdout)
                duration = float(info.get('format', {}).get('duration', 0))
                if not 0 < duration <= 10800:
                    raise ValueError('Audio duration must be within 3 hours')
                if not any(stream.get('codec_type') == 'audio' for stream in info.get('streams', [])):
                    return self.respond(200, {'language': language if language != 'auto' else '', 'segments': [], 'no_speech': True})
                segments, result = model.transcribe(str(source), language=None if language == 'auto' else language,
                                                    beam_size=5, vad_filter=True, condition_on_previous_text=False,
                                                    no_speech_threshold=.6, log_prob_threshold=-1.0,
                                                    compression_ratio_threshold=2.4)
                output = []
                deadline = time.monotonic() + int(os.getenv('SPEECH_TIMEOUT', '1800'))
                for segment in segments:
                    if time.monotonic() > deadline:
                        raise ValueError('Speech recognition time limit exceeded')
                    text = segment.text.strip()
                    if text and segment.no_speech_prob < .6 and segment.avg_logprob >= -1.0:
                        output.append({'start': segment.start, 'end': segment.end, 'text': text})
                    if len(output) > 10000:
                        raise ValueError('Too many caption segments')
                self.respond(200, {'language': result.language, 'segments': output, 'no_speech': not output})
            except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
                self.respond(400, {'error': 'Unable to transcribe the selected local media.'})
            except Exception:
                self.respond(500, {'error': 'Speech recognition failed.'})

        def log_message(self, format, *args):
            # Paths, source payloads and recognized speech are never logged.
            pass

    print(f'Local speech service ready on 127.0.0.1:{args.port} (offline {args.model})', flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
