import matplotlib.pyplot as plt
import numpy as np

# def add_err_prop(ssim_dB, frame_loss_rate, nframes_from_ref_frame):
#     '''Assume linear relationship between ssim_dB and N consecutive frames from
#     the reference frame.
#     Reference: Figure 10
#     https://arxiv.org/pdf/2305.12333.pdf
#     '''
#     # return max(-frame_loss_rate/2 * nframes_from_ref_frame + ssim_dB, ssim_dB - 9, 0)
#     decay_factor = 1 / 2
#     return 1 - (1 - frame_loss_rate * (decay_factor)**(nframes_from_ref_frame-1)) ** nframes_from_ref_frame

def frame_loss_rate_with_err_prop(frame_loss_rates):
    '''Reference: Figure 10
    https://arxiv.org/pdf/2305.12333.pdf
    '''
    y = 1
    decay_factor = 1 /1.1
    for idx, frame_loss_rate in enumerate(frame_loss_rates):
        y *= (1 - frame_loss_rate * (decay_factor** idx ))
    return 1 - y

def main():
    tot_frame_cnt = 10
    for loss in np.arange(0, 1, 0.1):
        loss = round(loss, 1)
        new_ssim_dBs = [frame_loss_rate_with_err_prop(np.ones(i)* loss) for i in range(tot_frame_cnt)]
        plt.plot(np.arange(tot_frame_cnt), new_ssim_dBs, lw='2', label=f'{loss}')
    plt.xlabel("# of consecutive incomplete frames (constant frame loss rate)\nfrom a complete reference frame")
    plt.ylabel("Estimated frame loss rate")
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.xlim(0, tot_frame_cnt)
    plt.ylim(0, 1)
    plt.savefig("test_err_prop.jpg", bbox_inches='tight')
