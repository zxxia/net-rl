from simulator_new.cc import BBRv1
from simulator_new.constant import TCP_INIT_CWND_BYTE
from simulator_new.host import Host
from simulator_new.packet import TCPPacket


class ConnectionState:
    def __init__(self):
        # Connection state used to estimate rates
        # The total amount of data (tracked in octets or in packets) delivered
        # so far over the lifetime of the transport connection.
        self.delivered_byte = 0

        # The wall clock time when C.delivered was last updated.
        self.delivered_time_ms = 0

        # If packets are in flight, then this holds the send time of the packet
        # that was most recently marked as delivered.  Else, if the connection
        # was recently idle, then this holds the send time of most recently
        # sent packet.
        self.first_sent_time_ms = 0

        # The index of the last transmitted packet marked as
        # application-limited, or 0 if the connection is not currently
        # application-limited.
        self.app_limited = 0

        # The data sequence number one higher than that of the last octet
        # queued for transmission in the transport layer write buffer.
        self.write_seq = 0

        # The number of bytes queued for transmission on the sending host at
        # layers lower than the transport layer (i.e. network layer, traffic
        # shaping layer, network device layer).
        self.pending_transmissions = 0

        # The number of packets in the current outstanding window
        # that are marked as lost.
        self.lost_out = 0

        # The number of packets in the current outstanding
        # window that are being retransmitted.
        self.retrans_out = 0

        # The sender's estimate of the number of packets outstanding in
        # the network; i.e. the number of packets in the current outstanding
        # window that are being transmitted or retransmitted and have not been
        # SACKed or marked lost (e.g. "pipe" from [RFC6675]).
        self.pipe_byte = 0


class RateSample:
    def __init__(self):

        # The delivery rate sample (in most cases rs.delivered / rs.interval).
        self.delivery_rate_Bps = 0.0
        # The P.is_app_limited from the most recent packet delivered; indicates
        # whether the rate sample is application-limited.
        self.is_app_limited = False
        # The length of the sampling interval.
        self.interval_ms = 0
        # The amount of data marked as delivered over the sampling interval.
        self.delivered_byte = 0
        # The P.delivered count from the most recent packet delivered.
        self.prior_delivered_byte = 0
        # The P.delivered_time from the most recent packet delivered.
        self.prior_time_ms = 0
        # Send time interval calculated from the most recent packet delivered
        # (see the "Send Rate" section above).
        self.send_elapsed_ms = 0
        # ACK time interval calculated from the most recent packet delivered
        # (see the "ACK Rate" section above).
        self.ack_elapsed_ms = 0
        # in flight before this ACK
        self.prior_bytes_in_flight = 0
        # number of packets marked lost upon ACK
        self.losses = 0
        self.pkt_in_fast_recovery_mode = False


