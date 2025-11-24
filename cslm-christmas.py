#!/usr/bin/env python3
########################################################################
# Filename    : I2CLCD2004.py
# Description : Use the LCD display data
# Author      : freenove
# modification: 2022/06/28
########################################################################
from PCF8574 import PCF8574_GPIO
from Adafruit_LCD2004 import Adafruit_CharLCD

from time import sleep
from datetime import datetime
import sys
import json
import textwrap
import os
import re
import subprocess
import logging
import socket
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoRegionError
except Exception:
    boto3 = None

# Configuration constants
# LCD geometry
LCD_COLS = 20
LCD_ROWS = 4
LINE_WIDTH = 20

# NeoPixel script (expected next to this file)
NEOPIXEL_SCRIPT = 'neopixel1.py'

# Messages log filename
MESSAGES_FILENAME = 'messages'

# LCD header text
HEADER_TEXT = 'HAPPY CSLM CHRISTMAS'

# Stats persistence
STATUS_FILENAME = 'stats.json'

# SQS / polling defaults
SQS_DEFAULT_QUEUE_URL = 'https://sqs.eu-west-2.amazonaws.com/567919078991/xmasjumper'
POLL_NO_MESSAGE_SHOW = 15          # seconds to show countdown when no messages
MESSAGE_HOLD_SECONDS = 60          # seconds to display an incoming message
# Default AWS region to use if none is provided via env or queue URL
DEFAULT_AWS_REGION = 'eu-west-2'


# Simple runtime counters for logging
api_call_count = 0
messages_picked_count = 0

# Cached sudo availability check (None = unknown, True/False = cached result)
_sudo_n_available = None

