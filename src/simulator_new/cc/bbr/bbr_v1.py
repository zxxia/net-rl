import math
import random
from enum import Enum

from simulator_new.cc import TCPCongestionControl
from simulator_new.constant import BITS_PER_BYTE, MSS, TCP_INIT_CWND_BYTE
from simulator_new.packet import BBRPacket


# A constant specifying the minimum gain value that will
# allow the sending rate to double each round (2/ln(2) ~= 2.89), used
# in Startup mode for both BBR.pacing_gain and BBR.cwnd_gain.
BBR_HIGH_GAIN = 2.89

# A constant specifying the length of the BBR.BtlBw max
# filter window for BBR.BtlBwFilter, BtlBwFilterLen is
# 10 packet-timed round trips.
BTLBW_FILTER_LEN = 10  # packet-timed round trips.

# A constant specifying the minimum time interval
# between ProbeRTT states
RTPROP_FILTER_LEN_SEC = 10

# A constant specifying the minimum duration for which
# ProbeRTT state holds inflight to BBRMinPipeCwnd or
# fewer packets
PROBE_RTT_DURATION_MS = 200

# The minimal cwnd value BBR tries to target using
BBR_MIN_PIPE_CWND_BYTE = 4 * MSS

# the number of phases in the BBR ProbeBW gain cycle
BBR_GAIN_CYCLE_LEN = 8


class BBRMode(Enum):
    BBR_STARTUP = "BBR_STARTUP"  # ramp up sending rate rapidly to fill pipe
    BBR_DRAIN = "BBR_DRAIN"  # drain any queue created during startup
    BBR_PROBE_BW = "BBR_PROBE_BW"  # discover, share bw: pace around estimated bw
    BBR_PROBE_RTT = "BBR_PROBE_RTT"  # cut inflight to min to probe min_rtt


class BBRBtlBwFilter:
    def __init__(self, btlbw_filter_len: int):
        self.btlbw_filter_len = btlbw_filter_len
        self.cache = {}

    def update(self, delivery_rate: float, round_count: int) -> None:
        self.cache[round_count] = max(self.cache.get(round_count, 0), delivery_rate)
        if len(self.cache) > self.btlbw_filter_len:
            self.cache.pop(min(self.cache))

    def get_btlbw(self) -> float:
        if not self.cache:
            return 0
        return max(self.cache.values())


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
        self.delivery_rate_byte_per_sec = 0.0
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


