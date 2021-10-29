#########################################################################################################
# TabCompare
# v2.0
# This script uses the Tableau Server Client To Compare Content on 2x Tableau Server Environments
# For more information, refer http://tableaujunkie.com
# To run the script, you must have installed Python 3.3 and later.
#
# Example:
#
#   python .\TabCompare.py --sa 'https://serverA.myco.com' --sb 'https://serverB.myco.com' --cv --cd --nt 10 --pi 'My Project' --u mcoles --f c:\myoutputfolder
#
#########################################################################################################

# import the necessary packages
import argparse
import getpass
import os
import pathlib
import shutil
import time
from datetime import datetime
from datetime import timedelta
import sys
import csv
import re
from threading import Thread
import threading
from queue import Queue, Empty
import requests
import tableauserverclient as TSC
from tableauserverclient.models import ServerInfoItem
from wand.image import Image
from pandas import read_csv, DataFrame
import pandas as pd
import logging
import logging.handlers
import log
import inspect
import math

# suppress SSL certificate warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

os.environ['MAGICK_HOME'] = os.path.abspath('.')


# main program generates images from Tableau Server
def main():
    # get info on the current script path
    filename = inspect.getframeinfo(inspect.currentframe()).filename
    path = os.path.dirname(os.path.abspath(filename))

    parser = argparse.ArgumentParser(description='Query View Image From Server')
    parser.add_argument('--sa', required=True, help='Server A URL (the target/new version of Tableau Server)')
    parser.add_argument('--sb', required=True, help='Server B URL (the old version of Tableau Server)')
    parser.add_argument('--si', required=False, help='(optional) Site Name Filter')
    parser.add_argument('--pi', required=False, help='(optional) Project Name Filter')
    parser.add_argument('--wi', required=False, help='(optional) Workbook Name Filter')
    parser.add_argument('--vi', required=False,
                        help='(optional) File Filter (provide path to input csv containing view LUIDs or content URLs to test)')
    parser.add_argument('--mm', required=False, default='content_url', choices=['content_url', 'luid'],
                        help='(optional) Match method (how views will be matched from server A to server B. Note that this also informs output directory structure naming convention.')
    parser.add_argument('--cv', required=False, action='store_true',
                        help='(optional) Compare views visually based on image exports')
    parser.add_argument('--cd', required=False, action='store_true',
                        help='(optional) Compare views by based on summary data exports')
    parser.add_argument('--cm', required=False, default='absolute',
                        help="(optional) Compare metrics type for visual comparisons. Default value: 'peak_signal_to_noise_ratio'. Possible values: 'undefined', 'absolute', 'mean_absolute', 'mean_error_per_pixel', 'mean_squared', 'normalized_cross_correlation', 'peak_absolute', 'peak_signal_to_noise_ratio', 'perceptual_hash', 'root_mean_square'")
    parser.add_argument('--nt', required=False, type=int, default=1, help='(optional) Number of threads to execute')
    parser.add_argument('--nr', required=False, type=int, default=3,
                        help='(optional) Number of retries to attempt for found differences')
    parser.add_argument('--u', required=True, help='Tableau Server Username')
    parser.add_argument('--p', required=False,
                        help='(optional) Tableau Server Password. USER WILL BE PROMPTED FOR PASSWORD IF NOT PROVIDED')
    parser.add_argument('--f', required=True,
                        help='filepath to save results to. EXISTING FILES IN FILEPATH WILL BE DELETED')
    parser.add_argument('--l', required=False, type=str, default=os.path.join(path, "logs", "TabCompare"),
                        help='(optional) Log file. Date and ".log" will be appended automatically to allow for rotation.')
    parser.add_argument('--ll', required=False, type=str, default='INFO', choices=['ERROR', 'WARN', 'INFO', 'DEBUG'],
                        help="(optional) Log level. Default value: 'ERROR'. Possible values: 'ERROR', 'WARN', 'INFO', 'DEBUG'")

    global retry_pairs
    retry_pairs = {}
    global args
    args = parser.parse_args()
    global report_path
    report_path = os.path.join(args.f, "report.csv")
    global task_queue
    task_queue = Queue()

    # initialize logging
    log.logger = logging.getLogger()
    if not len(log.logger.handlers):
        log.logger = log.LoggerQuickSetup(args.l, log_level=args.ll)

    # validate as much as possible before password prompt
    if not (args.cv or args.cd):
        log.logger.error(
            'Invalid options. You must provide either the --cv or --cd argument, or both, to run TabCompare')
        exit()

    # prompt for password if it is not passed as a command line parameter
    global password
    if args.p:
        password = args.p
    else:
        password = getpass.getpass("Tableau Server Password For " + args.u + ":")
    # password="admin"

    # Clean Filepath
    ret = cleanFilepath(args.f)

    # create output report with headers
    output = ['server_a_view_luid',
              'server_b_view_luid',
              'server_a_view_content_url',
              'server_b_view_content_url',
              'server_a_view_updated_at',
              'server_b_view_updated_at',
              'server_a_view_render_succeeded',
              'server_b_view_render_succeeded',
              'compare_succeeded',
              'attempt_number',
              'starttime',
              'view_render_a_start_time',
              'view_render_b_start_time',
              'view_render_a_duration',
              'view_render_b_duration',
              'view_render_a_filepath',
              'view_render_b_filepath',
              'view_render_a_filesize',
              'view_render_b_filesize',
              'view_render_a_url',
              'view_render_b_url',
              'compare_metric',
              'difference_value',
              'diff_filepath',
              'view_render_a_error_text',
              'view_render_b_error_text',
              'compare_error_text']

    with open(os.path.join(args.f, "report.csv"), 'a+', newline='') as f:
        writer = ThreadSafeCSVWriter(f)
        writer.writerow(output)

    if ret:
        # get Images from both servers
        log.logger.debug('getting view list')
        views_to_compare_a = getViews(args.sa)
        views_to_compare_b = getViews(args.sb)

        enqueueCompareViewTasks(views_to_compare_a, views_to_compare_b)

        # spin up N threads
        for index in range(args.nt):
            threadname = index + 1  # start thread names at 1
            worker = TaskWorker(threadname, task_queue)
            log.logger.info('Starting thread with name: {threadname}')
            worker.start()
            log.logger.debug(threading.active_count())

        # loop until work is done
        while 1 == 1:
            if threading.active_count() == 1:
                log.logger.info('Worker threads have completed. Exiting')
                return
            time.sleep(5)
            log.logger.info('Waiting on {} worker threads. Currently active threads:: {}'.format(
                threading.active_count() - 1,
                threading.enumerate()))

    # If image comparison finished successfully then display message
    if ret:
        log.logger.info("\n***********************************************************"
                        "\nTabCompare completed successfully!"
                        "\nPlease check TabCompare.twbx for your results."
                        "\nImage differences were saved to the /differences directory."
                        "\n***********************************************************")

        return False


