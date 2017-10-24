import logging
import socket

from .base import Plugin

log = logging.getLogger(__name__)


class AboutPlugin(Plugin):
    name = "about"

    def process_message(self, event):
        log.info("about")
        return socket.getfqdn()

    @classmethod
    def command_word(self):
        return "about"
