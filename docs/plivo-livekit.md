# Existing Plivo numbers → LiveKit SIP

Decision: retain the user's Plivo numbers for the first route rather than migrate them without evidence. Actual account eligibility, destination geography, caller ID and end-to-end quality are not verified yet.

The user confirmed these are **Indian numbers**. [Plivo's India deployment guide](https://www.plivo.com/docs/voice-agents/sip-trunking/deploy/calling-in-india) requires India-side media termination for traffic involving Indian numbers and an India-region Plivo organisation; it lists LiveKit region pinning as the supported approach. A UK-hosted application does not by itself establish a valid India phone route. Verify the actual LiveKit project pinning, number/KYC status, caller ID and permitted UK destination before a call. The user's India reply does not establish account eligibility or a spending cap. No UK number has been bought and no existing number has been migrated.

For this UK assessment, retain the Plivo account and compare only permitted routes: the existing Indian caller ID with required India routing, versus an authorised UK caller ID if one is available/approved. Measure actual handset latency and quality for the route used. Do not assume either is supported or buy a number before private account/budget verification.

Official references reviewed during implementation:

- [LiveKit: configuring Plivo](https://docs.livekit.io/telephony/start/providers/plivo/)
- [Plivo: voice-agent SIP trunking](https://docs.plivo.com/docs/voice-agents/sip-trunking/overview)
- [Plivo: Zentrunk documentation](https://docs.plivo.com/docs/sip-trunking)

An outbound Plivo trunk does not attach directly to a Plivo number. The existing number supplies an eligible, authorised caller ID; inbound routing is a separate configuration if incoming callbacks are needed. Do not present the assessment's fictional Brightwater number as a real caller ID. Its spoken callback number must also be replaced with an approved reachable destination before any production use.

1. Use the owner's Plivo account to verify the number is voice-capable, the desired caller ID is allowed and UK outbound permissions/trial restrictions permit the consented test destination.
2. Create a Plivo Zentrunk outbound route with the appropriate regional endpoint and authentication. Record its configuration in the account's secret/configuration store.
3. In a separate LiveKit project for the intended environment, configure an outbound SIP trunk using that Plivo endpoint and credentials. Configure the allowed calling number. Keep Plivo trunk credentials in the provider configuration rather than the business application's prompt or database.
4. Put the resulting LiveKit trunk ID in `BW_LIVEKIT_OUTBOUND_TRUNK_ID`. Supply `BW_LIVEKIT_URL`, `BW_LIVEKIT_API_KEY` and `BW_LIVEKIT_API_SECRET` through a private secret manager. Keep keys out of chat, commits, screenshots and logs.
5. Select the exact `BW_VOICE_STT_MODEL`, `BW_VOICE_LLM_MODEL`, `BW_VOICE_TTS_MODEL` and `BW_VOICE_ID` supported by that account. Configure an accurate `BW_RECORDING_NOTICE`, verify recording/media behavior and approve retention/access before collecting personal data.
6. Run the voice profile only after these release prerequisites are addressed. Readiness currently verifies local client construction/worker registration, not an end-to-end vendor inference health probe. That probe and handset qualification of the explicit semantic/adaptive configuration are outstanding.
7. Register only an owned or explicitly consented destination with an operator token and consent reference. Then complete controlled activation work and make the first attended call. All time/preference/suppression checks still apply; no hidden test-clock bypass exists in the phone path.

No account mutation or test call has been performed by this implementation. A spending cap and private account access are still required before paid provisioning or calls. Keep provider console configuration reviewable and record actual account IDs/regions/route versions outside public documentation.

Before production: inbound callback coverage, media export, provider event verification/reconciliation, egress controls, budget alarms and the required six real scenarios must all be implemented and tested. Phone naturalness cannot be determined from catalogue samples or the present code.