def getSites(serverName):
    sites = []
    try:
        # Step 1: Sign in to server.
        if args.si:
            tableau_auth = TSC.TableauAuth(args.u, password, site_id=args.si)
        else:
            tableau_auth = TSC.TableauAuth(args.u, password, site_id="")
        server = TSC.Server(serverName)
        server.add_http_options({'verify': False})
        # The new endpoint was introduced in Version 2.4
        server.version = APIVERSION

        with server.auth.sign_in(tableau_auth):
            # query the sites
            if args.si:
                sites.append(server.sites.get_by_name(args.si))
            else:
                sites.extend(list(TSC.Pager(server.sites)))

        return sites

    except Exception as e:
        log.logger.error(f"{sys.exc_info()[0]}, {e}")
        os._exit(1)
        return False


def cleanFilepath(filepath):
    # clean output file directory
    log.logger.debug(f"Cleaning all files in filepath {filepath}")

    try:
        if os.path.isdir(filepath):
            shutil.rmtree(filepath)

        if not os.path.isdir(filepath):
            os.mkdir(filepath)
            os.mkdir(os.path.join(filepath, "differences"))

        return True
    except Exception as e:
        log.logger.error(e)


def getCurrentMicrosecondsStr():
    # get the current microseconds time in a three-digit string
    current_time_microseconds_str = str(datetime.now().microsecond)[:3]
    num_zeros = 3 - len(current_time_microseconds_str)
    current_time_microseconds_str += ('0' * num_zeros)

    return current_time_microseconds_str


