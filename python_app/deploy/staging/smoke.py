"""Check the loopback staging deployment over HTTPS using its trusted CA."""
import argparse
from dataclasses import dataclass
from email.message import Message
from hashlib import sha512
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import hmac
import json
from pathlib import Path
import re
import ssl
import subprocess
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


@dataclass
class Reply:
    status: int
    headers: Message
    body: bytes

    def text(self):
        return self.body.decode('utf-8')

    def json(self):
        return json.loads(self.body)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        # In particular, never follow the fixture's payment redirect.
        return None


class BrowserSession:
    def __init__(self, origin, tls):
        self.origin = origin
        self.cookies = CookieJar()
        self.opener = build_opener(
            ProxyHandler({}), NoRedirects(), HTTPSHandler(context=tls), HTTPCookieProcessor(self.cookies),
        )

    def request(self, path, data=None):
        expect(path.startswith('/') and not path.startswith('//'), 'Expected a same-origin request path')
        headers = {}
        body = None
        if data is not None:
            csrf = next((cookie.value for cookie in self.cookies if cookie.name == 'csrftoken'), None)
            expect(csrf, 'Missing session CSRF cookie')
            body = urlencode({**data, 'csrfmiddlewaretoken': csrf}).encode()
            headers = {'Origin': self.origin, 'Referer': self.origin + '/'}
        request = Request(self.origin + path, data=body, headers=headers)
        try:
            response = self.opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        except URLError as error:
            raise RuntimeError('Cannot reach the isolated HTTPS staging stack. Check its service health and CA.') from error
        with response:
            return Reply(response.code, response.headers, response.read())

    def login(self, username, password):
        login = '/accounts/login/'
        expect(self.request(login).status == 200, 'Login form could not be loaded')
        response = self.request(login, {'username': username, 'password': password})
        expect(response.status == 302, 'Fixture login was not accepted')
        session = next((item for item in self.cookies if item.name == 'sessionid'), None)
        expect(session and session.secure and session.has_nonstandard_attr('HttpOnly'),
               'Session cookie must be Secure and HttpOnly')


