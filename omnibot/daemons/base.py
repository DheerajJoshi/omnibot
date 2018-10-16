from abc import ABCMeta
import logging
from time import sleep, time

from setproctitle import setproctitle

log = logging.getLogger(__name__)


def get_daemons():
    """
      Find all the subclasses of Daemon
      :returns: A dictionary of daemon names and the corresponding class
    """
    plugins = dict()
    for cls in Daemon.__subclasses__():
        if cls.name != "base":
            plugins[cls.name] = cls
    return plugins


class Daemon(object):
    """
      Daemons can be used to trigger periodic method calls.

      :ivar SlackClient slack_client: The instance of SlackClient to use
    """
    __metaclass__ = ABCMeta
    name = "base"

    # Interval to ran the job at
    interval = 60

    def __init__(self):
        if not hasattr(self, 'name'):
            self.name = self.__class__.__name__
        self.lastrun = 0
        setproctitle("omnibot [{0}]".format(self.name))

    def __str__(self):
        """
          String representation of the daemon
        """
        return "Daemon:{} Interval:{}secs LastRun:{}".format(self.__class__, self.interval, self.lastrun)

    def __repr__(self):
        """
          REPR representation of the daemon
        """
        return self.__str__()

    def run(self):
        """
          The periodic method to run
        """
        raise NotImplementedError

    def main(self, slack_client):
        """
          This method is called when the process it's started.
          It ensures that we run the task at the right interval
        """
        self.slack_client = slack_client

        # Sleep for 10s to ensure everything is setup correct
        sleep(10)

        # Infinitely loop
        while True:
            # Check if the process task should be run again
            if self.lastrun + self.interval < time():
                # Run the task
                self.run()
                self.lastrun = time()
