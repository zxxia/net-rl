class Packet:
    DATA_PKT = "data"
    ACK_PKT = "ack"

    def __init__(self, pkt_type, size_bytes: int, app_data) -> None:
        self.pkt_id = 0
        self.pkt_type = pkt_type
        self.size_bytes = size_bytes
        self.prop_delay_ms = 0
        self.queue_delay_ms = 0
        self.ts_sent_ms = 0
        self.app_data = app_data

    def add_prop_delay_ms(self, delay_ms: int) -> None:
        """Add to the propagation delay."""
        self.prop_delay_ms += delay_ms

    def add_queue_delay_ms(self, delay_ms: int) -> None:
        """Add to the queue delay"""
        self.queue_delay_ms += delay_ms

    def cur_delay_ms(self):
        return self.queue_delay_ms + self.prop_delay_ms

    def is_data_pkt(self):
        return self.pkt_type == self.DATA_PKT

    def is_ack_pkt(self):
        return self.pkt_type == self.ACK_PKT