def roundMixedDataframe(df):
    # return a dataframe of mixed types with all floats being rounded
    float_cols = []
    for column in df.columns:
        if df.dtypes[column] == 'float64':
            float_cols.append(column)
    df.update(df[float_cols].round())


class SiteView(object):
    # simple class that pairs a ViewItem from TSC with its respective site, server, and some convenience methods
    def __init__(self, view: TSC.ViewItem, site: TSC.SiteItem, server: TSC.Server, server_info: ServerInfoItem):
        self.view = view
        self.site = site
        self.server = server
        self.server_info = server_info
        self.workbook_content_url = view.content_url.split("/")[0]
        self.content_url_clean = view.content_url.replace("/sheets/", "~")

    def getCleanServerName(self):
        return re.search('(?:https?:\/\/)(.*)', self.server.server_address)[1]

    def getSiteContentUrlString(self):
        if self.site.content_url == '':
            return 'default'
        else:
            return self.site.content_url

    def getUrl(self):
        if self.getSiteContentUrlString() != 'default':
            site_str = f'/site/{self.getSiteContentUrlString()}'
        else:
            site_str = ''

        return f'{self.server.server_address}/#{site_str}/views/{self.view.content_url.replace("/sheets/", "/")}'


class ViewRenderer(object):
    # def __init__(self, site_view, render_type, '''filepath,''' attempt_num=0):
    def __init__(self, site_view, render_type, attempt_num=0):
        self.site_view = site_view
        self.render_type = render_type
        self.filepath = ''
        self.attempt_num = attempt_num
        self.start_timestamp = datetime.now()
        self.filesize = 0
        self.duration = 0
        self.start_time = None
        self.succeeded = False
        self.is_complete = False
        self.error_text = ''

    def getViewContentUrlClean(self):
        return self.site_view.view.content_url.replace("/sheets/", "~")

    def getOutputFilePathBase(self, server_name=None, diff=False):
        # this argument exists so we can create arbitrary filepath folders, like 'diffs'

        if not server_name:
            server_name = self.site_view.getCleanServerName()

        if diff:
            server_name = 'differences'  # diffs don't require this since we're comparing content between two servers

        if args.mm == 'luid':
            return (os.path.join(args.f, server_name, self.site_view.getSiteContentUrlString(),
                                 self.site_view.view.workbook_id, self.site_view.view.id))
        if args.mm == 'content_url':
            return (os.path.join(args.f, server_name, self.site_view.getSiteContentUrlString(),
                     self.site_view.workbook_content_url, self.site_view.content_url_clean))

    def getOutputFilePath(self, server_name=None, diff=False):
        suffix = ''
        if diff:
            suffix = '_diff'
        return f"{self.getOutputFilePathBase(server_name, diff)}_{self.attempt_num}{suffix}.{self.render_type}"

    def execute(self):
        process_start_time = time.process_time()
        try:
            tableau_auth = TSC.TableauAuth(args.u, password, site_id=self.site_view.site.content_url)
            server = TSC.Server(self.site_view.server.server_address)
            server.add_http_options({'verify': False})
            server.version = APIVERSION

            makePath(self.getOutputFilePathBase())
            with server.auth.sign_in(tableau_auth):
                if self.render_type == 'png':
                    # TSC something
                    image_req_option = TSC.ImageRequestOptions(imageresolution=TSC.ImageRequestOptions.Resolution.High,
                                                               maxage=0)

                    # now make the request, but only at or after the specified time
                    while datetime.now() < self.start_timestamp:
                        time.sleep(.05)

                    self.start_time = time.strftime('%Y-%m-%d %H:%M:%S.') + getCurrentMicrosecondsStr()
                    process_start_time = time.process_time()  # reset the timer so we get the most accurate duration
                    server.views.populate_image(self.site_view.view, image_req_option)
                    with open(self.getOutputFilePath(), "wb") as file_to_write:
                        file_to_write.write(self.site_view.view.image)
                elif self.render_type == 'csv':
                    csv_req_option = TSC.ImageRequestOptions(maxage=0)  # CSVRequestOption does not support "maxage"

                    # now make the request, but only at or after the specified time
                    while datetime.now() < self.start_timestamp:
                        time.sleep(.05)

                    self.start_time = time.strftime('%Y-%m-%d %H:%M:%S.') + getCurrentMicrosecondsStr()
                    process_start_time = time.process_time()  # reset the timer so we get the most accurate duration
                    server.views.populate_csv(self.site_view.view, csv_req_option)
                    with open(self.getOutputFilePath(), "wb") as file_to_write:
                        file_to_write.writelines(self.site_view.view.csv)
                else:
                    raise RuntimeError(f'Invalid render_type provided, {self.render_type}')

            if os.path.isfile(self.getOutputFilePath()):
                self.succeeded = True
        except Exception as e:
            self.error_text = f'Error rendering to {self.render_type}: {e}, {sys.exc_info()}'
            raise e
        finally:
            self.is_complete = True
            self.duration = time.process_time() - process_start_time
            if os.path.isfile(self.getOutputFilePath()):
                self.filesize = os.stat(self.getOutputFilePath()).st_size
                self.filepath = self.getOutputFilePath()
            else:
                self.error_text += f'File {self.getOutputFilePath()} is missing.'


