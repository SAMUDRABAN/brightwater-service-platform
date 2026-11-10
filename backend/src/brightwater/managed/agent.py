"""Versioned ElevenLabs configuration. No customer records or credentials embedded."""
from pathlib import Path

from brightwater.call_limits import ATTENDED_CALL_MAX_SECONDS
from brightwater.managed.quality import ASR_KEYTERMS, BACKCHANNELS, evaluation_criteria

TOOL_DEFINITIONS = {
    "confirm_identity": ("Confirm the named caller from each fresh identity reply, including a volunteered name or an answer interrupting recovery speech. The backend checks disclosure completion; follow its current result instead of repeating the opening/name question. Returns account only on success. Never pass a name or invented confirmation.", {}),
    "check_availability": ("Check real diary space for selected services at this caller's properties. Offer at most two options.", {"items": {"type": "array", "description": "Selected properties and services", "items": {"type": "object", "properties": {"property_id": {"type": "string"}, "service": {"type": "string", "enum": ["service", "cp12", "combined"]}}, "required": ["property_id", "service"]}}}),
    "review_arrangement": ("Read the current call's selected proposal or saved booking from the database, including dates, price and engineer. This is read-only and never creates a reservation. Use it to answer follow-up questions or recover uncertain status; do not restart the date search unless the caller changes their choice or the selection is expired/unavailable.", {}),
    "prepare_booking": ("Prepare the actual selected offer. Read account.kind: homeowners use tenants=[] and need no tenant names or phone numbers, even with multiple properties. Only landlords require contacts for every property. This is NOT a booking. Explain all returned booking facts in natural language, ask to save the arrangement and wait for the reply. Consent is interpreted in context; no special words are required.", {"offer_id": {"type": "string", "description": "ID returned by check_availability"}, "tenants": {"type": "array", "description": "Use [] for homeowners. Only landlords need one tenant contact per property", "items": {"type": "object", "properties": {"property_id": {"type": "string"}, "name": {"type": "string"}, "phone": {"type": "string", "description": "Landlord tenant contact in international format including country code, e.g. +44; never guess the country code"}}, "required": ["property_id", "name", "phone"]}}}),
    "confirm_booking": ("Reserve the prepared booking only AFTER speaking every prepared fact and receiving present authorisation for that arrangement, expressed in the caller's own words. A reply containing any unresolved question, including who the engineer will be, does not authorise this tool. Answer from returned facts or use review_arrangement first. Backend checks the conversation. Report success only if confirmed=true. Never retry this write after an authentication/authorization error (401/403) or a non-retryable failure; that is not a request for another customer yes. An evidence_pending result permits one retry only.", {"proposal_id": {"type": "string", "description": "ID from prepare_booking"}}),
    "cancel_arrangement": ("Cancel the current prepared or saved arrangement when the caller asks. Use the proposal ID from this conversation; never guess a historical appointment. Backend independently interprets the latest request.", {"proposal_id": {"type": "string", "description": "Current proposal ID from prepare_booking"}}),
    "record_followup": ("Record callbacks or quote interest when requested. An actual urgent problem, emergency or complaint requires this tool without asking permission. Give full safety advice before any emergency tool, then use native end_call even on tool failure. Say a handover was recorded only on saved=true. A refusal of an optional callback is not a request. Do not claim a live transfer or promise when someone will call.", {"kind": {"type": "string", "enum": ["callback", "complaint", "urgent", "gas_emergency", "co_alarm", "lead"]}}),
    "finish_conversation": ("Use this FIRST when a mailbox asks you to leave a message after the tone. The result gives the only approved message and tells you when to end. For a proxy saying the named person is unavailable, use this to record the outcome before saying goodbye. For other calls, finish after a brief truthful closing. Backend facts determine the outcome.", {}),
}


