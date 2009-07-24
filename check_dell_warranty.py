#!/usr/bin/env python

#=============================================================================
# Nagios plug-in to pull the Dell service tag and check it 
# against Dell's web site to see how many days remain. By default it 
# issues a warning when there is less than thirty days remaining and critical 
# when there is less than ten days remaining. These values can be adjusted 
# using the command line, see --help.                                                 
# Version: 1.6                                                                
# Created: 2009-02-12                                                         
# Author: Erinn Looney-Triggs                                                 
# Revised: 2009-07-09                                                                
# Revised by: Erinn Looney-Triggs, Justin Ellison, Harald Jensas                                                           
# Revision history:
#
# 2009-07-20 1.7: SNMP support, M1000e Blade support
#
# 2009-07-09 1.6: Threads!
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
    '''Extracts the serial number from the localhost using (in order of
    precedence) omreport or dmidecode.This function takes no arguments but 
    expects either omreport or dmidecode to exist and
    also expects dmidecode to accept -s system-serial-number (RHEL5 or later)
    
    '''
    import subprocess
    
    #Lifted straight from the Internet, can't find the site anymore if
    #I find it I will throw in appropriate thanks to the poster. 
 
    
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
        print 'Neither omreport nor dmidecode are available in $PATH, exiting!'
        sys.exit(WARNING)
    
    return serial_numbers

def extract_serial_number_snmp( hostname, community_string, mtk_installed=False ):
    '''Extracts the serial number from the a remote host using SNMP.
    This function takes the following arguments: community, hostname and mtk.
    The mtk argument will make the plug-in read the SNMP community string from  
    /etc/mtk.conf. (/etc/mtk.conf is used by the mtk-nagios plugin. 
    (mtk-nagios plug-in: http://www.hpccommunity.org/sysmgmt/)
    '''

    import subprocess
    import os

    serial_numbers = []
    snmpget = which('snmpget')
    
    #Test that we actually have snmpget installed
    if not snmpget:
        print 'Unable to locate snmpget, exiting!'
        sys.exit(UNKNOWN)
    
    # Get SNMP community string from /etc/mtk.conf
    if mtk_installed:
        mtk_conf_file='/etc/mtk.conf'
        
        if os.path.isfile(mtk_conf_file):
                try:
                    file = open(mtk_conf_file,'r')
                except:
                    print 'Unable to open %s, exiting!' % (mtk_conf_file)
                    sys.exit(UNKNOWN)
                
                #Iterate over the file and search for the community_string   
                for line in file:
                        token = line.split('=')
                        if token[0] == 'community_string':
                                community_string = token[1].strip()
                file.close()
        else:
                print 'The %s file does not exist, exiting!' % (mtk_conf_file)
                sys.exit(UNKNOWN)
    
    #This should be defined at this point, if not...
    if not community_string:
        print 'Community not defined, exiting!'
        sys.exit(UNKNOWN)
    

    #Construct the command line.
    # TODO: Find a way to pass this in that is 'nice' so the function can
    # stand alone
    if options.is_blade_m1000e:
        cmdline = ('%s -v1 -Ov -c %s %s SNMPv2-MIB::sysName.0')   
    else:
        cmdline = ('%s -v1 -Ov -c %s %s SNMPv2-SMI::enterprises.674.10892.1.300.10.1.11.1')
    
    cmdline = cmdline % (snmpget, community_string, hostname)
    
    #Run the command
    try:
        p = subprocess.Popen(cmdline, shell=True, stdout = subprocess.PIPE,
                             stderr = subprocess.STDOUT)
    except OSError:
          print 'Error:', sys.exc_value, 'exiting!'
          sys.exit(WARNING)

    #Parse through the output
    snmp_out = p.stdout.read()
    if len( snmp_out ) == 18: #7 Digit Service Tags
        snmp_out = snmp_out.replace ( 'STRING: ', '')
        snmp_out = snmp_out.replace ( '"', '')
        serial_numbers.append(snmp_out.strip())
    elif len( snmp_out ) == 16: #5 Digit Service Tags
        snmp_out = snmp_out.replace ( 'STRING:', '')
        snmp_out = snmp_out.replace ( '"', '')
        serial_numbers.append(snmp_out.strip())
    elif len( snmp_out ) == 35: #Blade sysName string is 35 chars and contain Service Tag.
        snmp_out = snmp_out.replace ( 'STRING: Dell Rack System -', '')
        serial_numbers.append(snmp_out.strip())
    else:
        print 'The snmpget command returned the following: %s     This does not look like a service tag, exiting!' % snmp_out
        sys.exit(WARNING)

    return serial_numbers

