#!/bin/bash

log_name=$1
truncate --size 0 $log_name

while true; do
    ss -into "dport = :5001" >> $log_name
    sleep 0.5
done
