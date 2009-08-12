#!/usr/bin/env python

#=============================================================================
# Nagios plug-in to pull the Dell service tag and check it 
# against Dell's web site to see how many days remain. By default it 
# issues a warning when there is less than thirty days remaining and critical 
# when there is less than ten days remaining. These values can be adjusted 
# using the command line, see --help.                                                 
# Version: 1.9                                                                
# Created: 2009-02-12                                                         
# Author: Erinn Looney-Triggs                                                 
# Revised: 2009-08-12                                                                
# Revised by: Erinn Looney-Triggs, Justin Ellison, Harald Jensas
#
# TODO: different output to screen, omreport md enclosures, use pysnmp or
# net-snmp, cap the threads, tests, more I suppose
#
# Revision history:
#
# 2009-08-07 1.9: Pretty output to screen versus nagios, add pysmbios
# as a way to get the serial number. Move away from old string formatting
# to new string formatting.
#
# 2009-08-04 1.8: Improved the parsing of Dell's website, output is now much
# more complete (read larger) and includes all warranties. Thresholds are
# measured against the warranty with the greatest number of days remaining.
# This fixes the bug with doubled or even tripled warranty days being 
# reported.
#
# 2009-07-24 1.7: SNMP support, DRAC - Remote Access Controller, CMC - 
# Chassis Management Controller and MD/PV Disk Enclosure support.
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
    precedence) omreport, libsmbios, or dmidecode.This function takes 
    no arguments but expects omreport, libsmbios or dmidecode to exist 
    and also expects dmidecode to accept -s system-serial-number 
    (RHEL5 or later).
    
    '''
    import os
    import subprocess
    
    dmidecode = which('dmidecode')
    libsmbios = False
    omreport  = which('omreport')
    serial_numbers = []
    
    #Test for the libsmbios module
    try:
        import libsmbios_c
    except ImportError:
        pass                #Module does not exist, move on
    finally:
        libsmbios = True

    if omreport:
        import re
        
        try:
            process = subprocess.Popen([omreport, "chassis", "info",
                                         "-fmt", "xml"],
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
        except OSError:
            print 'Error:', sys.exc_value, 'exiting!'
            sys.exit(WARNING)
            
        text = process.stdout.read()
        pattern = '''<ServiceTag>(\S+)</ServiceTag>'''
        regex = re.compile(pattern, re.X)
        serial_numbers = regex.findall(text)
        
    elif libsmbios:
        #You have to be root to extract the serial number via this method
        if os.geteuid() != 0: 
            print ('{0} must be run as root in order to access '
            'libsmbios, exiting!').format(sys.argv[0])
            sys.exit(WARNING)
        
        serial_numbers.append(libsmbios_c.system_info.get_service_tag())
           
    elif dmidecode: 
        #Gather the information from dmidecode
        
        sudo = which('sudo')
        
        if not sudo:
            print 'Sudo is not available, exiting!'
            sys.exit(WARNING)
        
        try:
            process = subprocess.Popen([sudo, dmidecode, "-s",
                                   "system-serial-number"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
        except OSError:
            print 'Error:', sys.exc_value, 'exiting!'
            sys.exit(WARNING)
        serial_numbers.append(process.stdout.read().strip())
        
    else:
        print ('Omreport, libsmbios and dmidecode are not available in '
        '$PATH, exiting!')
        sys.exit(WARNING)
    
    return serial_numbers

def extract_serial_number_snmp( hostname, community_string='public', 
                                mtk_installed=False ):
    '''Extracts the serial number from the a remote host using SNMP.
    This function takes the following arguments: community, hostname 
    and mtk. The mtk argument will make the plug-in read the SNMP 
    community string from /etc/mtk.conf. (/etc/mtk.conf is used by 
    the mtk-nagios plugin. 
    (mtk-nagios plug-in: http://www.hpccommunity.org/sysmgmt/)
    '''

    def run_snmp_command(snmp_cmd, cmdline, hostname, community_string, 
                         encl_id=None):
        '''Runs the command specified in snmp_cmd and collects the 
        output, the output is then sanitized to be passed back to 
        the requester.
        '''
        
        if encl_id: 
            cmdline = cmdline.format(snmp_cmd, 
                                     community_string, hostname, encl_id)
        else: 
            cmdline = cmdline.format(snmp_cmd, community_string, hostname)
        
        try:
            p = subprocess.Popen(cmdline, shell=True, 
                                 stdout = subprocess.PIPE, 
                                 stderr = subprocess.STDOUT)
        except OSError:
            print 'Error:', sys.exc_value, 'exiting!'
            sys.exit(WARNING) 
        
        #This is where we sanitize the output gathered.
        output = p.stdout.read()
       
        #Things we don't want in the strings:
        replacement_strings = {'"':'', 'STRING: ':'', 'INTEGER: ':'' }
        
        #Strip them out:
        for old, new in replacement_strings.iteritems():
            output = output.replace(old, new).strip()
        
        #This output should be clean now.
        return output
    
    
    import subprocess
    import os
    
    serial_numbers = []
    snmpget = which('snmpget')
    snmpgetnext = which('snmpgetnext')
    snmpwalk = which('snmpwalk')
    
    #Test that we actually have snmpget, snmpgetnext and snmpwalk installed 
    if not snmpget:
        print 'Unable to locate snmpget, exiting!'
        sys.exit(UNKNOWN)
    if not snmpgetnext:
        print 'Unable to locate snmpgetnext, exiting!'
        sys.exit(UNKNOWN)
    if not snmpwalk:
        print 'Unable to locate snmpwalk, exiting!'
        sys.exit(UNKNOWN)

    # Get SNMP community string from /etc/mtk.conf
    if mtk_installed:
        mtk_conf_file = '/etc/mtk.conf'
        
        if os.path.isfile(mtk_conf_file):
            try:
                conf_file = open(mtk_conf_file, 'r')
            except:
                print 'Unable to open {0}, exiting!'.format(mtk_conf_file)
                sys.exit(UNKNOWN)
                
                #Iterate over the file and search for the community_string   
            for line in conf_file:
                token = line.split('=')
                if token[0] == 'community_string':
                    community_string = token[1].strip()
                conf_file.close()
        else:
            print ('The {0} file does not exist, '
                   'exiting!').format(mtk_conf_file)
            sys.exit(UNKNOWN)
                
    
    #SnmpGetNext - Get next OID in Dell tree to decide device type
    cmdline_snmpgetnext          = ('{0} -v1 -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674') 
    #SnmpWalk - Get storage enclosure ID's
    cmdline_get_stor_encl        = ('{0} -v1 -Ov -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674.'
                                    '10893.1.20.130.3.1.1') 
    #SnmpGet - Get storage enclosure type's
    cmdline_get_stor_encl_type   = ('{0} -v1 -Ov -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674.'
                                    '10893.1.20.130.3.1.16.{3}') 
    #SnmpGet - Get storage enclosure serial number
    cmdline_get_stor_encl_serial = ('{0} -v1 -Ov -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674.'
                                    '10893.1.20.130.3.1.8.{3}') 
    #SnmpGet - Get server serial number (OMSA)
    cmdline_get_server_serial    = ('{0} -v1 -Ov -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674.'
                                    '10892.1.300.10.1.11.1') 
    #SnmpGet - Get server/blade chassis serial number (RAC)
    cmdline_get_rac_serial       = ('{0} -v1 -Ov -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674.'
                                    '10892.2.1.1.11.0') 
    #SnmpGet - Get PowerConnect switch serial number
    cmdline_get_pc_serial        = ('{0} -v1 -Ov -c {1} {2} '
                                    'SNMPv2-SMI::enterprises.674.'
                                    '10895.3000.1.2.100.8.1.4.1') 


    
    #Figure out device type OMSA on Server, DRAC/CMC or PowerConnect Switch
    snmp_out = run_snmp_command(snmpgetnext, cmdline_snmpgetnext, 
                                hostname, community_string)
    
    if snmp_out.find('SNMPv2-SMI::enterprises.674.10892.1.') != -1: 
        sysType = 'omsa'          #OMSA answered.
    elif snmp_out.find('SNMPv2-SMI::enterprises.674.10892.2.') != -1: 
        sysType = 'RAC'           #Blade CMC or Server DRAC answered.
    elif snmp_out.find('SNMPv2-SMI::enterprises.674.10895.')  != -1:  
        sysType = 'powerconnect'  #PowerConnect switch answered. 
    else:
        print ('snmpgetnext Failed: {0} System '
               'type or system unknown!').format(snmp_out)
        sys.exit(WARNING)

    #System is server with OMSA, will check for External DAS enclosure 
    #and get service tag.
    if sysType == 'omsa':
    
        #Is External DAS Storage Enclosure connected
        #TODO: get rid of the split()
        snmp_out = run_snmp_command(snmpwalk, cmdline_get_stor_encl,
                                hostname, community_string).split('\n')
        
        for encl_id in snmp_out:
            #Get enclosure type.
            #   1: Internal
            #   2: DellTM PowerVaultTM 200S (PowerVault 201S)
            #   3: Dell PowerVault 210S (PowerVault 211S)
            #   4: Dell PowerVault 220S (PowerVault 221S)
            #   5: Dell PowerVault 660F
            #   6: Dell PowerVault 224F
            #   7: Dell PowerVault 660F/PowerVault 224F
            #   8: Dell MD1000
            #   9: Dell MD1120
            encl_type = run_snmp_command(snmpget, cmdline_get_stor_encl_type,
                                      hostname, community_string, 
                                      encl_id)
                              
            if encl_type != '1':  #Enclosure type 1 is integrated backplane.
                #Get storage enclosure Service Tag.
                encl_serial_number = run_snmp_command(snmpget, 
                                                      cmdline_get_stor_encl_serial, 
                                                      hostname, 
                                                      community_string, 
                                                      encl_id)
                serial_numbers.append(encl_serial_number)

        #Get system Service Tag.
        serial_number = run_snmp_command(snmpget, cmdline_get_server_serial, 
                                        hostname, community_string)

    # Get DRAC/CMC or PowerConnect Service Tag.
    elif sysType == 'RAC':
        serial_number = run_snmp_command(snmpget, cmdline_get_rac_serial, 
                                         hostname, community_string)
                              
    elif sysType == 'powerconnect':
        serial_number = run_snmp_command(snmpget, cmdline_get_pc_serial, 
                                         hostname, community_string)
    
    serial_numbers.append(serial_number)

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
    dell_url = 'http://support.dell.com/support/topics/global.aspx/support/' \
    + 'my_systems_info/details?c=us&l=en&s=gen&ServiceTag='
    
    pattern = r"""(                         #Capture
                  <table                    #Beginning of table
                  .*?                       #Non-greedy match
                  class="contract_table"    #Get the right table
                  .*?                       #Non-greedy match
                  </table>)"""              #Closing tag
                              
    regex = re.compile(pattern, re.X)
    
    def fetch_result(thread_id, serial_number, dell_url, regex):
        '''Opens a connection to Dell's website and fetches the output
        of the page using the regex that is passed in. This function
        expects to be used in a threaded setup as such it requires 
        a thread id. In addition the serial number to be used needs to be
        passed as well as the url and the regex to pull the info.
        '''
        
        #Basic check of the serial number.
        if len( serial_number ) != 7 and len( serial_number ) != 5:
            print 'Invalid serial number: {0} exiting!'.format(serial_number)
            sys.exit(WARNING)
               
        #Build the full URL
        full_url = dell_url + serial_number
        
        #Try to open the page, exit on failure
        try:
            response = urllib2.urlopen(full_url)
        except URLError, error:
            if hasattr(error, 'reason'):
                print ('Unable to open URL: '
                       '{0} exiting! {1}').format(full_url, error.reason)
                sys.exit(UNKNOWN)
            elif hasattr(error, 'code'):
                print ('The server is unable to fulfill '
                'the request, error: {0}').format(error.code)
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
        thread.start_new(fetch_result, (thread_id, serial_number, 
                                        dell_url, regex))
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
    import re
    
    critical = 0
    warning  = 0
    
    def i8n_date(date):
        ''' Simple function that takes a North American style date string
        seperated by '/'s and converts it to ISO standard date format
        of yyy-mm-dd and returns it.
        '''
        
        month, day, year = date.split('/')
        return datetime.date(int(year), int(month), int(day))
        
    def parse_table(table):
        '''Takes an HTML string of a table and returns a list of lists of
        the contents of the table.
        '''
        
        results = []
        
        row_pattern     = """<tr>(.*?)</tr>"""
        table_pattern   = """<td.*?>(.*?)</td>"""
        row_regex       = re.compile(row_pattern)
        table_regex     = re.compile(table_pattern)
        
        #Pull the rows out
        rows = row_regex.findall(table)
        for row in rows:
            row_list = []
            tables = table_regex.findall(row)
            
            #Clean the tables
            for table in tables:
                row_list.append(re.sub(r'<[^>]*?>', '', table))
            
            results.append(row_list)
        
        return results
    
    
    for result in result_list:
        days = []
        
        serial_number = result[1]

        #We start to build our output line
        full_line = r'{0}: Service Tag: {1}' 
        
        if len(result[0]) == 0:
            print "Dell's database appears to be down."
            sys.exit(WARNING)
        
        for match in result[0]:
            
            #Because there can be multiple warranties for one system we get
            #them all
            warranties = parse_table(match)
           
            #Remove the header lines. 
            warranties.pop(0)
            
            for entry in warranties:
                (description, provider, start_date, end_date, 
                 days_left) = entry[0:5]
                
                #Convert the dates to international standard
                start_date = str(i8n_date(start_date))
                end_date   = str(i8n_date(end_date))
                
                full_line = full_line + ' Warranty: ' + description \
                + ', Provider: ' + provider + ', Start: ' + start_date \
                + ', End: ' + end_date + ', Days left: ' + days_left
                
                days.append(int(days_left))
        
        #Put the days remaining in ascending order
        days.sort()
        
        if days[-1] < options.critical_days:
            state = 'CRITICAL'
            critical += 1
            
        elif days[-1] < options.warning_days:
            state = 'WARNING'
            warning += 1
            
        else:
            state = 'OK'
            
        print full_line.format(state, serial_number ),
        
    if critical:
        sys.exit(CRITICAL)
    elif warning:
        sys.exit(WARNING)
    else:
        sys.exit(OK)
    
    return None #Should never get here

def sigalarm_handler(signum, frame):
    '''Handler for an alarm situation.'''
    
    print '{0} timed out after {1} seconds'.format(sys.argv[0], options.timeout)
    sys.exit(CRITICAL)
    
def which(program):
    '''This is the equivlant of the 'which' BASH builtin with a check to 
    make sure the program that is found is executable.
    '''
    
    import os
    
    def is_exe(file_path):
        '''Tests that a file exists and is executable.
        '''
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

    parser = optparse.OptionParser(description='''Nagios plug-in to pull the 
Dell service tag and check it against Dell's web site to see how many 
days remain. By default it issues a warning when there is less than 
thirty days remaining and critical when there is less than ten days 
remaining. These values can be adjusted using the command line, see --help.
''',
                                   prog="check_dell_warranty",
                                   version="%prog Version: 1.9")
    parser.add_option('-C', '--community', action='store', 
                      dest='community_string', type='string',default='public', 
                      help=('SNMP Community String to use. '
                      '(Default: %default)'))
    parser.add_option('-c', '--critical', dest='critical_days', default=10,
                     help=('Number of days under which to return critical '
                     '(Default: %default)'), type='int', metavar='<ARG>')
    parser.add_option('-H', '--hostname', action='store', type='string', 
                      dest='hostname', 
                      help='Specify hostname for SNMP')
    parser.add_option('--mtk', action='store_true', dest='mtk_installed', 
                      default=False,
                      help=('Get SNMP Community String from /etc/mtk.conf if '
                      'mtk-nagios plugin is installed. NOTE: This option '
                      'will make the mtk.conf community string take '
                      'precedence over anything entered at the '
                      'command line (Default: %default)'))
    parser.add_option('-s', '--serial-number', dest='serial_number', 
                       help=('Dell Service Tag of system, to enter more than '
                      'one use multiple flags (Default: auto-detected)'),  
                      action='append', metavar='<ARG>')
    parser.add_option('-t', '--timeout', dest='timeout', default=10,
                      help=('Set the timeout for the program to run '
                      '(Default: %default seconds)'), type='int', 
                      metavar='<ARG>')
    parser.add_option('-w', '--warning', dest='warning_days', default=30,
                      help=('Number of days under which to return a warning '
                      '(Default: %default)'), type='int', metavar='<ARG>' )
    
    (options, args) = parser.parse_args()
        
    signal.signal(signal.SIGALRM, sigalarm_handler)
    signal.alarm(options.timeout)
    
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
