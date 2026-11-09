"""Bounded TLS/OPTIONS diagnostic. Never sends INVITE or a PSTN destination."""
import argparse
import json
import re
import socket
import ssl
import uuid
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--state', type=Path, required=True, help='Private owned-route preparation state')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
state = json.loads(a.state.read_text())
assert state['stage'] == 'registered_disabled_not_qualified' and state['trunk_disabled']
host = state['trunk_domain']
assert re.fullmatch(r'[A-Za-z0-9.-]+', host) and host.endswith(('.zt.plivo.com', '.sip.plivo.com'))
value = {'phone_calls': 0, 'invite_sent': False, 'stage': 'tcp_connect', 'cutover_qualified': False}
try:
    with socket.create_connection((host, 5061), timeout=7) as raw:
        value.update(tcp_connected=True, stage='tls_handshake')
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as connection:
            value.update(tls_verified=True, tls_version=connection.version(), stage='sip_options')
            connection.settimeout(7)
            nonce = uuid.uuid4().hex
            request = ('OPTIONS sip:' + host + ' SIP/2.0\r\n'
                'Via: SIP/2.0/TLS healthcheck.invalid;branch=z9hG4bK' + nonce + ';rport\r\n'
                'From: <sip:healthcheck@example.invalid>;tag=' + nonce + '\r\n'
                'To: <sip:' + host + '>\r\nCall-ID: ' + nonce + '@healthcheck.invalid\r\n'
                'CSeq: 1 OPTIONS\r\nMax-Forwards: 1\r\nContent-Length: 0\r\n\r\n')
            connection.sendall(request.encode())
            response = connection.recv(4096).decode(errors='replace').split('\r\n')[0]
            assert re.fullmatch(r'SIP/2.0 \d{3}[^\r\n]*', response), 'Expected SIP status line'
            value.update(stage='complete', sip_status=response[:100])
except (OSError, AssertionError) as error:
    value['error_type'] = type(error).__name__
a.output.write_text(json.dumps(value, indent=2))
a.output.chmod(0o600)
print(json.dumps(value))
if value.get('stage') != 'complete':
    raise SystemExit('Transport diagnostic incomplete; no call was placed')