def can_use_sudo_n():
    """Return True if `sudo -n true` can run without prompting. Cached result."""
    global _sudo_n_available
    if _sudo_n_available is not None:
        return _sudo_n_available
    try:
        r = subprocess.run(['sudo', '-n', 'true'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _sudo_n_available = (r.returncode == 0)
    except Exception:
        _sudo_n_available = False
    return _sudo_n_available

def append_message_to_file(message_text, filename=MESSAGES_FILENAME):
    """Append a timestamped message to the `messages` file.
    Each line: YYYY-MM-DD HH:MM:SS - message
    """
    try:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(filename, 'a', encoding='utf-8') as fh:
            fh.write(f"{ts} - {message_text}\n")
    except Exception as e:
        logging.exception('Failed to write message file')

def log_stats():
    """Print simple stats about API usage and messages picked up."""
    try:
        logging.info(f"SQS API calls: {api_call_count}, messages picked: {messages_picked_count}")
        # persist stats
        try:
            save_stats()
        except Exception:
            logging.exception('Failed to save stats')
    except Exception:
        pass

def load_stats():
    global api_call_count, messages_picked_count
    try:
        if os.path.exists(STATUS_FILENAME):
            with open(STATUS_FILENAME, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                api_call_count = int(data.get('api_call_count', 0))
                messages_picked_count = int(data.get('messages_picked_count', 0))
                logging.info('Loaded stats from %s', STATUS_FILENAME)
    except Exception:
        logging.exception('Failed to load stats')

def save_stats():
    try:
        data = {'api_call_count': api_call_count, 'messages_picked_count': messages_picked_count}
        with open(STATUS_FILENAME, 'w', encoding='utf-8') as fh:
            json.dump(data, fh)
    except Exception:
        logging.exception('Failed to save stats')

# Neopixel subprocess controller
neopixel_proc = None

def start_neopixels():
    """Start `neopixel1.py` using sudo. If already running, do nothing."""
    global neopixel_proc
    if neopixel_proc is not None and neopixel_proc.poll() is None:
        return
    path = os.path.join(os.path.dirname(__file__), NEOPIXEL_SCRIPT)
    if not os.path.exists(path):
        logging.error('Neopixel script not found: %s', path)
        return
    # Determine how to run the neopixel script:
    # - If running as root, execute directly.
    # - Else, if `sudo -n` works (won't prompt), use `sudo -n`.
    # - Otherwise, refuse to start and log a helpful message.
    if os.geteuid() == 0:
        # Already root — run the script directly with the current Python
        cmd = [sys.executable, path]
    else:
        # Not root — prefer using non-interactive sudo if available
        if can_use_sudo_n():
            cmd = ['sudo', '-n', sys.executable, path]
        else:
            logging.error('Cannot start neopixels: sudo would prompt for a password.\nRun this script as root or configure passwordless sudo for the neopixel script.')
            return
    try:
        neopixel_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info('Started neopixel process, pid=%s', getattr(neopixel_proc, 'pid', None))
    except Exception as e:
        logging.exception('Failed to start neopixel process')
        neopixel_proc = None

def stop_neopixels():
    """Stop the running neopixel process if any."""
    global neopixel_proc
    if neopixel_proc is None:
        return
    try:
        neopixel_proc.terminate()
        try:
            neopixel_proc.wait(timeout=5)
        except Exception:
            neopixel_proc.kill()
    except Exception as e:
        logging.exception('Error stopping neopixel process')
    finally:
        neopixel_proc = None


 
def get_cpu_temp():     # get CPU temperature and store it into file "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as tmp:
            cpu = tmp.read()
        return '{:.2f}'.format(float(cpu)/1000) + ' C'
    except Exception:
        return 'N/A'

def is_network_available(timeout=2):
    """Quick check for basic network connectivity.
    Tries to open a socket to a well-known public DNS server (TCP) to
    determine if the network is up. Returns True if connection succeeds.
    """
    try:
        # use TCP to 1.1.1.1:53 (Cloudflare DNS) which should be reachable
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(('1.1.1.1', 53))
            return True
        finally:
            s.close()
    except Exception:
        return False
 
def calculate_time_to_christmas():
    # Set the target date for Christmas Day at midnight (00:00:00)
    # The year is set to the current year (2025 in this context)
    christmas_year = datetime.now().year
    christmas_day = datetime(christmas_year, 12, 25, 0, 0, 0)
    
    # Get the current date and time
    current_time = datetime.now()
    
    # Check if Christmas has already passed this year, and if so, target next year
    if current_time > christmas_day:
        christmas_year += 1
        christmas_day = datetime(christmas_year, 12, 25, 0, 0, 0)
        
    # Calculate the difference (timedelta)
    time_to_christmas = christmas_day - current_time
    
    # Calculate days, hours, minutes, and seconds from the timedelta object
    days = time_to_christmas.days
    seconds_in_day = time_to_christmas.seconds
    hours = seconds_in_day // 3600
    minutes = (seconds_in_day % 3600) // 60
    seconds = seconds_in_day % 60
    
    #print(f"Current Date and Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    #print(f"Christmas Day: {christmas_day.strftime('%Y-%m-%d %H:%M:%S')}")
    #print("\n--- Results ---")
    #print(f"Time to Christmas (D:H:M:S): {days} days, {hours} hours, {minutes} minutes, {seconds} seconds")
    #print(f"Total seconds to Christmas: {total_seconds} seconds")
    # Return only the values the rest of the program uses (days, hours, minutes, seconds)
    return (days, hours, minutes, seconds)


def get_wifi_ssid():
    """Try to determine the connected Wi-Fi SSID.
    Uses `iwgetid -r` if available, falls back to `nmcli` where present.
    Returns the SSID string or 'Unknown'.
    """
    try:
        # Try iwgetid first (commonly available on many systems)
        p = subprocess.run(['iwgetid', '-r'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        ssid = (p.stdout or '').strip()
        if ssid:
            return ssid
    except Exception:
        pass

    try:
        # Try nmcli: look for an active wifi line
        p = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        out = (p.stdout or '').strip()
        for line in out.splitlines():
            if line.startswith('yes:'):
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[1]:
                    return parts[1]
    except Exception:
        pass

    return 'Unknown'


def get_ip_address():
    """Return the primary IPv4 address of the host, or 'N/A' if unavailable.
    Uses a UDP socket hack to determine the outbound IP without sending data.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # This does not actually send data but forces the OS to pick a source IP
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            return ip
        finally:
            s.close()
    except Exception:
        return 'N/A'


def display_network_info(hold_seconds=60):
    """Display the Wi-Fi SSID and IP address on the LCD for `hold_seconds` seconds.
    This is intended to run once at startup.
    """
    try:
        ssid = get_wifi_ssid()
        ip = get_ip_address()
        lines = [f"WIFI: {ssid}", f"IP: {ip}", "", ""]
        # Join into a single text blob for the multiline display helper
        text = '\n'.join([l for l in lines if l is not None])
        _display_on_lcd_multiline(text, hold_seconds=hold_seconds)
    except Exception:
        logging.exception('Failed to display network info')
 
def loop():
    mcp.output(3,1)     # turn on LCD backlight
    lcd.begin(LCD_COLS, LCD_ROWS)     # set number of LCD lines and columns
    # draw static header once
    write_row(0, HEADER_TEXT)

    # track previous values so we only write changed rows
    prev_line1 = prev_line2 = prev_line3 = None
    while True:
        days, hours, minutes, seconds = calculate_time_to_christmas()
        # Prepare the text for each row. Use minute granularity to avoid per-second updates.
        line1 = f"{days} days {hours} hours"
        line2 = f"{minutes} minutes to Christmas day"
        # show time as HH:MM plus CPU temperature to reduce updates
        now = datetime.now()
        cpu = get_cpu_temp()
        # Format as 'HH:MM  xx.xx C' (fits in LINE_WIDTH); write_row will truncate/pad
        line3 = f"Time: {now.strftime('%H:%M')} CPU: {cpu}"

        # Only update rows that changed
        if line1 != prev_line1:
            write_row(1, line1)
            prev_line1 = line1
        if line2 != prev_line2:
            write_row(2, line2)
            prev_line2 = line2
        if line3 != prev_line3:
            write_row(3, line3)
            prev_line3 = line3

        sleep(1)
 
def destroy():
    try:
        stop_neopixels()
    except Exception:
        pass
    try:
        lcd.clear()
    except Exception:
        pass


def write_row(row, text):
    """Write a single 20-char row without clearing the display.
    Pads or truncates text to exactly 20 chars so previous content is overwritten."""
    try:
        s = str(text)[:LINE_WIDTH].ljust(LINE_WIDTH)
        lcd.setCursor(0, row)
        lcd.message(s)
    except Exception:
        # If LCD fails, ignore and continue
        pass


def _format_to_4_lines(text, width=20):
    """Format arbitrary text into up to four lines of given width for a 20x4 LCD.
    Returns a list of 4 strings (may be empty strings).
    """
    if text is None:
        text = ''
    # Normalize whitespace
    txt = ' '.join(str(text).split())
    # If text is JSON string representing an object with a 'message' key, prefer that
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, dict) and 'message' in parsed:
            txt = str(parsed['message'])
    except Exception:
        pass

    # Wrap into lines
    parts = textwrap.wrap(txt, width=width)
    # If there are more than 4 lines, concatenate extras into the last line truncated
    if len(parts) > 4:
        parts = parts[:3] + [ ' '.join(parts[3:]) ]
    # Ensure exactly 4 lines
    while len(parts) < 4:
        parts.append('')
    # Truncate each line to width
    parts = [p[:width] for p in parts]
    return parts


def _display_on_lcd_multiline(text, hold_seconds=6):
    """Clear the LCD and display `text` across 4 lines (20 chars each).
    Keeps message on screen for `hold_seconds` seconds.
    """
    lines = _format_to_4_lines(text, width=20)
    try:
        lcd.clear()
        for row, line in enumerate(lines):
            lcd.setCursor(0, row)
            # Adafruit LCD's message accepts a string
            lcd.message(line)
        # start neopixel effects while message is shown
        try:
            start_neopixels()
        except Exception:
            pass
        # keep the message visible for a short while
        sleep(hold_seconds)
        # stop neopixels and restore the static header after the message is shown
        try:
            stop_neopixels()
        except Exception:
            pass
        try:
                write_row(0, HEADER_TEXT)
        except Exception:
            pass
    except Exception:
        # ensure neopixels stopped on unexpected errors
        try:
            stop_neopixels()
        except Exception:
            pass
        logging.exception('LCD display error')


def show_countdown_for(duration_seconds):
    """Display the Christmas countdown (similar to loop()) for duration_seconds seconds.
    Updates once per second and then returns.
    """
    try:
        end = int(duration_seconds)
        # ensure backlight
        try:
            mcp.output(3,1)
            lcd.begin(20,4)
        except Exception:
            pass

        # draw static header for countdown
        try:
            write_row(0, HEADER_TEXT)
        except Exception:
            pass

        # Only update rows that changed while counting down to avoid excessive writes
        prev1 = prev2 = prev3 = None
        for i in range(end):
            days, hours, minutes, seconds = calculate_time_to_christmas()
            line1 = f"{days} days {hours} hours"
            line2 = f"{minutes} minutes to xmas"
            now = datetime.now()
            cpu = get_cpu_temp()
            line3 = f"Time: {now.strftime('%H:%M')} CPU: {cpu}"
            try:
                if line1 != prev1:
                    write_row(1, line1)
                    prev1 = line1
                if line2 != prev2:
                    write_row(2, line2)
                    prev2 = line2
                if line3 != prev3:
                    write_row(3, line3)
                    prev3 = line3
            except Exception:
                logging.info('Countdown values: %s days %s hours %s minutes %s seconds', days, hours, minutes, seconds)
            sleep(1)
    except Exception:
        logging.exception('Countdown display error')


def poll_sqs_and_display(queue_url, wait_time=10):
    """Long-poll the given SQS queue and display each incoming message on the LCD.

    This function requires `boto3` and valid AWS credentials (environment, IAM role, etc.).
    It deletes messages after displaying them.
    """
    if boto3 is None:
        raise RuntimeError('boto3 is required for SQS polling')

    # If there's no network connectivity, bail out so the main program can
    # continue displaying the local countdown instead of blocking here.
    try:
        if not is_network_available():
            logging.warning('Network appears to be offline; skipping SQS poller')
            return
    except Exception:
        # If the network check itself fails for any reason, don't prevent
        # the program from continuing.
        logging.exception('Network check failed; skipping SQS poller')
        return

    # Determine AWS region: prefer environment settings, then parse from the
    # queue URL, otherwise fall back to the configured default region.
    region = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION')
    if not region and queue_url:
        m = re.search(r'https?://sqs\.([a-z0-9-]+)\.amazonaws\.com', queue_url)
        if m:
            region = m.group(1)
    if not region:
        region = DEFAULT_AWS_REGION

    try:
        if region:
            sqs = boto3.client('sqs', region_name=region)
        else:
            sqs = boto3.client('sqs')
    except NoRegionError:
        raise RuntimeError('AWS region not configured. Set AWS_REGION or AWS_DEFAULT_REGION, or provide a queue URL that contains the region.')
    except Exception:
        logging.exception('Failed to create SQS client (network/credentials issue)')
        return
    logging.info('Polling SQS queue: %s', queue_url)
    # ensure backlight and LCD are ready
    try:
        mcp.output(3,1)
        lcd.begin(20,4)
    except Exception:
        pass

    # Poll every 15 seconds. We'll do a short receive (no long-poll) and then
    # when there are no messages display the countdown for 15 seconds.
    while True:
        try:
            # Count the API call (receive)
            global api_call_count, messages_picked_count
            api_call_count += 1
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=0,
                VisibilityTimeout=MESSAGE_HOLD_SECONDS,
                MessageAttributeNames=['All']
            )

            messages = resp.get('Messages') or []
            if not messages:
                # no messages — show countdown for POLL_NO_MESSAGE_SHOW seconds then poll again
                show_countdown_for(POLL_NO_MESSAGE_SHOW)
                continue

            # we received one or more messages
            messages_picked_count += len(messages)
            for msg in messages:
                body = msg.get('Body', '')
                display_text = None
                # body may itself be JSON; try to extract sensible text
                try:
                    parsed = json.loads(body)
                    # If SQS message contains SNS envelope or stringified message, try common fields
                    if isinstance(parsed, dict):
                        # Common SNS -> message key
                        if 'Message' in parsed and isinstance(parsed['Message'], str):
                            # Message may itself be JSON
                            try:
                                inner = json.loads(parsed['Message'])
                                if isinstance(inner, dict) and 'message' in inner:
                                    display_text = inner['message']
                                else:
                                    display_text = parsed['Message']
                            except Exception:
                                display_text = parsed['Message']
                        elif 'message' in parsed:
                            display_text = parsed['message']
                        else:
                            # fallback to the stringified dict
                            display_text = json.dumps(parsed)
                    else:
                        display_text = str(parsed)
                except Exception:
                    display_text = str(body)

                # Show on LCD for MESSAGE_HOLD_SECONDS seconds
                logging.info('Displaying message: %s', display_text)
                _display_on_lcd_multiline(display_text, hold_seconds=MESSAGE_HOLD_SECONDS)

                # append to messages file with timestamp
                try:
                    append_message_to_file(display_text)
                except Exception:
                    pass

                # Delete message from queue
                receipt = msg.get('ReceiptHandle')
                if receipt:
                    try:
                        # Count the API call (delete)
                        api_call_count += 1
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
                    except Exception:
                        logging.exception('Failed to delete message')
            # Log stats after processing this batch
            try:
                log_stats()
            except Exception:
                pass
        except (BotoCoreError, ClientError) as e:
            logging.exception('SQS receive error')
            sleep(5)
            continue
        except Exception as e:
            # Unexpected error — log and return to allow main to fall back to loop()
            logging.exception('Unexpected error in SQS poller')
            try:
                stop_neopixels()
            except Exception:
                pass
            return
    
# I2C addresses (kept here for historic reasons; can be changed)
PCF8574_address = 0x27  # I2C address of the PCF8574 chip.
PCF8574A_address = 0x3F  # I2C address of the PCF8574A chip.
# Create PCF8574 GPIO adapter.
try:
    mcp = PCF8574_GPIO(PCF8574_address)
except:
    try:
        mcp = PCF8574_GPIO(PCF8574A_address)
    except:
        print ('I2C Address Error !')
        exit(1)
# Create LCD, passing in MCP GPIO adapter.
lcd = Adafruit_CharLCD(pin_rs=0, pin_e=2, pins_db=[4,5,6,7], GPIO=mcp)
try:
    # Ensure the LCD object knows its dimensions early so startup displays
    # (network info, etc.) can call setCursor safely.
    lcd.begin(LCD_COLS, LCD_ROWS)
except Exception:
    # If begin fails, continue — other code will attempt to call begin when needed.
    logging.exception('LCD begin() failed at startup')

if __name__ == '__main__':
    try:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
        logging.info('Program is starting ...')
        # load persisted stats if present
        load_stats()
        # Show network info once at startup for 60 seconds (SSID + IP)
        try:
            display_network_info(60)
        except Exception:
            logging.exception('Error showing network info')
        # If boto3 is available and the user passed 'sq', 'sqs' or 'poll' as an argument, poll SQS
        if len(sys.argv) > 1 and sys.argv[1].lower().startswith(('sq','sqs','poll')):
            if boto3 is None:
                logging.error('boto3 is not installed; cannot start SQS polling. Falling back to local display loop.')
                try:
                    loop()
                except KeyboardInterrupt:
                    destroy()
                sys.exit(0)

            # allow optional queue URL as second argument, otherwise use the default from the request
            queue_url = sys.argv[2] if len(sys.argv) > 2 else SQS_DEFAULT_QUEUE_URL

            try:
                poll_sqs_and_display(queue_url)
                # if poller returns (unexpectedly), fall back to loop()
                logging.info('SQS poller exited; falling back to local loop()')
                try:
                    loop()
                except KeyboardInterrupt:
                    destroy()
            except KeyboardInterrupt:
                destroy()
            except Exception as e:
                logging.exception('Error starting poller')
                logging.info('Falling back to loop()')
                try:
                    loop()
                except KeyboardInterrupt:
                    destroy()
        else:
            try:
                loop()
            except KeyboardInterrupt:
                destroy()
    except KeyboardInterrupt:
        destroy()
    except Exception as e:
        # On any unexpected error, log and fall back to the loop display
        logging.exception('Unhandled exception at top level')
        try:
            loop()
        except KeyboardInterrupt:
            destroy()

