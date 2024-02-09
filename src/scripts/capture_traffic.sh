#!/bin/bash


# SERVER=128.135.203.168
# SERVER=farewell.cs.uchicago.edu
SERVER=13.52.163.96
PORT=5001
DURATION=300
SAVE_DIR=results/pcap_traces/blackbox-aws-test-campus

mkdir -p $SAVE_DIR

# cur_t=$(date +%s%N | cut -b1-13)
for i in $(seq 1 20); do
    cur_t=$(date +%Y%m%d%H%m%S)
    ssh $SERVER "iperf -s -D"
    timeout ${DURATION} ./src/scripts/run_ss.sh ${SAVE_DIR}/ss_output_${cur_t}.log $PORT &
    sudo timeout ${DURATION}s tcpdump tcp port $PORT -s 80 -w ${SAVE_DIR}/tcp_${cur_t}.pcap &
    iperf -t $DURATION -c $SERVER -p $PORT -i 5 > ${SAVE_DIR}/iperf_output_${cur_t}.log
    ssh $SERVER "pkill -f iperf"
done

# sudo tcpdump udp # -i wlp1s0 quic
# sudo timeout 30s tcpdump -i wlp1s0 -w results/pcap_traces/webrtc_${cur_t}.pcap
