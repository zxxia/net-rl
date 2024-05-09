
# save_root='./results/test_syn_traces_diff_loss_coeff'
# loss20_net_reward_model_path="./results/train_net_reward_20loss/seed_20/step_288000/model_step_288000.ckpt"
# net_reward_model_path="./results/train_net_reward/seed_20/step_576000/model_step_576000.ckpt"
# vid_reward_model_path="./results/train_vid_reward/seed_20/step_504000/model_step_504000.ckpt"
# vid_reward_model_path="./results/train_vid_reward/seed_20/step_633600/model_step_633600.ckpt"


save_root='./results/test_on_diff_vids_traces'
run_rl ()
{
    CUDA_VISIBLE_DEVICES="" TF_CPP_MIN_LOG_LEVEL=3 python src/simulator_new/simulate.py \
        --cc aurora --model $1 --lookup-table $2 --trace $3 --save-dir $4
}

traces=$(ls ./data/synthetic_traces/)
lookup_tables=$(ls ./data/AE_lookup_table/*.csv)

for lookup_table in ${lookup_tables}; do
    table_file=$(basename $lookup_table)
    vid_name="${table_file%.*}"
    for trace in $traces; do
        trace_file=$(basename $trace)
        trace_name="${trace_file%.*}"
        # python
        # echo $trace
        # TF_CPP_MIN_LOG_LEVEL=3 python src/simulator_new/simulate.py --cc aurora \
        #     --app file_transfer \
        #     --model ${net_reward_model_path} --reward-type vid \
        #     --trace data/synthetic_traces/${trace} \
        #     --save-dir ${save_root}/${vid_name}/aurora_net
        # TF_CPP_MIN_LOG_LEVEL=3 python src/simulator_new/simulate.py --cc aurora \
        #     --app file_transfer \
        #     --model ${vid_reward_model_path} --reward-type vid \
        #     --trace data/synthetic_traces/${trace} \
        #     --save-dir ${save_root}/${vid_name}/aurora_vid
        # TF_CPP_MIN_LOG_LEVEL=3 python src/simulator_new/simulate.py --cc aurora \
        #     --app file_transfer \
        #     --model ${loss20_net_reward_model_path} --reward-type net \
        #     --trace data/synthetic_traces/${trace} \
        #     --save-dir ${save_root}/${vid_name}/aurora_net_20loss

        # TF_CPP_MIN_LOG_LEVEL=3 python src/simulator_new/simulate.py --cc aurora \
        #     --app file_transfer \
        #     --model ${net_reward_model_path} --reward-type net \
        #     --trace data/synthetic_traces/${trace} \
        #     --save-dir ${save_root}/${vid_name}/aurora_net
        #

        model_path="./results/train_net_reward/seed_20/step_576000/model_step_576000.ckpt"
        run_rl ${model_path} ${lookup_table} data/synthetic_traces/${trace} ${save_root}/${vid_name}/${trace_name}/aurora

        model_path="./results/train_net_reward_1000loss_fix/seed_20/step_640800/model_step_640800.ckpt"
        run_rl ${model_path} ${lookup_table} data/synthetic_traces/${trace} ${save_root}/${vid_name}/${trace_name}/aurora_loss1000

        model_path="./results/train_net_reward_500loss_fix/seed_20/step_633600/model_step_633600.ckpt"
        run_rl ${model_path} ${lookup_table} data/synthetic_traces/${trace} ${save_root}/${vid_name}/${trace_name}/aurora_loss500

        model_path="./results/train_net_reward_100loss_fix/seed_20/step_655200/model_step_655200.ckpt"
        run_rl ${model_path} ${lookup_table} data/synthetic_traces/${trace} ${save_root}/${vid_name}/${trace_name}/aurora_loss100
    done
done
