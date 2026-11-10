"""Run bounded native provider regressions; no phone dispatch or CRM write.

Writes the durable invocation intent before POST and never retries an uncertain
submission. Keep the output path private: provider results contain transcripts.
"""
import argparse
import json
import os
import time
from pathlib import Path

import httpx
from brightwater.managed.agent import config

p = argparse.ArgumentParser()
p.add_argument('--agent-state', type=Path, required=True)
p.add_argument('--quality-state', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--select', nargs='*')
p.add_argument('--repeat', type=int, choices=[1, 2, 3], default=1)
p.add_argument('--profile', choices=['live', 'baseline', 'balanced', 'fast'], default='live')
a = p.parse_args()
assert not a.output.exists(), 'Invocation output exists; reconcile it, never resubmit blindly'
owned = json.loads(a.agent_state.read_text())
resources = json.loads(a.quality_state.read_text())
quality = {'dictionary': resources.get('dictionary'), **resources['agents'][owned['agent_id']]}
tests = quality['tests']
keys = a.select or list(tests)
assert 1 <= len(keys) * a.repeat <= 30 and set(keys) <= set(tests)
body = {'name': 'Brightwater / ' + a.profile + ' / ' + a.output.stem,
        'tests': [{'test_id': tests[k]['id']} for k in keys], 'repeat_count': a.repeat}
if a.profile != 'live':
    candidate = config(owned['knowledge_id'], 'https://api.46.101.11.137.sslip.io', owned['provider_secret_id'],
                       phone=owned.get('phone_profile', False), quality=quality, profile=a.profile)
    body['agent_config_override'] = {k: candidate[k] for k in ['conversation_config', 'platform_settings']}
record = {'submission_started_at': time.time(), 'profile': a.profile, 'keys': keys, 'repeat': a.repeat,
          'phone_calls': 0, 'evidence_scope': 'native provider behavior tests, not live business action or handset quality'}


def save():
    temp = a.output.with_name(a.output.name + '.refresh')
    temp.write_text(json.dumps(record, indent=2))
    temp.chmod(0o600)
    os.replace(temp, a.output)


save()
with httpx.Client(base_url='https://api.elevenlabs.io', headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']}, timeout=45) as c:
    live = c.get('/v1/convai/agents/' + owned['agent_id'])
    live.raise_for_status()
    current_ids = set(live.json()['conversation_config']['agent']['prompt']['tool_ids'])
    stale = [key for key in keys if tests[key].get('referenced_tool_id') and tests[key]['referenced_tool_id'] not in current_ids]
    if stale:
        record['preflight_failed'] = {'stale_test_tool_references': stale}
        save()
        raise SystemExit('Refresh native test tool references before running; no invocation submitted')
    r = c.post('/v1/convai/agents/' + owned['agent_id'] + '/run-tests', json=body)
    record['submission_status'] = r.status_code
    if r.status_code != 200:
        record['rejection'] = r.json()
        save()
        raise SystemExit('Native test submission rejected: ' + str(r.status_code))
    v = r.json()
    record['invocation_id'] = v['id']
    record['result'] = v
    save()
    print('Native invocation submitted:', v['id'], flush=True)
    for _ in range(90):
        r = c.get('/v1/convai/test-invocations/' + v['id'])
        r.raise_for_status()
        v = r.json()
        record['result'] = v
        save()
        statuses = [x['status'] for x in v['test_runs']]
        print('Native statuses:', statuses, flush=True)
        if statuses and all(s not in {'pending', 'running', 'queued', 'in_progress'} for s in statuses):
            break
        time.sleep(3)
    else:
        raise SystemExit('Native test polling window ended; retain invocation, do not resubmit')
    strict = []
    by_id = {value['id']: value for value in tests.values()}
    for run in v['test_runs']:
        expected = by_id[run['test_id']]
        calls = [call for response in run.get('agent_responses') or [] for call in response.get('tool_calls', [])]
        matches = [call for call in calls if call.get('tool_name') == expected.get('expected_tool')]
        passed = run['status'] == 'passed'
        if expected.get('expected_tool'):
            if expected.get('verify_absence'):
                passed = passed and not matches
            else:
                passed = passed and len(matches) == 1
                for call in matches:
                    args = json.loads(call['params_as_json'])
                    passed = passed and args.get('arguments', {}).get('proposal_id') == expected['expected_proposal_id']
                if run.get('test_name', '').startswith('Brightwater boundary'):
                    # The guarded finish followed by native end_call is the
                    # intended two-step automation closing, not two writes.
                    passed = passed and calls[0].get('tool_name') == 'finish_conversation'
                    passed = passed and len(calls) <= 2 and all(
                        call.get('tool_name') in {'finish_conversation', 'end_call'} for call in calls)
        elif run.get('test_name', '').endswith('technical_recovery'):
            passed = passed and not any(call.get('tool_name') in {'confirm_booking', 'record_followup'} for call in calls)
        strict.append({'test_id': run['test_id'], 'test_name': run.get('test_name'), 'passed': bool(passed)})
    record['strict_checks'] = strict
    record['all_passed'] = all(item['passed'] for item in strict)
    record['completed_at'] = time.time()
    save()
    print(json.dumps({'statuses': statuses, 'credits_used': sum(x.get('credits_used') or 0 for x in v['test_runs'])}))

if not record['all_passed']:
    raise SystemExit('Native or strict generated-parameter regression failed; inspect retained result')