class CompareTask(object):
    def __init__(self, view_render_a, view_render_b, diff_filepath, compare_metric=None, attempt_num=0):
        self.view_render_a = view_render_a
        self.view_render_b = view_render_b
        self.compare_metric = compare_metric
        self.attempt_num = attempt_num
        self.difference_value = 0
        self.diff_filepath = diff_filepath
        self.error_text = ''
        self.succeeded = False
        self.starttime = time.strftime('%Y-%m-%d %H:%M:%S')

    def output_result(self):
        output = [self.view_render_a.site_view.view.id,
                  self.view_render_b.site_view.view.id,
                  self.view_render_a.site_view.view.content_url,
                  self.view_render_b.site_view.view.content_url,
                  self.view_render_a.site_view.view.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                  self.view_render_b.site_view.view.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                  self.view_render_a.succeeded,
                  self.view_render_b.succeeded,
                  self.succeeded,
                  self.attempt_num,
                  self.starttime,
                  self.view_render_a.start_time,
                  self.view_render_b.start_time,
                  self.view_render_a.duration,
                  self.view_render_b.duration,
                  self.view_render_a.filepath,
                  self.view_render_b.filepath,
                  self.view_render_a.filesize,
                  self.view_render_b.filesize,
                  self.view_render_a.site_view.getUrl(),
                  self.view_render_b.site_view.getUrl(),
                  self.compare_metric,
                  self.difference_value,
                  self.diff_filepath,
                  self.view_render_a.error_text,
                  self.view_render_b.error_text,
                  self.error_text]

        log.logger.debug('writing output')
        log.logger.debug(f'writing this output: {output}')

        with open(report_path, 'a+', newline='') as f:
            writer = ThreadSafeCSVWriter(f)
            writer.writerow(output)

    def compare_images(self, image_a, image_b, compare_metric):
        if not os.path.exists(image_a):
            # image does not exist on serverB
            log.logger.debug(f"Could not find {image_a}")

        if not os.path.exists(image_b):
            # image does not exist on serverB
            log.logger.debug(f"Could not find {image_b}")

        try:
            with Image(filename=image_a) as image1:
                with Image(filename=image_b) as image2:

                    log.logger.debug('starting the image magic')

                    # if images are different sizes, resize target image to be same as source image before comparing
                    if image1.size != image2.size:
                        filesSizeDifferent = True

                        log.logger.debug('filesizes are different')

                        # trim images
                        image1.trim()
                        image2.trim()

                        log.logger.debug(f'images trimmed. comparing with metric {compare_metric}...')

                    difference_file, difference_value = image1.compare(image2, compare_metric)

                    log.logger.debug(f'difference value: {difference_value}')

                    # metric = comparison[1]

                    log.logger.debug(f"{compare_metric}, difference:, {difference_value}")
                    if difference_value == 0:
                        log.logger.debug("The images are the same")

                    else:
                        log.logger.debug(f'saving diff file to {self.diff_filepath}')

                        self.difference_value = difference_value

                        makePath(pathlib.Path(
                            self.diff_filepath).parent.resolve())  # make the full path to the file we're trying to write, in case it doesn't exist
                        difference_file.save(filename=self.diff_filepath)
                        log.logger.debug("the images are different")
        except Exception as e:
            errortext = f"Error encountered comparing images {image_a}, {image_b}: {e}, {sys.exc_info()}"
            self.error_text = errortext
            log.logger.error(errortext)

    def compare_csvs(self, csv_a, csv_b):
        if not os.path.exists(csv_a):
            # csv does not exist from serverA
            log.logger.debug(f"Could not find csv_a {csv_a}")
        if not os.path.exists(csv_b):
            # csv does not exist from serverB
            log.logger.debug(f"Could not find csv_b {csv_b}")

        try:
            log.logger.debug(f'going to compare these two csvs: {csv_a} = {csv_b}')

            # replace with empty data frames if the CSVs are blank / not present
            try:
                dataframe_a = pd.read_csv(csv_a, thousands=',')
                log.logger.debug('got the csv_a in a dataframe')
            except (pd.errors.EmptyDataError, FileNotFoundError) as e:
                dataframe_a = pd.DataFrame()

            try:
                dataframe_b = pd.read_csv(csv_b, thousands=',')
                log.logger.debug('got the csv_b in a dataframe')
            except (pd.errors.EmptyDataError, FileNotFoundError) as e:
                dataframe_b = pd.DataFrame()

            log.logger.debug(f'printing csv_a data: {dataframe_a}')
            log.logger.debug(f'printing csv_b data: {dataframe_b}')

            columns_diff = list(set(list(dataframe_a.columns)) ^ set(list(dataframe_b.columns)))
            rows_diff = list(set(list(dataframe_a.index)) ^ set(list(dataframe_b.index)))

            structural_diff = {}

            cell_diff_count = 0
            if columns_diff:
                structural_diff['column'] = columns_diff
                cell_diff_count += len(structural_diff['column']) * max(dataframe_a.size, dataframe_b.size)
            if rows_diff:
                structural_diff['row'] = rows_diff
                cell_diff_count += len(structural_diff['row']) * max(len(dataframe_a.columns), len(dataframe_b.columns))

            if structural_diff:
                log.logger.debug(f'{structural_diff}')
                makePath(pathlib.Path(
                    self.diff_filepath).parent.resolve())  # make the full path to the file we're trying to write, in case it doesn't exist
                pd.DataFrame(data=structural_diff).to_csv(self.diff_filepath)  # write the file
                difference_value = cell_diff_count / max(dataframe_a.size, dataframe_b.size)
                if math.isnan(difference_value):
                    self.difference_value = 0
                else:
                    self.difference_value = difference_value
            else:
                # round all float values to avoid random differences
                roundMixedDataframe(dataframe_a)
                roundMixedDataframe(dataframe_b)
                # sort these first
                dataframe_a = dataframe_a.sort_values(by=dataframe_a.columns.tolist()).reset_index(drop=True)
                dataframe_b = dataframe_b.sort_values(by=dataframe_a.columns.tolist()).reset_index(drop=True)
                # dataframe_b.sort_values(by=dataframe_b.columns.tolist(), inplace=True).reset_index(drop=True)
                dataframe_diff = dataframe_a.compare(dataframe_b)
                log.logger.debug(f'{dataframe_diff}')
                difference_value = dataframe_diff.size / max(dataframe_a.size, dataframe_b.size)
                if math.isnan(difference_value):
                    self.difference_value = 0
                else:
                    self.difference_value = difference_value

                log.logger.debug(f'difference value: {self.difference_value}')
                if self.difference_value != 0:
                    makePath(pathlib.Path(
                        self.diff_filepath).parent.resolve())  # make the full path to the file we're trying to write, in case it doesn't exist
                    dataframe_diff.to_csv(self.diff_filepath)  # write the file

        except ValueError as e:
            errortext = f"Unable to compare CSVs {csv_a}, {csv_b}: shapes differ"
            self.error_text = errortext
            log.logger.error(errortext)
            raise e
        except Exception as e:
            errortext = f"Error encountered comparing CSVs {csv_a}, {csv_b}: {e}, {sys.exc_info()}"
            self.error_text = errortext
            log.logger.error(errortext)
            raise e

    def execute(self):
        try:

            # my version
            # spin up 2 threads
            render_queue = Queue()

            # this ensures (hopefully) that our requests run at exactly the same time
            start_timestamp = datetime.now() + timedelta(seconds=1)
            self.view_render_a.start_timestamp = start_timestamp
            self.view_render_b.start_timestamp = start_timestamp

            render_queue.put(self.view_render_a)
            render_queue.put(self.view_render_b)

            threadname_a = f'RendererThread_a_{self.view_render_a.site_view.view.id}'
            threadname_b = f'RendererThread_b_{self.view_render_b.site_view.view.id}'

            worker_a = TaskWorker(threadname_a, render_queue)
            worker_b = TaskWorker(threadname_b, render_queue)

            log.logger.debug(f'starting thread a')
            worker_a.start()
            log.logger.debug(f'starting thread b')
            worker_b.start()

            # loop until work is done
            while not (self.view_render_a.is_complete and self.view_render_b.is_complete):
                # while set([threadname_a, threadname_b]).intersection(set([thread.name for thread in threading.enumerate()])):
                outstanding_threads = set([threadname_a, threadname_b]).intersection(
                    set([thread.name for thread in threading.enumerate()]))
                log.logger.debug(f'Waiting on threads: {outstanding_threads}')
                time.sleep(5)

            log.logger.debug(f'finished both threads')

            if self.view_render_a.succeeded and self.view_render_b.succeeded:
                # both views are rendered, compare them to each other

                if not os.path.exists(self.view_render_a.filepath):
                    # csv does not exist from serverA
                    log.logger.debug(f"Could not find csv_a {self.view_render_a.filepath}")
                if not os.path.exists(self.view_render_b.filepath):
                    # csv does not exist from serverB
                    log.logger.debug(f"Could not find csv_b {self.view_render_b.filepath}")
                if self.view_render_a.render_type == 'png' and self.view_render_b.render_type == 'png':
                    log.logger.debug(f'comparing pngs {self.view_render_a.filepath} to {self.view_render_b.filepath}')
                    self.compare_images(self.view_render_a.filepath, self.view_render_b.filepath, self.compare_metric)
                elif self.view_render_a.render_type == 'csv' and self.view_render_b.render_type == 'csv':
                    log.logger.debug(f'comparing csvs {self.view_render_a.filepath} to {self.view_render_b.filepath}')
                    self.compare_csvs(self.view_render_a.filepath, self.view_render_b.filepath)
                else:
                    raise RuntimeError(
                        f'Invalid render_type pairs, A: {self.view_render_a.render_type}, B: {self.view_render_b.render_type}')
                self.succeeded = True
        except Exception as e:
            errortext = f"Error encountered processing {self.view_render_a.site_view.view.id} and/or {self.view_render_b.site_view.view.id} into {self.view_render_a.render_type} / {self.view_render_b.render_type}: {e}, {sys.exc_info()}"
            self.error_text = errortext
            log.logger.error(errortext)
            raise e
        finally:
            # retry comparison if it failed, and we're still under the retry limit
            if (not self.succeeded or self.difference_value > 0) and self.attempt_num < args.nr:
                new_attempt_num = self.attempt_num + 1
                log.logger.debug(f'Enqueuing this comparison for retry number {new_attempt_num}')
                enqueueCompareViewTask(self.view_render_a.site_view, self.view_render_b.site_view,
                                       self.view_render_a.render_type,
                                       self.compare_metric, attempt_num=new_attempt_num)
            self.output_result()


