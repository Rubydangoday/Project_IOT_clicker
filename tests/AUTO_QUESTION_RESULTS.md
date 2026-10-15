# V3.13 validation — 2026-10-13

Commands from project root:

```bash
bash tests/firmware_host/run.sh
python3 tests/gatt_unit.py
python3 tests/room_switch_unit.py
```

All passed. Host mocks execute the actual V3.13 .ino, ars_ble.cpp, display.cpp
and status_led.cpp; they do not exercise the physical radio or GPIO timing.

Verified scenarios:

- No STATE after login: answer selection/send blocked; steady --.
- STATE selects current question, including a jump from question 1 to 7.
- Duplicate STATE preserves an unsent choice.
- LEFT/RIGHT cannot alter the teacher's question.
- Close/reopen/change/options changes clear unsent selection.
- CL segment pattern differs from sync, pending and numeric modes.
- Closed, missing, out-of-range and zero-option states block answers.
- Invalid answer options are blocked.
- Question change in flight does not change pending question/sequence/answer.
- Retry still sends the original question and answer.
- Wrong-question ACK is ignored; exact old-question ACK resolves the transaction
  without moving the UI back to the old question.
- A close racing with an answer can return a matching NACK and stops retries.
- Disconnect clears question metadata and does not replay an answer on reconnect.
- Room save clears old question; LEFT still cancels identity entry.
- Prior HELLO/discovery/login correlation/heartbeat/display scenarios still pass.

Python: 19 protocol/backend tests plus 10 MQTT/room lifecycle tests pass.

Actual ARM cross-compile: Adafruit nRF52 core 1.7.0, GCC 9-2019q4,
reference FQBN adafruit:nrf52:feather52840. Flash 138504/815104 bytes,
RAM 15752/237568 bytes. DFU zip recipe disabled (nrfutil unavailable);
ELF/HEX compile succeeds. No reference-board binary is distributed.
Use the user's already working SuperMini profile for actual upload.

Server runtime files, DB/web, radio source and physical pin mappings are unchanged
from V3.12. Firmware V3.11 is kept byte-identical as a fallback.
No V3.13 radio/PCB test or end-to-end latency measurement has been performed here.
