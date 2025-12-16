# xmasjumper

A small Raspberry Pi project that displays festive messages on a 20x4 I2C LCD and drives a NeoPixel strip. Messages can be submitted from a static S3-hosted web page (`index.html`) which posts to an API endpoint that places messages onto an SQS queue. The Pi polls SQS, displays incoming messages on the LCD, logs them to a `messages` file, and can be paired with NeoPixels for visual effects.

**Contents**
- `index.html` — static web UI to post messages (S3-hostable).
- `cslm-christmas.py` — main Pi script: LCD display, SQS poller, message logging.
- `neopixel1.py` — example NeoPixel control script (uses `board.D18`).
- `messages` — runtime-generated log of received messages (created by the script).
- `jumper-with-qr.png` — architecture diagram with QR code.

**Quick run**
- Countdown display (local):
```
python3 cslm-christmas.py
```
- Poll SQS and display incoming messages (requires `boto3` and AWS credentials):
```
python3 cslm-christmas.py sq [QUEUE_URL]
```

Hardware
--------

Minimum parts
- Raspberry Pi (any model with I2C + PWM / SPI GPIOs; Pi 3/4 recommended)
- 20x4 LCD with PCF8574 I2C backpack (or equivalent I2C LCD adapter)
- NeoPixel strip (e.g. 30 WS2812 LEDs) and power supply
- Logic-level advice: NeoPixels use 5V power and expect ~5V data — use a level shifter or ensure safe wiring (see notes below).

Pinout (Raspberry Pi 40-pin header)

LCD (PCF8574 I2C backpack)
- SDA (BCM 2) — physical pin 3
- SCL (BCM 3) — physical pin 5
- VCC            — physical pin 2 or 4 (5V) depending on module; many PCF8574 modules accept 5V
- GND            — physical pin 6 (or any ground)

PCF8574 I2C address
- Typical addresses used in this project: `0x27` or `0x3F` (see `cslm-christmas.py` variables `PCF8574_address` and `PCF8574A_address`).

NeoPixel strip (WS2812 / Neopixel)
- Data: GPIO18 (BCM 18) — physical pin 12 — this is `board.D18` in `neopixel1.py`
- 5V Power: physical pin 2 or 4 (use an external 5V supply if many LEDs)
- GND: common ground with Raspberry Pi (physical pin 6 or other ground)

Recommended wiring notes
- Put a 300-500Ω resistor in series with the NeoPixel data line to reduce ringing.
- Place a 1000 µF electrolytic capacitor across the NeoPixel 5V and GND rails to stabilise power.
- Use a level shifter (e.g. 74HCT245 or MOSFET-based) between the Pi (3.3V) data pin and NeoPixel data if your strip is 5V.

Software architecture
---------------------

Overview

1. The static UI (`index.html`) runs in the browser (S3). When a user submits a message, it POSTs JSON to an API endpoint (API Gateway).
2. The API endpoint enqueues the message onto an AWS SQS queue.
3. The Raspberry Pi runs `cslm-christmas.py` which polls the SQS queue, receives messages, and displays them on the LCD (20x4). Each message is:
   - formatted to 4 lines of 20 chars,
   - displayed on the LCD for the configured hold time,
   - appended to a local `messages` file with a timestamp,
   - logged to stdout with simple counters for API calls and messages picked.
4. Optionally, `neopixel1.py` can run (separately or integrated) to add LED effects when messages arrive.

Diagram

ASCII diagram

```
[Browser: index.html]
	|
	| POST JSON
	v
[API Gateway / Endpoint]
	|
	| -> put message on SQS
	v
[AWS SQS Queue]
	|
	| (polled by)
	v
[Raspberry Pi]
   - runs `cslm-christmas.py`
   - I2C -> PCF8574 -> LCD (20x4)
   - GPIO18 -> NeoPixel data -> NeoPixel strip
   - writes `messages` file and prints stats
```

![Architecture Diagram](jumper-with-qr.png)

Files and responsibilities
- `index.html`: builds and POSTs JSON. Designed for S3 static hosting.
- `cslm-christmas.py`: LCD driver, SQS poller, message formatting, logging to `messages` file.
- `neopixel1.py`: NeoPixel demo using `board.D18` and the `neopixel` library.

Security & deployment notes
- The Pi needs network access and AWS credentials (environment variables or instance role) to poll SQS.
- Keep the API endpoint secured (CORS, API keys, IAM authorizers) if you expose it publicly.

Troubleshooting
- If you see NoRegionError: ensure `AWS_REGION` or `AWS_DEFAULT_REGION` is set or pass a queue URL containing the region.
- If NeoPixels flicker or show incorrect colours, check `ORDER` in `neopixel1.py` (RGB vs GRB), wiring, and power.

Further improvements
- Integrate NeoPixel effects into `cslm-christmas.py` so LEDs animate when a message is displayed.
- Rotate or compress the `messages` log (`logrotate`) to avoid unbounded growth.
- Use long-polling on SQS for lower API call rates (increase `WaitTimeSeconds`).

License
-------
This project follows the repository author license (no explicit license file included). Add a `LICENSE` if you want a permissive/open-source license.

Enjoy the jumper! 🎄
