#!/bin/bash

save_dir=results
exp_name=train_file_trans
total_step=720000
train_seed=20

lookup_table=./AE_lookup_table/segment_0vu1_dwHF7g_480x360.mp4.csv

# CUDA_VISIBLE_DEVICES="" mpiexec -np 4
# python src/simulator_new/cc/pcc/aurora/train.py \
#     --tensorboard-log tensorboard_log \
#     --exp-name ${exp_name} \
#     --save-dir ${save_dir}/${exp_name}/seed_${train_seed} \
#     --seed ${train_seed} \
#     --total-timesteps ${total_step} \
#     --validation \
#     --dataset synthetic \
#     --app video_streaming \
#     --lookup-table ${lookup_table} \
#     udr \
#     --config-file config/config.json

source src/scripts/utils.sh

mkdir -p ${save_dir}/${exp_name}
git_summary ${save_dir}/${exp_name}

CUDA_VISIBLE_DEVICES="" mpiexec -np 4 python src/simulator_new/cc/pcc/aurora/train.py \
    --tensorboard-log tensorboard_log \
    --exp-name ${exp_name} \
    --save-dir ${save_dir}/${exp_name}/seed_${train_seed} \
    --seed ${train_seed} \
    --total-timesteps ${total_step} \
    --validation \
    --dataset synthetic \
    --app file_transfer \
    udr \
    --config-file config/config.json
    # --train-trace-file data/${conn_type}_train_traces.txt \
    # --val-trace-file data/${conn_type}_val_traces.txt \
    # --real-trace-prob 1
