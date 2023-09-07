#VERSION: 1.10
#AUTHORS: victorBuzdugan
# https://github.com/victorBuzdugan/QbittorrentFilelistSearchPlugin

# LICENSING INFORMATION

# FileList.io search engine plugin for qBittorrent

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

# maximum number of search results pages
MAX_PAGES = 5

FILE_PATH = os.path.dirname(os.path.realpath(__file__))

# region: logging configuration
logging.basicConfig(
    filename=os.path.join(FILE_PATH, 'filelist.log'),
    filemode='w',
    # qBittorrent installs Python 3.8 by default; encoding was added in 3.9
    # encoding='UTF-8',
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%d.%m %H:%M:%S',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)
# endregion

# region: LOGIN credentials
# enter credentials in filelist_credentials.json file
# get model from github repo and rename it to filelist_credentials.json
# OR ENTER YOUR LOGIN DATA HERE:
credentials = {
    'username': 'your_username_here',
    'password': 'your_password_here'
}

# try to get login credentials from json file if it exists
CREDENTIALS_FILE = os.path.join(FILE_PATH, 'filelist_credentials.json')
try:
    with open(CREDENTIALS_FILE, mode='r', encoding='UTF-8') as file:
        logger.debug('Credentials file found. Credentials loaded.')
        credentials = json.load(file)
except FileNotFoundError:
    logger.debug('Credentials file not found. Using data from current file.')
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
RE_NEXT_PAGE = re.compile(
    r"<a href='\?search=[\S]+<font class='small'>&raquo;"
)
# endregion


class filelist():
    ''' filelist.io search class. '''

    url: str = 'https://filelist.io'
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
    url_dl: str = url + '/download.php?id='
    url_login: str = url + '/login.php'
    url_login_post: str = url + '/takelogin.php'
    url_search: str = url + '/browse.php?search'
    url_details: str = url + '/details.php?id='
    url_download: str = url + '/download.php?id='
    critical_error: bool = False
    request_retry: int = 0

    # initialize cookie jar
    cj = CookieJar()
    # initialize an OpenerDirector with the cookie jar attached
    session = build_opener(HTTPCookieProcessor(cj))
    session.addheaders = [USER_AGENT]

    def __init__(self):
        """ Initialize the class. """
        logger.debug('New filelist object created.')
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
                logger.critical('Default username! Change username!')
            else:
                logger.critical('Default password! Change password!')
            self.critical_error = True
            return
        else:
            self.payload['username'] = credentials['username']
            self.payload['password'] = credentials['password']

        # load cookies and get validator value
        login_page = self._make_request(self.url_login)
        if not login_page:
            logger.critical("Can't acces login page!")
            self.critical_error = True
            return

        self.payload['validator'] = re.search(RE_VALIDATOR, login_page).group()
        if not self.payload['validator']:
            logger.critical('Could not retrieve validator key!')
            self.critical_error = True
            return
        else:
            logger.debug('Retrieved validator key.')

        # check if cookie is in the jar
        if "PHPSESSID" not in [cookie.name for cookie in self.cj]:
            logger.critical('Could not load cookie!')
            self.critical_error = True
            return
        else:
            logger.debug('Cookie is in the jar.')

        # encode payload to a percent-encoded ASCII text string
        # and encode to bytes
        self.payload = urlencode(self.payload).encode()
        # endregion

        # POST form and login
        main_page = self._make_request(self.url_login_post, data=self.payload)
        if main_page:
            logger.info('Logged in.')

    def _make_request(
            self,
            url: str,
            data: Optional[bytes] = None,
            decode: bool = True
            ) -> Optional[Union[str, bytes]]:
        ''' GET and POST to 'url'.

        If 'data' is passed results a POST.
        '''
        if data:
            logger.debug('POST data to %s with decode = %s', url, decode)
        else:
            logger.debug('GET data from %s with decode = %s', url, decode)

        if self.request_retry > MAX_REQ_RETRIES:
            self.request_retry = 0
            return

        try:
            with self.session.open(url, data=data, timeout=10) as response:
                response: HTTPResponse
                logger.debug('Response status: %s', response.status)
                if response.url == self.url_login_post:
                    logger.critical('Redirected to error page!')
                    bad_response = response.read().decode('UTF-8', 'replace')
                    if 'Numarul maxim permis de actiuni' in bad_response:
                        logger.error('Exceeded maximum number of '
                                'login attempts. Retry in an hour!')
                    elif 'User sau parola gresite.' in bad_response:
                        logger.error('Wrong username and/or password!')
                    elif 'Invalid login attempt!' in bad_response:
                        logger.error('Wrong validator key '
                                     'or cookie not loaded!')
                    self.critical_error = True
                    return
                else:
                    good_response = response.read()
                    if decode:
                        logger.debug('Returned url decoded as string.')
                        self.request_retry = 0
                        return good_response.decode('UTF-8', 'replace')
                    else:
                        logger.debug('Returned url raw as bytes.')
                        self.request_retry = 0
                        return good_response
        except HTTPError as error:
            if error.code == 403:
                logger.critical('Error 403: Connection refused! '
                                'Bad "user-agent" or header not loaded.')
                self.critical_error = True
                return
            if error.code == 404:
                logger.error('Error 404: Page not found!')
                self.request_retry += 1
                logger.debug('Retry %d/%d', self.request_retry, MAX_REQ_RETRIES)
                return self._make_request(url, data, decode)
        except URLError as error:
            logger.error(error.reason)
            self.request_retry += 1
            logger.debug('Retry %d/%d', self.request_retry, MAX_REQ_RETRIES)
            return self._make_request(url, data, decode)
        except TimeoutError:
            logger.error('Request timed out')
            self.request_retry += 1
            logger.debug('Retry %d/%d', self.request_retry, MAX_REQ_RETRIES)
            return self._make_request(url, data, decode)

    def download_torrent(self, url: str) -> None:
        """ Return download link to qBittorrent. """

        if self.critical_error:
            self._return_error()
            return

        # Download url
        response = self._make_request(url, decode=False)
        if not response:
            logger.error('Cannot acces download torrent url!')
            return

        # Create a torrent file
        with NamedTemporaryFile(suffix=".torrent", delete=False) as temp_file:
            temp_file.write(response)

            # return file path and url
            logger.info('Returned to qBittorrent:"%s %s"', temp_file.name, url)
            print(temp_file.name + " " + url)
            # return (fd.name + " " + url)

    def search(self, what: str, cat: str = 'all') -> None:
        """ Search for torrent and return with prettyPrint(your_dict).

        `what` to search for
        `cat` is the name of a search category
        """
        if self.critical_error:
            self._return_error()
            return

        what = what.replace('%20', '+')

        logger.debug('Searching for "%s" in category "%s"', what, cat)

        if cat not in self.supported_categories:
            logger.warning('Category "%s" not found, setting to "all".', cat)
            cat = 'all'

        def create_search_link(page_no: int = 0) -> str:
            ''' Creates a search link based on page number. '''

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
                ('sort', '5'),
                ('page', str(page_no))
            ]
            search_link = urlencode(search_link, safe=':/?+')
            logger.debug('Encoded url: %s', search_link)
            return search_link

        page_no = 0
        total_results = 0
        while page_no < MAX_PAGES:
            logger.debug('Requesting page number %d', page_no)
            search_page = self._make_request(create_search_link(page_no))
            if not search_page:
                logger.error('Cannot access results page!')
                break
            if 'Rezultatele cautarii dupa' in search_page:
                logger.info('Accessed results page.')
                if 'Nu s-a găsit nimic!' not in search_page:
                    torrent_rows = re.finditer(RE_ALL_RESULTS, search_page)
                    for torrent in torrent_rows:
                        self._parse_torrent(torrent.group())
                        total_results += 1
                    # check if there is a next page
                    # every page has 20 elements
                    # '»' signals there is a next page
                    if ((total_results % 20 == 0) and
                            re.search(RE_NEXT_PAGE, search_page)):
                        page_no += 1
                    else:
                        break
                else:
                    logger.info('No results found.')
                    break
            else:
                logger.error('Cannot access results page!')
                break
        logger.info('Parsed %d torrents.', total_results)

    def _parse_torrent(self, torrent: str) -> None:
        """ Get details from torrent and prettyPrint. """

        torrent_data = {'engine_url': f"{self.url}"}
        tid = re.search(RE_GET_ID, torrent).group()
        if not tid:
            logger.error('Cannot retrieve torrent id!')
            return
        # download link
        torrent_data['link'] = f'{self.url_download}{tid}'
        # description page
        torrent_data['desc_link'] = f'{self.url_details}{tid}'
        # name
        torrent_data['name'] = re.search(RE_GET_NAME, torrent).group()
        if not torrent_data['name']:
            logger.warning('Cannot retrieve torrent name. Setting a default.')
            torrent_data['name'] = 'Could not retrieve torrent name'
        # size
        size = re.search(RE_GET_SIZE, torrent)
        if size:
            size = size.groups()
            torrent_data['size'] = ' '.join(size)
            logger.debug("Torrent size: %s", torrent_data['size'])
        else:
            logger.debug('Could not retrieve torrent size. Setting -1.')
            torrent_data['size'] = -1
        # seeders
        seeders = re.search(RE_GET_SEEDERS, torrent)
        if seeders:
            torrent_data['seeds'] = seeders.group()
        else:
            logger.debug('Could not retrieve number of seeders. Setting 0.')
            torrent_data['seeds'] = '0'
        # leechers
        leechers = re.search(RE_GET_LEECHERS, torrent)
        if leechers:
            torrent_data['leech'] = leechers.group()
        else:
            logger.debug('Could not retrieve number of leechers. Setting 0.')
            torrent_data['leech'] = '0'

        logger.info('Sending to prettyPrinter: %s|%s|%s|%s|%s|%s|%s|',
                    torrent_data["link"],
                    torrent_data["name"],
                    torrent_data["seeds"],
                    torrent_data["size"],
                    torrent_data["leech"],
                    torrent_data["engine_url"],
                    torrent_data["desc_link"])
        prettyPrinter(torrent_data)

    def _return_error(self) -> None:
        # intended high seeds, leech and big size to see the error when sorting
        logger.info('Sending critical error to prettyPrinter!')
        prettyPrinter({
            'engine_url': self.url,
            'desc_link': 'https://github.com/victorBuzdugan/QbittorrentFilelistSearchPlugin',
            'name': 'CRITICAL error check log file',
            'link': self.url + "/error",
            'size': '1 TB',
            'seeds': 100,
            'leech': 100})
        self.critical_error = False


if __name__ == "__main__":
    # test = filelist()
    # test.search('linux', 'all')
    # test.download_torrent('https://filelist.io/download.php?id=60739')
    pass
