#!/bin/bash

log_name=$1
dport=$2
truncate --size 0 $log_name

while true; do
    ss -into "dport = :${dport}" >> $log_name
    sleep 0.5
done
