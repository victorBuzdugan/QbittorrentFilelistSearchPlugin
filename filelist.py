#VERSION: 0.10

# FileList.io search engine plugin for qBittorrent
# [x] login
# [x] test login errors
# [x] get search results
# [x] get individual results from search results
# [ ] parse torrent data from search results
# [ ] return to qBitTorrent data
# [ ] get search results from all pages
# [ ] test in qBitTorrent
# [ ] implement logging
# [ ] github readme and others

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
from http.client import HTTPResponse

import sgmllib3
from helpers import download_file

USER_AGENT: tuple = ('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15')

# region: regex patterns
# get validator key from login page 
RE_VALIDATOR = re.compile(r"(?<=name='validator' value=')(.*)(?=' \/>)")
RE_ALL_RESULTS = re.compile(
    r"""
    <div\sclass='torrentrow'>                    # starts with
    [\S\s]*?                                    # any char, including new line
    <div\sclass='clearfix'><\/div>\s*<\/div>     # ends with
    """, re.VERBOSE)
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


class filelist:
    ''' filelist.io search class. '''

    name = 'FileList'
    url = 'https://filelist.io/'
    url_dl = url + 'download.php?id='
    url_login = url + 'login.php'
    url_login_post = url + 'takelogin.php'
    url_search = url + 'browse.php?search'
    url_details = url + 'details.php?id='
    supported_categories = {
        'all': '0',
        'movies': '19',
        'tv': '21',
        'music': '11',
        'games': '9',
        'anime': '24',
        'software': '8'
    }
    
    # initialize cookie jar
    cj = CookieJar()
    # initialize an OpenerDirector with the cookie jar attached
    session = build_opener(HTTPCookieProcessor(cj))
    session.addheaders = [USER_AGENT]

    def __init__(self):
        """ Initialize the class. """

        # login
        self._login()

    
    def _login(self) -> None:
        ''' Login to filelist. 
        
        Login to filelist passing custom header,
        cookie with session id from cookie jar and
        username, password and validator from encoded payload.
        '''
        # create payload
        self.payload = {
            'unlock': '1',
            'returnto': '%2F',
        }
        self.payload['username'] = credentials['username']
        self.payload['password'] = credentials['password']

        # load cookies and get validator value
        login_page = self._make_request(self.url_login)
        self.payload['validator'] = re.search(RE_VALIDATOR, login_page).group()

        # encode payload to a percent-encoded ASCII text string
        # and encode to bytes
        self.payload = urlencode(self.payload).encode()

        # POST form and login
        main_page = self._make_request(self.url_login_post, data=self.payload)

    def _make_request(self, url: str, data=None) -> Optional[str]:
        ''' GET and POST to 'url'.
        
        If 'data' is passed results a POST.
        '''
        try:
            with self.session.open(url, data=data, timeout=10) as response:
                response : HTTPResponse
                # print(response.url)
                # print(response.status)
                if response.url == self.url_login_post:
                    bad_response = response.read().decode('UTF-8', 'replace')
                    if 'Numarul maxim permis de actiuni' in bad_response:
                        print('Exceeded maximum number of login attempts. '
                              'Retry in an hour!')
                    elif 'User sau parola gresite.' in bad_response:
                        print('Wrong username or password!')
                    elif 'Invalid login attempt!' in bad_response:
                        print('Wrong validator key, or cookie not loaded!')
                else:
                    # print('Logged in.')
                    good_response = response.read()
                    good_response = good_response.decode('UTF-8', 'replace')
                    return good_response
        except HTTPError as error:
            if error.code == 403:
                print('Bad "user-agent". Header not loaded. '
                      'Connection refused!')
            if error.code == 404:
                print('404 Page not found!')
            # print(error.code, error.reason)
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
    def search(self, what: str, cat='all') -> None:
        """
        Here you can do what you want to get the result from the search engine website.
        Everytime you parse a result line, store it in a dictionary
        and call the prettyPrint(your_dict) function.

        `what` is a string with the search tokens, already escaped (e.g. "Ubuntu+Linux")
        `cat` is the name of a search category in ('all', 'movies', 'tv', 'music', 'games', 'anime', 'software', 'pictures', 'books')
        """

        if cat not in self.supported_categories:
            # print(f'Category "{cat}" not found, defaulting to "all".')
            cat = 'all'

        # create search url
        search_link = [
            # ('https://filelist.io/browse.php?search', search_string)
            (self.url_search, what),
            # category
            ('cat', self.supported_categories[cat]),
            # 0: Name & Description, 1: Name, 2: Description, 3: IMDB id
            ('searchin', '1'),
            # 0: Hybrid, 1: Relevance, 2: Date, 3: Size, 
            # 4: Downloads, 5:Seeders
            ('sort', '5')
        ]
        # print('Before encoding url: ', search_link)
        search_link = urlencode(search_link, safe=':/?+')
        # print('Encoded url: ', search_link)

        search_results_page = self._make_request(search_link)
        if 'Rezultatele cautarii dupa' in search_results_page:
            # retutned results page
            torrent_row = re.finditer(RE_ALL_RESULTS, search_results_page)

        else:
            # print('Cannot access search results page!')
            pass

# You must pass to this function a dictionary containing the following keys
# (value should be -1 if you do not have the info):

# [ ] link => A string corresponding the the download link (the .torrent file or magnet link)
# [ ] name => A unicode string corresponding to the torrent's name (i.e: "Ubuntu Linux v6.06")
# [ ] size => A string corresponding to the torrent size (in bytes???) (i.e: "6 MB" or "200 KB" or "1.2 GB"...)
# [ ] seeds => The number of seeds for this torrent (as a string)
# [ ] leech => The number of leechers for this torrent (a a string)
# [ ] engine_url => The search engine url (i.e: http://www.mininova.org)
# [ ] desc_link => A string corresponding to the the description page for the torrent



if __name__ == "__main__":
    a = filelist()
    a.search('mandalorian+s01', 'tv')
    pass

# with open('FileListResults.html') as file:
#     a = file.read()

# # print(a)


# b = re.finditer(RE_ALL_RESULTS, a)


# for i in b:
#     print(i.group())