class TaskWorker(Thread):
    def __init__(self, threadname, queue):
        Thread.__init__(self, name=threadname)
        self.queue = queue
        self.threadname = threadname

    def run(self):
        # loop infinitely, breaking when the queue is out of work (should add a timeout!)
        log.logger.info(f'Taskworker with thread {self.threadname} has started')
        log.logger.info(f'Taskworker says queue has {self.queue.qsize()} tasks')
        while not self.queue.empty():
            # Get the task from the queue and run it
            task = self.queue.get()
            log.logger.debug(f'Taskworker got task {task}')

            # process the task
            try:
                task.execute()
            except Exception as e:
                errortext = f'{e}, {sys.exc_info()}'
                log.logger.error(errortext)
                task.error_text = errortext
                continue


class ThreadSafeCSVWriter(object):
    def __init__(self, *args, **kwargs):
        self._writer = csv.writer(*args, **kwargs)
        self._lock = threading.Lock()

    def writerow(self, row):
        with self._lock:
            return self._writer.writerow(row)

    def writerows(self, rows):
        with self._lock:
            return self._writer.writerows(rows)


def getViews(servername):
    # return a list of views found on a given server, site, project, and with a particular name
    views = []
    return_list = []
    sites = getSites(servername)

    for site in sites:
        if args.si:
            # if filtered to a site, skip all but the one we want
            if site.name != args.si:
                continue

        tableau_auth = TSC.TableauAuth(args.u, password, site_id=site.content_url)
        server = TSC.Server(servername)
        server.add_http_options({'verify': False})
        server.version = APIVERSION

        with server.auth.sign_in(tableau_auth):
            log.logger.info(f"signed in to {servername}, {site.name}, {site.content_url}, {site.state}")
            req_option = TSC.RequestOptions()

            # get the server information
            server_info = server.server_info.get()

            # if workbook name passed, filter on it
            if args.wi:
                req_option.filter.add(TSC.Filter(TSC.RequestOptions.Field.Name,
                                                 TSC.RequestOptions.Operator.Equals,
                                                 args.wi))

            # if filtering by project, add that criteria
            if args.pi:
                req_option.filter.add(TSC.Filter(TSC.RequestOptions.Field.ProjectName,
                                                 TSC.RequestOptions.Operator.Equals,
                                                 args.pi))

            if args.wi or args.pi:
                # get the filtered workbooks, then derive the views from them
                filtered_workbooks = list(TSC.Pager(server.workbooks, req_option))
                filtered_views = []
                for workbook in filtered_workbooks:
                    server.workbooks.populate_views(workbook)
                    filtered_views.extend(workbook.views)
                    log.logger.debug(f'Found {len(filtered_views)} views')
            else:
                # no filtering, so just grab all the views on the site
                filtered_views = list(TSC.Pager(server.views))

            # if filtering by file, remove any non-matches
            if args.vi:
                log.logger.debug(f'filtering views to those provided in {args.vi}')
                view_list = []
                with open(args.vi, newline='') as view_list_file:
                    view_list_reader = csv.reader(view_list_file)
                    log.logger.debug('iterating over the views found')
                    for line in view_list_reader:
                        view_list.append(line[0])

                file_filtered_views = []
                for view in filtered_views:
                    for luid in view_list:
                        if view.id == luid:
                            file_filtered_views.append(view)
                log.logger.debug(f'will run over {len(file_filtered_views)} views')
                time.sleep(5)
                filtered_views = file_filtered_views

        log.logger.debug(f'Final count is {len(filtered_views)} views')

        # now package up the return list views with their contextual information
        for view in filtered_views:
            return_list.append(SiteView(view, site, server, server_info))
        # views.append({"site_content_url": site.content_url, "views": filtered_views})

    return return_list


