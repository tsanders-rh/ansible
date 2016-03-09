#! /usr/bin/env python
#
# Copyright (c) 2016 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

#
#Imports
#

import os
import sys
import json
import time
from gettext import gettext as _
from optparse import OptionParser
from progress.bar import Bar #https://github.com/verigak/progress

#
#Constants
#

USAGE = _('%prog <options>')

DESCRIPTION = _('Start a fifo reader that will process an Ansible event stream.')

DISPLAY = _('Set the display mode.  Valid options are: raw or pretty.')

PIPE = _('Set the location of the fifo pipe for reading events.')

FIFO_PATH = '/tmp/eventstream'

SUFFIX = '%(index)d/%(max)d [%(elapsed)d secs elapsed]'

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    CYAN = '\033[36m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def get_options():
    '''
    Parse and return command line options.
    Sets defaults and validates options.
    '''

    parser = OptionParser(usage=USAGE, description=DESCRIPTION)
    parser.add_option("-d", "--display", help=DISPLAY)
    parser.add_option("-p", "--pipe", help=PIPE)

    (opts, args) = parser.parse_args()

    # validate
    if opts.display is not None:
        if (opts.display != "raw") and (opts.display != "pretty"):
            print "Please enter a valid display option.  (see -h for help)"
            sys.exit(1)
    return opts

def banner(msg, color=None):
    '''
    Prints a header-looking line with stars taking up to 80 columns
    of width (3 columns, minimum)
    '''

    msg = msg.strip()
    star_len = (79 - len(msg))
    if star_len < 0:
        star_len = 3
    stars = "*" * star_len

    if color:
        return "\n%s%s %s%s" % (color, msg, stars, bcolors.ENDC)
    else:
        return "\n%s %s" % (msg, stars)


def output_statistics(statistics):
    '''
    Outputs the playbook run statistics.
    '''

    output = ''

    #get statistics
    processed = json.loads(statistics)['processed']
    ok = json.loads(statistics)['ok']
    changed = json.loads(statistics)['changed']
    dark = json.loads(statistics)['dark']
    failures = json.loads(statistics)['failures']
    skipped = json.loads(statistics)['skipped']

    #output stats for every host
    for key in processed:

        output += key

        if key in ok:
            output +=  "\t:" + bcolors.OKGREEN +  "ok=" + str(ok[key]) + bcolors.ENDC
        else:
            output +=  "\t:ok=0"

        if key in changed:
            output += "\t" + bcolors.WARNING +  "changed=" + str(changed[key]) + bcolors.ENDC
        else:
            output +=  "\tchanged=0"

        if key in dark:
            output += "\t" + bcolors.FAIL +  "unreachable=" + str(dark[key]) + bcolors.ENDC
        else:
            output +=  "\tunreachable=0"

        if key in failures:
            output += "\t" + bcolors.FAIL +  "failed=" + str(failures[key]) + bcolors.ENDC
        else:
            output +=  "\tfailed=0"

        output += "\n"

    return output


def output_errors(error_list):
    '''
    Outputs the playbook run errors.
    '''

    output = ''

    for key in error_list:
        output += "[" + key + "] : " + bcolors.FAIL + error_list[key]['msg'] + bcolors.ENDC + "\n\n"

    return output

def raw(stream):
    '''
    Read from fifo pipe and output a raw event stream to stdout.
    '''

    try:
        while True:
            for line in iter(stream.readline, ""):
                event = json.loads(line)
                print json.dumps(event, sort_keys=True, indent=4)
                
    except KeyboardInterrupt:
       stream.flush()
       pass

def pretty(stream):
    '''
    Read from fifo pipe and output a formatted stream to stdout.
    '''

    progress = None
    started_tasks = 0
    error_messages = {}

    try:
        while True:
            for line in iter(stream.readline, ""):
                event = json.loads(line)

                if event['tag'] == 'playbook_start':
                    print banner(event['title'])
                    print bcolors.WARNING + "Contains: " + str(json.loads(event['text'])['plays']) + " Play(s)." + bcolors.ENDC

                elif event['tag'] == 'play_start':
                    num_tasks = json.loads(event['text'])['tasks']
                    print banner(event['title'])
                    print bcolors.WARNING + "Contains: " + str(json.loads(event['text'])['tasks']) +  \
                    " Task(s) for " + str(json.loads(event['text'])['hosts']) + " Host(s)." + bcolors.ENDC +  "\n"
                    print "TASK(s):"
                    progress = Bar("Processing...", max=num_tasks, suffix=SUFFIX)
                    progress.update()

                elif event['tag'] == 'task_start':

                    #Don't count fact collection in progress
                    if event['title'] != 'setup':

                        started_tasks = started_tasks + 1
                        if progress:
                            progress.message = event['title']
                            progress.update()
                            if started_tasks > 1:
                                progress.next()

                elif event['tag'] == 'playbook_complete':
                    if progress:
                        progress.next()
                        progress.finish()
                        print banner(event['title'])
                        print banner("RUN Statistics:")
                        print output_statistics(event['text'])

                        if len(error_messages) > 0:
                            print banner("RUN Errors:")
                            print output_errors(error_messages)

                elif event['tag'] == 'unreachable':
                    error_messages[event['host']] = event['text']

    except KeyboardInterrupt:
        stream.flush()
        stream.close()


def main():
    '''
    The command entry point.
    '''

    options = get_options()
    pipe = None

    if options.pipe:
        pipe = options.pipe
    else:
        pipe = FIFO_PATH

    #check to see if pipe exists
    if not os.path.exists(pipe):
        try:
            os.mkfifo(pipe)
        except OSError, e:
            print "Failed to create FIFO: %s" % e
            sys.exit(1)

    #open pipe for reading
    stream = open(pipe, 'r')

    #read from stream and output based on user preference
    if options.display and options.display == 'raw':
        raw(stream)
    else:
        pretty(stream)


## MAIN
if __name__ == "__main__":
    main()
