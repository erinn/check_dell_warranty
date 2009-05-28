#!/usr/bin/env python

#=============================================================================
# Nagios plugin to pull the Dell service tag and check it 
# against Dell's website to see how many days remain. By default it 
# issues a warning when there is less than thirty days remaining and critical when 
# there is less than ten days remaining. These values can be adjusted using
# the command line, see --help.                                                 
# Version: 1.1                                                                
# Created: 2009-02-12                                                         
# Author: Erinn Looney-Triggs                                                 
# Revised: 2009-05-27                                                                
# Revised by: Erinn Looney-Triggs, Justin Ellison                                                                
# Revision history:
#
# 2009-05-28 1.2 Added service tag to output for nagios. Fixed some typos.
# Added command-line option for specifying a serial number.  This gets    
# rid of the sudo dependency as well as the newer python dependency
# allowing it to run on older RHEL distros. justin@techadvise.com
#  
# 2009-05-27 1.1 Fixed string conversions to do int comparisons properly. 
# Remove import csv as I am not using that yet. Add a license to the file.  
#
# License:
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#                                       
#=============================================================================

import re
import sys
import urllib2

#Nagios exit codes in English
UNKNOWN  = 3
CRITICAL = 2
WARNING  = 1
OK       = 0


def extract_serial_number():
    '''Extracts the serial number from the localhost using dmidecode.
    This function takes no arguments but expects dmidecode to exist and
    also expects dmidecode to accept -s system-serial-number
    
    '''
    import subprocess
    

    #Gather the information from dmidecode
    try:
        p = subprocess.Popen(["sudo", "dmidecode", "-s",
                               "system-serial-number"], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE)
    except OSError:
        print 'Error:', sys.exc_value, 'exiting!'
        sys.exit(1)
    
    #Strip the newline off of result
    serial_number = p.stdout.read()
    
    #Basic check of the serial number, can they be longer, maybe
    if len( serial_number.strip() ) != 7:
        print 'Invalid serial number:%s exiting!' % (serial_number)
        sys.exit(WARNING)
    
    return serial_number.strip()

def get_warranty(serial_number):
    #The URL to Dell's site
    dell_url='http://support.dell.com/support/topics/global.aspx/support/my_systems_info/details?c=us&l=en&s=gen&ServiceTag='

    #Regex to pull the information from Dell's site
    pattern=r""".*>                          #Match anything up to >
                (\d{1,2}/\d{1,2}/\d{4})<     #Match North American style date
                .*>(\d{1,2}/\d{1,2}/\d{4})<  #Match date, good for 8000 years
                .*>                          #Match anything up to >
                (\d+)                        #Match number of days
                <.*                          #Match < and the rest of the line
                """
    
    #Build the full URL
    full_url = dell_url + serial_number
    
    #Try to open the page, exit on failure
    try:
        response = urllib2.urlopen(full_url)
    except URLError:
        print 'Unable to open URL: %s exiting!' % (full_url)
        sys.exit(UNKNOWN)
    
    #Build our regex
    regex = re.compile(pattern, re.X)

    #Gather the results returns a list of tuples
    result = (regex.findall(response.read()), serial_number)
    
    return result

def parse_exit(result):
    if len(result) == 0:
        print "Dell's database appears to be down."
        sys.exit(WARNING)
    
    start_date, end_date, days_left = result[0][0]
    serial_number = result[1]
    
    if int(days_left) < options.critical_days:
        print 'CRITICAL: Service Tag: %s Warranty start: %s End: %s Days left: %s' \
        % (serial_number, start_date, end_date, days_left)
        sys.exit(CRITICAL)
        
    elif int(days_left) < options.warning_days:
        print 'WARNING: Service Tag: %s Warranty start: %s End: %s Days left: %s' \
        % (serial_number, start_date, end_date, days_left)
        sys.exit(WARNING)
        
    else:
        print 'OK: Service Tag: %s Warranty start: %s End: %s Days left: %s' \
        % (serial_number, start_date, end_date, days_left)
        sys.exit(OK)
        
def sigalarm_handler(signum, frame):
    print '%s timed out after %d seconds' % (sys.argv[0], options.timeout)
    sys.exit(CRITICAL)
    
if __name__ == '__main__':
    import optparse
    import signal

    parser = optparse.OptionParser(version="%prog 1.2")
    parser.add_option('-c', '--critical', dest='critical_days', default=10,
                     help='Number of days under which to return critical \
                     (Default: 10)', type='int')
    parser.add_option('-s', '--serial-number', dest='serial_number', 
                      default='', help='Dell Service Tag of server \
                      (Default: auto-detected)', type='string')
    parser.add_option('-t', '--timeout', dest='timeout', default=10,
                      help='Set the timeout for the program to run \
                      (Default: 10 seconds)', type='int')
    parser.add_option('-w', '--warning', dest='warning_days', default=30,
                      help='Number of days under which to return a warning \
                      (Default: 30)', type='int' )
    
    (options, args) = parser.parse_args()
        
    signal.signal(signal.SIGALRM, sigalarm_handler)
    signal.alarm(options.timeout)
    
    if options.serial_number:
        serial_number = options.serial_number
    else:
        serial_number = extract_serial_number()
    
    result = get_warranty(serial_number)
    
    signal.alarm(0)
    
    parse_exit(result)