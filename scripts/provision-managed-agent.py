"""Create/update only the private Brightwater candidate, never phone resources.

ELEVENLABS_API_KEY must be supplied privately. State is a private path outside
this source package. Run from the repository root with PYTHONPATH=backend/src.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx
from brightwater.managed.agent import config
from brightwater.managed.provision import retain_tools

parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, required=True)
parser.add_argument("--api-url", required=True)
parser.add_argument("--phone", action="store_true", help="Create the separate Plivo phone profile; does not dial or import a number")
parser.add_argument("--quality-state", type=Path, help="Private native-test and pronunciation resource state")
parser.add_argument("--profile", choices=["baseline", "balanced", "fast"], default="balanced")
parser.add_argument("--campaign", action="store_true", help="Separate UK customer profile; does not enable dialing")
args = parser.parse_args()
quality = json.loads(args.quality_state.read_text()) if args.quality_state and args.quality_state.exists() else {}
state = json.loads(args.state.read_text()) if args.state.exists() else {}
key = os.environ["ELEVENLABS_API_KEY"]
text = Path("backend/src/brightwater/managed/business-facts.txt").read_text()
digest = hashlib.sha256(text.encode()).hexdigest()
with httpx.Client(base_url="https://api.elevenlabs.io", headers={"xi-api-key": key}, timeout=45) as client:
    actual_before = {}
    if state.get("agent_id"):
        existing = client.get("/v1/convai/agents/" + state["agent_id"])
        existing.raise_for_status()
        assert existing.json()["name"].startswith("Brightwater Managed Candidate"), "Refusing to change another agent"
        actual_before = existing.json()
    if state.get("knowledge_sha256") != digest:
        response = client.post("/v1/convai/knowledge-base/text", json={"name": "Brightwater approved business facts", "text": text})
        response.raise_for_status()
        state.update(knowledge_id=response.json()["id"], knowledge_sha256=digest)
        args.state.write_text(json.dumps(state, indent=2))
        os.chmod(args.state, 0o600)
    if not state.get("provider_secret_id"):
        response = client.post("/v1/convai/secrets", json={"type": "new", "name": "Brightwater candidate tool authentication", "value": os.environ["BRIGHTWATER_MANAGED_WEBHOOK_SECRET"]})
        response.raise_for_status()
        state["provider_secret_id"] = response.json()["secret_id"]
        args.state.write_text(json.dumps(state, indent=2))
        os.chmod(args.state, 0o600)
    resources = {"dictionary": quality.get("dictionary"), **quality.get("agents", {}).get(state.get("agent_id"), {})}
    body = config(state["knowledge_id"], args.api_url.rstrip("/"), state["provider_secret_id"], phone=args.phone, quality=resources, profile=args.profile, campaign=args.campaign)
    prompt = body["conversation_config"]["agent"]["prompt"]
    if actual_before:
        prompt["tool_ids"] = retain_tools(client, actual_before, [t for t in prompt["tools"] if t["type"] == "webhook"])
        prompt["built_in_tools"] = dict(actual_before["conversation_config"]["agent"]["prompt"].get("built_in_tools") or {})
        prompt["built_in_tools"]["end_call"] = next(t for t in prompt["tools"] if t["type"] == "system")
        del prompt["tools"]  # The API forbids tools and tool_ids in one request.

    if state.get("selected_voice_id"):
        body["conversation_config"]["tts"]["voice_id"] = state["selected_voice_id"]
    if state.get("agent_id"):
        response = client.patch("/v1/convai/agents/" + state["agent_id"], json=body)
    else:
        response = client.post("/v1/convai/agents/create", json=body)
    if response.status_code != 200:
        # Config contains only public facts; validation response may be inspected.
        print("Provider configuration rejected", response.status_code, response.text[:3000])
        raise SystemExit(1)
    state.update(agent_id=state.get("agent_id") or response.json()["agent_id"], stage="connected_candidate", phone_attached=False, phone_profile=args.phone, campaign_profile=args.campaign, quality_profile=args.profile,
                 config_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest())
    args.state.write_text(json.dumps(state, indent=2))
    os.chmod(args.state, 0o600)
    check = client.get("/v1/convai/agents/" + state["agent_id"])
    check.raise_for_status()
    actual = check.json()
    assert actual["platform_settings"]["auth"]["enable_auth"] is True
    assert actual["conversation_config"]["tts"]["voice_id"] == body["conversation_config"]["tts"]["voice_id"]
    assert any(t.get("params", {}).get("system_tool_type") == "end_call" for t in actual["conversation_config"]["agent"]["prompt"]["tools"]), "Provider did not retain native ending tool"
    if resources.get("test_ids"):
        attached = {item["test_id"] for item in actual["platform_settings"]["testing"]["attached_tests"]}
        assert set(resources["test_ids"]) <= attached, "Native tests were not retained"
    assert len(actual["platform_settings"]["evaluation"]["criteria"]) == 6, "Evaluation criteria were not retained"
    if args.profile != "baseline":
        assert actual["conversation_config"]["asr"]["keywords"], "Domain keyterms were not retained"
        assert actual["conversation_config"]["turn"]["interruption_ignore_terms"] == ([] if args.phone else ["mm-hmm", "mhm", "uh-huh"])
        if resources.get("dictionary"):
            assert actual["conversation_config"]["tts"]["pronunciation_dictionary_locators"], "Dictionary missing"
    print(json.dumps({"agent_id": state["agent_id"], "signed_access": True, "phone_attached": False,
                      "tool_count": len(actual["conversation_config"]["agent"]["prompt"]["tools"]),
                      "tts_model": actual["conversation_config"]["tts"]["model_id"]}))
