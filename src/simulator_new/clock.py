from abc import ABC, abstractmethod

class ClockObserver(ABC):
    @abstractmethod
    def tick(self, ts_ms):
        """Set a clock to a timestamp."""
        pass

    @abstractmethod
    def reset(self):
        pass

