"""Speech presentation and the pinned SDK's speculative-tool safety boundary."""
import asyncio
import time
from types import SimpleNamespace

import pytest

from brightwater.plivo_gateway import speech_timing_sample
from brightwater.speech import ENGINEERING_PREFIX, booking_readback
from brightwater.voice_pipeline import DirectVoiceOptions, voice_pipeline_manifest


@pytest.fixture(autouse=True)
def database():
    yield  # These tests have no business/database connection.


def item(**changes):
    return {"address": "18 Albert Road, Southsea, PO4 0JT", "day": "2026-11-16", "period": "MORNING", "service": "service"} | changes


def test_readback_uses_natural_dates_and_actual_service_without_mutating_proposal():
    original = item()
    assert booking_readback([original]) == "That's a boiler service at 18 Albert Road, Southsea, PO4 0JT on Monday 16 November 2026, in the morning. Shall I book that for you?"
    assert original == item()
    assert "gas safety check" in booking_readback([item(service="cp12", period="AFTERNOON")])
    assert "boiler service and gas safety check" in booking_readback([item(service="combined")])


def test_engineering_metadata_is_omitted_only_for_explicit_engineering_context():
    value = item(address=ENGINEERING_PREFIX + "18 Albert Road")
    assert ENGINEERING_PREFIX in booking_readback([value])
    assert ENGINEERING_PREFIX not in booking_readback([value], engineering=True)
    assert value["address"].startswith(ENGINEERING_PREFIX)
    assert booking_readback([item(address="Fictional Road")], engineering=True).startswith("That's a boiler service at Fictional Road")


def test_multi_property_readback_keeps_every_property_and_rejects_bad_data():
    result = booking_readback([item(), item(address="22 Fawcett Road", service="cp12")])
    assert "18 Albert Road" in result and "22 Fawcett Road" in result
    assert result.count("Shall I book") == 1
    with pytest.raises(ValueError):
        booking_readback([])
    with pytest.raises(ValueError):
        booking_readback([item(day="not a date")])
    with pytest.raises(KeyError):
        booking_readback([item(period="unknown")])


def test_speech_timings_allow_numeric_fields_only():
    result = speech_timing_sample(SimpleNamespace(metrics={"e2e_latency":1.2,"llm_node_ttft":.2,"tts_node_ttfb":.1,"text":"private speech","api_key":"private","playback_latency":float('nan'),"transcription_delay":True}))
    assert set(result) == {"metric_type","unit","observed_at","e2e_latency","llm_node_ttft","tts_node_ttfb"}
    assert speech_timing_sample(SimpleNamespace(metrics={"text":"private"})) is None


def test_voice_controls_propagate_into_manifest():
    cfg=SimpleNamespace(openai_api_key="explicit-openai",elevenlabs_api_key="explicit-eleven",voice_stt_model="gpt-4o-mini-transcribe",voice_llm_model="gpt-4.1-mini",voice_tts_model="eleven_v4_turbo",voice_id="licensed-voice",voice_direct_mode="cascaded",voice_speed=1.0,voice_stability=.5,voice_similarity=.75,voice_speaker_boost=False,voice_preemptive_generation=True)
    opts=DirectVoiceOptions.from_settings(cfg)
    assert opts.voice_speed==1.0 and not opts.voice_speaker_boost and opts.preemptive_generation
    manifest=voice_pipeline_manifest(opts)
    assert manifest['preemptive_generation'] and not manifest['preemptive_tts']
    assert manifest['elevenlabs_model']=='eleven_v4_turbo'


