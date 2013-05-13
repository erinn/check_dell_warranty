'''
Created on May 2, 2013

@author: erinn
'''
import datetime
import requests

class DellWarrantyException(Exception):
    pass

class system(object):
    '''
    classdocs
    '''

    def __init__(self, ServiceTag):
        '''
        Constructor
        '''
        self.ServiceTag = ServiceTag
    
    def _check_response_faults(self, response):
        '''
        This function checks the json content for faults that are raised by 
        Dell's API. Any faults results in an exception being raised.
        '''
        
        #logger.debug('Testing for faults in json response.')
        fault = (response['GetAssetWarrantyResponse']['GetAssetWarrantyResult']
                 ['Faults'])
        #logger.debug('Raw fault return: {0}'.format(fault))
        
        if fault:
            #logger.debug('Fault found.')
            
            code = fault['FaultException']['Code']
            message = fault['FaultException']['Message']
            
            raise DellWarrantyException('API fault code: "{0}" encountered, '
                                        'message: "{1}".'.format(code, message))

        
        #logger.debug('No faults found.')
        return None

    def _convert_date(self, date):
        '''
        This function converts the date as returned by the Dell API into a 
        datetime object. Dell's API format is as follows: 2010-07-01T01:00:00
        '''
        #Split on 'T' grab the date then split it out on '-'
        year, month, day = date.split('T')[0].split('-')
        
        return datetime.date(int(year), int(month), int(day))
    
    def get(self, timeout=30):
        '''
        Obtains the warranty information from Dell's website. This function 
        expects a list containing one or more serial numbers to be checked
        against Dell's database.
        '''
        
        xml_url = 'https://api.dell.com/support/v2/assetinfo/warranty/tags'
        json_url = xml_url + '.json'
        
        #Additional API keys, just in case: 
        #d676cf6e1e0ceb8fd14e8cb69acd812d
        #849e027f476027a394edd656eaef4842
        
        apikey = '1adecee8a60444738f280aad1cd87d0e'
        
        #logger.debug('Requesting service tags: {0}'.format(service_tags))
        
        payload = {'svctags': self.ServiceTag, 'apikey': apikey}
        
        #logger.debug('Requesting warranty information from Dell url: '
        #             '{0}'.format(response.url))
        
        self._json_reponse = self._get_https(json_url, payload, timeout)
        
        #We check for faults raised by the API, this raises a 
        #DellWarrantyException when a fault is encountered, accepts json only
        self._check_response_faults(self._json_reponse.json())
        
        self._parse_json_response(self._json_reponse.json())
        #logger.debug('Raw output received: \n {0}'.format(result))
        self._xml_response = self._get_https(xml_url, payload, timeout)
        
        #We test for any faults asserted by the api.
        #check_faults(result)
        
        return None
    
    def _get_https(self, url, payload, timeout):
        
        response = requests.get(url, params=payload, verify=False, 
                                timeout=timeout)
        
        #Raise requests.exceptions.HTTPError if return is anything but 200
        response.raise_for_status()

        
        return response
    
    def _parse_json_response(self, response):
        '''
        Method to parse out the details we want to use an return.
        '''
        
        #Strip out the unneeded information.
        response = (response['GetAssetWarrantyResponse']
                    ['GetAssetWarrantyResult']['Response']['DellAsset'])
        
        self.MachineDescription = response['MachineDescription']
        self.OrderNumber = response['OrderNumber']
        self.ShipDate = response['ShipDate']
        self.Warranties = response['Warranties']['Warranty']
         
    def json(self):
        
        return self._json_reponse.json()
    
    def json_raw(self):
        
        return self._json_reponse.text
    
    def type(self):
        '''
        Return the system type.
        '''
        
    
    def xml_etree(self):
        from xml.etree import cElementTree as et
        
        return et.fromstring(self._xml_response.text)
    
    def xml_raw(self):
        return self._xml_response.text