class CheckoutFields(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.active = False
        self.values = {}
        self.feed(markup)

    def handle_starttag(self, tag, attributes):
        details = dict(attributes)
        if tag == 'form':
            self.active = details.get('id') == 'membership-form'
        if not self.active or tag != 'input' or 'name' not in details:
            return
        if details.get('type') == 'hidden' and details['name'] != 'csrfmiddlewaretoken':
            self.values[details['name']] = details.get('value', '')
        if details.get('type') == 'radio' and (details['name'] not in self.values or 'checked' in details):
            self.values[details['name']] = details.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.active = False


def expect(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def play_fixture(host, decode):
    movie = host.request('/movies/tram-anh-sang-demo/')
    expect(movie.status == 200, 'Fixture movie was not published on staging')
    match = re.search(r'href="(/watch/\d+/)', movie.text())
    expect(match, 'No episode link was found')
    watch_path = match.group(1)
    watch = host.request(watch_path)
    expect(watch.status == 200, 'Authenticated watch page was not available')

    ticket = host.request(watch_path + 'ticket/', {})
    expect(ticket.status == 200, 'Could not issue a playback ticket')
    manifest = host.request(ticket.json()['url'])
    expect(manifest.status == 200 and manifest.body.startswith(b'#EXTM3U'), 'Invalid HLS playlist')
    expect('no-store' in manifest.headers.get('Cache-Control', ''), 'Private HLS must not be cached')
    lines = manifest.text().splitlines()
    if any(line.startswith('#EXT-X-STREAM-INF:') for line in lines):
        rendition_url = next((line for line in lines if line and not line.startswith('#')), '')
        expect(rendition_url, 'HLS master playlist has no rendition')
        manifest = host.request(rendition_url)
        expect(manifest.status == 200 and manifest.body.startswith(b'#EXTM3U'),
               'HLS rendition playlist could not be fetched')
        expect('no-store' in manifest.headers.get('Cache-Control', ''), 'Private HLS must not be cached')
        lines = manifest.text().splitlines()
    expect(not any(line.startswith('#EXT-X-STREAM-INF:') for line in lines)
           and any(line.startswith('#EXTINF:') for line in lines), 'Invalid HLS media playlist')
    segment_url = next((line for line in lines if line and not line.startswith('#')), '')
    expect(segment_url, 'HLS media playlist has no segment')
    segment = host.request(segment_url)
    expect(segment.status == 200 and segment.body[:1] == b'\x47' and len(segment.body) >= 188,
           'HLS media segment could not be fetched')
    if decode:
        with NamedTemporaryFile(suffix='.ts') as fixture:
            fixture.write(segment.body)
            fixture.flush()
            subprocess.run(
                ['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', fixture.name,
                 '-map', '0:v:0', '-frames:v', '1', '-f', 'null', '-'],
                check=True, timeout=20,
            )

    track_urls = re.findall(r'src="(/watch/\d+/subtitles/\d+\.vtt)"', watch.text())
    expect(len(set(track_urls)) >= 2, 'The fixture must have two subtitle tracks')
    for url in track_urls:
        track = host.request(url)
        expect(track.status == 200 and track.body.startswith(b'WEBVTT'), 'Caption track did not load')
    print(f'PASS playback ticket, HLS manifest/segment{" and FFmpeg decode" if decode else ""}, and WebVTT')
    return watch_path


def check_room(host, viewer, watch_path):
    created = host.request(watch_path + 'room/', {'name': 'Staging smoke', 'requires_approval': 'on'})
    room = created.headers.get('Location', '')
    expect(created.status == 302 and re.fullmatch(r'/rooms/[0-9a-f-]+/', room), 'Could not create a watch room')
    try:
        expect(viewer.request(room).status == 200, 'The viewer could not open the room lobby')
        expect(viewer.request(room + 'join/', {}).status == 302, 'The viewer could not request admission')
        admission = host.request(room + 'admission/')
        expect(admission.status == 200 and admission.json()['pending_count'] == 1, 'Host did not receive the request')
        queue_id = admission.json()['pending'][0]['pk']
        approved = host.request(room + 'admission/', {'action': 'approve', 'request': queue_id})
        expect(approved.status == 200, 'Host could not approve the viewer')
        expect(viewer.request(room + 'join/', {}).status == 302, 'Approved viewer could not join')

        request = host.request(room + 'state/', {'action': 'sync', 'position': '7', 'playing': 'false'})
        state = viewer.request(room + 'state/')
        expect(request.status == state.status == 200 and state.json()['position'] == 7,
               'Host position did not sync to the viewer session')
        expect(len(state.json()['members']) == 2, 'Expected two independently authenticated room members')
    finally:
        host.request(room + 'state/', {'action': 'close'})
    print('PASS room admission and playback sync across two HTTPS sessions')


def fixture_hash(values, secret):
    query = urlencode(sorted((key, value) for key, value in values.items() if key != 'vnp_SecureHash'))
    return hmac.new(secret.encode(), query.encode(), sha512).hexdigest()


def check_payment(viewer, secret, origin):
    plans = viewer.request('/vip/?renew=1')
    expect(plans.status == 200, 'VIP options could not be loaded')
    fields = CheckoutFields(plans.text()).values
    expect(fields.get('plan') and fields.get('checkout_token'), 'Checkout form must include a plan and retry token')
    first = viewer.request('/checkout/', fields)
    replay = viewer.request('/checkout/', fields)
    location = urlsplit(first.headers.get('Location', ''))
    replay_location = urlsplit(replay.headers.get('Location', ''))
    expect(first.status == replay.status == 302 and location.netloc == 'payments.example.invalid'
           and location.path == '/vnpay-fixture', 'Checkout did not redirect to the isolated fixture')
    order = dict(parse_qsl(location.query))
    expect(order.get('vnp_TmnCode') == 'LUMIFIXT' and order.get('vnp_ReturnUrl') == origin + '/payments/return/',
           'Checkout does not use the configured staging fixture')
    expect(order.get('vnp_TxnRef') == dict(parse_qsl(replay_location.query)).get('vnp_TxnRef'),
           'Retrying checkout generated a different order')
    expect(hmac.compare_digest(order['vnp_SecureHash'], fixture_hash(order, secret)), 'Checkout signature mismatch')

    # Call the isolated local application's IPN, with reserved fixture credentials.
    callback = {key: order[key] for key in ('vnp_TmnCode', 'vnp_TxnRef', 'vnp_Amount')}
    callback.update(vnp_ResponseCode='00', vnp_TransactionStatus='00', vnp_TransactionNo='314159265')
    callback['vnp_SecureHash'] = fixture_hash(callback, secret)
    path = '/payments/ipn/?' + urlencode(callback)
    first = viewer.request(path)
    second = viewer.request(path)
    expect(first.status == second.status == 200 and first.json()['RspCode'] == '00'
           and second.json()['RspCode'] == '02', 'Fixture callback was not accepted exactly once')
    membership = viewer.request('/vip/')
    expect(membership.status == 200 and 'VIP của bạn đang hoạt động' in membership.text(),
           'The confirmed fixture order did not activate VIP')
    print('PASS checkout retry, signed fixture IPN, and VIP activation over HTTPS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, default=Path(__file__).with_name('.env'))
    parser.add_argument('--ca', type=Path, required=True)
    parser.add_argument('--decode', action='store_true', help='Decode the first HLS segment using ffmpeg.')
    args = parser.parse_args()
    env = dict(line.split('=', 1) for line in args.env.read_text().splitlines() if line and not line.startswith('#'))
    port = int(env.get('STAGING_PORT', '8443'))
    origin = f'https://localhost:{port}'
    tls = ssl.create_default_context(cafile=str(args.ca))
    host = BrowserSession(origin, tls)
    viewer = BrowserSession(origin, tls)

    landing = host.request('/')
    expect(landing.status == 200 and 'Lumière' in landing.text(), 'HTTPS landing was not available')
    static = re.search(r'src="(/static/bundles/catalog/[^"]+\.js)"', landing.text())
    expect(static and host.request(unescape(static.group(1))).status == 200, 'Built Vue bundle was not served')
    expect(host.request('/private_media/').status == 404, 'Private storage path is publicly exposed')
    host.login('staging-host', env['STAGING_HOST_PASSWORD'])
    viewer.login('staging-viewer', env['STAGING_VIEWER_PASSWORD'])
    print('PASS trusted HTTPS, Vue bundle, private storage boundary, and secure sessions')
    route = play_fixture(host, args.decode)
    check_room(host, viewer, route)
    check_payment(viewer, env['STAGING_PAYMENT_SECRET'], origin)


if __name__ == '__main__':
    main()
