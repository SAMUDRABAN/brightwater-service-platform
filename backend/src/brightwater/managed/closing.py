"""Bounded ElevenLabs farewell for server-enforced purpose endings only."""
import re

from livekit import rtc

from brightwater.managed.boundaries import CLOSING


async def farewell(http, key, agent_id, output):
    # Resolve the actual owned phone profile, never a stale legacy voice default
    # or a caller/model-supplied voice. Normal conversations never call this path.
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', agent_id):
        raise ValueError('Invalid owned agent')
    headers = {'xi-api-key': key}
    result = await http.get('https://api.elevenlabs.io/v1/convai/agents/' + agent_id,
                            headers=headers, timeout=3)
    result.raise_for_status()
    tts = result.json()['conversation_config']['tts']
    voice = tts['voice_id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', voice):
        raise ValueError('Invalid configured voice')
    # Use the owned profile's current voice/model. This single neutral goodbye
    # is operational audio, never business readback or customer-consent evidence.
    async with http.stream('POST', 'https://api.elevenlabs.io/v1/text-to-speech/' + voice + '/stream',
        headers=headers, params={'output_format': 'pcm_16000'}, timeout=5,
        json={'text': CLOSING, 'model_id': tts['model_id'],
              'voice_settings': {k: tts[k] for k in ('stability', 'similarity_boost', 'speed') if k in tts}}) as response:
        response.raise_for_status()
        pcm = bytearray()
        async for chunk in response.aiter_bytes():
            pcm.extend(chunk)
            if len(pcm) > 32000 * 8:
                raise ValueError('Farewell exceeded audio bound')
    if not pcm or len(pcm) % 2:
        raise ValueError('Invalid farewell PCM')
    resampler = rtc.AudioResampler(16000, 8000, quality=rtc.AudioResamplerQuality.HIGH)
    for offset in range(0, len(pcm), 640):
        part = bytes(pcm[offset:offset + 640])
        for frame in resampler.push(rtc.AudioFrame(part, 16000, 1, len(part) // 2)):
            await output.capture_frame(frame)
    for frame in resampler.flush():
        await output.capture_frame(frame)
    output.flush()
    result = await output.wait_for_playout()
    return not result.interrupted
