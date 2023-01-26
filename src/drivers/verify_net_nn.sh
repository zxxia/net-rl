#!/bin/bash

set -e
save_dir=results
pretrain_model_path=models/cc/pretrained/pretrained.ckpt
exp_name=verify_net_nn
total_step=720001
train_seed=20

conn_type=ethernet
conn_type=cellular
arch_type=large_arch
CUDA_VISIBLE_DEVICES="" mpiexec -np 4 python src/simulator/train.py \
    --tensorboard-log tensorboard_log \
    --exp-name ${exp_name} \
    --save-dir ${save_dir}/${exp_name}/${conn_type}/${arch_type}/seed_${train_seed} \
    --seed ${train_seed} \
    --total-timesteps ${total_step} \
    --validation \
    --dataset synthetic \
    udr \
    --train-trace-file data/${conn_type}_train_traces.txt \
    --val-trace-file data/${conn_type}_val_traces.txt \
    --real-trace-prob 1