def get_warranty(serial_numbers):
    '''Obtains the warranty information from Dell's website. This function 
    expects a list containing one or more serial numbers to be checked
    against Dell's database.
    '''
    
    import re
    import thread
    import time
    import urllib2
    
    thread_id = 0
    result_list = [] #List of results
    list_write_mutex = thread.allocate_lock()
    exit_mutexes = [0] * len(serial_numbers)
    
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
    
    #Build our regex
    regex = re.compile(pattern, re.X)
    
    def fetch_result(thread_id, serial_number, dell_url, regex):
        '''Opens a connection to Dell's website and fetches the output
        of the page using the regex that is passed in. This function
        expects to be used in a threaded setup as such it requires 
        a thread id. In addition the serial number to be used needs to be
        passed as well as the url and the regex to pull the info.
        '''
        
        #Basic check of the serial number.
        #TODO: can have serial numbers with a length of five
        if len( serial_number ) != 7 and len( serial_number ) != 5:
            print 'Invalid serial number: %s exiting!' % (serial_number)
            sys.exit(WARNING)
               
        #Build the full URL
        full_url = dell_url + serial_number
        
        #Try to open the page, exit on failure
        try:
            response = urllib2.urlopen(full_url)
        except URLError, e:
            if hasattr(e, 'reason'):
                print 'Unable to open URL: %s exiting! %s' % (full_url, e.reason)
                sys.exit(UNKNOWN)
            elif hasattr(e, 'code'):
                print 'The server is unable to fulfill the request, error: %s' \
                % (e.code)
                sys.exit(UNKNOWN)  
              
        list_write_mutex.acquire()      #Acquire our lock to write to the list
        result_list.append((regex.findall(response.read()), serial_number))
        list_write_mutex.release()      #Release the lock
        
        exit_mutexes[thread_id] = 1     #Communicate that this thread is done
        
        thread.exit()                   #Not necessary, but pretty
    
    # Remove duplicates:
    if len( serial_numbers ) > 1:
        serial_numbers = dict.keys(dict.fromkeys(serial_numbers))
          
    for serial_number in serial_numbers:
        thread.start_new(fetch_result, (thread_id, serial_number, dell_url, regex))
        thread_id += 1
    
    #Check that all threads have exited
    while 0 in exit_mutexes: 
        time.sleep(.05)     #Give the CPU a break
        pass
    
    return result_list

def parse_exit(result_list):
    '''This parses the results from the get_warranty() function and outputs 
    the appropriate information.
    '''
    
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
        
        #Sort the dates and grab the first and last date
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
            
        print '%s: Service Tag: %s Warranty start: %s End: %s Days left: %d' \
            % (state, serial_number, start_date, end_date, days_left),
        
    if critical:
        sys.exit(CRITICAL)
    elif warning:
        sys.exit(WARNING)
    else:
        sys.exit(OK)
    
    return None #Should never get here

def sigalarm_handler(signum, frame):
    '''Handler for an alarm situation.
    '''
    print '%s timed out after %d seconds' % (sys.argv[0], options.timeout)
    sys.exit(CRITICAL)
    
def which(program):
    '''This is the equivlant of the 'which' BASH builtin with a check to 
    make sure the program that is found is executable.
    '''
    
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
                                   version="%prog Version: 1.7")
    parser.add_option('-C', '--community', action='store', 
                      dest='community_string', type='string',
                      default=None, 
                      help='SNMP Community String to use. (Default: %default)')
    parser.add_option('-c', '--critical', dest='critical_days', default=10,
                     help='Number of days under which to return critical \
                     (Default: %default)', type='int', metavar='<ARG>')
    parser.add_option('-H', '--hostname', action='store',type='string', 
                      dest='hostname', 
                      help='Specify hostname for SNMP')
    parser.add_option('--m1000e', action='store_true', dest='is_blade_m1000e', 
                      default=False,
                      help='Specify that device is Dell PowerEdge M1000e \
                      blade chassis, SNMP Only! (Default: %default)')
    parser.add_option('--mtk', action='store_true', dest='mtk_installed', 
                      default=False,
                      help='Get SNMP Community String from /etc/mtk.conf if \
                      mtk-nagios plugin is installed. NOTE: This option \
                      will make the mtk.conf community string take \
                      precedence over anything entered at the \
                      command line(Default: %default)')
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
    
    
    if options.is_blade_m1000e and not options.hostname:
        print 'Option --m1000e requires option -H (--hostname)'
        parser.print_help()
        sys.exit(UNKNOWN)

    if options.serial_number:
        serial_numbers = options.serial_number
    elif options.hostname or options.mtk_installed:
        serial_numbers = extract_serial_number_snmp(options.hostname,
                                                    options.community_string,
                                                    options.mtk_installed)
    else:
        serial_numbers = extract_serial_number()
    
    result = get_warranty(serial_numbers)
    
    signal.alarm(0)
    
    parse_exit(result)