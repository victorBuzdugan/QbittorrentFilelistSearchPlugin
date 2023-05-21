#VERSION: 0.20
#AUTHORS: authors

# LICENSING INFORMATION

# FileList.io search engine plugin for qBittorrent
# [x] login
# [x] test login errors
# [x] get search results
# [x] get individual results from search results
# [x] parse torrent data from search results
# [x] return to qBitTorrent parsed torrent data
# [ ] add search plugin to qBitTorrent problems
# [ ] download_torrent method problems
# [ ] test in qBitTorrent
# [ ] get search results from all pages
# [ ] implement logging
# [ ] github readme and others

import json
import os
import re
from http.client import HTTPResponse
from http.cookiejar import CookieJar
from tempfile import NamedTemporaryFile
from typing import Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, build_opener

from novaprinter import prettyPrinter

USER_AGENT: tuple = ('User-Agent', 
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15')

# region: regex patterns
RE_VALIDATOR = re.compile(r"""
    # starts with but not including
    (?<=name='validator'\svalue=')
    # capture
    (.*)
    # ends with but not included
    (?='\s\/>)
    """, re.VERBOSE)
RE_ALL_RESULTS = re.compile(r"""
    # starts with
    <div\sclass='torrentrow'>
    # any char, including new line
    [\S\s]*?
    # ends with
    <div\sclass='clearfix'><\/div>\s*<\/div>
    """, re.VERBOSE)
RE_GET_ID = re.compile(r"""
    # starts with but not including
    (?<=id=)
    # one or more digits
    \d+
    """, re.VERBOSE)
RE_GET_NAME = re.compile(r"""
    # starts with but not including
    (?<=title=')
    # one or more characters (excluding new line '.')
    .+?
    # ends with '
    (?=')
    """, re.VERBOSE)
RE_GET_SIZE = re.compile(r"""
    # starts with but not including
    (?<=<font\sclass='small'>)
    # catch group 1
    ([\d.]+)
    # continues with but not included
    (?:<br\s\/>)
    # catch group 2
    (\w+)
    """, re.VERBOSE)
RE_GET_SEEDERS = re.compile(r"""
    # starts with but not including (hex color 'w{6}')
    (?<=<font\scolor=\#\w{6}>)
    # catch digits
    \d+
    """, re.VERBOSE)
RE_GET_LEECHERS = re.compile(
    r"(?<=vertical-align:middle;display:table-cell;'><b>)\d+"
)
# endregion

# region: login credentials
# enter your login data here or in filelist_credentials.json file
credentials = {
    'username': 'your_username_here',
    'password': 'your_password_here'
}

FILE_PATH = os.path.dirname(os.path.realpath(__file__))
CREDENTIALS_FILE = os.path.join(FILE_PATH, 'filelist_credential.json')
# try to get login credentials from json file if exists
try:
    with open(CREDENTIALS_FILE, mode='r', encoding='UTF-8') as file:
        # print(f'"{file.name}" found. Credentials loaded.')
        credentials = json.load(file)
except FileNotFoundError:
    # print(f'Credentials file not found. Using data from current file.')
    pass
# endregion


class filelist(object):
    ''' filelist.io search class. '''

    url = 'https://filelist.io/'
    name = 'FileList'
    supported_categories = {
        'all': '0',
        'movies': '19',
        'tv': '21',
        'music': '11',
        'games': '9',
        'anime': '24',
        'software': '8'
    }
    url_dl = url + 'download.php?id='
    url_login = url + 'login.php'
    url_login_post = url + 'takelogin.php'
    url_search = url + 'browse.php?search'
    url_details = url + 'details.php?id='
    url_download = url + 'download.php?id='
    
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

    def _make_request(
            self, url: str,
            data: Optional[bytes]=None,
            decode: bool=True) -> Optional[Union [str, bytes]]:
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
                    if decode:
                        return good_response.decode('UTF-8', 'replace')
                    else:
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

    def download_torrent(self, url: str) -> None:
        """
        Providing this function is optional.
        It can however be interesting to provide your own torrent download
        implementation in case the search engine in question does not allow
        traditional downloads (for example, cookie-based download).
        """
        # Download url
        response = self._make_request(url, decode=False)

        # Create a torrent file
        with NamedTemporaryFile(suffix=".torrent", delete=False) as fd:
            fd.write(response)

            # return file path
            print(fd.name + " " + url)
            return (fd.name + " " + url)

        # print(download_file(url))

    # DO NOT CHANGE the name and parameters of this function
    # This function will be the one called by nova2.py
    def search(self, what: str, cat: str='all') -> None:
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
            if 'Nu s-a găsit nimic!' not in search_results_page:
                torrent_rows = re.finditer(RE_ALL_RESULTS, search_results_page)
                for torrent in torrent_rows:
                    self._parse_torrent(torrent.group())
            else:
                # print('No results found.')
                pass
        else:
            # print('Cannot access search results page!')
            pass

    def _parse_torrent(self, torrent: str) -> None:
        """ Get details from torrent and prettyPrint. """

        torrent_data = {'engine_url': f"{self.url.rstrip('/')}"}
        id = re.search(RE_GET_ID, torrent).group()
        # download link
        torrent_data['link'] = f'{self.url_download}{id}'
        # description page
        torrent_data['desc_link'] = f'{self.url_details}{id}'
        # name
        torrent_data['name'] = re.search(RE_GET_NAME, torrent).group()
        # size
        size = re.search(RE_GET_SIZE, torrent)
        if size:
            size = size.groups()
            torrent_data['size'] = ' '.join(size)
        else:
            torrent_data['size'] = -1
        # seeders
        seeders = re.search(RE_GET_SEEDERS, torrent)
        if seeders:
            torrent_data['seeds'] = seeders.group()
        else:
            torrent_data['seeds'] = -1
        # leechers
        leechers = re.search(RE_GET_LEECHERS, torrent)
        if leechers:
            torrent_data['leech'] = leechers.group()
        else:
            torrent_data['leech'] = '0'

        prettyPrinter(torrent_data)


if __name__ == "__main__":
    # a = filelist()
    # a.search('ubuntu', 'all')
    # a.download_torrent('https://filelist.io/download.php?id=60739')
    pass

