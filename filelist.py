#VERSION: 0.30
#AUTHORS: authors

# LICENSING INFORMATION

# FileList.io search engine plugin for qBittorrent
# [x] login
# [x] test login errors
# [x] get search results
# [x] get individual results from search results
# [x] parse torrent data from search results
# [x] return to qBitTorrent parsed torrent data
# [x] implement logging
# [ ] add search plugin to qBitTorrent problems
# [ ] download_torrent method problems
# [ ] test in qBitTorrent
# [ ] get search results from all pages
# [ ] github readme and others

import json
import logging
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
# maximum number of request retries
MAX_REQ_RETRIES = 3

# logging configuration
logging.basicConfig(
    filename='filelist.log',
    filemode='w',
    encoding='UTF-8',
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%d.%m %H:%M:%S',
    level=logging.DEBUG,
    force=True
)

# region: LOGIN credentials
# enter credentials in filelist_credentials.json file
# get model from github repo and rename it to filelist_credentials.json
# OR ENTER YOUR LOGIN DATA HERE:
credentials = {
    'username': 'your_username_here',
    'password': 'your_password_here'
}

# try to get login credentials from json file if it exists
FILE_PATH = os.path.dirname(os.path.realpath(__file__))
CREDENTIALS_FILE = os.path.join(FILE_PATH, 'filelist_credentials.json')
try:
    with open(CREDENTIALS_FILE, mode='r', encoding='UTF-8') as file:
        logging.debug(f'Credentials file found. Credentials loaded.')
        credentials = json.load(file)
except FileNotFoundError:
    logging.debug('Credentials file not found. Using data from current file.')
# endregion

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


