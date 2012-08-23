#!/usr/bin/env python
'''
Nagios plug-in to pull the Dell service tag and check it 
against Dell's web site to see how many days remain. By default it 
issues a warning when there is less than thirty days remaining and critical 
when there is less than ten days remaining. These values can be adjusted 
using the command line, see --help.

                                                 
Version: 3.0                                                                
Created: 2009-02-12                                                         
Author: Erinn Looney-Triggs                                                 
Revised: 2010-08-18                                                                
Revised by: Erinn Looney-Triggs, Justin Ellison, Harald Jensas
'''

#=============================================================================
# TODO: omreport md enclosures, cap the threads, tests, more I suppose
#
# Revision history:
#
# 2010-04-13 2.1.1: Change to deal with Dell's change to their web site
# dropping the warranty extension field.
#
# 2009-12-17 2.1: Change format back to % to be compatible with python 2.4
# and older.
#
# 2009-11-16 2.0: Fix formatting issues, change some variable names, fix 
# a file open exception issue, Dell changed the interface so updated to 
# work with that, new option --short for short output.
#
# 2009-08-07 1.9: Add smbios as a way to get the serial number. 
# Move away from old string formatting to new string formatting.
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

import logging
import os
import sys


__author__ = 'Erinn Looney-Triggs'
__credits__ = ['Erinn Looney-Triggs', 'Justin Ellison', 'Harald Jensas' ]
__license__ = 'GPL 3.0'
__maintainer__ = 'Erinn Looney-Triggs'
__email__ = 'erinn.looneytriggs@gmail.com'
__version__ = 3.0
__status__ = 'Production'

#Nagios exit codes in English
UNKNOWN  = 3
CRITICAL = 2
WARNING  = 1
OK       = 0


    
def extract_mtk_community():
    # Get SNMP community string from /etc/mtk.conf

    mtk_conf_file = '/etc/mtk.conf'
    
    if os.path.isfile(mtk_conf_file):
        try:
            conf_file = open(mtk_conf_file, 'r')
        except IOError:
            print 'Unable to open %s, exiting!' % (mtk_conf_file)
            sys.exit(UNKNOWN)
            
            #Iterate over the file and search for the community_string   
        for line in conf_file:
            token = line.split('=')
            if token[0] == 'community_string':
                community_string = token[1].strip()
            conf_file.close()
    else:
        print ('The %s file does not exist, '
               'exiting!') % (mtk_conf_file)
        sys.exit(UNKNOWN)
        
    return community_string

