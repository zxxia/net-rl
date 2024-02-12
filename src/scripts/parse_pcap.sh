#!/bin/bash

pcap_file_dir=./results/pcap_traces/gpuserver-farewell
pcap_files=$(ls ${pcap_file_dir}/*.pcap)

datalink_args=""
acklink_args=""
tput_args=""
for pcap_file in ${pcap_files}; do
    fname=$(basename $pcap_file)
    trace_name="${fname%.*}"
    datalink_args+=$pcap_file" "${pcap_file_dir}/${trace_name}_datalink.csv" "
    acklink_args+=$pcap_file" "${pcap_file_dir}/${trace_name}_acklink.csv" "
    tput_args+=$pcap_file" "${pcap_file_dir}/${trace_name}_tput.csv" "
done
echo ${datalink_args} | xargs -P 8 -n 2 bash -c \
    'tshark -2 -Y tcp.dstport==5001 -T fields -e frame.number \
        -e frame.time_relative -e tcp.seq -e tcp.analysis.rto \
        -e tcp.analysis.rto_frame -e tcp.analysis.retransmission \
        -e tcp.analysis.fast_retransmission -e tcp.analysis.spurious_retransmission \
        -E header=y -E separator=, -r $0 > $1'

echo ${acklink_args} | xargs -P 8 -n 2 bash -c \
    'tshark -2 -Y tcp.srcport==5001 -T fields -e frame.time_relative \
        -e tcp.ack -e tcp.analysis.ack_rtt -e tcp.analysis.duplicate_ack_num \
        -E header=y -E separator=, -r $0 > $1'
echo ${tput_args} | xargs -P 8 -n 2 bash -c \
    'tshark -r $0 -q -z io,stat,0.5,tcp.dstport==5001 | grep -P "\d+\.?\d*\s+<>\s+|Interval +\|" | tr -d " " | tr "|" "," | sed -E "s/<>/,/; s/(^,|,$)//g; s/Interval/Start,Stop/g"> $1'
