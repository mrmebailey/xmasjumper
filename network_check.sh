#!/bin/bash

# Configuration
TARGET="8.8.8.8"          # IP to ping (Google DNS). Use your router IP for local check.
TIMEOUT=15                # Time to wait in seconds
FALLBACK_SCRIPT="/home/mark/xmasjumper/cslm-christmas.py sqs" # Path to your fallback script

echo "Starting network check..."

# Loop for the duration of TIMEOUT
end_time=$((SECONDS + TIMEOUT))

while [ $SECONDS -lt $end_time ]; do
    if ping -c 1 -W 1 "$TARGET" &> /dev/null; then
        echo "Network connection established."
        /usr/bin/git -C /home/mark/xmasjumper pull >> /home/mark/xmasjumper/git_reboot.log 2>&1
        /usr/bin/python3 "$FALLBACK_SCRIPT"
        exit 0
    fi
    sleep 1
done

# If we reach here, the timeout has passed with no connection
echo "No network found after $TIMEOUT seconds. Starting fallback script..."

# Execute the fallback script (ensure python or bash is used depending on script type)
/usr/bin/python3 "$FALLBACK_SCRIPT"