OPTIONAL_ARGUMENTS = {"check_availability": {"preferred_day", "preferred_period", "engineer_id", "after_day", "same_day"}}
TOOL_DEFINITIONS["check_availability"][1].update({
    "same_day": {"type": "boolean", "description": "Defaults true. Set false only after the landlord agrees to visits on separate days; all properties remain in one priced proposal."},
    "preferred_day": {"type": "string", "description": "Optional requested UK calendar date, YYYY-MM-DD, interpreted from the conversation using reference_uk_date. Omit if no date preference."},
    "preferred_period": {"type": "string", "enum": ["MORNING", "AFTERNOON"], "description": "Optional requested arrival window. Omit when either window is acceptable."},
    "engineer_id": {"type": "string", "description": "Optional requested engineer ID from the verified account's actual engineers list. Never invent an ID or silently substitute a different engineer."},
    "after_day": {"type": "string", "description": "Optional exclusive YYYY-MM-DD lower bound when the customer wants later/different dates than the previously offered ones. Omit for the initial search."},
})


def tools(base_url=None, secret_id=None, *, profile="balanced"):
    def describe(value):
        if isinstance(value, dict):
            if "type" in value:
                value.setdefault("description", "Value supplied from the current conversation")
            for child in value.values():
                describe(child)
        elif isinstance(value, list):
            for child in value:
                describe(child)
    for _, parameters in TOOL_DEFINITIONS.values():
        describe(parameters)
    result = []
    for name, (description, parameters) in TOOL_DEFINITIONS.items():
        arguments = {"type": "object", "description": "Business operation arguments", "properties": parameters, "required": [p for p in parameters if p not in OPTIONAL_ARGUMENTS.get(name, set())]}
        if base_url and secret_id:
            result.append({"type": "webhook", "name": name, "description": description,
                "response_timeout_secs": 10, "pre_tool_speech": "force" if name == "record_followup" or (profile != "baseline" and name == "check_availability") else "off", "interruption_mode": "allow",
                "api_schema": {"url": base_url + "/v1/managed/tools/" + name, "method": "POST",
                    "request_headers": {"X-Brightwater-Provider": {"secret_id": secret_id},
                        "X-Brightwater-Session": {"variable_name": "secret__session_token"},
                        "X-Brightwater-Conversation": {"variable_name": "system__conversation_id"}},
                    "request_body_schema": {"type": "object", "properties": {
                        "history": {"type": "string", "dynamic_variable": "system__conversation_history"},
                        "text_only": {"type": "boolean", "dynamic_variable": "system__is_text_only"},
                        "arguments": arguments}, "required": ["history", "text_only", "arguments"]}}})
        else:
            result.append({"type": "client", "name": name, "description": description,
                "expects_response": True, "response_timeout_secs": 10, "pre_tool_speech": "off",
                "parameters": arguments})
    return result


