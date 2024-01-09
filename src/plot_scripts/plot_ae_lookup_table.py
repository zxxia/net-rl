import csv
import glob
import os

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from flow_level_simulator import load_lookup_table, ssim_db, MODEL_ID_MAP

def bar_plot(df, fps, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    hatches = ['', '/', '\\', '|', '-', '*', 'x', 'o', 'O', '.', 'O.']
    handles = []

    for idx, model_id in enumerate(df['model_id'].unique()):
        if idx >= 10:
            c = 'salmon'
        else:
            c = f'C{idx}'
        handles.append(mpatches.Patch(color=c, label=f'{model_id}'))
    for idx_loss, loss in enumerate(df['loss'].unique()):
        pat = mpatches.Patch(color='k', label=f'{loss}', fill=False)
        pat.set_hatch(hatches[idx_loss])
        handles.append(pat)
    for frame_id in df['frame_id'].unique():
        ssims = []
        rates = []
        colors = []
        hatches2plot = []
        for idx, model_id in enumerate(df['model_id'].unique()):
            for idx_loss, loss in enumerate(df['loss'].unique()):
                mask = (df['frame_id'] == frame_id) & (df['loss'] == loss) & (df['model_id'] == model_id)
                ssims.append(-10 * np.log10(1 - df[mask]['ssim'].item()))
                rates.append(df[mask]['size'] * fps * 8 / 1000)
                if idx >= 10:
                    c = 'salmon'
                else:
                    c = f'C{idx}'
                colors.append(c)
                hatches2plot.append(hatches[idx_loss])
        fig, axes = plt.subplots(2, 1, figsize=(15, 5))
        ax = axes[0]
        ax.bar(np.arange(len(ssims)) * 1.5, ssims, width=1.2, color=colors, hatch=hatches2plot)
        ax.legend(handles=handles, ncol=9)
        ax.set_ylabel('SSIM (dB)')
        ax.set_xticks([])

        ax = axes[1]
        ax.plot(np.arange(len(rates)) * 1.5, rates, 'o-')
        ax.set_ylabel('Bitrate (Kbps)')
        ax.set_xticks([])
        ax.grid(True)
        fig.tight_layout()
        fig.savefig(os.path.join(save_dir, f"{frame_id:03d}.jpg"), bbox_inches='tight')
        plt.close()


def scatter_plot(df, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    immediate_greater_bitrate_ssim_gaps = []
    immediate_greater_bitrate_losses = []
    sec_immediate_greater_bitrate_ssim_gaps = []
    sec_immediate_greater_bitrate_losses = []
    for frame_id in df['frame_id'].unique():
        low_model_loss = 0
        df_frame = df[(df['frame_id'] == frame_id) & (df['loss'] == low_model_loss)]
        fig, axes = plt.subplots(2, 5, figsize=(18, 6))
        for idx, (_, row) in enumerate(df_frame.iterrows()):
            low_rate = row['size']
            mask = df_frame['model_id'] > row['model_id']
            high_model_ids = df_frame[mask]['model_id'].to_numpy()
            high_model_losses = 1 - low_rate / df_frame[mask]['size'].to_numpy()
            if len(high_model_losses) == 0:
                continue
            high_model_losses = high_model_losses[high_model_losses >= 0]
            rounded_high_model_losses = np.minimum(np.round(high_model_losses, 1), 0.9)
            high_model_ssims = []
            colors = []
            for high_model_id, rounded_high_model_loss in zip(high_model_ids, rounded_high_model_losses):
                if rounded_high_model_loss < 0:
                    continue
                mask = (df['frame_id'] == frame_id) & (df['loss'] == rounded_high_model_loss) & (df['model_id'] == high_model_id)
                high_model_ssims.append(df[mask]['ssim'].to_numpy().item())
                if MODEL_ID_MAP[high_model_id] - 1 == 10:
                    colors.append("salmon")
                else:
                    colors.append("C{}".format(MODEL_ID_MAP[high_model_id] - 1))

            delta_ssim_db = ssim_db(np.array(high_model_ssims)) - ssim_db(row['ssim'])
            immediate_greater_bitrate_losses.append(high_model_losses[0])
            immediate_greater_bitrate_ssim_gaps.append(delta_ssim_db[0])
            if len(high_model_losses) > 1:
                sec_immediate_greater_bitrate_losses.append(high_model_losses[1])
                sec_immediate_greater_bitrate_ssim_gaps.append(delta_ssim_db[1])
            assert high_model_losses.shape == delta_ssim_db.shape
            ax = axes.flatten()[idx]
            ax.scatter(high_model_losses, delta_ssim_db, c=colors)
            ax.set_title("Low model id {}".format(row['model_id']))
            ax.set_xlim(0, 1)
            ax.set_xlabel('Loss rate')
            ax.set_ylabel('delta ssim (dB)')
        handles = []
        for idx, model_id in enumerate(df['model_id'].unique()):
            if idx >= 10:
                c = 'salmon'
            else:
                c = f'C{idx}'
            handles.append(mpatches.Patch(color=c, label=f'{model_id}'))
        fig.legend(handles=handles, ncol=11, bbox_to_anchor=(0.5, 1.05), loc='upper center')
        fig.tight_layout()
        fig.savefig(os.path.join(save_dir, "frame_{:03d}".format(frame_id)), bbox_inches='tight')
        plt.close()
    with open(os.path.join(save_dir, "summary.csv"), 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['Levels above low lambda', 'SSIM (dB) avg', 'SSIM (dB) median', 'SSIM (dB) stddev', 'Losses avg', 'Losses median', 'Losses stddev'])
        writer.writerow([
            1, np.mean(immediate_greater_bitrate_ssim_gaps), np.median(immediate_greater_bitrate_ssim_gaps), np.std(immediate_greater_bitrate_ssim_gaps),
            np.mean(immediate_greater_bitrate_losses), np.median(immediate_greater_bitrate_losses), np.std(immediate_greater_bitrate_losses)])
        writer.writerow([
            2, np.mean(sec_immediate_greater_bitrate_ssim_gaps), np.median(sec_immediate_greater_bitrate_ssim_gaps), np.std(sec_immediate_greater_bitrate_ssim_gaps),
            np.mean(sec_immediate_greater_bitrate_losses), np.median(sec_immediate_greater_bitrate_losses), np.std(sec_immediate_greater_bitrate_losses)])
        # print("One level greater than low lamdb")
        # print("\tSSIM(dB) avg {:.2f}, median {:.2f}, stddev {:.2f}".format(np.mean(immediate_greater_bitrate_ssim_gaps), np.median(immediate_greater_bitrate_ssim_gaps), np.std(immediate_greater_bitrate_ssim_gaps)))
        # print("\tLosses avg {:.2f}, median {:.2f}, stddev {:.2f}".format(np.mean(immediate_greater_bitrate_losses), np.median(immediate_greater_bitrate_losses), np.std(immediate_greater_bitrate_losses)))
        # print("Two levels greater than low lamdb")
        # print("\tSSIM(dB) avg {:.2f}, median {:.2f}, stddev {:.2f}".format(np.mean(sec_immediate_greater_bitrate_ssim_gaps), np.median(sec_immediate_greater_bitrate_ssim_gaps), np.std(sec_immediate_greater_bitrate_ssim_gaps)))
        # print("\tLosses avg {:.2f}, median {:.2f}, stddev {:.2f}".format(np.mean(sec_immediate_greater_bitrate_losses), np.median(sec_immediate_greater_bitrate_losses), np.std(sec_immediate_greater_bitrate_losses)))


def main():
    fps = 25
    lookup_tabs = glob.glob("./AE_lookup_table/*.csv")
    for lookup_tab in lookup_tabs:
        if os.path.basename(lookup_tab) == "all.csv":
            continue
        vid_name = os.path.basename(lookup_tab).split('.')[0]
        print(lookup_tab, vid_name)
        df = load_lookup_table(lookup_tab)
        print(f"Generate bar plots for {vid_name}")
        save_dir = os.path.join("results", "frame_bar_plots", vid_name)
        if os.path.exists(save_dir):
            print(f"{save_dir} already exists, skip!")
            continue
        bar_plot(df, fps, save_dir)

        print(f"Generate scatter plots for {vid_name}")
        save_dir = os.path.join("results", "frame_scatter_plots", vid_name)
        if os.path.exists(save_dir):
            print(f"{save_dir} already exists, skip!")
            continue
        scatter_plot(df, save_dir)


if __name__ == "__main__":
    main()
