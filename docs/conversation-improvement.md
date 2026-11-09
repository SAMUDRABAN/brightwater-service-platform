# Brightwater voice and conversation improvement — 7 November 2026

The selected voice is **Lily with ElevenLabs v4 Turbo**, chosen by the owner after listening to real provider auditions. The current engineering route remains Plivo India, with GPT-4.1 mini, timestamp-bearing OpenAI transcription, the existing business API and the independent identity/booking gates. UK customer calling stays disabled. No additional phone call is authorised by this work.

## Why it sounded artificial

The last carrier recording and transcript exposed formal, long responses, repeated identity/confirmation language and technical booking speech. The readback spoke an ISO date and an internal fictional-property label. One failure response used 41 words and volunteered office hours. A clear voice alone could not compensate for that interaction.

The transport also failed to emit LiveKit's `playback_started` event. Its logs therefore showed the agent thinking while audible speech was being delivered. The pinned SDK uses that event to enter its speaking state and start playback/response timing. This is a concrete integration defect, not a missing GPT-token allowance. The correction emits speech start only after the first sent-audio carrier checkpoint is acknowledged, once per segment. Queueing audio does not claim playback. That observation remains a conservative carrier signal, not proof of handset audibility or comprehension.

The real-provider replay also exposed a short answer reaching the existing three-second semantic endpointing limit. On one replay through the real mu-law bridge with simulated carrier acknowledgements, SDK end-to-end response time was 4.412 seconds: end-of-utterance delay 3.000 seconds, post-tool model first token 1.016 seconds and TTS first audio 0.167 seconds. These overlap and do not form an additive accounting model. This is one offline replay, not a telephone latency distribution. It identifies remaining endpoint/roundtrip work and does not support a claim that every pause is fixed.

## Changes implemented

- Lily/v4 Turbo replaces the old Alice/Flash v2.5 profile for the attended engineering service. Normal speed is 1.0, stability 0.5 and similarity 0.75. Voice controls are explicit configuration rather than hidden factory constants.
- A 320-word identity-stage prompt and nine appropriate tools replace the previous 755-word all-purpose starting prompt with fourteen tools. The verified service/booking stage becomes available only after successful backend identity assertion and account retrieval. A speaker change restores the restricted stage. Emergency, opt-out and callback routes remain available before identity.
- The opening gives the AI identity and recording notice, then goes directly to the guarded named-person question. It no longer inserts an extra permission question before asking identity. An interruption yields to the caller.
- Ordinary replies use everyday language, concise acknowledgements and short next steps. Callback acknowledgements avoid office-hours speeches, live-transfer offers and response-time promises. The staff summary is not spoken aloud.
- Booking readbacks use service names and natural calendar dates rather than ISO strings. Internal fixture prefixes are omitted from speech only for explicit engineering context; the stored property and proposal fingerprint are unchanged. The recorded test notice still identifies fictional details.
- Bounded early LLM generation is enabled for the cascaded gateway: one attempt, short turns only, no speculative TTS. Actual pinned-SDK tests prove that a draft cannot execute a tool before final turn authorisation, and a cancelled draft executes none.
- Numeric-only speech-stage timing now includes SDK speech/playback fields. Existing bounded Redis retention remains. No transcript, account fact or token enters that metric channel.
- A same-timestamp stale-turn boundary is rejected conservatively; its regression test uses explicit speech times rather than racing wall-clock calls.
- The Quality page contains the selected Lily audition and matching comparisons. Independent scores remain NOT EVALUATED.

## What the provider checks show

Four real ElevenLabs WebSocket candidates succeeded, including the account's newer conversational models. The owner selected Lily/v4 Turbo by listening. That preference is useful evidence, not an independent MOS score.

A counterbalanced six-request component pilot retained all results: old Alice/Flash first-audio median 0.336 seconds (n=3, range 0.288–0.568); selected Lily/v4 Turbo median 0.354 seconds (n=3, range 0.214–0.354). Different voices/settings and small samples prevent a model-speed conclusion. In particular, this pilot does **not** show that buying a newer TTS model fixes the long pauses. Lily's selection is about the owner's preferred delivery.

Six final synthetic dialogue cases passed with the staged GPT-4.1 mini prompt: verified outbound purpose, callback acknowledgement, busy caller, no live transfer, proxy privacy and returned availability. Earlier failed prompt revisions were preserved. A larger GPT-4.1 comparator was also tried; in one final callback case it called finish without a spoken acknowledgement. These narrow samples do not establish a general model ranking, and the larger model was not promoted merely because it was larger.