def makePath(path):
    if not os.path.exists(path):
        os.makedirs(path)


def enqueueCompareViewTasks(site_view_list_a, site_view_list_b):
    # compare and match two lists of SiteViews, returning a list of view pairs that match in a dict
    view_pair_site_list = []

    for site_view_a in site_view_list_a:
        for site_view_b in site_view_list_b:
            # match views
            if (args.mm == 'luid' and site_view_a.view.id == site_view_b.view.id) or \
                    (args.mm == 'content_url' and site_view_a.view.content_url == site_view_b.view.content_url):
                if args.cv:
                    enqueueCompareViewTask(site_view_a, site_view_b, 'png', args.cm)
                if args.cd:
                    enqueueCompareViewTask(site_view_a, site_view_b, 'csv')


def enqueueCompareViewTask(site_view_a, site_view_b, render_type, compare_metric=None, attempt_num=0):
    # add a pair of views to the queue for comparison
    view_render_a = ViewRenderer(site_view_a, render_type, attempt_num)
    view_render_b = ViewRenderer(site_view_b, render_type, attempt_num)
    #    def __init__(self, view_render_a, view_render_b, diff_filepath, compare_metric=None, attempt_num=0):
    compare_task = CompareTask(view_render_a, view_render_b,
                               f"{view_render_a.getOutputFilePath(server_name='differences', diff=True)}",
                               compare_metric, attempt_num)
    log.logger.info(f"Enqueuing new render pair task of type PNG for {site_view_a.view.id}, {site_view_b.view.id}")
    task_queue.put(compare_task)


if __name__ == '__main__':
    APIVERSION = "3.10"
    main()