def extract_serial_number():
    '''Extracts the serial number from the localhost using (in order of
    precedence) omreport, libsmbios, or dmidecode. This function takes 
    no arguments but expects omreport, libsmbios or dmidecode to exist 
    and also expects dmidecode to accept -s system-serial-number 
    (RHEL5 or later).
    
    '''
    
    dmidecode = which('dmidecode')
    libsmbios = False
    omreport  = which('omreport')
    serial_numbers = []
    
    #Test for the libsmbios module
    try:
        logger.debug('Attempting to load libsmbios_c.')
        import libsmbios_c
    except ImportError:
        logger.debug('Unable to load libsmbios_c continuing.')
        pass                #Module does not exist, move on
    else:
        libsmbios = True
    
    if omreport:
        import subprocess
        import re
        
        try:
            process = subprocess.Popen([omreport, "chassis", "info",
                                         "-fmt", "xml"],
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
        except OSError:
            print 'Error: {0} exiting!'.format(sys.exc_info)
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
        import subprocess 
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
            print 'Error: {0} exiting!'.format(sys.exc_info)
            sys.exit(WARNING)
        serial_numbers.append(process.stdout.read().strip())
        
    else:
        print ('Omreport, libsmbios and dmidecode are not available in '
        '$PATH, exiting!')
        sys.exit(WARNING)
    
    return serial_numbers

def extract_serial_number_snmp( options ):
    '''
    Extracts the serial number from the a remote host using SNMP.
    This function takes the following arguments: hostname, community, 
    and mtk. The mtk argument will make the plug-in read the SNMP 
    community string from /etc/mtk.conf. (/etc/mtk.conf is used by 
    the mtk-nagios plugin. 
    (mtk-nagios plug-in: http://www.hpccommunity.org/sysmgmt/)
    '''
    try:
        import netsnmp
    except ImportError:
        print "Unable to load netsnmp python module, aborting!"
        sys.exit(UNKNOWN)
    
    serial_numbers = []
    hostname = options.hostname
    port = options.port
    version = options.version           
    
    if version == 3:
        sec_level = options.secLevel
        sec_name = options.secName
        priv_protocol = options.privProtocol
        priv_password = options.privPassword
        auth_protocol = options.authProtocol
        auth_password = options.authPassword
        
        session = netsnmp.Session(DestHost=hostname, Version=version, 
                                  SecLevel=sec_level, SecName=sec_name, 
                                  AuthProto=auth_protocol, 
                                  AuthPass=auth_password,
                                  PrivProto=priv_protocol,
                                  PrivPass=priv_password,
                                  RemotePort = port,
                                  )
        
    elif version == 2 or version == 1:
        community = options.community
        
        session = netsnmp.Session(DestHost=hostname, Version=version,
                                  Community=community, RemotePort=port)
        
    else:
        print 'Unknown SNMP version {0}, exiting!'.format(version)
    

    def _autodetect_dell_device(session):
        
        logger.debug('Beginning auto detection of system type.')
        
        var = netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises', 
                                              '.674.'))
        session.getnext(var)
        tag = var.varbinds.pop().tag
    
        if tag.find('enterprises.674.10892.1.') != -1: 
            sys_type = 'omsa'          #OMSA answered.
        elif tag.find('enterprises.674.10892.2.') != -1: 
            sys_type = 'RAC'           #Blade CMC or Server DRAC answered.
        elif tag.find('enterprises.674.10895.')  != -1:  
            sys_type = 'powerconnect'  #PowerConnect switch answered. 
        else:
            print ('snmpgetnext Failed:{0} System type or system '
                   'unknown!').format(tag)
            sys.exit(WARNING)
        
        logger.debug('System type is: {0}'.format(sys_type))
        
        return sys_type
        
    system_type = _autodetect_dell_device(session)
    
    #System is server with OMSA, will check for External DAS enclosure 
    #and get service tag.    
    if system_type == 'omsa':
        
        #Is External DAS Storage Enclosure connected?
        var = netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises',
                                              '.674.10893.1.20.130.3.1.1'))
        enclosure_ids = session.walk(var)
        
        logger.debug('Enclosure IDs: {0}'.format(enclosure_ids))
        
        for enclosure_id in enclosure_ids:
            
            #For backwards compatibility with OM 5.3
            if not enclosure_id: continue
            
            var = netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises',
                                                  '.674.10893.1.20.130.3.1.16.{0}'.format(enclosure_id)))
            
            enclosure_type = session.get(var)[0]
            
            logger.debug('Enclosure type: {0}'.format(enclosure_type))
            
            if enclosure_type != '1': #Enclosure type 1 is integrated backplane.
                
                #Get storage enclosure Service Tag.
                var =  netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises',
                                                       '.674.10893.1.20.130.3.1.8.{0}'.format(enclosure_id)))
                enclosure_serial_number = session.get(var)[0]
                
                logger.debug('Enclosure Serial Number obtained: {0}'
                              .format(enclosure_serial_number))
                
                serial_numbers.append(enclosure_serial_number)
                
        #Get system Service Tag.
        var = netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises',
                                              '.674.10892.1.300.10.1.11.1'))
        
        serial_number = session.get(var)[0]
    
    elif system_type == 'RAC':
        var = netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises',
                                              '.674.10892.2.1.1.11.0'))
        serial_number = session.get(var)[0]
        
        logger.debug('RAC serial number obtained: {0}'.format(serial_number))
    
    elif system_type == 'powerconnect':
        var = netsnmp.VarList(netsnmp.Varbind('SNMPv2-SMI::enterprises',
                                              '.674.10895.3000.1.2.100'
                                              '.8.1.4.1'))
        serial_number = session.get(var)[0]
        
        logger.debug('PowerConnect serial number obtained: {0}'
                      .format(serial_number))
    
    serial_numbers.append(serial_number)
    
    logger.debug('Serial numbers obtained: {0}'.format(serial_numbers))
    
    return serial_numbers

#            
#            #Get enclosure type.
#            #   1: Internal
#            #   2: DellTM PowerVaultTM 200S (PowerVault 201S)
#            #   3: Dell PowerVault 210S (PowerVault 211S)
#            #   4: Dell PowerVault 220S (PowerVault 221S)
#            #   5: Dell PowerVault 660F
#            #   6: Dell PowerVault 224F
#            #   7: Dell PowerVault 660F/PowerVault 224F
#            #   8: Dell MD1000
#            #   9: Dell MD1120


