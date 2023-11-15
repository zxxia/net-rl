class CongestionControl:
    def __init__(self) -> None:
        pass

    def can_send(self):
        return True

    def on_pkt_sent(self, pkt):
        pass

    def on_pkt_acked(self, pkt):
        pass