@pytest.mark.parametrize("authorise", [False, True])
def test_actual_sdk_drafts_cannot_execute_tools_until_authorised(authorise):
    from livekit.agents import Agent, AgentSession, TurnHandlingOptions, function_tool, llm
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from livekit.agents.utils import http_context
    from livekit.agents.voice.speech_handle import SpeechHandle

    async def check():
        drafted=asyncio.Event()
        executed=asyncio.Event()

        @function_tool
        async def attempted_write():
            """Test-only sentinel, no real business action."""
            executed.set()
            return "done"

        class Draft(llm.LLMStream):
            async def _run(self):
                self._event_ch.send_nowait(llm.ChatChunk(id="speculative-test",delta=llm.ChoiceDelta(role="assistant",tool_calls=[llm.FunctionToolCall(name="attempted_write",arguments="{}",call_id="draft-call")])))
                drafted.set()

        class Model(llm.LLM):
            def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
                return Draft(self,chat_ctx=chat_ctx,tools=tools or [],conn_options=conn_options)

        async with http_context.open():
            session=AgentSession(llm=Model(),turn_handling=TurnHandlingOptions(turn_detection="manual",preemptive_generation={"enabled":True,"preemptive_tts":False,"max_retries":1,"max_speech_duration":6.0}))
            try:
                await session.start(Agent(instructions="Test tool scheduling",tools=[attempted_write]))
                activity=session._activity
                activity.on_preemptive_generation(SimpleNamespace(new_transcript="yes",started_speaking_at=time.time(),transcript_confidence=1.0))
                await asyncio.wait_for(drafted.wait(),2)
                await asyncio.sleep(.05)
                assert not executed.is_set(), "A speculative draft executed a tool before final turn authorisation"
                if authorise:
                    handle=activity._preemptive_generation.speech_handle
                    activity._preemptive_generation=None
                    activity._schedule_speech(handle,priority=SpeechHandle.SPEECH_PRIORITY_NORMAL)
                    await asyncio.wait_for(executed.wait(),2)
                else:
                    activity._cancel_preemptive_generation()
                    await asyncio.sleep(.05)
                    assert not executed.is_set(), "Cancelled speculative draft executed a tool"
            finally:
                await session.aclose()
    asyncio.run(check())


def test_verification_phase_and_speaker_change_switch_prompt_and_tool_access():
    from livekit.agents.llm.tool_context import get_function_info

    from brightwater.voice_agent import BrightwaterAgent

    async def check():
        agent=BrightwaterAgent(None,"synthetic","token",None,cfg=SimpleNamespace())
        await agent.configure_identity("Helen",purpose="engineering")
        def names():
            return {get_function_info(tool).name for tool in agent.tools}
        assert "confirm_customer" in names() and "emergency" in names()
        assert "check_availability" not in names() and "commit_booking" not in names()
        assert "OUTBOUND renewal call" not in agent.instructions
        async def final(**kwargs):
            return SimpleNamespace(event_id="fresh-user")
        async def event(*args,**kwargs):
            return "event"
        async def request(method,path,payload=None):
            assert path=="/runtime/account"
            return {"properties":[]}
        agent.turns.final,agent.event,agent.request=final,event,request
        result=await agent.confirm_customer()
        assert result['identity_confirmed'] and agent.identity_verified
        assert "check_availability" in names() and "commit_booking" in names()
        assert "OUTBOUND renewal call" in agent.instructions
        await agent.reset_identity()
        assert not agent.identity_verified and "check_availability" not in names()
        assert agent.call_purpose=="engineering"
    asyncio.run(check())


@pytest.mark.parametrize('interrupted',[True,False])
def test_opening_yields_to_interruptions_and_does_not_ask_an_extra_permission_question(interrupted):
    from brightwater.voice_agent import BrightwaterAgent

    async def check():
        spoken=[]
        asked=[]
        class Speech:
            async def wait_for_playout(self):
                pass
        speech=Speech()
        speech.interrupted=interrupted
        agent=BrightwaterAgent(None,"synthetic","token",None,cfg=SimpleNamespace(recording_notice="This test is recorded."))
        class Session:
            def say(self,text,**kwargs):
                spoken.append(text)
                return speech
        async def identity():
            asked.append(True)
        # Session is exposed by AgentActivity; replace only the test property.
        from unittest.mock import PropertyMock, patch
        agent.ask_customer_identity=identity
        with patch.object(BrightwaterAgent,'session',new_callable=PropertyMock,return_value=Session()):
            await agent.deliver_opening()
        assert "This test is recorded." in spoken[0]
        assert "AI assistant" in spoken[0]
        assert "moment" not in spoken[0] and "good time" not in spoken[0]
        assert bool(asked) is (not interrupted)
        assert agent.notice_delivered is (not interrupted)
    asyncio.run(check())


