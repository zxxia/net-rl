from simulator_new.link import Link
from simulator_new.packet import Packet
from simulator.trace import generate_trace

trace = generate_trace(duration_range=(30, 30),
                       bandwidth_lower_bound_range=(0.12, 0.12),
                       bandwidth_upper_bound_range=(0.12, 0.12),
                       delay_range=(25, 25),
                       loss_rate_range=(0, 0),
                       queue_size_range=(10, 10),
                       T_s_range=(0, 0), delay_noise_range=(0, 0))

data_link = Link(trace)

pacing_rate_bytes_per_sec = 15000
next_send_time_ms = 0
for ts_ms in range(1001):
    if ts_ms >= next_send_time_ms:
        pkt = Packet('data', 1500)
        pkt.ts_sent_ms = ts_ms
        data_link.push(pkt)
        next_send_time_ms += 1000 / (pacing_rate_bytes_per_sec / 1500)
    data_link.tick(ts_ms)
    # print(ts_ms, data_link.queue_size_bytes)
assert(len(data_link.ready_pkts) == 10)

cnt = 0
while data_link.pull():
    cnt += 1
assert cnt == 9
