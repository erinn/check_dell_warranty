#!/usr/bin/env python

#=============================================================================
# Nagios plug-in to pull the Dell service tag and check it 
# against Dell's web site to see how many days remain. By default it 
# issues a warning when there is less than thirty days remaining and critical 
# when there is less than ten days remaining. These values can be adjusted 
# using the command line, see --help.                                                 
# Version: 1.5                                                                
# Created: 2009-02-12                                                         
# Author: Erinn Looney-Triggs                                                 
# Revised: 2009-06-25                                                                
# Revised by: Erinn Looney-Triggs, Justin Ellison                                                                
# Revision history:
#
# 2009-06-25 1.5: Changed optparse to handle multiple serial numbers. Changed
# the rest of the program to be able to handle multiple serial numbers. Added
# a de-duper for serial numbers just in case you get two of the same from
# the command line or as is the case with Dell blades, two of the same
# from omreport. So this ought to handle blades, though I don't have
# any to test against. 
# 
# 2009-06-05 1.4 Changed optparse to display %default in help output. Pretty
# up the help output with <ARG> instead of variable names. Add description
# top optparse. Will now use prefer omreport to dmidecode for systems
# that have omreport installed and in $PATH. Note, that you do not have to be
# root to run omreport and get the service tag.
#
# 2009-05-29 1.3 Display output for all warranties for a system. Add up the
# number of days left to give an accurate count of the time remaining. Fix
# basic check for Dell's database being down. Fixed regex to be non-greedy.
# Start and end dates for warranty now takes all warranties into account.
# Date output is now yyyy-mm-dd because that is more international.
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


import sys


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
    
    #Lifted straight from the Internet, can't find the site anymore if
    #I find it I will throw in appropriate thanks to the poster. 
    def which(program):
        import os
        
        def is_exe(file_path):
            return os.path.exists(file_path) and os.access(file_path, os.X_OK)
        
        file_path, fname = os.path.split(program)
        
        if file_path:
            if is_exe(program):
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return exe_file
        
        return None
    
    omreport = which('omreport')
    dmidecode = which('dmidecode')
    
    serial_numbers = []
    
    if omreport:
        import re
        try:
            p = subprocess.Popen([omreport, "chassis", "info", "-fmt", "xml"],
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
        except OSError:
            print 'Error:', sys.exc_value, 'exiting!'
            sys.exit(WARNING)
            
        text = p.stdout.read()
        pattern = '''<ServiceTag>(\S+)</ServiceTag>'''
        regex = re.compile(pattern, re.X)
        serial_numbers = regex.findall(text)
        
    elif dmidecode: 
        #Gather the information from dmidecode
        try:
            p = subprocess.Popen(["sudo", "dmidecode", "-s",
                                   "system-serial-number"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
        except OSError:
            print 'Error:', sys.exc_value, 'exiting!'
            sys.exit(WARNING)
        serial_numbers.append(p.stdout.read().strip())
        
    else:
        print 'Neither omreport nor dmidecode are available in $PATH, aborting!'
        sys.exit(WARNING)
    

    
    return serial_numbers

def get_warranty(serial_numbers):
    import re
    import urllib2
    
    result_list = [] #List of results
    
    #The URL to Dell's site
    dell_url='http://support.dell.com/support/topics/global.aspx/support/my_systems_info/details?c=us&l=en&s=gen&ServiceTag='

    #Regex to pull the information from Dell's site
    pattern=r""">                            #Match  >
                (\d{1,2}/\d{1,2}/\d{4})<     #Match North American style date
                .*?>(\d{1,2}/\d{1,2}/\d{4})< #Match date, good for 8000 years
                .*?>                         #Match anything up to >
                (\d+)                        #Match number of days
                <                            #Match <
                """
    
    # Remove duplicates:
    if len( serial_numbers ) > 1:
        serial_numbers = dict.keys(dict.fromkeys(serial_numbers))
    
    #Basic check of the serial number, can they be longer? Maybe.
    for number in serial_numbers:
        if len( number ) != 7:
            print 'Invalid serial number: %s exiting!' % (number)
            sys.exit(WARNING)
    
    #TODO: Make this async in the future
    for serial_number in serial_numbers:   
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
        result_list.append((regex.findall(response.read()), serial_number))
    
    return result_list

def parse_exit(result_list):
    import datetime
    
    critical = 0
    warning = 0
    
    for result in result_list:
        days = 0
        dates = []
        
        serial_number = result[1]
        
        if len(result[0]) == 0:
            print "Dell's database appears to be down."
            sys.exit(WARNING)
        
        for match in result[0]:
            start_date, end_date, days_left = match
            
            #This makes this plugin limited to North American style dates but
            #as long as the service tag is run through the dell.com website
            #it does not matter. (I think)
            for date in start_date, end_date:
                month, day, year = date.split('/')
                dates.append(datetime.date(int(year), int(month), int(day)))
            
            days += int(days_left)
        
        dates.sort()
        
        start_date = dates[0]
        end_date = dates[-1]
        days_left = days
        
        if days_left < options.critical_days:
            state ='CRITICAL'
            critical+= 1
            
        elif days_left < options.warning_days:
            state = 'WARNING'
            warning+= 1
            
        else:
            state = 'OK'
            
        print '| %s: Service Tag: %s Warranty start: %s End: %s Days left: %d |' \
            % (state, serial_number, start_date, end_date, days_left),
        
    if critical:
        sys.exit(CRITICAL)
    elif warning:
        sys.exit(WARNING)
    else:
        sys.exit(OK)
    
    return None #Should never get here

def sigalarm_handler(signum, frame):
    print '%s timed out after %d seconds' % (sys.argv[0], options.timeout)
    sys.exit(CRITICAL)



if __name__ == '__main__':
    import optparse
    import signal

    parser = optparse.OptionParser(description='''Nagios plug-in to pull the \
Dell service tag and check it against Dell's web site to see how many \
days remain. By default it issues a warning when there is less than \
thirty days remaining and critical when there is less than ten days \
remaining. These values can be adjusted using the command line, see --help.
    ''',
                                   prog="check_dell_warranty",
                                   version="%prog Version: 1.5")
    parser.add_option('-c', '--critical', dest='critical_days', default=10,
                     help='Number of days under which to return critical \
                     (Default: %default)', type='int', metavar='<ARG>')
    parser.add_option('-s', '--serial-number', dest='serial_number', 
                       help='Dell Service Tag of system, to enter more than \
                      one use multiple flags (Default: auto-detected)',  
                      action='append', metavar='<ARG>')
    parser.add_option('-t', '--timeout', dest='timeout', default=10,
                      help='Set the timeout for the program to run \
                      (Default: %default seconds)', type='int', metavar='<ARG>')
    parser.add_option('-w', '--warning', dest='warning_days', default=30,
                      help='Number of days under which to return a warning \
                      (Default: %default)', type='int', metavar='<ARG>' )
    
    (options, args) = parser.parse_args()
        
    signal.signal(signal.SIGALRM, sigalarm_handler)
    signal.alarm(options.timeout)
    
    if options.serial_number:
        serial_numbers = options.serial_number
    else:
        serial_numbers = extract_serial_number()
    
    result = get_warranty(serial_numbers)
    
    signal.alarm(0)
    
    parse_exit(result)