def config(knowledge_id=None, base_url=None, secret_id=None, *, phone=False, quality=None, profile="balanced", campaign=False):
    if profile not in {"baseline", "balanced", "fast"}:
        raise ValueError("Unknown voice quality profile")
    quality = quality or {}
    prompt = Path(__file__).with_name("prompt.txt").read_text()
    if phone:
        start = prompt.index("When you hear a real voicemail")
        stop = prompt.index(" For a current keypad menu", start)
        prompt = prompt[:start] + (
            "When you hear a voicemail greeting, call finish_conversation immediately and wait silently. "
            "The phone gateway plays any approved message and hangs up. Never say goodbye, play a message "
            "yourself or invoke end_call for voicemail. When someone asks never to be called again, "
            "wait silently for the gateway to acknowledge suppression and hang up. "
            "If they refuse recording, stop immediately."
        ) + prompt[stop:]
        start = prompt.index(" For an approved voicemail message")
        stop = prompt.index(" No menu navigation", start)
        prompt = prompt[:start] + " For an automated menu or screening bot, wait for finish_conversation before ending." + prompt[stop:]
    if campaign:
        if not phone:
            raise ValueError("A customer campaign requires the telephone profile")
        prompt = prompt.replace("using fictional engineering accounts and a real isolated booking database", "using verified live account and diary tools")
        prompt = prompt.replace("The opening gives AI/recording/test disclosure.", "The opening gives automated-assistant and recording disclosure; do not describe a customer call as a fictional test.")
    return {
        "name": "Brightwater Managed Candidate — UK customer reminders" if campaign else "Brightwater Managed Candidate — Plivo phone" if phone else "Brightwater Managed Candidate — private engineering",
        "conversation_config": {
            "agent": {"language": "en", "first_message": ("Hi, I’m Alex, an automated assistant calling on behalf of Brightwater Plumbing and Heating. This call is recorded. Am I speaking with {{customer_name}}?" if campaign else "Hi, I'm Alex, Brightwater's AI assistant. This recorded engineering test uses fictional details. Am I speaking with {{customer_name}}?"),
                      "disable_first_message_interruptions": False,
                      "dynamic_variables": {"dynamic_variable_placeholders": {"customer_name": "Helen Price"}},
                      "prompt": {"prompt": prompt, "llm": "gpt-4.1", "temperature": 0.4, "max_tokens": 300,
                                 "ignore_default_personality": True, "enable_parallel_tool_calls": False, "tools": [*tools(base_url, secret_id, profile=profile),
                                     {"type": "system", "name": "end_call",
                                      "description": "End after the brief truthful closing for a completed task, caller goodbye, annual-service refusal or work serviced elsewhere. For an explicit refusal/serviced-elsewhere closing, a failed finish_conversation must not cause another offer or repeated write. Voicemail or automated greetings are never a caller goodbye. Call finish_conversation first and require stopped=true or finished=true. Speak any approved_message before end_call. Never end a proxy call before recording unavailability with finish_conversation. For misuse, first use finish_conversation and require stopped=true or finished=true. Never end for a complaint, service frustration, isolated swearing, assistive speech or uncertainty; finished=false means continue. Give one polite generic goodbye, with no account disclosure or invented callback." + (" Never invoke this tool for voicemail or an opt-out. The phone gateway owns those closings." if phone else ""),
                                      "params": {"system_tool_type": "end_call"}}],
                                 "timezone": "Europe/London",
                                 "knowledge_base": [{"type": "text", "id": knowledge_id, "name": "Brightwater approved business facts", "usage_mode": "prompt"}] if knowledge_id else []}},
            "tts": {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "model_id": "eleven_v4_turbo", "speed": 1.0,
                    "expressive_mode": False, "stability": 0.45, "similarity_boost": 0.8, "agent_output_audio_format": "pcm_16000",
                    "pronunciation_dictionary_locators": [quality["dictionary"]] if quality.get("dictionary") and profile != "baseline" else []},
            "asr": {"provider": "scribe_realtime", "quality": "high", "user_input_audio_format": "pcm_16000", "keywords": ASR_KEYTERMS if profile != "baseline" else []},
            "turn": {"turn_timeout": 7, "silence_end_call_timeout": 20, "turn_eagerness": "eager" if profile == "fast" else "normal",
                     "spelling_patience": "auto", "speculative_turn": profile == "fast",
                     "interruption_ignore_terms": BACKCHANNELS if profile != "baseline" and not phone else [], "merge_with_default_ignore_terms": False},
            "conversation": {"max_duration_seconds": 900 if campaign else ATTENDED_CALL_MAX_SECONDS if phone else 180, "client_events": ["audio", "interruption", "user_transcript", "agent_response", "agent_response_correction", "agent_tool_response", "agent_response_metadata", "agent_response_complete"]}},
        "platform_settings": {
            "auth": {"enable_auth": True},
            "evaluation": {"criteria": evaluation_criteria()},
            "testing": {"attached_tests": [{"test_id": i} for i in quality.get("test_ids", [])]},
            "overrides": {"conversation_config_override": {"conversation": {"text_only": True}}},
            "privacy": {"record_voice": True, "retention_days": 7},
            "call_limits": {"agent_concurrency_limit": 1, "daily_limit": 20 if campaign else 10, "bursting_enabled": False}},
    }
