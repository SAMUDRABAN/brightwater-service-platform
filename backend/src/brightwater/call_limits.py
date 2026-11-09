"""Shared limits for attended phone tests, distinct from automated evaluations."""

# ElevenLabs requires a maximum duration and supports up to two hours.
ATTENDED_CALL_MAX_SECONDS = 7200
ATTENDED_SESSION_TTL_SECONDS = ATTENDED_CALL_MAX_SECONDS + 300
MAX_CARRIER_RECORDING_BYTES = 256 * 1024 * 1024
MAX_STORED_RECORDING_BYTES = 256 * 1024 * 1024
