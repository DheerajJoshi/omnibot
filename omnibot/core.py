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


class OmniBot(object):
    def __init__(self, config):
        # Set the process title 
        setproctitle("omnibot [manager]")
        # TODO config for proxies

        # set the config object
        self.config = config

        # set slack token
        self.token = config.get('SLACK_TOKEN', None)
        if not self.token:
            raise ValueError("Please add a SLACK_TOKEN to your config file.")

        # initialize stateful fields
        self.last_ping = 0
        self.connected = False
        self.bot_daemons = {}
        self.bot_plugins = {}
        self.keep_running = True
        self.slack_client = SlackClient(self.token)

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
                for plugin in self.bot_plugins.values():
                    if plugin.determine_request(event['text'].split()[0]):
                        plugin.process(self.slack_client, "message", event)
            # Process other type of event types
            elif event_type not in IGNORED_EVENT_TYPES:
                for plugin in self.bot_plugins.values():
                    plugin.process(self.slack_client, event_type, event)

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