def test_interrupted_identity_question_does_not_consume_complete_clarification_budget():
    from unittest.mock import PropertyMock, patch

    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        agent=BrightwaterAgent(None,'synthetic','token',None,cfg=SimpleNamespace())
        await agent.configure_identity('Samudra')
        spoken=[]
        results=iter([True,False,False])
        class Session:
            def say(self,text,**kwargs):
                spoken.append(text)
                class Speech:
                    interrupted=next(results)
                    async def wait_for_playout(self):
                        pass
                return Speech()
        async def event(*args,**kwargs):
            return 'event'
        agent.event=event
        with patch.object(BrightwaterAgent,'session',new_callable=PropertyMock,return_value=Session()):
            await agent.ask_customer_identity()
            assert agent.identity_completed_questions==0
            agent.turns.begin()
            agent.turns.end()
            await agent.ask_customer_identity()
            assert agent.identity_completed_questions==1
            agent.identity_failures=1
            agent.turns.begin()
            agent.turns.end()
            await agent.ask_customer_identity()
            assert spoken[-1]=='Could you tell me your name, please?'
            assert agent.identity_completed_questions==2 and agent.identity_questions==3
            agent.turns.begin()
            agent.turns.end()
            result=await agent.ask_customer_identity()
            assert result['status']=='needs_office_help' and len(spoken)==3
    asyncio.run(run())


@pytest.mark.parametrize('text,allowed',[("I'm Samudra",True),("I'm Samudra's daughter",False),("Yes, he was.",False)])
def test_volunteered_named_identity_can_recover_after_budget_without_accepting_proxy(text,allowed):
    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        agent=BrightwaterAgent(None,'synthetic','token',None,cfg=SimpleNamespace())
        await agent.configure_identity('Samudra')
        agent.identity_failures=2
        calls=[]
        async def final(**kwargs):
            return SimpleNamespace(event_id='fresh',text=text)
        async def event(*args,**kwargs):
            calls.append('assertion')
            return 'event'
        async def request(*args,**kwargs):
            calls.append('account')
            return {'properties':[]}
        agent.turns.final,agent.event,agent.request=final,event,request
        result=await agent.confirm_customer()
        assert result['identity_confirmed'] is allowed
        assert bool(calls) is allowed
    asyncio.run(run())


def test_callback_refusal_is_preserved_until_new_explicit_request():
    from brightwater.voice_agent import BrightwaterAgent

    async def run():
        events=[]
        async def event(kind,*args,**kwargs):
            events.append(kind)
            return 'event-'+str(len(events))
        agent=BrightwaterAgent(None,'synthetic','token',None,cfg=SimpleNamespace())
        await agent.configure_identity('Samudra')
        agent.event=event
        agent.turns.writer=event
        def reply(key,text):
            return SimpleNamespace(id=key,text_content=text,metrics={})
        await agent.capture_caller(reply('refusal',"I don't want a callback, I want the service to be booked."))
        assert agent.callback_declined and 'callback declined' in agent.instructions
        result=await agent.escalate('callback','Test request')
        assert result['status']=='callback_declined' and result['write_attempted'] is False
        assert 'callback' not in events
        await agent.capture_caller(reply('request','Please call me back.'))
        assert not agent.callback_declined
        result=await agent.escalate('callback','Caller explicitly requested it')
        assert result['recorded'] is True and events.count('callback')==1
        replay=await agent.escalate('callback','Repeated model tool call for same reply')
        assert replay==result and events.count('callback')==1
    asyncio.run(run())
