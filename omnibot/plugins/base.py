from abc import ABCMeta
import logging

from setproctitle import setproctitle

log = logging.getLogger(__name__)


def get_plugins():
    """
      Find all the subclasses of Daemon
      :returns: A dictionary of daemon names and the corresponding class
    """
    plugins = dict()
    for cls in Plugin.__subclasses__():
        if cls.name != "base":
            plugins[cls.name] = cls
    return plugins


class Plugin(object):
    """
      Base class for bot plugins/ integrations
      :ivar SlackClient slack_client: The instance of SlackClient to use
    """
    __metaclass__ = ABCMeta
    nae = "base"

    def __init__(self):
        if not hasattr(self, 'name'):
            self.name = self.__class__.__name__

    @classmethod
    def process(self, slack_client, event_type, event):
        self.slack_client = slack_client
        try:
            func = getattr(self, "process_{0}".format(event_type))
        except AttributeError:
            pass
        else:
            try:
                log.debug("Attempting to run plugin: `{0}`, function: `{1}`".format(self.name, event_type))
                func(event)
            except:
                log.exception("Unable to execute plugin: `{0}`, function: `{1}`".format(self.name, event_type))

    @classmethod
    def determine_request(self, name):
        if self.command_word() is None:
            return True
        if type(self.command_word()) == list and str(name) in self.command_word():
            return True
        elif type(self.command_word()) == str and str(name) == self.command_word():
            return True
        else:
            return False
 
    @classmethod
    def plugin_word(self):
        """
          The command word to give grab the plugin's attention
          This can be a single string, a list of command words (strings) or None to listen to everything
        """
        raise NotImplementedError

    @classmethod
    def info_text(self):
        """
          Base helper function
        """
        return "No help given. Sorry :("
