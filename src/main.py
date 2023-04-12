"""
GPS acquisition and echo to VX8R, convert to FGPS-2 compatible sentences
------------------------------------------------------------------

MIT License

Copyright (c) 2023 Erik Tkal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

------------------------------------------------------------------

Main loops forever reading GPS data.  The sentences are modified to meet
the expectations of the Yaesu VX-8DR and sent to the radio.

GP22 is monitored and program will exit if it detects that is grounded.

This version is for integrated device w/ Raspberry Pi Pico and GT-U7 board.

Customize your GPIO and UART/I2C IDs in the code below as needed.

------------------------------------------------------------------
"""

from machine import Pin, UART
import utime, time

led = machine.Pin("LED", machine.Pin.OUT)

def blinkLED():
    led.on()
    time.sleep_ms(10)
    led.off()

# Input GPS module using GP0/1 UART0
uartGPS  = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1), timeout=5000)
# Output UART using GP4/5 UART1
uartRadio = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5), timeout=50)

pinExit = Pin(22, Pin.IN, Pin.PULL_UP)

DEBUG_APP = False

FIX_TIME = False
FIX_STATUS = False

def verifySentence(buff):
    slen = len(buff)
    if (slen < 1 or buff[0] != '$'):
        print("Sentence does not start with $")
        return False
    if (slen < 6 or buff[slen-2:slen] != '\r\n' or buff[slen-5] != '*'):
        print("Sentence does not end with *XX\\r\\n")
        return False
    specifiedCheck = buff[slen-4:slen-2]
    expectedCheck = checkSum(buff[1:slen-5])
    if (expectedCheck != specifiedCheck):
        print("Error verifying: " + buff)
        print("         Passed: " + buff[1:slen-5])
        print("Sentence calculated checksum " + expectedCheck + " does not match " + specifiedCheck)
        return False
    return True

def stripSentence(buff):
    if (not verifySentence(buff)):
        return ""
    slen = len(buff)
    return buff[1:slen-5]

def checkSum(sentence):
    # Calculate XOR of all bytes between the $ and * in a sentence
    check = 0
    for element in sentence:
        check = check ^ ord(element)
    retval = "{:02X}".format(check)
    return retval

def writeSentence(sentence, gpsModule):
    # Write given un-checksummed sentence
    hexChecksum = checkSum(sentence)
    outstr = "$" + sentence + "*" + hexChecksum + "\r\n"
    if (DEBUG_APP):
        print("Echo: " + outstr)
    outbuff = outstr.encode('ascii')
    gpsModule.write(outbuff)

#
# Main loop
#

while True:
    if (pinExit.value() == 0):  # Check if pinExit was grounded as an exit signal
        print("Exiting program.")
        break

    # Check for data from the GPS module
    inputData = uartGPS.readline()

    try:
        buff = str(inputData, 'ascii')  # NMEA is ASCII by definition
    except:
        print("Unable to convert input data to ascii")
        print(str(inputData))
        GPGSV_IN_PROGRESS = False; # In case $GPGSV is in progress, reset
        continue

    # Validate received data
    if (verifySentence(buff) != True):
        print("Ignoring invalid data")
        GPGSV_IN_PROGRESS = False; # In case $GPGSV is in progress, reset
        continue
    if (DEBUG_APP):
        print("GPS:  " + buff[:len(buff)-2])
    buff = stripSentence(buff)
    elems = buff.split(',')
    if (len(elems) == 0):
        continue

    try:
        # Handle the $GPRMC sentence - time, position and speed
        if (elems[0] == "GPRMC"):
            if (len(elems) >= 10 and elems[1] and elems[2] and elems[3] and elems[4] and elems[5] and elems[6]):
                #Convert to FGPS-2
                if (not elems[7]):
                    elems[7] = "0.0"
                if (not elems[8]):
                    elems[8] = "0.0"
                outstr = "GPRMC," + "{0:010.3f}".format(float(elems[1])) + ","  # Time
                outstr = outstr + elems[2]+ ","
                outstr = outstr + "{0:09.4f}".format(float(elems[3])) + "," + elems[4] + "," # Latitute
                outstr = outstr + "{0:010.4f}".format(float(elems[5])) + "," + elems[6] + "," # Longitude
                outstr = outstr + "{0:07.2f}".format(float(elems[7])) + ","
                outstr = outstr + "{0:06.2f}".format(float(elems[8])) + "," + elems[9] + ",,"
                writeSentence(outstr, uartRadio)
            if (elems[1]):
                FIX_TIME = True
            else:
                FIX_TIME = False;
            if (elems[2] == "A"):  # A = valid, V = not valid
                FIX_STATUS = True
            else:
                FIX_STATUS = False

            if (FIX_STATUS):  # single blink
                blinkLED()
            elif (FIX_TIME):  # double blink
                blinkLED()
                time.sleep_ms(90)
                blinkLED()


        # Handle the $GPGGA sentence - number of satellites used (also time and position)
        if (elems[0] == "GPGGA"):
            if (elems[1] and elems[2] and elems[3] and elems[4] and elems[5] and elems[6] and elems[7]):
                #Convert to FGPS-2
                outstr = "GPGGA," + "{0:010.3f}".format(float(elems[1])) + ","  # Time
                outstr = outstr + "{0:09.4f}".format(float(elems[2])) + "," + elems[3] + "," # Latitute
                outstr = outstr + "{0:010.4f}".format(float(elems[4])) + "," + elems[5] + "," # Longitude
                outstr = outstr + elems[6]+ "," + elems[7] + ","
                outstr = outstr + "{0:04.1f}".format(float(elems[8])) + ","
                outstr = outstr + "{0:07.1f}".format(float(elems[9])) + "," + elems[10] + ","
                outstr = outstr + "{0:06.1f}".format(float(elems[11])) + "," + elems[12] + ",000.0,0000"
                writeSentence(outstr, uartRadio)
            if (elems[1]):
                FIX_TIME = True
            else:
                FIX_TIME = False;

        # Handle the $GPGSV / $GPGSA sentences, just pass them on as is
        if (elems[0] == "GPGSV" or elems[0] == "GPGSA"):
            writeSentence(buff, uartRadio)

    except:
        print("Exception caught")