class filelist(object):
    ''' filelist.io search class. '''

    url: str = 'https://filelist.io/'
    name: str = 'FileList'
    supported_categories: dict = {
        'all': '0',
        'movies': '19',
        'tv': '21',
        'music': '11',
        'games': '9',
        'anime': '24',
        'software': '8'
    }
    url_dl: str = url + 'download.php?id='
    url_login: str = url + 'login.php'
    url_login_post: str = url + 'takelogin.php'
    url_search: str = url + 'browse.php?search'
    url_details: str = url + 'details.php?id='
    url_download: str = url + 'download.php?id='
    critical_error: bool = False
    request_retry: int = 0
    
    # initialize cookie jar
    cj = CookieJar()
    # initialize an OpenerDirector with the cookie jar attached
    session = build_opener(HTTPCookieProcessor(cj))
    session.addheaders = [USER_AGENT]

    def __init__(self):
        """ Initialize the class. """
        logging.debug('New filelist object created.')
        self._login()

    def _login(self) -> None:
        ''' Login to filelist. 
        
        Login to filelist passing custom header,
        cookie with session id from cookie jar and
        username, password and validator from encoded payload.
        '''
        # region: create payload
        self.payload = {
            'unlock': '1',
            'returnto': '%2F',
        }
        if (credentials['username'] == 'your_username_here' or
            credentials['password'] == 'your_password_here'):
            if credentials['username'] == 'your_username_here':
                logging.critical('Default username! Change username!')
            else:
                logging.critical('Default password! Change password!')
            self.critical_error = True
            return
        else:
            self.payload['username'] = credentials['username']
            self.payload['password'] = credentials['password']

        # load cookies and get validator value
        login_page = self._make_request(self.url_login)
        if not login_page:
            logging.critical("Can't acces login page!")
            self.critical_error = True
            return
        
        self.payload['validator'] = re.search(RE_VALIDATOR, login_page).group()
        if not self.payload['validator']:
            logging.critical('Could not retrieve validator key!')
            self.critical_error = True
            return
        else:
            logging.debug('Retrieved validator key.')
        
        # check if cookie is in the jar
        if "PHPSESSID" not in [cookie.name for cookie in self.cj]:
            logging.critical('Could not load cookie!')
            self.critical_error = True
            return
        else:
            logging.debug('Cookie is in the jar.')

        # encode payload to a percent-encoded ASCII text string
        # and encode to bytes
        self.payload = urlencode(self.payload).encode()
        # endregion

        # POST form and login
        main_page = self._make_request(self.url_login_post, data=self.payload)
        if main_page:
            logging.info('Logged in.')

    def _make_request(
            self,
            url: str,
            data: Optional[bytes]=None,
            decode: bool=True
            ) -> Optional[Union [str, bytes]]:
        ''' GET and POST to 'url'.
        
        If 'data' is passed results a POST.
        '''
        if data:
            logging.debug(f'POST data to {url} with {decode = }')
        else:
            logging.debug(f'GET data from {url} with {decode = }')

        if self.request_retry > MAX_REQ_RETRIES:
            self.request_retry = 0
            return

        try:
            with self.session.open(url, data=data, timeout=10) as response:
                response : HTTPResponse
                logging.debug(f'Response status: {response.status}')
                if response.url == self.url_login_post:
                    logging.critical(f'Redirected to error page!')
                    bad_response = response.read().decode('UTF-8', 'replace')
                    if 'Numarul maxim permis de actiuni' in bad_response:
                        logging.error('Exceeded maximum number of '
                                'login attempts. Retry in an hour!')
                    elif 'User sau parola gresite.' in bad_response:
                        logging.error('Wrong username and/or password!')
                    elif 'Invalid login attempt!' in bad_response:
                        logging.error('Wrong validator key '
                                      'or cookie not loaded!')
                    self.critical_error = True
                    return
                else:
                    good_response = response.read()
                    if decode:
                        logging.debug('Returned url decoded as string.')
                        self.request_retry = 0
                        return good_response.decode('UTF-8', 'replace')
                    else:
                        logging.debug('Returned url raw as bytes.')
                        self.request_retry = 0
                        return good_response
        except HTTPError as error:
            if error.code == 403:
                logging.critical('Error 403: Connection refused! '
                                 'Bad "user-agent" or header not loaded.')
                self.critical_error = True
                return
            if error.code == 404:
                logging.error('Error 404: Page not found!')
                self.request_retry += 1
                logging.debug(f'Retry {self.request_retry}/{MAX_REQ_RETRIES}')
                return self._make_request(url, data, decode)
        except URLError as error:
            logging.error(error.reason)
            self.request_retry += 1
            logging.debug(f'Retry {self.request_retry}/{MAX_REQ_RETRIES}')
            return self._make_request(url, data, decode)
        except TimeoutError:
            logging.error('Request timed out')
            self.request_retry += 1
            logging.debug(f'Retry {self.request_retry}/{MAX_REQ_RETRIES}')
            return self._make_request(url, data, decode)

    def download_torrent(self, url: str) -> None:
        """ Return download link to qBittorrent. """
        
        if self.critical_error:
            self._return_error()
            return

        # Download url
        response = self._make_request(url, decode=False)
        if not response:
            logging.error('Cannot acces download torrent url!')
            return

        # Create a torrent file
        with NamedTemporaryFile(suffix=".torrent", delete=False) as fd:
            fd.write(response)

            # return file path
            logging.info(f'Returned download to qBittorrent:"{fd.name} {url}"')
            print(fd.name + " " + url)
            return (fd.name + " " + url)

    def search(self, what: str, cat: str='all') -> None:
        """ Search for torrent and return with prettyPrint(your_dict).

        `what` to search for
        `cat` is the name of a search category
        """
        if self.critical_error:
            self._return_error()
            return

        logging.debug(f'Searching for "{what}" in category "{cat}" ')

        if cat not in self.supported_categories:
            logging.warning(f'Category "{cat}" not found, defaulting to "all".')
            cat = 'all'

        # region: create search url
        # create a list of tuples for urlencode
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
        search_link = urlencode(search_link, safe=':/?+')
        logging.debug('Encoded url: ', search_link)
        # endregion

        search_results_page = self._make_request(search_link)
        if not search_results_page:
            logging.error('Cannot access results page!')
        if 'Rezultatele cautarii dupa' in search_results_page:
            logging.debug('Accessed results page.')
            if 'Nu s-a găsit nimic!' not in search_results_page:
                torrent_rows = re.finditer(RE_ALL_RESULTS, search_results_page)
                total_results = 0
                for torrent in torrent_rows:
                    self._parse_torrent(torrent.group())
                    total_results += 1
                else:
                    logging.info(f'Parsed {total_results} torrents.')
            else:
                logging.debug('No results found.')
        else:
            logging.error('Cannot access results page!')
            pass

    def _parse_torrent(self, torrent: str) -> None:
        """ Get details from torrent and prettyPrint. """

        torrent_data = {'engine_url': f"{self.url.rstrip('/')}"}
        id = re.search(RE_GET_ID, torrent).group()
        if not id:
            logging.error('Cannot retrieve torrent id!')
            return
        # download link
        torrent_data['link'] = f'{self.url_download}{id}'
        # description page
        torrent_data['desc_link'] = f'{self.url_details}{id}'
        # name
        torrent_data['name'] = re.search(RE_GET_NAME, torrent).group()
        if not torrent_data['name']:
            logging.warning('Cannot retrieve torrent name. Setting a default.')
            torrent_data['name'] = 'Could not retrieve torrent name'
        # size
        size = re.search(RE_GET_SIZE, torrent)
        if size:
            size = size.groups()
            torrent_data['size'] = ' '.join(size)
            logging.debug(f"Torrent size: {torrent_data['size']}")
        else:
            logging.debug('Could not retrieve torrent size. Setting -1.')
            torrent_data['size'] = -1
        # seeders
        seeders = re.search(RE_GET_SEEDERS, torrent)
        if seeders:
            torrent_data['seeds'] = seeders.group()
        else:
            logging.debug('Could not retrieve number of seeders. Setting 0.')
            torrent_data['seeds'] = '0'
        # leechers
        leechers = re.search(RE_GET_LEECHERS, torrent)
        if leechers:
            torrent_data['leech'] = leechers.group()
        else:
            logging.debug('Could not retrieve number of leechers. Setting 0.')
            torrent_data['leech'] = '0'

        logging.info(f'Sending to prettyPrinter:'
                     f' {torrent_data["link"]} |'
                     f' {torrent_data["name"]} |'
                     f' {torrent_data["size"]} |'
                     f' {torrent_data["seeds"]} |'
                     f' {torrent_data["leech"]} |'
                     f' {torrent_data["engine_url"]} |'
                     f' {torrent_data["desc_link"]}'
                     )
        prettyPrinter(torrent_data)

    def _return_error(self) -> None:
        # intended high seeds, leech and big size to see the error when sorting
        logging.info('Sending critical error to prettyPrinter!')
        prettyPrinter({
            'engine_url': f'{self.url.rstrip("/")}',
            "desc_link": f'{self.url.rstrip("/")}',
            "name": 'CRITICAL error. Check "filelist.log" file',
            "link": f'{self.url.rstrip("/")}',
            "size": '1 TB',
            "seeds": 100,
            "leech": 100})
        self.critical_error = False

if __name__ == "__main__":
    # a = filelist()
    # a.search('ubuntu', 'all')
    # a.download_torrent('https://filelist.io/download.php?id=60739')
    pass

