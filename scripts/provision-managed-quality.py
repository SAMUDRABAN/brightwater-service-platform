"""Idempotently provision owned native tests/dictionary. No calls or diary writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx

from brightwater.managed.quality import PRONUNCIATION_RULES, native_tests

p = argparse.ArgumentParser()
p.add_argument('--state', type=Path, required=True)
p.add_argument('--agent-state', type=Path, action='append', required=True)
a = p.parse_args()
state = json.loads(a.state.read_text()) if a.state.exists() else {'agents': {}}


def save():
    temp = a.state.with_name(a.state.name + '.refresh')
    temp.write_text(json.dumps(state, indent=2))
    temp.chmod(0o600)
    os.replace(temp, a.state)


with httpx.Client(base_url='https://api.elevenlabs.io', headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']}, timeout=40) as c:
    if not state.get('dictionary'):
        r = c.post('/v1/pronunciation-dictionaries/add-from-rules', json={
            'name': 'Brightwater approved terms v1', 'description': 'CP12, VAT and Southsea; no personal customer data',
            'rules': PRONUNCIATION_RULES})
        r.raise_for_status()
        v = r.json()
        state['dictionary'] = {'pronunciation_dictionary_id': v['id'], 'version_id': v['version_id']}
        save()
    for file in a.agent_state:
        owned = json.loads(file.read_text())
        aid = owned['agent_id']
        r = c.get('/v1/convai/agents/' + aid)
        r.raise_for_status()
        v = r.json()
        assert v['name'].startswith('Brightwater Managed Candidate'), 'Refusing another agent'
        tool_ids = {}
        for tid in v['conversation_config']['agent']['prompt']['tool_ids']:
            r = c.get('/v1/convai/tools/' + tid)
            r.raise_for_status()
            tool = r.json()
            # Provider returns the authoritative standalone configuration.
            name = (tool.get('tool_config') or tool).get('name')
            if name:
                tool_ids[name] = tid
        assert {'prepare_booking', 'confirm_booking', 'cancel_arrangement'} <= set(tool_ids), 'Required tool identity absent'
        tests = state.setdefault('agents', {}).setdefault(aid, {'tests': {}})['tests']
        for definition in native_tests(tool_ids):
            body = dict(definition)
            key = body.pop('key')
            digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            if tests.get(key, {}).get('sha256') == digest:
                evaluation = body.get('tool_call_parameters', {})
                expected = next((name for name, tid in tool_ids.items() if tid == evaluation.get('referenced_tool', {}).get('id')), None)
                tests[key].update(referenced_tool_id=evaluation.get('referenced_tool', {}).get('id'), expected_tool=expected, verify_absence=evaluation.get('verify_absence', False),
                    expected_proposal_id='quality-fixture-proposal' if expected in {'confirm_booking', 'cancel_arrangement'} and not evaluation.get('verify_absence') else None)
                continue
            # Retain old test IDs rather than deleting regression evidence.
            r = c.put('/v1/convai/agent-testing/' + tests[key]['id'], json=body) if key in tests else c.post('/v1/convai/agent-testing/create', json=body)
            if r.status_code not in {200, 201}:
                print('Native test creation rejected', key, r.status_code, r.text[:1200])
                raise SystemExit(1)
            test_id = r.json().get('id') or r.json().get('test_id') or tests.get(key, {}).get('id')
            assert test_id
            evaluation = body.get('tool_call_parameters', {})
            expected = next((name for name, tid in tool_ids.items() if tid == evaluation.get('referenced_tool', {}).get('id')), None)
            tests[key] = {'id': test_id, 'sha256': digest, 'referenced_tool_id': evaluation.get('referenced_tool', {}).get('id'), 'expected_tool': expected,
                'verify_absence': evaluation.get('verify_absence', False),
                'expected_proposal_id': 'quality-fixture-proposal' if expected in {'confirm_booking', 'cancel_arrangement'} and not evaluation.get('verify_absence') else None}
            save()
        state['agents'][aid]['test_ids'] = [v['id'] for v in tests.values()]
        save()
        print(json.dumps({'agent_state': file.name, 'native_tests': len(tests), 'dictionary_provisioned': True}))