Three short fragments of the already-consented owner recording were compared using mini and full transcription. Both recognised the two clear replies; neither established a reliable rendering of the unclear fragment. These were batch requests, not a streaming latency comparison. The deployed transcription model was therefore retained rather than changed on weak evidence. The owner recording and its fragments remain private and are excluded from this report and source ZIP.

The full replay used real OpenAI STT, GPT and ElevenLabs TTS, the actual LiveKit SDK, the real isolated business API and the Plivo mu-law output bridge. Identity was verified by the test API with original caller timing, and the agent transitioned into the booking-capable phase and explained the outbound service reason. Acknowledgements were simulated; no carrier call or production business write occurred.

## What the other platforms actually document

[Awaz's voice-setting guide](https://help.awaz.ai/en/articles/10758692-configuring-ai-voice-settings-in-awaz-ai) exposes tone, pace, volume, responsiveness, interruption sensitivity and backchannels. These are useful controls to compare. Its public human-likeness claims are vendor marketing, not a benchmark against this application. No Awaz account, campaign, subscription or number was created.

[LiveKit's turn-taking guide](https://docs.livekit.io/agents/logic/turns/tuning/) describes semantic endpointing, early LLM generation, optional early TTS, interruption classification and false-interruption recovery. The shipped change uses bounded early LLM generation while preserving caller completion and tool authorisation. Hosted adaptive interruption handling has a separate account/usage boundary; it was not silently enabled.

[Retell's prompting guidance](https://docs.retellai.com/build/prompt-engineering-guide) recommends concise task instructions, removing repetition and avoiding endless patches to individual utterances. That informed the staged prompt and tool exposure, instead of adding a larger single script.

The pinned ElevenLabs plugin and actual account model inventory were inspected directly. Its v4 path uses the text-to-dialogue streaming interface, and the selected voice/model actually emitted aligned audio in the component and full-pipeline checks. A more capable provider model is useful only when the surrounding turn-taking, timing, tools and actual conversation work together.

## Ranking the next steps against the owner's priorities

| Rank | Approach | Evidence and decision |
|---|---|---|
| 1 | Improve the owned stack and selected Lily delivery | Implemented. Preserves the existing action gates, staff access and carrier route. Best immediate control of voice/conversation behaviour without introducing a new vendor deployment. Handset recheck still required. |
| 2 | Compare realtime semantic audio input with the same Lily output | Lab candidate for reducing the measured endpoint/roundtrip delay. Promotion requires original caller-timing proof, interrupted/corrected booking tests, deterministic scripts and held-out cases; fluency alone is insufficient. |
| 3 | Benchmark managed Awaz/ElevenLabs Agents | Relevant comparator, not an automatic migration. Needs a controlled identical-script, identical-route and task-correctness comparison, with consent, account access and budget checked before any paid campaign. |

No invented numerical scores are assigned. Voice 35% and conversation 35% remain the leading weighted criteria, after safety/privacy/action gates; correctness is 15%, operations 10%, cost 5%.

## Validation and limits

The final code passed **229 native PostgreSQL integration/unit tests in 38.91 seconds** and **229 isolated Linux/PostgreSQL 17 tests in 114.14 seconds**, including actual SDK speech-start, interrupt/clear and speculative-tool authorisation checks. Ruff passed. The office's four auth tests and production frontend build passed. Caller recordings, provider credentials and staff passwords are not deliverables.

This is an implemented voice/conversation improvement, not proof of human equivalence or customer-production readiness. A fresh attended call must verify Lily on the actual handset, the new speaking/interrupt states, natural booking completion and measured pauses. The ordinary three-second semantic maximum is retained because lowering it globally can cut off slower or unfinished callers. Ten authorised attempts remain used out of ten; no eleventh call was placed. No new host or subscription was created.

## Deployed component verification

India voice release `0325039d76cacdb82ac514c3cfe4eada62cc0706` is healthy. A check inside the actual deployed container verified Lily/v4 Turbo, bounded early generation, 300 startup input packets, 35,200 actual mu-law output bytes and the SDK speaking state using simulated carrier acknowledgements. The comparison media on the office host match the reviewed source hashes. Office release is `38ced1e7ce221675a0423674b165bb27976bb4ec`; API remains `9c3bc10239f23e2e80d57ca55bb82d147cd40ee4`. Staff sessions and business records were not reset.

The additional realtime semantic-input lab replay also passed the isolated API identity check with original caller timing and Lily mu-law output. It has no handset qualification, interrupted-booking matrix or comparable end-to-end timing distribution yet, and remains a lab candidate rather than the active gateway mode.

Status: **DONE_WITH_CONCERNS**. The implemented release is deployed and checked; another attended handset call is still required, and all existing quality/UK-production gates remain. The owner has been asked for one new bounded call allowance; no call is placed without that readiness reply.
