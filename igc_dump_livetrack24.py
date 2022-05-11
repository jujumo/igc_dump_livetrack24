#!/usr/bin/env python3
import argparse
import logging
import os
import os.path as path
import requests
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import yaml
from tqdm import tqdm

logger = logging.getLogger('igc_dump_lt24')
logging.basicConfig(format='%(name)s::%(levelname)-8s: %(message)s')

SERVER_LT24 = 'https://www.livetrack24.com'


def login(driver, username, password):
    driver.get(f'{SERVER_LT24}/login')
    current_url = driver.current_url
    driver.find_element_by_id("user").send_keys(username)
    driver.find_element_by_name("pass").send_keys(password)
    driver.find_element_by_name("pass").send_keys(Keys.ENTER)
    driver.find_element_by_name("pass").submit()
    # wait for URL to change with 15 seconds timeout
    WebDriverWait(driver, 15).until(EC.url_changes(current_url))


def extract_track_ids(driver, username, page_num=1):
    url = f'{SERVER_LT24}/user/{username}/tracks/page_num/{page_num}'
    driver.get(url)
    content = driver.page_source
    track_page_bf = BeautifulSoup(content, 'html.parser')
    divs = track_page_bf.find_all(attrs={"class": "boxgridSocial"})
    if not divs:  # ending condition
        return set()
    track_id_list = set(div.attrs['data-trackid'] for div in divs)
    return track_id_list


def download_track_igc(igc_filepath, username, track_id=1):
    url = f'{SERVER_LT24}/leo_live.php?op=igc&user={username}&trackID={track_id}'
    r = requests.get(url, allow_redirects=True)
    with open(igc_filepath, 'wb') as f:
        f.write(r.content)


class VerbosityParsor(argparse.Action):
    """ accept debug, info, ... or theirs corresponding integer value formatted as string."""
    def __call__(self, parser, namespace, values, option_string=None):
        try:  # in case it represent an int, directly get it
            values = int(values)
        except ValueError:  # else ask logging to sort it out
            assert isinstance(values, str)
            values = logging.getLevelName(values.upper())
        setattr(namespace, self.dest, values)


def main():
    try:
        parser = argparse.ArgumentParser(description='Dump all igc tracks from livertack24.')
        parser_verbosity = parser.add_mutually_exclusive_group()
        parser_verbosity.add_argument(
            '-v', '--verbose', nargs='?', default=logging.WARNING, const=logging.INFO, action=VerbosityParsor,
            help='verbosity level (debug, info, warning, critical, ... or int value) [warning]')
        parser_verbosity.add_argument(
            '-q', '--silent', '--quiet', action='store_const', dest='verbose', const=logging.CRITICAL)
        parser.add_argument('-u', '--username', required=True,
                            help='username')
        parser.add_argument('-p', '--password', required=False,
                            help='password. If password is given, try to log in.')
        parser.add_argument('-f', '--track_file', nargs='?', const='track_ids.yaml', default=None,
                            help='optional input path to track id file. '
                                 'Write it if it does not exists')
        parser.add_argument('-o', '--output', default='tracks',
                            help='output path [tracks]')

        args = parser.parse_args()
        args.track_file = path.abspath(args.track_file) if args.track_file else None
        args.output = path.abspath(args.output)

        logger.setLevel(args.verbose)
        logger.debug('config:\n' + '\n'.join(f'\t\t{k}={v}' for k, v in vars(args).items()))

        # login
        username = args.username
        password = args.password
        page_num_max = 200
        track_ids_file_path = args.track_file

        track_ids = set()
        if track_ids_file_path and path.isfile(track_ids_file_path):
            with open(track_ids_file_path, encoding='utf-8') as f:
                track_ids = set(yaml.safe_load(f))

        if not track_ids:
            try:
                driver = webdriver.Firefox()
                if password:
                    login(driver=driver, username=username, password=password)
                for page_num in range(1, page_num_max):
                    # goto tracks
                    logger.debug(f'parsing page {page_num:02} : {len(track_ids)} tracks so far')
                    # track_page_bf = BeautifulSoup(driver.page_source)
                    track_page_ids = extract_track_ids(driver, username=username, page_num=page_num)
                    if not track_page_ids:
                        break
                    track_ids.update(track_page_ids)

                if track_ids_file_path:
                    logger.info(f'saving track ids to {track_ids_file_path}.')
                    with open(track_ids_file_path, 'w', encoding='utf-8') as f:
                        f.write(yaml.dump(list(track_ids)))
            except Exception as e:
                raise
            finally:
                driver.quit()

        logger.info(f'retrieved {len(track_ids)} track ids.')
        os.makedirs(args.output, exist_ok=True)
        for track_id in tqdm(track_ids):
            igc_filepath = path.join(args.output, f'{username}_{track_id}.igc')
            download_track_igc(igc_filepath=igc_filepath, username=username, track_id=track_id)

    except Exception as e:
        logger.critical(e)
        if args.verbose <= logging.DEBUG:
            raise


if __name__ == '__main__':
    main()
