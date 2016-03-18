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

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

#from ansible.plugins.callback import CallbackBase
import json
import os

class Event(object):

    def __init__(self, title, tag, alert_type, text='', host=None, extra_vars=None):

        self.title = title
        self.tag = tag
        self.alert_type = alert_type
        self.text = text
        self.host = host
        self.extra_vars = extra_vars

    def serialize(self):

        event = {
            'extra_vars': self.extra_vars,
            'host': self.host,
            'text': self.text,
            'alert_type': self.alert_type,
            'tag': self.tag,
            'title': self.title
        }
        return json.dumps(event)

    def flush(self, stream):
        stream.write(self.serialize() + "\n")
        stream.flush()

#class CallbackModule(CallbackBase):
class CallbackModule(object):

    #CALLBACK_VERSION = 2.0
    #CALLBACK_TYPE = 'notify'
    #CALLBACK_NAME = 'eventstream'

    def __init__(self):

        super(CallbackModule, self).__init__()

        self.pipe = "/tmp/eventstream"

    def setup_stream(self):

        if not os.path.exists(self.pipe):
            os.mkfifo(self.pipe)

        self.stream = open(self.pipe, 'w+')

    def close_stream(self):
        self.stream.close()


    #v2.x Callback Methods ------------------------------

    def v2_runner_on_failed(self, result, ignore_errors=False):

        #Task Run Failed for specific Host
        e = Event(title='TASK: Errored',
                  tag='errored',
                  alert_type='error',
                  text=result._result,
                  host=result._host.get_name(),
                  extra_vars=self.extra_vars)

        e.flush(self.stream)

    def v2_runner_on_ok(self, result):

        #Task Run Succeeded for specific Host
        changed = 'Changed' if result._result.pop('Changed', False) else 'ok'

        if 'module_name' in result._result['invocation']:
            module_name = result._result['invocation']['module_name']
        else:
            module_name = ''

        e = Event(title='TASK %s: %s' % (changed, module_name),
                  tag=changed,
                  alert_type='info',
                  text=result._result,
                  host=result._host.get_name(),
                  extra_vars=self.extra_vars)

        e.flush(self.stream)

    def v2_runner_on_skipped(self, result):

        #Task Run Skipped for specific Host
        e = Event(title='TASK: Skipped',
                  tag='skipped',
                  alert_type='info',
                  text="Item: '%s'" % self._get_item(getattr(result._result,'results',{})),
                  host=result._host.get_name(),
                  extra_vars=self.extra_vars)

        e.flush(self.stream)

    def v2_runner_on_unreachable(self, result):

        #Task Run Host Unreachable
        e = Event(title='TASK: Host Unreachable: %s' % result._host.get_name(),
                  tag='unreachable',
                  alert_type='error',
                  text=result._result,
                  host=result._host.get_name(),
                  extra_vars=self.extra_vars)

        e.flush(self.stream)


    def v2_playbook_on_start(self, playbook):

        plays = playbook.get_plays()
        if len(plays) > 0:
            vm = plays[0].get_variable_manager()
            self.extra_vars = vm._extra_vars

        #Check to see if user supplied named pipe location?
        #If so, use it.
        if 'pipe' in self.extra_vars:
            self.pipe = self.extra_vars['pipe']

        self.setup_stream()

        data = {
            'plays':len(playbook._entries),
        }

        #Playbook Started
        e = Event(title='PLAYBOOK: Started',
                  tag='playbook_start',
                  alert_type='info',
                  text=json.dumps(data),
                  extra_vars=self.extra_vars)

        e.flush(self.stream)


    def v2_playbook_on_task_start(self, task, is_conditional):

        #Task Started
        e = Event(title=task.get_name(),
                  tag='task_start',
                  alert_type='info',
                  extra_vars=self.extra_vars)

        e.flush(self.stream)


    def v2_playbook_on_play_start(self, play):

        vm = play.get_variable_manager()

        task_count = len(play.get_tasks()[0])

        #Add implicit task for fact gathering if appropriate
        if play.gather_facts or play.gather_facts is None:
            task_count = task_count + 1

        data = {
            'tasks':task_count,
            'hosts':len(vm._inventory.get_hosts())
        }

        #Play Started
        e = Event(title="PLAY: Started [%s]" % play.name,
                  tag='play_start',
                  alert_type='info',
                  text=json.dumps(data),
                  extra_vars=self.extra_vars)

        e.flush(self.stream)


    def v2_playbook_on_stats(self, stats):

        data = {
            'processed': stats.processed,
            'ok': stats.ok,
            'changed': stats.changed,
            'dark': stats.dark,
            'failures': stats.failures,
            'skipped': stats.skipped
        }

        #Playbook Finished
        e = Event(title='PLAYBOOK: Complete',
                  tag='playbook_complete',
                  alert_type='info',
                  extra_vars=self.extra_vars,
                  text=json.dumps(data))

        e.flush(self.stream)
        self.close_stream()


    #v1.x Callback Methods ------------------------------

    def playbook_on_start(self):

        #Check to see if user supplied named pipe location?
        #If so, use it.
        if 'pipe' in self.playbook.extra_vars:
            self.pipe = self.playbook.extra_vars['pipe']

        self.setup_stream()

        data = {
            'plays':len(self.playbook.playbook),
        }

        #Playbook Started
        e = Event(title='PLAYBOOK: Started',
                  tag='playbook_start',
                  alert_type='info',
                  text=json.dumps(data),
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)

    def playbook_on_play_start(self, name):

        playbook = self.playbook.playbook[0]

        task_count = 0

        for task in self.play._ds['tasks']:
            if 'action' in task:
                task_count = task_count + 1

        #Add implicit task for fact gathering if appropriate
        if 'gather_facts' in playbook and playbook['gather_facts'] or 'gather_facts' not in playbook:
           task_count = task_count + 1

        data = {
            'tasks':task_count
        }

        #Play Started
        e = Event(title="PLAY: Started [%s]" % self.play.name,
                  tag='play_start',
                  alert_type='info',
                  text=json.dumps(data),
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)

    def playbook_on_task_start(self, name, is_conditional):

        #Task Started
        e = Event(title=name,
                  tag='task_start',
                  alert_type='info',
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)


    def runner_on_failed(self, host, res, ignore_errors=False):

        #Task Run Failed for specific Host
        e = Event(title='TASK: Errored',
                  tag='errored',
                  alert_type='error',
                  text=res['msg'],
                  host=host,
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)


    def runner_on_ok(self, host, res):

        #Task Run Succeeded for specific Host
        changed = 'Changed' if res.pop('Changed', False) else 'ok'

        if 'module_name' in res['invocation']:
            module_name = res['invocation']['module_name']
        else:
            module_name = ''

        e = Event(title='TASK %s: %s' % (changed, module_name),
                  tag=changed,
                  alert_type='info',
                  text=json.dumps(res),
                  host=host,
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)


    def runner_on_skipped(self, host, item=None):

        #Task Run Skipped for specific Host
        e = Event(title='TASK: Skipped',
                  tag='skipped',
                  alert_type='info',
                  text="Item: %s" % item,
                  host=host,
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)


    def runner_on_unreachable(self, host, res):

         #Task Run Host Unreachable
        e = Event(title='TASK: Host Unreachable: %s' % host,
                  tag='unreachable',
                  alert_type='error',
                  text=res,
                  host=host,
                  extra_vars=self.playbook.extra_vars)

        e.flush(self.stream)


    def playbook_on_stats(self, stats):

        data = {
            'processed': stats.processed,
            'ok': stats.ok,
            'changed': stats.changed,
            'dark': stats.dark,
            'failures': stats.failures,
            'skipped': stats.skipped
        }

        #Playbook Finished
        e = Event(title='PLAYBOOK: Complete',
                  tag='playbook_complete',
                  alert_type='info',
                  extra_vars=self.playbook.extra_vars,
                  text=json.dumps(data))

        e.flush(self.stream)
        self.close_stream()