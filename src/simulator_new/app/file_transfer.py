from simulator_new.app import Application

class FileSender(Application):
    def __init__(self):
        super().__init__()

    def has_data(self) -> bool:
        return True

    def get_pkt(self):
        return 1500, {}

    def deliver_pkt(self, pkt):
        return

    def tick(self, ts_ms):
        return

    def reset(self):
        return

class FileReceiver(Application):
    def __init__(self):
        super().__init__()

    def has_data(self) -> bool:
        return False

    def get_pkt(self):
        return 0, {}

    def deliver_pkt(self, pkt):
        return

    def tick(self, ts_ms):
        return

    def reset(self):
        return