def get_warranty(serial_numbers):
    '''
    Obtains the warranty information from Dell's website. This function 
    expects a list containing one or more serial numbers to be checked
    against Dell's database.
    '''
    
    import cookielib
    import re
    import thread
    import time
    import urllib2
    
    thread_id = 0
    result_list = []
    list_write_mutex = thread.allocate_lock()
    exit_mutexes = [0] * len(serial_numbers)
    
    #The URL to Dell's site
    dell_url = ('https://www.dell.com/support/troubleshooting/us/en/04/'
                'TroubleShooting/Display_Warranty_Tab?name='
                'TroubleShooting_WarrantyTab')
    
    pattern = r"""(                         #Capture
                  <table                    #Beginning of table
                  .*?                       #Non-greedy match
                  class="uif_table.*?"         #Get the right table
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
        
        logger.debug('Thread ID: {0}, beginning connection to '
                     'website.'.format(thread_id))
        #Build the cookie configuration
        urlopen = urllib2.urlopen
        cj = cookielib.CookieJar()
        Request = urllib2.Request
        
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        urllib2.install_opener(opener)
        
        logger.debug('Thread ID: {0}, building cookie.'.format(thread_id))
        
        #Build the cookie
        cookie = cookielib.Cookie(version=0, name='OLRProduct', 
                                  value='OLRProduct=' + serial_number + '|',
                                  port=None, port_specified=False, 
                                  domain='.dell.com', 
                                  domain_specified=True, 
                                  domain_initial_dot=True, path='/', 
                                  path_specified=True, secure=False, 
                                  expires=None, discard=True, comment=None, 
                                  comment_url=None, rest={'HttpOnly': None})
        cj.set_cookie(cookie)
        
        logger.debug('Thread ID: {0}, cookie created with value: '
                     '{1}.'.format(thread_id, cookie.value))
        
        txdata = None
        txheaders =  {'User-agent' : 
                      'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)'}
        
        #Basic check of the serial number.
        if len( serial_number ) != 7 and len( serial_number ) != 5:
            print 'Invalid serial number: %s exiting!' % (serial_number)
            sys.exit(WARNING)
        
        #Try to open the page, exit on failure
        try:
            logger.debug('Thread ID: {0}, requesting data from URL: {1},'
                         ' with headers {2}.'.format(thread_id, dell_url, 
                                                     txheaders))
            req = Request(dell_url, txdata, txheaders)
            response = urlopen(req)
        except urllib2.URLError, error:
            if hasattr(error, 'reason'):
                print ('Unable to open URL: '
                       '%s exiting! %s') % (dell_url, error.reason)
                sys.exit(UNKNOWN)
            elif hasattr(error, 'code'):
                print ('The server is unable to fulfill '
                'the request, error: %s') % (error.code)
                sys.exit(UNKNOWN)  
        
        #Just to be tidy
        cj.clear()
        
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
    
    logger.debug('Number of results obtained from Dell web site: '
                 '{0}'.format(len(result_list)))
    
    return result_list


def parse_exit(result_list, short_output=False):
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
        full_line = r'%s: Service Tag: %s' 
        
        if len(result[0]) == 0:
            print "Dell's database appears to be down."
            sys.exit(WARNING)
        
        for match in result[0]:
            
            #Because there can be multiple warranties for one system we get
            #them all
            warranties = parse_table(match)
            
            for entry in warranties:
                (description, provider, start_date, end_date, 
                 days_left) = entry[0:5]
                 
                
                #Convert the dates to international standard
                start_date = str(i8n_date(start_date))
                end_date   = str(i8n_date(end_date))
                
                if short_output:
                    full_line = full_line + ', End: ' + end_date \
                    + ', Days left: ' + days_left
                    
                else: 
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
            
        print full_line % (state, serial_number),
        
    if critical:
        sys.exit(CRITICAL)
    elif warning:
        sys.exit(WARNING)
    else:
        sys.exit(OK)
    
    return None #Should never get here

def sigalarm_handler(signum, frame):
    '''
    Handler for an alarm situation.
    '''
    
    print ('%s timed out after %s seconds, '
           'signum:%s, frame: %s') % (sys.argv[0], options.timeout, 
                                            signum, frame)
    
    sys.exit(CRITICAL)
    return None

def which(program):
    '''This is the equivalent of the 'which' BASH built-in with a check to 
    make sure the program that is found is executable.
    '''
    
    def is_exe(file_path):
        '''Tests that a file exists and is executable.
        '''
        return os.path.exists(file_path) and os.access(file_path, os.X_OK)
    
    file_path = os.path.split(program)[0]
    
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
                                   version="%prog Version: 3.0")
    parser.add_option('-a', dest='authProtocol', action='store',
                      help=('Set the default authentication protocol for '
                            'SNMPv3 (MD5 or SHA).'))
    parser.add_option('-A', dest='authPassword', 
                      help=('Set the SNMPv3 authentication protocol password.')
                      )
    parser.add_option('-C', '--community', action='store', 
                      dest='community', type='string',default='public', 
                      help=('SNMP Community String to use. '
                      '(Default: %default)'))
    parser.add_option('-c', '--critical', dest='critical_days', default=10,
                     help=('Number of days under which to return critical '
                     '(Default: %default).'), type='int', metavar='<ARG>')
    parser.add_option('-H', '--hostname', action='store', type='string', 
                      dest='hostname', 
                      help='Specify hostname for SNMP')
    parser.add_option('-l', dest='secLevel', default='noAuthNoPriv',
                      action='store',
                      help=('Set the SNMPv3 security level, (noAuthNoPriv'
                      '|authNoPriv|authPriv) (Default: noAuthNoPriv)'))
    parser.add_option('--mtk', action='store_true', dest='mtk_installed', 
                      default=False,
                      help=('Get SNMP Community String from /etc/mtk.conf if '
                      'mtk-nagios plugin is installed. NOTE: This option '
                      'will make the mtk.conf community string take '
                      'precedence over anything entered at the '
                      'command line (Default: %default)'))
    parser.add_option('-p', '--port', dest='port', default=161,
                      help=('Set the SNMP port to be connected to '
                      '(Default:161).'), type='int')
    parser.add_option('-s', '--serial-number', dest='serial_number', 
                       help=('Dell Service Tag of system, to enter more than '
                      'one use multiple flags (Default: auto-detected)'),  
                      action='append', metavar='<ARG>')
    parser.add_option('-S', '--short', dest='short_output', 
                      action='store_true', default = False,
                      help=('Display short output: only the status, '
                      'service tag, end date and days left for each '
                      'warranty.'))
    parser.add_option('-t', '--timeout', dest='timeout', default=10,
                      help=('Set the timeout for the program to run '
                      '(Default: %default seconds)'), type='int', 
                      metavar='<ARG>')
    parser.add_option('-u', dest='secName', action='store',
                      help='Set the SNMPv3 security name (user name).')
    parser.add_option('-v', dest='version', default=3, action='store',
                      help=('Specify the SNMP version (1, 2c, 3) Default: 3'),
                      type='int'
                      )
    parser.add_option('-V', dest='verbose', action='store_true', 
                      default=False, help =('Give verbose output (Default: '
                                            'Off)') 
                      )
    parser.add_option('-w', '--warning', dest='warning_days', default=30,
                      help=('Number of days under which to return a warning '
                      '(Default: %default)'), type='int', metavar='<ARG>' )
    parser.add_option('-x', dest='privProtocol', action='store',
                      help='Set the SNMPv3 privacy protocol (DES or AES).')
    parser.add_option('-X', dest='privPassword', action='store',
                      help='Set the SNMPv3 privacy pass phrase.')
    
    (options, args) = parser.parse_args()
    
    ##Configure logging
    logger = logging.getLogger("check_dell_warranty")
    handler = logging.StreamHandler()
    if options.verbose:
        handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        
    ##Set the logging format, time, log level name, and the message
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)

    signal.signal(signal.SIGALRM, sigalarm_handler)
    signal.alarm(options.timeout)
    
    if options.serial_number:
        SERIAL_NUMBERS = options.serial_number
    elif options.hostname or options.mtk_installed:
        SERIAL_NUMBERS = extract_serial_number_snmp(options)
    else:
        SERIAL_NUMBERS = extract_serial_number()
    
    RESULT = get_warranty(SERIAL_NUMBERS)
    
    signal.alarm(0)
    
    parse_exit(RESULT, options.short_output)