class BBRv1(TCPCongestionControl):
    """

    Reference:
        https://datatracker.ietf.org/doc/html/draft-cardwell-iccrg-bbr-congestion-control-00
        https://datatracker.ietf.org/doc/html/draft-cheng-iccrg-delivery-rate-estimation#section-3.1.3
    """
    def __init__(self, seed: int):
        super().__init__()
        self.prng = random.Random(seed)

        self.conn_state = ConnectionState()
        self.rs = RateSample()
        self.btlbw_byte_per_sec = 0  # bottleneck bw in bytes/sec

        self.next_send_time_ms = 0

        self.pacing_gain = BBR_HIGH_GAIN

        self.target_cwnd_byte = 0

        self.in_fast_recovery_mode = False
        self.exit_fast_recovery_ts = -1
        self.limited_by_cwnd = False
        self.ts_ms = 0

        self._init()
        # self.bbr_log = []

    def register_host(self, host):
        super().register_host(host)
        self._init_pacing_rate()

    def can_send(self):
        # wait for ack or timeout
        return self.bytes_in_flight < self.cwnd_byte

    def on_pkt_sent(self, ts_ms, pkt):
        self._send_packet(ts_ms, pkt)
        super().on_pkt_sent(ts_ms, pkt)

    def on_pkt_acked(self, ts_ms, pkt):
        self._generate_rate_sample(ts_ms, pkt)
        super().on_pkt_acked(ts_ms, pkt)
        self._update_on_ack(pkt)

    def on_pkt_lost(self, ts_ms, pkt):
        raise NotImplementedError

    def tick(self, ts_ms):
        self.ts_ms = ts_ms
        pass

    def reset(self):
        super().reset()
        self.conn_state = ConnectionState()
        self.rs = RateSample()
        self.btlbw_byte_per_sec = 0  # bottleneck bw in bytes/sec

        self.next_send_time_ms = 0

        self.target_cwnd_byte = 0

        self.in_fast_recovery_mode = False
        self.exit_fast_recovery_ts = -1
        self.limited_by_cwnd = False
        self.ts_ms = 0

        self._init()
        self._init_pacing_rate()

    def _init(self):
        # init_windowed_max_filter(filter=BBR.BtlBwFilter, value=0, time=0)
        self.btlbw_filter = BBRBtlBwFilter(BTLBW_FILTER_LEN)

        # TODO: double check srtt
        if self.srtt_ms:
            self.rtprop_ms = self.srtt_ms
        else:
            self.rtprop_ms = math.inf

        # The wall clock time at which the current
        # BBR.RTProp sample was obtained.
        self.rtprop_stamp_ms = 0

        # A boolean recording whether the BBR.RTprop
        # has expired and is due for a refresh with an
        # application idle period or a transition into
        # ProbeRTT state.
        self.rtprop_expired = False

        self.probe_rtt_done_stamp_ms = 0
        self.probe_rtt_round_done = False
        self.packet_conservation = False
        self.prior_cwnd_byte = 0
        self.idle_restart = False
        self._init_round_counting()
        self._init_full_pipe()
        self._enter_startup()

    def _init_round_counting(self):
        self.next_round_delivered_byte = 0
        self.round_start = False
        self.round_count = 0

    def _init_full_pipe(self):
        self.filled_pipe = False
        self.full_bw_byte_per_sec = 0
        self.full_bw_count = 0

    def _init_pacing_rate(self):
        # nominal_bandwidth = InitialCwnd / (SRTT ? SRTT : 1ms)
        if self.srtt_ms <= 0:
            nominal_bw_byte_per_sec = 1000 * self.cwnd_byte  # 1ms
        else:
            nominal_bw_byte_per_sec = 1000 * self.cwnd_byte / self.srtt_ms
        assert self.host
        self.host.set_pacing_rate_byte_per_sec(
            self.pacing_gain * nominal_bw_byte_per_sec)

    def _enter_startup(self):
        self.state = BBRMode.BBR_STARTUP
        self.pacing_gain = BBR_HIGH_GAIN
        self.cwnd_gain = BBR_HIGH_GAIN

    def _update_on_ack(self, pkt: BBRPacket):
        self._update_model_and_state(pkt)
        self._update_control_parameters()

    def _update_model_and_state(self, pkt):
        self._update_btlbw(pkt)
        self._check_cycle_phase()
        self._check_full_pipe()
        self._check_drain()
        self._update_rtprop(pkt)
        self._check_probe_rtt()

    def _update_control_parameters(self):
        self._set_pacing_rate()
        self._set_send_quantum()
        self._set_cwnd()

    def _update_round(self, pkt: BBRPacket):
        if pkt.delivered_byte >= self.next_round_delivered_byte:
            self.next_round_delivered_byte = self.conn_state.delivered_byte
            self.round_count += 1
            self.round_start = True
        else:
            self.round_start = False

    def _update_btlbw(self, pkt: BBRPacket):
        if self.rs.delivery_rate_byte_per_sec == 0.0:
            return
        self._update_round(pkt)
        if self.rs.delivery_rate_byte_per_sec >= self.btlbw_byte_per_sec or not self.rs.is_app_limited:
            self.btlbw_filter.update(self.rs.delivery_rate_byte_per_sec, self.round_count)
            self.btlbw_byte_per_sec = self.btlbw_filter.get_btlbw()

    def _check_cycle_phase(self):
        if self.state == BBRMode.BBR_PROBE_BW and self._is_next_cycle_phase():
            self._advance_cycle_phase()

    def _advance_cycle_phase(self):
        self.cycle_stamp_ms = self.ts_ms
        self.cycle_index = (self.cycle_index + 1) % BBR_GAIN_CYCLE_LEN
        pacing_gain_cycle = [5/4, 3/4, 1, 1, 1, 1, 1, 1]
        self.pacing_gain = pacing_gain_cycle[self.cycle_index]

    def _is_next_cycle_phase(self):
        is_full_length = (self.ts_ms - self.cycle_stamp_ms) > self.rtprop_ms
        if self.pacing_gain == 1:
            return is_full_length
        if self.pacing_gain > 1:
            return is_full_length and (self.rs.losses > 0 or self.rs.prior_bytes_in_flight >= self._inflight_bytes(self.pacing_gain))
        else:  # (BBR.pacing_gain < 1)
            return is_full_length or self.rs.prior_bytes_in_flight <= self._inflight_bytes(1)

    def _check_full_pipe(self):
        if self.filled_pipe or not self.round_start or self.rs.is_app_limited:
            return  # no need to check for a full pipe now
        if self.btlbw_byte_per_sec >= self.full_bw_byte_per_sec * 1.25:  # BBR.BtlBw still growing?
            self.full_bw_byte_per_sec = self.btlbw_byte_per_sec    # record new baseline level
            self.full_bw_count = 0
            return
        self.full_bw_count += 1   # another round w/o much growth
        if self.full_bw_count >= 3:
            self.filled_pipe = True

    def _check_drain(self):
        if self.state == BBRMode.BBR_STARTUP and self.filled_pipe:
            self._enter_drain()
        if self.state == BBRMode.BBR_DRAIN and self.bytes_in_flight <= self._inflight_bytes(1.0):
            self._enter_probe_bw()  # we estimate queue is drained

    def _update_rtprop(self, pkt: BBRPacket):
        self.rtprop_expired = self.ts_ms > self.rtprop_stamp_ms + RTPROP_FILTER_LEN_SEC * 1000
        if (pkt.rtt_ms() >= 0 and (pkt.rtt_ms() <= self.rtprop_ms or self.rtprop_expired)):
            self.rtprop_ms = pkt.rtt_ms()
            self.rtprop_stamp_ms = self.ts_ms

    def _check_probe_rtt(self):
        if self.state != BBRMode.BBR_PROBE_RTT and self.rtprop_expired and not self.idle_restart:
            self._enter_probe_rtt()
            self.prior_cwnd = self._save_cwnd()
            self.probe_rtt_done_stamp_ms = 0
        if self.state == BBRMode.BBR_PROBE_RTT:
            self._handle_probe_rtt()
        self.idle_restart = False

    def _set_pacing_rate_with_gain(self, pacing_gain: float):
        assert self.host
        rate = pacing_gain * self.btlbw_byte_per_sec
        if self.filled_pipe or rate > self.host.pacing_rate_byte_per_sec:
            self.host.set_pacing_rate_byte_per_sec(rate)

    def _set_pacing_rate(self):
        self._set_pacing_rate_with_gain(self.pacing_gain)

    def _set_send_quantum(self):
        assert self.host
        if self.host.pacing_rate_byte_per_sec < 1.2 * 1e6 / BITS_PER_BYTE:  # 1.2Mbps
            self.send_quantum = 1 * MSS
        elif self.host.pacing_rate_byte_per_sec < 24 * 1e6 / BITS_PER_BYTE:  # Mbps
            self.send_quantum = 2 * MSS
        else:
            # 1 means 1ms, fix the unit, 64 means 64Kbytes
            self.send_quantum = min(self.host.pacing_rate_byte_per_sec * 1e-3, 64*1e3)

    def _set_cwnd(self):
        # on each ACK that acknowledges "packets_delivered"
        #    packets as newly ACKed or SACKed, BBR runs the following BBRSetCwnd()
        #    steps to update cwnd:
        # TODO: fix this bug
        packets_delivered = 1
        self._update_target_cwnd()
        if self.in_fast_recovery_mode:
            self._modulate_cwnd_for_recovery(packets_delivered)
        if not self.packet_conservation:
            if self.filled_pipe:
                self.cwnd_byte = min(self.cwnd_byte + packets_delivered,
                                self.target_cwnd_byte)
            elif self.cwnd_byte < self.target_cwnd_byte or self.conn_state.delivered_byte < TCP_INIT_CWND_BYTE:
                self.cwnd_byte = self.cwnd_byte + packets_delivered
            self.cwnd_byte = max(self.cwnd_byte, BBR_MIN_PIPE_CWND_BYTE)

        self._modulate_cwnd_for_probe_rtt()

    def _inflight_bytes(self, gain: float):
        if self.rtprop_ms > 0 and math.isinf(self.rtprop_ms):
            return TCP_INIT_CWND_BYTE  # no valid RTT samples yet
        quanta = 3 * self.send_quantum
        estimated_bdp = self.btlbw_byte_per_sec * self.rtprop_ms / 1000
        return gain * estimated_bdp + quanta

    def _update_target_cwnd(self):
        self.target_cwnd_byte = int(self._inflight_bytes(self.cwnd_gain))

    def _enter_probe_rtt(self):
        self.state = BBRMode.BBR_PROBE_RTT
        self.pacing_gain = 1
        self.cwnd_gain = 1

    def _handle_probe_rtt(self):
        # Ignore low rate samples during ProbeRTT:
        self.conn_state.app_limited = 0  # assume always have available data to send from app
        # instead of (BW.delivered + packets_in_flight) ? : 1
        if self.probe_rtt_done_stamp_ms == 0 and self.bytes_in_flight <= BBR_MIN_PIPE_CWND_BYTE:
            self.probe_rtt_done_stamp_ms = self.ts_ms + PROBE_RTT_DURATION_MS
            self.probe_rtt_round_done = False
            self.next_round_delivered_byte = self.conn_state.delivered_byte
        elif self.probe_rtt_done_stamp_ms != 0:
            if self.round_start:
                self.probe_rtt_round_done = True
            if self.probe_rtt_round_done and self.ts_ms > self.probe_rtt_done_stamp_ms:
                self.rtprop_stamp_ms = self.ts_ms
                self._restore_cwnd()
                self._exit_probe_rtt()

    def _exit_probe_rtt(self):
        if self.filled_pipe:
            self._enter_probe_bw()
        else:
            self._enter_startup()

    def _modulate_cwnd_for_probe_rtt(self):
        if self.state == BBRMode.BBR_PROBE_RTT:
            self.cwnd_byte = min(self.cwnd_byte, BBR_MIN_PIPE_CWND_BYTE)

    def _modulate_cwnd_for_recovery(self, packets_delivered: int):
        # TODO: fix the unit here
        packets_lost = self.rs.losses
        if packets_lost > 0:
            self.cwnd_byte = max(self.cwnd_byte - packets_lost, 1)
        if self.packet_conservation:
            self.cwnd_byte = max(self.cwnd_byte, self.bytes_in_flight + packets_delivered)

    def _save_cwnd(self):
        if not self.in_fast_recovery_mode and self.state != BBRMode.BBR_PROBE_RTT:
            return self.cwnd_byte
        else:
            return max(self.prior_cwnd_byte, self.cwnd_byte)

    def _restore_cwnd(self):
        self.cwnd_byte = max(self.cwnd_byte, self.prior_cwnd_byte)

    def _enter_drain(self):
        self.state = BBRMode.BBR_DRAIN
        self.pacing_gain = 1 / BBR_HIGH_GAIN  # pace slowly
        self.cwnd_gain = BBR_HIGH_GAIN    # maintain cwnd

    def _enter_probe_bw(self):
        self.state = BBRMode.BBR_PROBE_BW
        self.pacing_gain = 1
        self.cwnd_gain = 2
        self.cycle_index = BBR_GAIN_CYCLE_LEN - 1 - self.prng.randint(0, 6)
        self._advance_cycle_phase()

    # Upon receiving ACK, fill in delivery rate sample rs.
    def _generate_rate_sample(self, ts_ms, pkt: BBRPacket):
        # for each newly SACKed or ACKed packet P:
        #     self.update_rate_sample(P, rs)
        # fix the btlbw overestimation bug by not updating delivery_rate
        if not self._update_rate_sample(ts_ms, pkt):
            return False

        # Clear app-limited field if bubble is ACKed and gone.
        if self.conn_state.app_limited and self.conn_state.delivered_byte > self.conn_state.app_limited:
            self.conn_state.app_limited = 0

        # TODO: need to recheck
        if self.rs.prior_time_ms == 0:
            return False  # nothing delivered on this ACK

        # Use the longer of the send_elapsed and ack_elapsed
        self.rs.interval_ms = max(self.rs.send_elapsed_ms, self.rs.ack_elapsed_ms)
        # print(self.rs.send_elapsed, self.rs.ack_elapsed)

        self.rs.delivered_byte = self.conn_state.delivered_byte - self.rs.prior_delivered_byte
        # print("C.delivered: {}, rs.prior_delivered: {}".format(self.delivered, self.rs.prior_delivered))

        # Normally we expect interval >= MinRTT.
        # Note that rate may still be over-estimated when a spuriously
        # retransmitted skb was first (s)acked because "interval"
        # is under-estimated (up to an RTT). However, continuously
        # measuring the delivery rate during loss recovery is crucial
        # for connections suffer heavy or prolonged losses.

        if self.rs.interval_ms < self.rtprop_ms:
            self.rs.interval_ms = -1
            return False  # no reliable sample
        # self.rs.pkt_in_fast_recovery_mode = pkt.in_fast_recovery_mode
        if self.rs.interval_ms != 0: #and not pkt.in_fast_recovery_mode:
            self.rs.delivery_rate_byte_per_sec = 1000 * self.rs.delivered_byte / self.rs.interval_ms

        return True  # we filled in rs with a rate sample

    # Update rs when packet is SACKed or ACKed.
    def _update_rate_sample(self, ts_ms, pkt: BBRPacket):
        # TODO: double check this line
        # comment out because we don't need this in the simulator.
        # if pkt.delivered_time == 0:
        #     return  # P already SACKed

        self.rs.prior_bytes_in_flight = self.bytes_in_flight
        self.conn_state.delivered_byte += pkt.size_bytes
        self.conn_state.delivered_time_ms = ts_ms

        # Update info using the newest packet:
        if (not self.rs.prior_delivered_byte) or pkt.delivered_byte > self.rs.prior_delivered_byte:
            self.rs.prior_delivered_byte = pkt.delivered_byte
            self.rs.prior_time_ms = pkt.delivered_time_ms
            self.rs.is_app_limited = pkt.is_app_limited
            self.rs.send_elapsed_ms = pkt.ts_sent_ms - pkt.ts_first_sent_ms
            self.rs.ack_elapsed_ms = self.conn_state.delivered_time_ms - pkt.delivered_time_ms
            # print("pkt.sent_time:", pkt.sent_time, "pkt.first_sent_time:", pkt.first_sent_time, "send_elapsed:", self.rs.send_elapsed)
            # print("C.delivered_time:", self.conn_state.delivered_time, "P.delivered_time:", pkt.delivered_time, "ack_elapsed:", self.rs.ack_elapsed)
            self.conn_state.first_sent_time_ms = pkt.ts_sent_ms
            return True
        return False
        # pkt.debug_print()

        # Mark the packet as delivered once it's SACKed to
        # avoid being used again when it's cumulatively acked.

        # TODO: double check this line
        # pkt.delivered_time = 0

    def _send_packet(self, ts_ms, pkt: BBRPacket):
        if self.bytes_in_flight == 0:
            self.conn_state.first_sent_time_ms = ts_ms
            self.conn_state.delivered_time_ms = ts_ms
        pkt.ts_first_sent_ms = self.conn_state.first_sent_time_ms
        pkt.delivered_time_ms = self.conn_state.delivered_time_ms
        pkt.delivered_byte = self.conn_state.delivered_byte
        pkt.is_app_limited = (self.conn_state.app_limited != 0)
        # pkt.in_fast_recovery_mode = self.in_fast_recovery_mode