class TCPHost(Host):
    """Simulate TCP behavior
    srtt reference: https://datatracker.ietf.org/doc/html/rfc6298
    """

    SRTT_ALPHA = 1 / 8
    SRTT_BETA = 1 / 4
    RTO_K = 4

    def __init__(self, id, tx_link, rx_link, cc, rtx_mngr, app) -> None:
        self.bytes_in_flight = 0
        self.rtt_min_ms = None
        self.srtt_ms = 0
        self.rttvar_ms = 0
        assert isinstance(cc, BBRv1)
        self.cwnd_byte = TCP_INIT_CWND_BYTE
        self.conn_state = ConnectionState()
        self.rs = RateSample()
        super().__init__(id, tx_link, rx_link, cc, rtx_mngr, app)
        self.pkt_cls = TCPPacket

    def can_send(self, pkt_size_byte):
        return self.bytes_in_flight < self.cwnd_byte and self.pacer.can_send(pkt_size_byte)

    def _on_pkt_sent(self, ts_ms, pkt):
        if self.bytes_in_flight == 0:
            self.conn_state.first_sent_time_ms = ts_ms
            self.conn_state.delivered_time_ms = ts_ms
        pkt.ts_first_sent_ms = self.conn_state.first_sent_time_ms
        pkt.delivered_time_ms = self.conn_state.delivered_time_ms
        pkt.delivered_byte = self.conn_state.delivered_byte
        pkt.is_app_limited = (self.conn_state.app_limited != 0)
        self.bytes_in_flight += pkt.size_bytes

    def _on_pkt_acked(self, ts_ms, data_pkt, ack_pkt):
        self.bytes_in_flight -= ack_pkt.acked_size_bytes
        rtt_ms = ack_pkt.rtt_ms()
        if self.rtt_min_ms is None:
            self.rtt_min_ms = rtt_ms
        else:
            self.rtt_min_ms = min(rtt_ms, self.rtt_min_ms)
        if self.srtt_ms == 0 and self.rttvar_ms == 0:
            self.srtt_ms = rtt_ms
            self.rttvar_ms = rtt_ms / 2
        elif self.srtt_ms and self.rttvar_ms:
            self.srtt_ms = (1 - self.SRTT_ALPHA) * self.srtt_ms + \
                self.SRTT_ALPHA * ack_pkt.rtt_ms()
            self.rttvar_ms = (1 - self.SRTT_BETA) * self.rttvar_ms + \
                self.SRTT_BETA * abs(self.srtt_ms - rtt_ms)
        else:
            raise ValueError("srtt and rttvar should be both 0 or both non-zeros.")
        rto_ms = max(1000, min(self.srtt_ms + self.RTO_K * self.rttvar_ms, 60000))
        self._generate_rate_sample(ts_ms, data_pkt)

    def reset(self) -> None:
        self.bytes_in_flight = 0
        self.srtt_ms = 0
        self.rttvar_ms = 0
        self.rtt_min_ms = None
        self.cwnd_byte = TCP_INIT_CWND_BYTE
        self.conn_state = ConnectionState()
        self.rs = RateSample()
        super().reset()

    # Upon receiving ACK, fill in delivery rate sample rs.
    def _generate_rate_sample(self, ts_ms, pkt: TCPPacket):
        # for each newly SACKed or ACKed packet P:
        #     self.update_rate_sample(P, rs)
        # fix the btlbw overestimation bug by not updating delivery_rate
        self._update_rate_sample(ts_ms, pkt)
            # return False

        # Clear app-limited field if bubble is ACKed and gone.
        if self.conn_state.app_limited and self.conn_state.delivered_byte > self.conn_state.app_limited:
            self.conn_state.app_limited = 0

        # TODO: need to recheck
        if self.rs.prior_time_ms == 0:
            return False  # nothing delivered on this ACK

        # Use the longer of the send_elapsed and ack_elapsed
        self.rs.interval_ms = max(self.rs.send_elapsed_ms, self.rs.ack_elapsed_ms)

        self.rs.delivered_byte = self.conn_state.delivered_byte - self.rs.prior_delivered_byte
        # print("C.delivered: {}, rs.prior_delivered: {}".format(self.delivered, self.rs.prior_delivered))

        # Normally we expect interval >= MinRTT.
        # Note that rate may still be over-estimated when a spuriously
        # retransmitted skb was first (s)acked because "interval"
        # is under-estimated (up to an RTT). However, continuously
        # measuring the delivery rate during loss recovery is crucial
        # for connections suffer heavy or prolonged losses.

        if self.rtt_min_ms and self.rs.interval_ms < self.rtt_min_ms:
            self.rs.interval_ms = -1
            return False  # no reliable sample
        # self.rs.pkt_in_fast_recovery_mode = pkt.in_fast_recovery_mode
        if self.rs.interval_ms != 0: #and not pkt.in_fast_recovery_mode:
            self.rs.delivery_rate_Bps = 1000 * self.rs.delivered_byte / self.rs.interval_ms

        return True  # we filled in rs with a rate sample

    # Update rs when packet is SACKed or ACKed.
    def _update_rate_sample(self, ts_ms, pkt: TCPPacket):
        # TODO: double check this line
        # comment out because we don't need this in the simulator.
        # if pkt.delivered_time == 0:
        #     return  # P already SACKed

        self.rs.prior_bytes_in_flight = self.bytes_in_flight
        self.conn_state.delivered_byte += pkt.size_bytes
        self.conn_state.delivered_time_ms = ts_ms

        # Update info using the newest packet:
        if pkt.delivered_byte > self.rs.prior_delivered_byte:
            self.rs.prior_delivered_byte = pkt.delivered_byte
            self.rs.prior_time_ms = pkt.delivered_time_ms
            self.rs.is_app_limited = pkt.is_app_limited
            self.rs.send_elapsed_ms = pkt.ts_sent_ms - pkt.ts_first_sent_ms
            self.rs.ack_elapsed_ms = self.conn_state.delivered_time_ms - pkt.delivered_time_ms
            # print("pkt.sent_time:", pkt.sent_time, "pkt.first_sent_time:", pkt.first_sent_time, "send_elapsed:", self.rs.send_elapsed)
            # print("C.delivered_time:", self.conn_state.delivered_time, "P.delivered_time:", pkt.delivered_time, "ack_elapsed:", self.rs.ack_elapsed)
            self.conn_state.first_sent_time_ms = pkt.ts_sent_ms
            # return True
        # return False
        # pkt.debug_print()

        # Mark the packet as delivered once it's SACKed to
        # avoid being used again when it's cumulatively acked.

        # TODO: double check this line
        # pkt.delivered_time = 0
