#!/usr/bin/env python3
########################################################################
# Filename    : I2CLCD2004.py
# Description : Use the LCD display data
# Author      : freenove
# modification: 2022/06/28
########################################################################
from PCF8574 import PCF8574_GPIO
from Adafruit_LCD2004 import Adafruit_CharLCD

from time import sleep, strftime
from datetime import datetime
import sys
import json
import textwrap
import os
import re
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoRegionError
except Exception:
    boto3 = None


 
def get_cpu_temp():     # get CPU temperature and store it into file "/sys/class/thermal/thermal_zone0/temp"
    tmp = open('/sys/class/thermal/thermal_zone0/temp')
    cpu = tmp.read()
    tmp.close()
    return '{:.2f}'.format( float(cpu)/1000 ) + ' C'
 
def get_time_now():     # get system time
    return datetime.now().strftime('    %H:%M:%S')
   
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
    
    # Convert total difference to seconds
    total_seconds = int(time_to_christmas.total_seconds())
    
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
    return (days, seconds_in_day, hours, minutes, seconds)
 
def loop():
    mcp.output(3,1)     # turn on LCD backlight
    lcd.begin(20,4)     # set number of LCD lines and columns

    # draw static header once
   

    # track previous values so we only write changed rows
    prev_line1 = prev_line2 = prev_line3 = None
    while True:
        write_row(0, 'HAPPY CSLM CHRISTMAS')
        days, seconds_in_day, hours, minutes, seconds = calculate_time_to_christmas()
        # Prepare the text for each row. Use minute granularity to avoid per-second updates.
        line1 = f"{days} days {hours}h"
        line2 = f"{minutes}m to xmas"
        # show time as HH:MM (no seconds) to reduce updates
        now = datetime.now()
        line3 = now.strftime('    %H:%M')

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
    lcd.clear()


def write_row(row, text):
    """Write a single 20-char row without clearing the display.
    Pads or truncates text to exactly 20 chars so previous content is overwritten."""
    try:
        s = str(text)[:20].ljust(20)
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
        # keep the message visible for a short while
        sleep(hold_seconds)
    except Exception as e:
        print('LCD display error:', e)


def show_countdown_for(duration_seconds):
    """Display the Christmas countdown (similar to loop()) for duration_seconds seconds.
    Updates once per second and then returns.
    """
    try:
        end = int(duration_seconds)
        start_time = 0
        # ensure backlight
        try:
            mcp.output(3,1)
            lcd.begin(20,4)
        except Exception:
            pass

        # Only update rows that changed while counting down to avoid excessive writes
        prev1 = prev2 = prev3 = None
        for i in range(end):
            days, seconds_in_day, hours, minutes, seconds = calculate_time_to_christmas()
            line1 = f"{days} days {hours}h"
            line2 = f"{minutes}m to xmas"
            now = datetime.now()
            line3 = now.strftime('    %H:%M')
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
                print('Countdown:', days, hours, minutes, seconds)
            sleep(1)
    except Exception as e:
        print('Countdown display error:', e)


def poll_sqs_and_display(queue_url, wait_time=10):
    """Long-poll the given SQS queue and display each incoming message on the LCD.

    This function requires `boto3` and valid AWS credentials (environment, IAM role, etc.).
    It deletes messages after displaying them.
    """
    if boto3 is None:
        raise RuntimeError('boto3 is required for SQS polling')

    # Determine AWS region: prefer env vars, else try to parse from the queue URL
    region = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION')
    if not region and queue_url:
        m = re.search(r'https?://sqs\.([a-z0-9-]+)\.amazonaws\.com', queue_url)
        if m:
            region = m.group(1)

    try:
        if region:
            sqs = boto3.client('sqs', region_name="eu-west-2")
        else:
            sqs = boto3.client('sqs')
    except NoRegionError:
        raise RuntimeError('AWS region not configured. Set AWS_REGION or AWS_DEFAULT_REGION, or provide a queue URL that contains the region.')
    print('Polling SQS queue:', queue_url)
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
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=0,
                VisibilityTimeout=60,
                MessageAttributeNames=['All']
            )

            messages = resp.get('Messages') or []
            if not messages:
                # no messages — show countdown for 15 seconds then poll again
                show_countdown_for(15)
                continue

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

                # Show on LCD for 60 seconds
                print('Displaying message:', display_text)
                _display_on_lcd_multiline(display_text, hold_seconds=60)

                # Delete message from queue
                receipt = msg.get('ReceiptHandle')
                if receipt:
                    try:
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
                    except Exception as e:
                        print('Failed to delete message:', e)
        except (BotoCoreError, ClientError) as e:
            print('SQS receive error:', e)
            sleep(5)
            continue
        except Exception as e:
            # Unexpected error — log and return to allow main to fall back to loop()
            print('Unexpected error in SQS poller:', e)
            return
    
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

if __name__ == '__main__':
    try:
        print('Program is starting ... ')
        # If boto3 is available and the user passed 'sq', 'sqs' or 'poll' as an argument, poll SQS
        if len(sys.argv) > 1 and sys.argv[1].lower().startswith(('sq','sqs','poll')):
            if boto3 is None:
                print('boto3 is not installed; install it to use SQS polling: pip install boto3')
                sys.exit(1)

            # allow optional queue URL as second argument, otherwise use the default from the request
            queue_url = sys.argv[2] if len(sys.argv) > 2 else 'https://sqs.eu-west-2.amazonaws.com/567919078991/xmasjumper'

            try:
                poll_sqs_and_display(queue_url)
                # if poller returns (unexpectedly), fall back to loop()
                print('SQS poller exited; falling back to local loop()')
                try:
                    loop()
                except KeyboardInterrupt:
                    destroy()
            except KeyboardInterrupt:
                destroy()
            except Exception as e:
                print('Error starting poller:', e)
                print('Falling back to loop()')
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
        # On any unexpected error, print and fall back to the loop display
        print('Unhandled exception at top level:', e)
        try:
            loop()
        except KeyboardInterrupt:
            destroy()

