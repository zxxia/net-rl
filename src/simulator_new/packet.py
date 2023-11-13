class Packet:
    def __init__(self, pkt_type, size_bytes: int) -> None:
        self.pkt_id = 0
        self.pkt_type = pkt_type
        self.size_bytes = size_bytes
        self.prop_delay_ms = 0
        self.queue_delay_ms = 0
        self.ts_sent_ms = 0

    def add_prop_delay_ms(self, delay_ms: int) -> None:
        """Add to the propagation delay and add to the timestamp too."""
        self.prop_delay_ms += delay_ms

    def add_queue_delay_ms(self, delay_ms: int) -> None:
        """Add to the queue delay and add to the timestamp too."""
        self.queue_delay_ms += delay_ms

    def cur_delay_ms(self):
        return self.queue_delay_ms + self.prop_delay_ms
