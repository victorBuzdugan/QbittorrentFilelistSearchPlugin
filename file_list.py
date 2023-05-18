#VERSION: 0.10

# FileList.io search engine plugin for qBittorrent
# [ ] get search results
# [ ] parse torrent data from search results
# [ ] return to qBitTorrent data
# [ ] get search results from all pages
# [ ] implement logging

import json
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from pprint import pprint
from typing import Optional
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, build_opener

import sgmllib3
from helpers import download_file, retrieve_url

USER_AGENT: tuple = ('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15')

# region: regex patterns
# get validator key from login page 
RE_VALIDATOR = re.compile(r"(?<=name='validator' value=')(.*)(?=' \/>)")
# endregion

# region: login credentials
# enter your login data here or create a json file
credentials = {
    'username': 'your_username_here',
    'password': 'your_password_here'
}
# try to get login credentials from json file if exists
try:
    with open('credentials.json', mode='r', encoding='UTF-8') as file:
        # print(f'"{file.name}" found. Credentials loaded.')
        credentials = json.load(file)
except FileNotFoundError:
    # print(f'Credentials file not found. Using credentials from current file.')
    pass
# endregion


class file_list:
    ''' filelist.io search class. '''

    name = 'FileList'
    url = 'https://filelist.io/'
    url_dl = url + 'download.php?id='
    url_login = url + 'login.php'
    url_login_post = url + 'takelogin.php'
    url_details = url + 'details.php?id='
    supported_categories = {
        'all': '0',
        'software': '8',
        'games': '9',
        'music': '11',
        'anime': '24'
    }
    
    # initialize cookie jar
    cj = CookieJar()
    # initialize an OpenerDirector with the cookie jar attached
    session = build_opener(HTTPCookieProcessor(cj))
    session.addheaders = [USER_AGENT]

    def __init__(self):
        """ Initialize the class. """

        # create payload
        self.payload = {
            'unlock': '1',
            'returnto': '%2F',
            'validator': ''
        }
        self.payload['username'] = credentials['username']
        self.payload['password'] = credentials['password']

        # load cookies and get validator value
        login_page = self._make_request(self.url_login)
        self.payload['validator'] = re.search(RE_VALIDATOR, login_page).group()

        # encode payload to a percent-encoded ASCII text string
        # and encode to bytes
        self.payload = urlencode(self.payload).encode()

        # login
        self._login()

    
    def _login(self) -> None:
        ''' Login to filelist. 
        
        Login to filelist passing custom header,
        cookie with session id from cookie jar and
        username, password and validator from encoded payload.
        '''
        a = self._make_request(self.url_login_post, data=self.payload)
        pprint(a)

    def _make_request(self, url: str, data=None) -> Optional[str]:
        ''' GET and POST to 'url'.
        
        If 'data' is passed results a POST.
        '''
        try:
            with self.session.open(url, data=data, timeout=10) as response:
                # print(response.url)
                # print(response.status)
                return response.read().decode('UTF-8')
        except HTTPError as error:
            # print(error.status, error.reason)
            pass
        except URLError as error:
            # print(error.reason)
            pass
        except TimeoutError:
            # print("Request timed out")
            pass



    def download_torrent(self, info):
        """
        Providing this function is optional.
        It can however be interesting to provide your own torrent download
        implementation in case the search engine in question does not allow
        traditional downloads (for example, cookie-based download).
        """
        print(download_file(info))

    # DO NOT CHANGE the name and parameters of this function
    # This function will be the one called by nova2.py
    def search(self, what, cat='all'):
        """
        Here you can do what you want to get the result from the search engine website.
        Everytime you parse a result line, store it in a dictionary
        and call the prettyPrint(your_dict) function.

        `what` is a string with the search tokens, already escaped (e.g. "Ubuntu+Linux")
        `cat` is the name of a search category in ('all', 'movies', 'tv', 'music', 'games', 'anime', 'software', 'pictures', 'books')
        """


a = file_list()