import math
import random
from enum import Enum

from simulator_new.cc import CongestionControl
from simulator_new.constant import MSS, TCP_INIT_CWND_BYTE
from simulator_new.packet import TCPPacket, Packet


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


class BBRv1(CongestionControl):
    """

    Reference:
        https://datatracker.ietf.org/doc/html/draft-cardwell-iccrg-bbr-congestion-control-00
        https://datatracker.ietf.org/doc/html/draft-cheng-iccrg-delivery-rate-estimation#section-3.1.3
    """
    def __init__(self, seed: int):
        super().__init__()
        self.prng = random.Random(seed)

        self.btlbw_Bps = 0  # bottleneck bw in bytes/sec

        self.next_send_time_ms = 0

        self.pacing_gain = BBR_HIGH_GAIN

        self.target_cwnd_byte = 0

        self.in_fast_recovery_mode = False
        self.exit_fast_recovery_ts = -1
        self.limited_by_cwnd = False
        self.ts_ms = 0

    def register_host(self, host):
        # TODO: needs to be TCPhost
        super().register_host(host)
        self._init()
        self._init_pacing_rate()

    def can_send(self):
        # wait for ack or timeout
        assert self.host
        return self.host.bytes_in_flight < self.host.cwnd_byte

    def on_pkt_sent(self, ts_ms, pkt):
        super().on_pkt_sent(ts_ms, pkt)

    def on_pkt_acked(self, ts_ms, data_pkt, ack_pkt):
        self._update_on_ack(ts_ms, data_pkt, ack_pkt)

    def on_pkt_lost(self, ts_ms, pkt):
        raise NotImplementedError

    def tick(self, ts_ms):
        self.ts_ms = ts_ms

    def reset(self):
        super().reset()
        self.btlbw_Bps = 0  # bottleneck bw in bytes/sec

        self.next_send_time_ms = 0

        self.target_cwnd_byte = 0

        self.in_fast_recovery_mode = False
        self.exit_fast_recovery_ts = -1
        self.limited_by_cwnd = False
        self.ts_ms = 0

        self._init()
        self._init_pacing_rate()

    def _init(self):
        assert self.host
        # init_windowed_max_filter(filter=BBR.BtlBwFilter, value=0, time=0)
        self.btlbw_filter = BBRBtlBwFilter(BTLBW_FILTER_LEN)

        # TODO: double check srtt
        if self.host.srtt_ms:
            self.rtprop_ms = self.host.srtt_ms
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
        self.full_bw_Bps = 0
        self.full_bw_count = 0

    def _init_pacing_rate(self):
        assert self.host
        # nominal_bandwidth = InitialCwnd / (SRTT ? SRTT : 1ms)
        if self.host.srtt_ms <= 0:
            nominal_bw_Bps = 1000 * self.host.cwnd_byte  # 1ms
        else:
            nominal_bw_Bps = 1000 * self.host.cwnd_byte / self.host.srtt_ms
        assert self.host
        self.host.set_pacing_rate_Bps(
            self.pacing_gain * nominal_bw_Bps)

    def _enter_startup(self):
        self.state = BBRMode.BBR_STARTUP
        self.pacing_gain = BBR_HIGH_GAIN
        self.cwnd_gain = BBR_HIGH_GAIN

    def _update_on_ack(self, ts_ms, data_pkt: TCPPacket, ack_pkt: Packet):
        self._update_model_and_state(ts_ms, data_pkt, ack_pkt)
        self._update_control_parameters(data_pkt.size_bytes)

    def _update_model_and_state(self, ts_ms, data_pkt, ack_pkt):
        self._update_btlbw(data_pkt)
        self._check_cycle_phase(ts_ms)
        self._check_full_pipe()
        self._check_drain(ts_ms)
        self._update_rtprop(ts_ms, ack_pkt)
        self._check_probe_rtt(ts_ms)

    def _update_control_parameters(self, bytes_delivered):
        self._set_pacing_rate()
        self._set_send_quantum()
        self._set_cwnd(bytes_delivered)

    def _update_round(self, pkt: TCPPacket):
        assert self.host
        if pkt.delivered_byte >= self.next_round_delivered_byte:
            self.next_round_delivered_byte = self.host.conn_state.delivered_byte
            self.round_count += 1
            self.round_start = True
        else:
            self.round_start = False

    def _update_btlbw(self, pkt: TCPPacket):
        assert self.host
        if self.host.rs.delivery_rate_Bps == 0.0:
            return
        self._update_round(pkt)
        if self.host.rs.delivery_rate_Bps >= self.btlbw_Bps or not self.host.rs.is_app_limited:
            self.btlbw_filter.update(self.host.rs.delivery_rate_Bps, self.round_count)
            self.btlbw_Bps = self.btlbw_filter.get_btlbw()

    def _check_cycle_phase(self, ts_ms):
        if self.state == BBRMode.BBR_PROBE_BW and self._is_next_cycle_phase(ts_ms):
            self._advance_cycle_phase(ts_ms)

    def _advance_cycle_phase(self, ts_ms):
        self.cycle_stamp_ms = ts_ms
        self.cycle_index = (self.cycle_index + 1) % BBR_GAIN_CYCLE_LEN
        pacing_gain_cycle = [5/4, 3/4, 1, 1, 1, 1, 1, 1]
        self.pacing_gain = pacing_gain_cycle[self.cycle_index]

    def _is_next_cycle_phase(self, ts_ms):
        assert self.host
        is_full_length = (ts_ms - self.cycle_stamp_ms) > self.rtprop_ms
        if self.pacing_gain == 1:
            return is_full_length
        if self.pacing_gain > 1:
            return is_full_length and (self.host.rs.losses > 0 or self.host.rs.prior_bytes_in_flight >= self._inflight_bytes(self.pacing_gain))
        else:  # (BBR.pacing_gain < 1)
            return is_full_length or self.host.rs.prior_bytes_in_flight <= self._inflight_bytes(1)

    def _check_full_pipe(self):
        assert self.host
        if self.filled_pipe or not self.round_start or self.host.rs.is_app_limited:
            return  # no need to check for a full pipe now
        if self.btlbw_Bps >= self.full_bw_Bps * 1.25:  # BBR.BtlBw still growing?
            self.full_bw_Bps = self.btlbw_Bps    # record new baseline level
            self.full_bw_count = 0
            return
        self.full_bw_count += 1   # another round w/o much growth
        if self.full_bw_count >= 3:
            self.filled_pipe = True

    def _check_drain(self, ts_ms):
        assert self.host
        if self.state == BBRMode.BBR_STARTUP and self.filled_pipe:
            self._enter_drain()
        if self.state == BBRMode.BBR_DRAIN and self.host.bytes_in_flight <= self._inflight_bytes(1.0):
            self._enter_probe_bw(ts_ms)  # we estimate queue is drained

    def _update_rtprop(self, ts_ms, pkt):
        self.rtprop_expired = ts_ms > self.rtprop_stamp_ms + RTPROP_FILTER_LEN_SEC * 1000
        rtt_ms = pkt.rtt_ms()
        if rtt_ms >= 0 and (rtt_ms <= self.rtprop_ms or self.rtprop_expired):
            self.rtprop_ms = rtt_ms
            self.rtprop_stamp_ms = ts_ms

    def _check_probe_rtt(self, ts_ms):
        if self.state != BBRMode.BBR_PROBE_RTT and self.rtprop_expired and not self.idle_restart:
            self._enter_probe_rtt()
            self.prior_cwnd = self._save_cwnd()
            self.probe_rtt_done_stamp_ms = 0
        if self.state == BBRMode.BBR_PROBE_RTT:
            self._handle_probe_rtt(ts_ms)
        self.idle_restart = False

    def _set_pacing_rate_with_gain(self, pacing_gain: float):
        assert self.host
        rate = pacing_gain * self.btlbw_Bps
        if self.filled_pipe or rate > self.host.pacing_rate_Bps:
            self.host.set_pacing_rate_Bps(rate)

    def _set_pacing_rate(self):
        self._set_pacing_rate_with_gain(self.pacing_gain)

    def _set_send_quantum(self):
        assert self.host
        if self.host.pacing_rate_Bps < 1.2 * 1e6 / 8:  # 1.2Mbps
            self.send_quantum = 1 * MSS
        elif self.host.pacing_rate_Bps < 24 * 1e6 / 8:  # Mbps
            self.send_quantum = 2 * MSS
        else:
            # 1 means 1ms, fix the unit, 64 means 64Kbytes
            self.send_quantum = min(self.host.pacing_rate_Bps * 1e-3, 64*1e3)

    def _set_cwnd(self, bytes_delivered):
        assert self.host
        # on each ACK that acknowledges "packets_delivered"
        #    packets as newly ACKed or SACKed, BBR runs the following BBRSetCwnd()
        #    steps to update cwnd:
        self._update_target_cwnd()
        if self.in_fast_recovery_mode:
            self._modulate_cwnd_for_recovery(bytes_delivered)
        if not self.packet_conservation:
            if self.filled_pipe:
                self.host.cwnd_byte = min(self.host.cwnd_byte + bytes_delivered,
                                self.target_cwnd_byte)
            elif self.host.cwnd_byte < self.target_cwnd_byte or self.host.conn_state.delivered_byte < TCP_INIT_CWND_BYTE:
                self.host.cwnd_byte = self.host.cwnd_byte + bytes_delivered
            self.host.cwnd_byte = max(self.host.cwnd_byte, BBR_MIN_PIPE_CWND_BYTE)

        self._modulate_cwnd_for_probe_rtt()

    def _inflight_bytes(self, gain: float):
        if self.rtprop_ms > 0 and math.isinf(self.rtprop_ms):
            return TCP_INIT_CWND_BYTE  # no valid RTT samples yet
        quanta = 3 * self.send_quantum
        estimated_bdp = self.btlbw_Bps * self.rtprop_ms / 1000
        return gain * estimated_bdp + quanta

    def _update_target_cwnd(self):
        self.target_cwnd_byte = int(self._inflight_bytes(self.cwnd_gain))

    def _enter_probe_rtt(self):
        self.state = BBRMode.BBR_PROBE_RTT
        self.pacing_gain = 1
        self.cwnd_gain = 1

    def _handle_probe_rtt(self, ts_ms):
        assert self.host
        # Ignore low rate samples during ProbeRTT:
        self.host.conn_state.app_limited = 0  # assume always have available data to send from app
        # instead of (BW.delivered + packets_in_flight) ? : 1
        if self.probe_rtt_done_stamp_ms == 0 and self.host.bytes_in_flight <= BBR_MIN_PIPE_CWND_BYTE:
            self.probe_rtt_done_stamp_ms = ts_ms + PROBE_RTT_DURATION_MS
            self.probe_rtt_round_done = False
            self.next_round_delivered_byte = self.host.conn_state.delivered_byte
        elif self.probe_rtt_done_stamp_ms != 0:
            if self.round_start:
                self.probe_rtt_round_done = True
            if self.probe_rtt_round_done and ts_ms > self.probe_rtt_done_stamp_ms:
                self.rtprop_stamp_ms = ts_ms
                self._restore_cwnd()
                self._exit_probe_rtt(ts_ms)

    def _exit_probe_rtt(self, ts_ms):
        if self.filled_pipe:
            self._enter_probe_bw(ts_ms)
        else:
            self._enter_startup()

    def _modulate_cwnd_for_probe_rtt(self):
        assert self.host
        if self.state == BBRMode.BBR_PROBE_RTT:
            self.host.cwnd_byte = min(self.host.cwnd_byte, BBR_MIN_PIPE_CWND_BYTE)

    def _modulate_cwnd_for_recovery(self, packets_delivered: int):
        assert self.host
        # TODO: fix the unit here
        packets_lost = self.host.rs.losses
        if packets_lost > 0:
            self.host.cwnd_byte = max(self.host.cwnd_byte - packets_lost, 1)
        if self.packet_conservation:
            self.host.cwnd_byte = max(self.host.cwnd_byte, self.host.bytes_in_flight + packets_delivered)

    def _save_cwnd(self):
        assert self.host
        if not self.in_fast_recovery_mode and self.state != BBRMode.BBR_PROBE_RTT:
            return self.host.cwnd_byte
        else:
            return max(self.prior_cwnd_byte, self.host.cwnd_byte)

    def _restore_cwnd(self):
        assert self.host
        self.host.cwnd_byte = max(self.host.cwnd_byte, self.prior_cwnd_byte)

    def _enter_drain(self):
        self.state = BBRMode.BBR_DRAIN
        self.pacing_gain = 1 / BBR_HIGH_GAIN  # pace slowly
        self.cwnd_gain = BBR_HIGH_GAIN    # maintain cwnd

    def _enter_probe_bw(self, ts_ms):
        self.state = BBRMode.BBR_PROBE_BW
        self.pacing_gain = 1
        self.cwnd_gain = 2
        self.cycle_index = BBR_GAIN_CYCLE_LEN - 1 - self.prng.randint(0, 6)
        self._advance_cycle_phase(ts_ms)
