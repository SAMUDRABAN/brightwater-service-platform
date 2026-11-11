# Qualifying the UK outbound route

The deployed India gateway handles attended tests to its configured Indian recipient. UK campaign calling is paused. When you get access to a UK number, first confirm what you can use it for.

| What you have | What to confirm |
| --- | --- |
| A UK handset to receive a test call | You own it or the recipient has agreed to an attended, recorded test. Keep the number and consent reference in the private operator workspace. |
| A UK number to display as caller ID | The outbound carrier account authorises that exact +44 number as caller ID and supports calls to the intended UK destination. A rented or inbound-only number may need separate outbound setup. |
| A UK office callback number | Someone can answer or handle returned calls. This is the number the agent reads in an approved first voicemail. Test the inbound callback separately. |

One number can fill multiple roles if it meets each role's checks. Use fictional customer details during assessment tests and keep assessment sample numbers out of all dialling lists.

## Set up and verify the carrier

1. Use the carrier's authorised test procedure to place one attended call to the approved UK handset. Verify that it rings, the handset displays the intended caller ID, and speech works both ways. Record the carrier call reference and result privately. Resolve any rejected caller ID, account permission or routing failure with the carrier before proceeding.
2. Configure a separate GB gateway using [the voice gateway runbook](voice-gateway.md) and the repository's [voice gateway Compose definition](../infra/plivo/compose.yaml). Set `BW_GATEWAY_COUNTRY=GB` and `BW_VOICE_BACKEND=elevenlabs`. For Twilio, set `BW_GATEWAY_CARRIER=twilio` and provide private `BW_TWILIO_ACCOUNT_SID`, `BW_TWILIO_AUTH_TOKEN` and `BW_TWILIO_FROM_NUMBER`. Twilio uses the gateway’s signed answer, status, recording and media routes. The gateway opens the ElevenLabs conversation with the call’s scoped CRM context. For a Plivo route, use `BW_PLIVO_FROM_NUMBER` and the Plivo credentials. Configure private carrier credentials, the HTTPS origin and API connection, gateway/runtime authentication, encrypted state and the managed closing credential `BW_MANAGED_CLOSING_API_KEY`. Check that the gateway's readiness endpoint reports `region: GB`.
3. Configure the London API's private `BW_CAMPAIGN_GATEWAY_URL`, matching `BW_CAMPAIGN_GATEWAY_TOKEN`, `BW_MANAGED_CAMPAIGN_AGENT_ID` and `BW_OFFICE_CALLBACK_NUMBER`. Check recording notice and encrypted media storage. For the attended pilot set `BW_CAMPAIGN_PILOT_CUSTOMER_ID` and `BW_CAMPAIGN_PILOT_RECIPIENT` to the fictional record ID and its approved real UK handset. This restricts all admissions to that pair and skips automatic reminder queueing. Set `BW_CAMPAIGN_ROUTE_VERIFIED` only after the carrier check succeeds. Review remaining blockers in CRM **Call controls** or authenticated `GET /v1/campaign/status`.

## Run the attended Brightwater test

The **Call my test phone** button is for the India route. For UK qualification, use a controlled GB campaign pilot with only the approved test destination eligible for dispatch. Keep the normal customer campaign paused during setup.

1. Register the approved +44 recipient against the fictional test customer using authenticated `POST /v1/customers/{customer_id}/destination`, with `phone` and `consent_reference`. Check eligibility and suppression. Keep every other destination ineligible and verify there is no queued campaign work for other recipients before opening the pilot.
2. Use the ordinary campaign admission path for the pilot. Roll out the same release and pilot configuration to the API, workers and Beat before enabling dialling. In the pilot environment, verify `BW_GATEWAY_ENABLED`, `BW_GATEWAY_CAMPAIGN_ENABLED`, `BW_DIALING_ENABLED` and the CRM dialling control. Choose a permitted UK calling window and keep periodic Beat scheduling paused. Queue one call through authenticated `POST /v1/calls` with the test `customer_id` and a unique `request_key`. With the workers running, trigger one controlled `brightwater.tick` to publish the outbox entry. The pilot flags prevent this tick from queueing reminders. Existing queued work is still subject to the pilot admission gate. If the test cannot be isolated, keep dialling paused and resolve that before dispatch.
3. Verify that the handset receives the call with the intended caller ID and intelligible two-way audio. Confirm the automated and recording disclosure, identity check, a saved booking or callback in the CRM, normal close, and protected recording playback. Save the masked destination, timestamp, carrier reference and CRM outcome in private test evidence.
4. With separate test permission, use eligible fictional test records for the follow-up scenarios, since a completed conversation stops further attempts on the same campaign contact. Let one call reach voicemail and listen for the complete approved message in the mailbox. Run opt-out last. Verify the spoken acknowledgement and that the CRM blocks later admission for that number. Use an eligibility check to verify suppression. Pause dialling after the pilot and record any failure before considering wider rollout.

## Outcome review

If an answered attempt is still marked **Needs review**, Sarah can open the call record and record a supported disposition with an evidence note. An answered call without adequate evidence stays available for review. The action cannot create a booking or claim that an emergency message was played.

## Attended test form

An administrator can open **Call controls → UK test call**, choose the fictional customer, enter the recipient’s UK phone number and confirm consent to the recorded call. The form creates a separate roleplay record and opens it in **Calls**. It leaves automatic reminders paused and never registers the recipient against the original customer record.

The optional London overlay `infra/digitalocean/compose.uk-voice.yaml` provides the Twilio gateway. Give it a private env file, a separate Redis database index, a distinct gateway token and an HTTPS hostname. The API uses `BW_CAMPAIGN_GATEWAY_URL` and `BW_CAMPAIGN_GATEWAY_TOKEN` to reach it. Set `BW_UK_TEST_ENABLED` and `BW_UK_TEST_CALLER_ID` for the attended form. Keep `BW_DIALING_ENABLED=false` for review calls. The attended test form is available outside campaign calling hours when the recipient has agreed to take the call. It checks suppression and admits one active call at a time. Use **Pause new calls** to close attended admission.
