#!/usr/bin/env python
from __future__ import unicode_literals
import logging
import os
from multiprocessing import Process
import signal
import socket
import sys
import time

from setproctitle import setproctitle
from slackclient import SlackClient

from daemons.base import get_daemons
from plugins.base import get_plugins

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s [%(processName)s:%(process)d] %(message)s')
IGNORED_EVENT_TYPES = ['hello', 'pong', 'reconnect_url']
main_process_pid = os.getpid()


class OmniBot(object):
    def __init__(self, config):
        # Set the process title 
        setproctitle("omnibot [manager]")

        # set the config object
        self.config = config

        # set slack token
        self.token = config.get('SLACK_TOKEN', None)
        if not self.token:
            raise ValueError("Please add a SLACK_TOKEN to your config file.")

        # Setup https proxy if required
        if self.config.get("PROXY", None) is not None:
            self.proxy = {"http": self.config.get("PROXY"),
                          "https": self.config.get("PROXY")}
        else:
            self.proxy = None

        # initialize stateful fields
        self.bot_id = None
        self.last_ping = 0
        self.connected = False
        self.bot_daemons = {}
        self.bot_plugins = {}
        self.daemon_processes = []
        self.keep_running = True
        self.slack_client = SlackClient(self.token, self.proxy)

    def ping(self):
        """
          Ping the Slack websocket to let them know we're alive
        """
        now = int(time.time())
        if now > self.last_ping + 3:
            log.debug("Sending Ping")
            # Try to ping the Websocket to keep it alive
            try:
                self.slack_client.server.ping()
                self.last_ping = now
            # If we cannot ping, try to reconnect
            except:
                log.error("Bot has been disconnected from Slack")
                self.connected = False
                self.connect()

    def connect(self):
        """
          Convenience method that creates Server instance
        """
        while self.connected is False:
            log.info("Connecting to Slack")
            self.connected = self.slack_client.rtm_connect()
            time.sleep(5)
        log.info("Connected to Slack")

    def determine_bot_id(self, username):
        """
          Determine the ID of the Slack Bot User
        """
        user_list = self.slack_client.api_call('users.list')
        for user in user_list['members']:
            if user['name'] == username:
                return user['id']
        log.error("Could not find Bot ID")

    def load_daemons(self):
        """
          Load and start the background daemons
        """
        self.bot_daemons = get_daemons()
        log.info("Discovered the following daemons: {0}".format([p for p in sorted(self.bot_daemons.keys())]))
        for daemon in self.bot_daemons.values():
            job = daemon(self.slack_client)
            child = Process(name=daemon.name, target=job.main)
            child.daemon = True
            log.info("Starting background daemon: {0} with an interval of {1}secs".format(daemon.name, job.interval))
            child.start()
            self.daemon_processes.append(child)

    def load_plugins(self):
        """
          Discovery bot plugins
        """
        self.bot_plugins = get_plugins()
        log.info("Discovered the following plugins: {0}".format([p for p in sorted(self.bot_plugins.keys())]))

    def process_event(self, event):
        """
          Find the right integration to handle the request 
        """
        # Try to extract the new event type
        if "type" in event:
            event_type = event['type']
            # Process standard messages
            if event_type == "message":
                # Ensure we aren't infinitely responding to the bot itself
                if "bot_id" not in event:
                    for plugin in self.bot_plugins.values():
                        if event['text'].split()[0] == "<@{0}>".format(self.bot_id) and plugin.determine_request(event['text'].split()[1]):
                            plugin = plugin(self.slack_client, event_type, event)
                            plugin.process()
            # Process other type of event types
            elif event_type not in IGNORED_EVENT_TYPES:
                for plugin in self.bot_plugins.values():
                    plugin = plugin(self.slack_client, event_type, event)
                    plugin.process()
 
    def setup_signal_handler(self):
        """
          Setup signal handlers for HUP, INT, TERM signals
        """
        log.debug("Registering signal handlers")
        signal.signal(signal.SIGINT, self.int_handler)
        signal.signal(signal.SIGTERM, self.term_handler)
        log.debug("Completed setting up signal handlers")

    def int_handler(self, frame, num):
        """
          Sets exit flag
        """
        log.info("Caught INT signal.")
        self.shutdown()
 
    def term_handler(self, frame, num):
        """
          Sets exit flag
        """
        log.info("Caught TERM signal.")
        self.shutdown()
            
    def run(self):
        """
          Main process
        """
        # Setup signal handlers
        self.setup_signal_handler()

        # Connect to Slack
        self.connect()

        # Determine the ID of the Slack bot
        self.bot_id = self.determine_bot_id(self.slack_client.server.username)

        # Ping just incase it took a long time to connect to Slack
        self.ping()

        # Load bot plugins
        self.load_plugins()

        # Load daemons
        self.load_daemons()
 
        # Run forever
        while self.keep_running:
            # Read an event from the web-socket
            for event in self.slack_client.rtm_read():
                log.debug("Incoming event: {0}".format(event))
                # Process the event
                self.process_event(event)

            # See if we need to ping Slack
            self.ping()

            self._reap_children()

    def _reap_children(self):
        """
          Clean up dead processes that haven't been reaped
        """

        dead = [child for child in self.daemon_processes if not child.is_alive()]
        self.daemon_processes = [child for child in self.daemon_processes if child.is_alive()]

        for child in dead:
            log.warn("Reaping {0} PID {1} with exit code {2}".format(child.pid, child.name, child.exitcode))
            child.join(0.1)
        return

    def shutdown(self):
        """
          Shut down the bot
        """
        log.info("Disabling run loop")
        self.keep_running = False
        time.sleep(1)
        log.info("Disconnecting from Slack")
        self.slack_client.server.websocket.shutdown()
        log.info("Shutting down")
        sys.exit(0)
