'''
Created on May 2, 2013

@author: erinn
'''

import requests

class DellWarrantyException(Exception):
    pass

class warranty(object):
    '''
    classdocs
    '''

    def __init__(self, serviceTag):
        '''
        Constructor
        '''
        self.serviceTag = serviceTag
    
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

    
    def get(self):

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
        timeout = 30
        
        #logger.debug('Requesting service tags: {0}'.format(service_tags))
        
        payload = {'svctags': self.serviceTag, 'apikey': apikey}
        
        #logger.debug('Requesting warranty information from Dell url: '
        #             '{0}'.format(response.url))
        
        self._json_reponse = self._get_https(json_url, payload, timeout)
        
        #We check for faults raised by the API, this raises a 
        #DellWarrantyException when a fault is encountered, accepts json only
        self._check_response_faults(self._json_reponse.json())
        
        #logger.debug('Raw output received: \n {0}'.format(result))
        self._xml_response = self._get_https(xml_url, payload, timeout)
        
        #We test for any faults asserted by the api.
        #check_faults(result)
        
        return None
    
    def _get_https(self, url, payload, timeout):
        
        response = requests.get(url, params=payload, verify=True, 
                                timeout=timeout)
        try:
            #Throw an exception for anything but 200 response code
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            print 'Unable to contact url: {0}.format(url)'
        
        return response
    
    def json(self):
        
        return self._json_reponse.json()
    
    def json_raw(self):
        
        return self._json_reponse.text
    
    def xml_etree(self):
        from xml.etree import cElementTree as et
        
        return et.fromstring(self._xml_response.text)
    
    def xml_raw(self):
        return self._xml_response.text