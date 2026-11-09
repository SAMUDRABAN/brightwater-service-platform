"""Prepare an inactive owned-number SIP route. Never calls or changes number routing.

The credential state is private. Each mutation is durably marked before POST;
uncertain requests require reconciliation instead of duplicate resource creation.
"""
import argparse
import hashlib
import json
import os
import secrets
import string
from pathlib import Path

import httpx
from dotenv import dotenv_values

p = argparse.ArgumentParser()
p.add_argument('--voice-env', type=Path, required=True)
p.add_argument('--state', type=Path, required=True)
a = p.parse_args()
env = dotenv_values(a.voice_env)
number = env['BW_PLIVO_FROM_NUMBER']
assert number.startswith('+91'), 'This qualification is for the existing owned India number only'
state = json.loads(a.state.read_text()) if a.state.exists() else {
    'stage': 'preparing_disabled', 'username': 'bw' + secrets.token_hex(7),
    'password': ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(18)) + '!9',
    'phone_calls': 0, 'cutover_enabled': False,
    'qualification': {'regional_route_verified': False, 'recording_verified': False,
                      'native_consent_evidence_verified': False, 'handset_verified': False}}


def save():
    temp = a.state.with_name(a.state.name + '.refresh')
    temp.write_text(json.dumps(state, indent=2))
    temp.chmod(0o600)
    os.replace(temp, a.state)


def once(c, path, phase, payload):
    assert not state.get(phase + '_started'), 'Uncertain mutation: reconcile ' + phase + ', never retry automatically'
    state[phase + '_started'] = True
    save()
    r = c.post(path, json=payload)
    state[phase + '_status'] = r.status_code
    if r.status_code not in {200, 201}:
        state['stage'] = phase + '_rejected'
        state['rejection'] = r.json()
        save()
        raise SystemExit('SIP preparation rejected during ' + phase + ': HTTP ' + str(r.status_code))
    return r.json()


save()
base = 'https://api.plivo.com/v1/Account/' + env['BW_PLIVO_AUTH_ID']
def prepare():
    with httpx.Client(base_url=base, auth=(env['BW_PLIVO_AUTH_ID'], env['BW_PLIVO_AUTH_TOKEN']), timeout=30) as carrier:
        route = '/Number/' + number.lstrip('+') + '/'
        r = carrier.get(route)
        r.raise_for_status()
        original_application = r.json().get('application')
        assert original_application, 'Refusing to prepare without existing number application ownership'
        digest = hashlib.sha256(original_application.encode()).hexdigest()
        assert state.get('original_application_sha256', digest) == digest, 'Existing number application changed; review before continuing'
        state['original_application_sha256'] = digest
        save()
        if not state.get('credential_uuid'):
            value = once(carrier, '/Zentrunk/Credential/', 'credential_create', {
                'name': 'Brightwater disabled SIP qualification', 'username': state['username'], 'password': state['password']})
            state['credential_uuid'] = value['credential_uuid']
            save()
        if not state.get('trunk_id'):
            value = once(carrier, '/Zentrunk/Trunk/', 'trunk_create', {
                'name': 'Brightwater disabled secure outbound', 'trunk_direction': 'outbound',
                'trunk_status': 'disabled', 'secure': True, 'credential_uuid': state['credential_uuid']})
            state['trunk_id'] = value['trunk_id']
            save()
        r = carrier.get('/Zentrunk/Trunk/' + state['trunk_id'] + '/')
        if r.status_code >= 500:
            listing = carrier.get('/Zentrunk/Trunk/', params={'limit': 20, 'trunk_status': 'disabled', 'trunk_direction': 'outbound'})
            listing.raise_for_status()
            trunk = next((item for item in listing.json().get('objects', []) if str(item.get('trunk_id')) == str(state['trunk_id'])), None)
            assert trunk and trunk.get('credential_uuid') == state['credential_uuid'], 'Exact owned trunk not verified in account listing'
            state['detail_read_fallback'] = r.status_code
        else:
            r.raise_for_status()
            trunk = r.json()['object']
        assert trunk['trunk_status'] == 'disabled' and trunk['secure'] is True
        domain = trunk['trunk_domain']
        assert domain.endswith(('.zt.plivo.com', '.sip.plivo.com')), 'Unexpected carrier SIP host'
        state['trunk_domain'] = domain
        with httpx.Client(base_url='https://api.elevenlabs.io', headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']}, timeout=30) as native:
            if not state.get('eleven_phone_number_id'):
                value = once(native, '/v1/convai/phone-numbers', 'number_import', {
                    'provider': 'sip_trunk', 'phone_number': number, 'label': 'Brightwater Plivo / inactive qualification',
                    'agent_id': None, 'supports_inbound': False, 'supports_outbound': True,
                    'outbound_trunk_config': {'address': domain, 'transport': 'tls', 'media_encryption': 'required',
                        'enabled_codecs': ['PCMU/8000', 'PCMA/8000'], 'credentials': {'username': state['username'], 'password': state['password']}}})
                state['eleven_phone_number_id'] = value['phone_number_id']
                save()
            r = native.get('/v1/convai/phone-numbers/' + state['eleven_phone_number_id'])
            r.raise_for_status()
            assert r.json().get('agent_id') is None and not r.json().get('assigned_agent')
        r = carrier.get(route)
        r.raise_for_status()
        assert r.json().get('application') == original_application, 'Existing number application changed unexpectedly'
        state.update(stage='registered_disabled_not_qualified', application_unchanged=True,
                     trunk_disabled=True, secure=True, agent_assigned=False)
        save()


try:
    prepare()
except httpx.HTTPError as error:
    status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
    raise SystemExit('SIP provider operation failed safely: ' + str(status) + '; reconcile private state before proceeding') from None
print(json.dumps({'stage': state['stage'], 'number_registered_in_elevenlabs': True,
                  'carrier_trunk_disabled': True, 'agent_assigned': False, 'existing_application_unchanged': True,
                  'phone_calls': 0, 'cutover_enabled': False}))
