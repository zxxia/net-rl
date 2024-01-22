#!/bin/bash


# SERVER=128.135.203.168
# SERVER=farewell.cs.uchicago.edu
SERVER=13.52.163.96
PORT=5001
DURATION=300
SAVE_DIR=results/pcap_traces/blackbox-aws-test

mkdir -p $SAVE_DIR

cur_t=$(date +%s%N | cut -b1-13)
ssh $SERVER "iperf -s -D"
iperf -t $DURATION -c $SERVER -p $PORT -i 5 > ${SAVE_DIR}/iperf_output_${cur_t}.log &
sudo timeout ${DURATION}s tcpdump tcp port $PORT -s 80 -w ${SAVE_DIR}/tcp_${cur_t}.pcap
ssh $SERVER "pkill -f iperf"

# sudo tcpdump udp # -i wlp1s0 quic
# sudo timeout 30s tcpdump -i wlp1s0 -w results/pcap_traces/webrtc_${cur_t}.pcap
