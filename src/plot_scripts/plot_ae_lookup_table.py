import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


df = pd.read_csv('../AE_lookup_table/segment_3IY83M-m6is_480x360.mp4.csv')

for model_id in df['model_id'].unique():
    for loss in df['loss'].unique():
        mask = (df['loss'] == loss) & (df['model_id'] == model_id)
        plt.plot(df[mask]['frame_id'], df[mask]['ssim'], label=f'loss={loss}, model_id={model_id}')
        break
    # print(loss)
plt.legend()
plt.tight_layout()
plt.savefig('lookup_table_plot.jpg', bbox_inches='tight')


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
    # pat.set_hatch('.')
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
            rates.append(df[mask]['size'] * 25 * 8 / 1000)
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
    fig.savefig(f"results/frame_plots/{frame_id:03d}.jpg", bbox_inches='tight')
    plt.close()
