from typing import Dict, Tuple
from simulator_new.clock import ClockObserver

from abc import abstractmethod

class Application(ClockObserver):
    def __init__(self):
        self.host = None

    @abstractmethod
    def peek_pkt(self) -> int:
        """Return the packet size at the front of application packet queue."""
        pass

    @abstractmethod
    def get_pkt(self) -> Tuple[int, Dict]:
        """Get a packet from the application to the transport layer"""
        pass

    @abstractmethod
    def deliver_pkt(self, pkt):
        """Deliver a packet from the transport layer to the application"""
        pass

    def register_host(self, host):
        self.host = host
