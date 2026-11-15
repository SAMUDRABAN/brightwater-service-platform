# Attended call evidence

The office holds the original transcripts, recordings and saved CRM outcomes for these six roleplays. Open **Call history** with a staff account. The recordings and full transcripts are shared through protected access. The source repository holds the evidence index.

| Required scenario | Protected record | Verified result |
| --- | --- | --- |
| Straightforward booking | [UK test, 11 November 2026 at 20:19 UK](https://office.46.101.11.137.sslip.io/calls/328e8299-01ca-41aa-b301-483d392583b7) | **Booked.** Alex verified Peter Lund, offered two options, read back the visit and price, saved the confirmed £95 visit and delivered the spoken booking confirmation. |
| Multi-property landlord | India attended attempt 26 | **Booked.** Three CP12 visits at £60 each were saved in one arrangement after corrected tenant contact details. |
| Callback | India attended attempt 23 | **Callback requested.** The caller accepted office help after booking preparation failed. This is callback evidence from booking recovery. |
| Do not call | India attended attempt 34 | **Do not call.** The CRM saved permanent suppression. The audio connection ended before the spoken acknowledgement finished. |
| Someone else answers | India attended attempt 30 | **Not available.** In the corrected retest, Alex withheld the reason for calling and recorded that the named customer was unavailable. |
| Gas smell | India attended attempt 28 | **Gas emergency advice.** The transcript includes the emergency service number and ventilation guidance. The CRM saved the emergency outcome. |

## UK booking verification

The 20:19 UK call used the CRM's attended UK test form and the Twilio UK route to an agreed handset. The CRM recorded 89 connected seconds and ten transcript entries. The protected stereo recording decoded successfully to 87.5 seconds. The diary shows a confirmed fictional boiler service with Priya Shah for Wednesday 18 November 2026, 08:00–12:00, at £95 including VAT. Carrier status recorded a completed call and playback evidence covers the spoken booking confirmation.

The transcript repeats “Let me check the diary” in adjacent entries. The handset test established booking completion. The evening-before text was described during the call. SMS delivery was outside this check.

## 15 November voice follow-up

The 11 November UK conversation log records the diary acknowledgement twice, once as forced pre-tool speech and once in the spoken result. The UK and India ElevenLabs profiles now start the availability lookup directly and speak the actual result. The first verified service offer is shorter. The full address, postcode, window, price and payment remain in the final booking readback.

On the successful UK call, provider TTS started in 69–93 ms. Four business webhooks took 1.52–1.99 seconds each. Across the available pre-change provider history, the first spoken response after a caller turn had these timings:

| Route | Retained calls | Replies with timing | Min / median / max |
| --- | ---: | ---: | --- |
| UK | 2 | 4 | 1.57 / 3.56 / 3.91 s |
| India | 7 | 38 | 1.05 / 2.74 / 9.54 s |

These are ElevenLabs silence-to-audio timings and exclude carrier delivery to the handset. The sample is from attended tests and does not provide a representative across-caller or interruption baseline. Two native replays returned the diary options directly. Sixteen native regressions and 517 backend tests passed. Fresh handset comparisons are needed to quantify the effect.

For the next handset comparison, record the first audible response after the caller stops, whether the agent yields during a correction, and whether a brief backchannel clips its reply. Use consenting recipients and preserve the time and outcome in the CRM. Run first voicemail on a fresh test destination after configuring an approved UK callback number, then verify the full stored message in the mailbox. Test opt-out last on a separately consented destination and check both the spoken acknowledgement and subsequent suppression through eligibility checks. Customer campaign admission remains paused.

## Additional evidence and retests

- The earlier 19:45 UK attempt verified identity and retained a recording. It missed the refusal during an interrupted offer and remains marked **Needs review**. A read-only replay with the updated classifier returned **Not interested**. The spoken refusal goodbye still needs a handset check.
- India attended attempt 33 saved **Voicemail**. The approved first message was not verified in the recipient's mailbox. Confirm an approved callback number and complete first-message playback on a fresh consenting destination.
- The [voicemail and opt-out playback fix](https://github.com/SAMUDRABAN/brightwater-service-platform/commit/741570c) is in the repository. The first voicemail message and the full spoken opt-out acknowledgement still need separate handset evidence.
- The reviewer-triggered live call is a separate assessment step. Use the reviewer's agreed number and fictional roleplay details. After the call, open its outcome and any diary entry in the office.

Historical call reports retain unsuccessful attempts and recovery findings. Backend and provider simulations supplement the handset records.
