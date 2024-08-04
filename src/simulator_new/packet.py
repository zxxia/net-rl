class Packet:
    DATA_PKT = "data"
    ACK_PKT = "ack"

    def __init__(self, pkt_id, pkt_type, size_bytes: int, app_data) -> None:
        self.pkt_id = pkt_id
        self.pkt_type = pkt_type
        self.size_bytes = size_bytes
        self.prop_delay_ms = 0
        self.queue_delay_ms = 0
        self.ts_sent_ms = 0
        self.ts_first_sent_ms = 0
        self.ts_rcvd_ms = 0
        self.data_pkt_ts_sent_ms = 0
        self.acked_size_bytes = 0
        self.app_data = app_data
        self.pacing_rate_Bps = 0  # pacing rate when sent
        self.ts_prev_pkt_sent_ms = 0
        self.ts_prev_pkt_rcvd_ms = 0

    def add_prop_delay_ms(self, delay_ms: int) -> None:
        """Add to the propagation delay."""
        self.prop_delay_ms += delay_ms

    def add_queue_delay_ms(self, delay_ms: int) -> None:
        """Add to the queue delay"""
        self.queue_delay_ms += delay_ms

    def delay_ms(self):
        return self.queue_delay_ms + self.prop_delay_ms

    def is_data_pkt(self):
        return self.pkt_type == self.DATA_PKT

    def is_ack_pkt(self):
        return self.pkt_type == self.ACK_PKT

    def rtt_ms(self):
        assert self.pkt_type == Packet.ACK_PKT
        return self.ts_rcvd_ms - self.data_pkt_ts_sent_ms


class TCPPacket(Packet):
    def __init__(self, pkt_id: int, pkt_type, pkt_size_bytes, app_data):
        super().__init__(pkt_id, pkt_type, pkt_size_bytes, app_data)
        self.delivered_byte = 0
        self.delivered_time_ms = 0
        self.is_app_limited = False
        self.in_fast_recovery_mode = False


class RTPPacket(Packet):
    DATA_PKT = "RTP"
    ACK_PKT = "RTCP"
    NACK_PKT = "NACK"
    def __init__(self, pkt_id, pkt_type, size_bytes: int, app_data) -> None:
        super().__init__(pkt_id, pkt_type, size_bytes, app_data)
        self.estimated_rate_Bps = 0
        self.loss_fraction = 0.0
        self.tput_Bps = 0.0
        self.owd_ms = 0
        self.delay_interval_ms = 0
        self.probe_info = {}

    def is_rtcp_pkt(self):
        return self.pkt_type == self.ACK_PKT

    def is_rtp_pkt(self):
        return self.pkt_type == self.DATA_PKT

    def is_nack_pkt(self):
        return self.pkt_type == self.NACK_PKT
