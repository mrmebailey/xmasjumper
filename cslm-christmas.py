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
        christmas_day = datetime.datetime(christmas_year, 12, 25, 0, 0, 0)
        
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
    lcd.setCursor(0,0)  # set cursor position
    lcd.message( 'HAPPY CSLM CHRISTMAS')
    while(True):         
        days, seconds_in_day, hours, minutes, seconds = calculate_time_to_christmas()
        #lcd.clear()
        lcd.setCursor(0,1)  # set cursor position
        lcd.message(("{} days, {} hours".format(days, hours, minutes, seconds)))
        lcd.setCursor(0,2)  # set cursor position
        #lcd.message( 'CPU: ' + get_cpu_temp()+'\n' )# display CPU temperature
        lcd.message(("{} minutes and".format(minutes, seconds)))
        lcd.setCursor(0,3)  # set cursor position
        lcd.message(("{} seconds to xmas".format(seconds)))
        #lcd.message( get_time_now() )   # display the time
        sleep(1)
 
def destroy():
    lcd.clear()
    
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
    print ('Program is starting ... ')
    try:
        loop()
    except KeyboardInterrupt:
        destroy()
