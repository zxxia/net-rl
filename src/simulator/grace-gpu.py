from audioop import avg, avgpp
from statistics import mode
import warnings
warnings.simplefilter("ignore")
warnings.filterwarnings("ignore")

import ctypes
import json
import pandas as pd
import pandas as pd
#from cabac_coder.cabac_coder import CABACCoder, CABACCoderTorchWrapper
import os, sys
import subprocess as sp
import io
import shlex
import cv2
from copy import deepcopy
from tqdm import tqdm
from dvc.dvc_gpu_interface import DVCInterface
from torchvision.transforms.functional import to_tensor, to_pil_image
import torch
import numpy as np
from torchvision.utils import save_image
from PIL import Image, ImageFile, ImageFilter
from skimage.metrics import peak_signal_noise_ratio
import time
# from skimage.metrics import structural_similarity as ssim
from scipy.stats import pearsonr
from queue import PriorityQueue
from dataclasses import dataclass
import PIL
import random
from pytorch_msssim import ssim, ms_ssim, SSIM, MS_SSIM

torch.manual_seed(0)
random.seed(0)
np.random.seed(0)


df_psnr = None

def print_usage():
    print(
        f"Usage: {sys.argv[0]} <video_file> <output file> <mode> [dvc_model]"
        f""
        f"  mode = mpeg | ae"
    )
    exit(1)

def PSNR(Y1_raw, Y1_com):
    Y1_com = Y1_com.to(Y1_raw.device)
    log10 = torch.log(torch.FloatTensor([10])).squeeze(0).to(Y1_raw.device)
    train_mse = torch.mean(torch.pow(Y1_raw - Y1_com, 2))
    quality = 10.0*torch.log(1/train_mse)/log10
    return quality

def SSIM(Y1_raw, Y1_com):
    y1 = Y1_raw.permute([1,2,0]).cpu().detach().numpy()
    y2 = Y1_com.permute([1,2,0]).cpu().detach().numpy()
    return ssim(y1, y2, multichannel=True)

def PSNR_YUV(yuv1, yuv2):
    mse = np.mean((yuv1 - yuv2) ** 2)
    max_pixel = max(np.max(yuv1), np.max(yuv2))
    psnr = 20 * np.log10(max_pixel/np.sqrt(mse))
    return psnr

def SSIM_YUV(y1, y2):
    return ssim(y1, y2, multichannel=False)

def rgb_tensor_to_img(rgbtensor):
    return np.array(to_pil_image(rgbtensor.clip(0, 1)))

def RGB2YUV(rgb, isTensor):
    """
    rgb: numpy array in (h, w, c)
    """
    if isTensor:
        rgb = rgb_tensor_to_img(rgb)
    yvu = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    y, v, u = cv2.split(yvu)
    u = cv2.resize(u, (u.shape[1]//2, u.shape[0]//2))
    v = cv2.resize(v, (v.shape[1]//2, v.shape[0]//2))
    return y, u, v, np.concatenate((y,u,v), axis=None)

def metric_all_in_one(Y1_raw, Y1_com):
    """
    returns:
        rgbpsnr, rgbssim, yuvpsnr, yuvssim
    """
    rgbpsnr = PSNR(Y1_raw, Y1_com)
    # breakpoint()
    rgbssim = float(ssim( Y1_raw.float().cuda().unsqueeze(0), Y1_com.float().unsqueeze(0), data_range=1, size_average=False).cpu().detach())

    # y1, u1, v1, yuv1 = RGB2YUV(Y1_raw, True)
    # y2, u2, v2, yuv2 = RGB2YUV(Y1_com, True)

    # yuvpsnr = PSNR_YUV(yuv1, yuv2)
    # yuvssim = SSIM_YUV(y1, y2)
    return float(rgbpsnr), rgbssim, 0, 0

def FFMPEG_PSNR(enc_frames, raw_frames, outfile):
    """
    frames: frames in torch tensor C,H,W format
    raw_video: the name of raw_video
    """
    def get_output_folder():
        output_filename = f'/tmp/output-{np.random.randint(0, 100000)}-folder'
        while os.path.exists(output_filename):
            output_filename = f'/tmp/output-{np.random.randint(0, 100000)}-folder'
        os.makedirs(output_filename, exist_ok=True)
        return output_filename

    def free_tmp_folder(outfile):
        os.system("rm -rf {}".format(outfile))

    outfolder = get_output_folder()
    print("The folder is", outfolder)
    for idx, frame in tqdm(enumerate(enc_frames)):
        save_image(frame, os.path.join(outfolder, f"enc-{idx:03d}.png"))
    for idx, frame in tqdm(enumerate(raw_frames)):
        save_image(frame, os.path.join(outfolder, f"raw-{idx:03d}.png"))

    cmd = f"ffmpeg -i {outfolder}/enc-%03d.png -crf 0 {outfolder}/enc.mp4"
    os.system(cmd)
    cmd = f"ffmpeg -i {outfolder}/raw-%03d.png -crf 0 {outfolder}/raw.mp4"
    os.system(cmd)

    os.system(f"ffmpeg -i {outfolder}/enc.mp4 -i {outfolder}/raw.mp4 -lavfi psnr=stats_file={outfile}.psnr -f null -")
    os.system(f"ffmpeg -i {outfolder}/enc.mp4 -i {outfolder}/raw.mp4 -lavfi ssim=stats_file={outfile}.ssim -f null -")

    free_tmp_folder(outfolder)


def get_block_psnr(frame_id, gt_frame, dec_frame, w_step, h_step):
    """
    return frame_id, blk_id, psnr
    """
    C, H, W = dec_frame.shape
    psnrs = []
    for h in range(0, H, h_step):
        for w in range(0, W, w_step):
            gt_clip = gt_frame[:, h:h+h_step, w:w+w_step]
            dec_clip = dec_frame[:, h:h+h_step, w:w+w_step]
            value = PSNR(gt_clip, dec_clip)
            psnrs.append(float(value))
    ret = pd.DataFrame()
    ret["psnr"] = psnrs
    ret["frame_id"] = frame_id
    ret["block_id"] = ret.index
    return ret


METRIC_FUNC = PSNR

def read_video_into_frames(video_path, frame_size=None, nframes=1000):
    """
    Input:
        video_path: the path to the video
        frame_size: resize the frame to a (width, height), if None, it will not do resize
        nframes: number of frames
    Output:
        frames: a list of PIL images
    """
    def create_temp_path():
        path = f"/tmp/yihua_frames-{np.random.randint(0, 1000)}/"
        while os.path.isdir(path):
            path = f"/tmp/yihua_frames-{np.random.randint(0, 1000)}/"
        os.makedirs(path, exist_ok=True)
        return path

    def remove_temp_path(tmp_path):
        os.system("rm -rf {}".format(tmp_path))

    frame_path = create_temp_path()
    if frame_size is None:
        cmd = f"ffmpeg -i {video_path} {frame_path}/%03d.png 2>/dev/null 1>/dev/null"
        #cmd = f"ffmpeg -i {video_path} {frame_path}/%03d.png"
    else:
        width, height = frame_size
        cmd = f"ffmpeg -i {video_path} -s {width}x{height} {frame_path}/%03d.png 2>/dev/null 1>/dev/null"

    print(cmd)
    os.system(cmd)

    image_names = os.listdir(frame_path)
    frames = []
    for img_name in sorted(image_names)[:nframes]:
        frame = Image.open(os.path.join(frame_path, img_name))

        ''' pad to nearest 64 for DVC model '''
        padsz = 64
        w, h = frame.size
        pad_w = int(np.ceil(w / padsz) * padsz)
        pad_h = int(np.ceil(h / padsz) * padsz)

        frames.append(frame.resize((pad_w, pad_h)))

    print(f"frame path is: {frame_path}")
    print(f"Got {len(image_names)} image names and {len(frames)} frames")
    print("frameSize", len(frames))
    print("Resizing image to", frames[0].size)
    remove_temp_path(frame_path)
    return frames

def read_video_into_frames_opencv(video_path, frame_size=None, nframes=1000):
    """
    Input:
        video_path: the path to the video
        frame_size: resize the frame to a (width, height), if None, it will not do resize
        nframes: number of frames
    Output:
        frames: a list of PIL images
    """
    import cv2
    cap = cv2.VideoCapture(video_path)
    frames = []
    while cap.isOpened():
        ret, img = cap.read()
        if not ret:
            break
        if np.sum(img) == 0:
            continue

        img = Image.fromarray(img)
        if frame_size is not None:
            img = img.resize(frame_size)
        else:
            ''' pad to nearest 64 '''
            padsz = 64
            w, h = img.size
            pad_w = int(np.ceil(w / padsz) * padsz)
            pad_h = int(np.ceil(h / padsz) * padsz)
            img = img.resize((pad_w, pad_h))
        frames.append(img)

        if len(frames) >= nframes:
            break
    print("Resizing image to", frames[-1].size)
    return frames

lib = ctypes.CDLL("libs/bpgenc.so")
lib2 = ctypes.CDLL("libs/bpgdec.so")
bpg_encode_bytes = lib.bpg_encode_bytes
bpg_decode_bytes = lib2.bpg_decode_bytes
get_buf = lib.get_buf
get_buflen = lib.get_buf_length
free_mem = lib.free_memory
get_buf.restype = ctypes.POINTER(ctypes.c_char)
bpg_decode_bytes.restype = ctypes.POINTER(ctypes.c_char)

def bpg_encode(img):
    frame = (torch.clamp(img, min = 0, max = 1) * 255).round().byte()
    _, h, w = frame.shape
    frame2 = frame.permute((1, 2, 0)).flatten()
    bs = frame2.numpy().tobytes()
    ubs = (ctypes.c_ubyte * len(bs)).from_buffer(bytearray(bs))
    bpg_encode_bytes(ubs, h, w)
    buflen =  get_buflen()
    buf = get_buf()
    bpg_stream = ctypes.string_at(buf, buflen)
    free_mem(buf)
    return bpg_stream, h, w, len(bpg_stream)

def bpg_decode(bpg_stream, h, w):
    ub_result = (ctypes.c_ubyte * len(bpg_stream)).from_buffer(bytearray(bpg_stream))
    rgb_decoded = bpg_decode_bytes(ub_result, len(bpg_stream), h, w)
    b = ctypes.string_at(rgb_decoded, h * w * 3)
    bytes = np.frombuffer(b, dtype=np.byte).reshape((h, w, 3))
    image = torch.tensor(bytes).permute((2, 0, 1)).byte().float().cuda()
    image = image / 255
    free_mem(rgb_decoded)
    return image

class IPartFrame:
    def __init__(self, code, shapex, shapey, offset_width, offset_height):
        self.code = code
        self.shapex = shapex
        self.shapey = shapey
        self.offset_width = offset_width
        self.offset_height = offset_height

class EncodedFrame:
    """
    self.code is torch.tensor
    """
    def __init__(self, code, shapex, shapey, frame_type, frame_id):
        self.code = code
        self.shapex = shapex
        self.shapey = shapey
        self.frame_type = frame_type
        self.frame_id = frame_id
        self.loss_applied = False
        self.ipart = None
        self.isize = None

    def apply_loss(self, loss_ratio, blocksize = 100):
        """
        default block size is 100
        """
        torch.manual_seed(0)
        random.seed(0)
        np.random.seed(0)

        leng = torch.numel(self.code)
        nblocks = (leng - 1) // blocksize + 1

        rnd = torch.rand(nblocks).to(self.code.device)
        rnd = (rnd > loss_ratio).long()
        #print("DEBUG: loss ratio =", loss_ratio, ", first 16 elem:", rnd[:16])
        rnd = rnd.repeat_interleave(blocksize)
        rnd = rnd[:leng].reshape(self.code.shape)
        self.code = self.code * rnd

        if self.ipart is not None and np.random.random() < loss_ratio:
            self.ipart = None

    def apply_loss_determ(self, loss_prob):
        REPEATS=64
        nelem = torch.numel(self.code)
        group_len = int((nelem - 1) // REPEATS + 1)
        rnd = torch.rand(group_len).cuda()
        rnd = (rnd > loss_prob).long()
        rnd = rnd.repeat(REPEATS)[:nelem]
        rnd = rnd.reshape(self.code.shape)
        self.code = self.code * rnd

    def apply_mask(self, mask):
        self.code = self.code * mask

    def np_code(self):
        """
        return the code in flattened numpy array
        """
        return self.code.cpu().detach().numpy().flatten()

def find_mn_from_ab(a, b):
    """
    return m, n such that a = mp, b = nq and p > 1, q > 1 and mn = {10, 12, 8, 15, 6}
    """
    mnlist = [(2, 5), (5, 2), (10, 1), (1, 10),
              (2, 6), (6, 2), (3, 4), (4, 3), (1, 12), (12, 1),
              (3, 5), (5, 3), (2, 3), (3, 2), (1, 6), (6, 1)]
    for m, n in mnlist:
        if a % m == 0 and a // m > 1 and b % n == 0 and b // n > 1:
            return m, n
    raise RuntimeError(f"No suitable m, n found for a, b = {a}, {b}")

def set_hw_step(h, w):
    """
    returns h_step and w_step
    """
    a, b = h // 64, w // 64
    m, n = find_mn_from_ab(a, b)
    return h // m, w // n

class AEModel:
    def __init__(self, qmap_coder, dvc_coder: DVCInterface, only_P=True):
        self.qmap_coder = qmap_coder
        self.dvc_coder = dvc_coder

        self.reference_frame = None
        self.frame_counter = 0
        self.gop = 8

        self.debug_output_dir = None

        self.p_index = 0
        # self.w_step = 256
        # self.h_step = 384
        self.w_step = 128
        self.h_step = 128



    def set_gop(self, gop):
        self.gop = gop

    def encode_ipart(self, frame, no_index_referesh=False):
        """
        Input:
            frame: the PIL image
        Output:
            ipart, isize: encoded frame and it's size, icode is torch.tensor on GPU
        Note:
            this function will NOT update the reference
        """
        c, h, w = frame.shape
        if w % self.w_step != 0 or h % self.h_step != 0:
            raise RuntimeError("w_step and h_step need to divide W and H")
        w_tot = w / self.w_step
        h_tot = h / self.h_step
        w_offset = int((self.p_index % w_tot) * self.w_step)
        h_offset = int(((self.p_index // w_tot) % h_tot) * self.h_step)
        print(f"P_index = {self.p_index}, w_offset = {w_offset}, h_offset = {h_offset}")


        part_iframe = frame[:, h_offset:h_offset+self.h_step, w_offset:w_offset+self.w_step]
        icode, shapex, shapey, isize = self.qmap_coder.encode(part_iframe)
        ipart = IPartFrame(icode, shapex, shapey, w_offset, h_offset)
        if no_index_referesh == False:
            self.p_index += 1

        return ipart, isize

    def encode_frame(self, frame, isIframe = False, no_index_referesh=False):

        """
        Input:
            frame: the PIL image
        Output:
            eframe: encoded frame, code is torch.tensor on GPU
            tot_size: the total size of p rame and I patch
        Note:
            this function will NOT update the reference
        """
        print("steps:", self.h_step , self.w_step )
        self.frame_counter += 1
        frame = to_tensor(frame)
        if isIframe:
            # torch.cuda.synchronize()
            # start =time.time()
            # code, shapex, shapey, size = self.qmap_coder.encode(frame)
            code, shapex, shapey, size = bpg_encode(frame)
            # torch.cuda.synchronize()
            # end =time.time()
            # print("QMAP TIME SPENT IS: ", (end - start) * 1000)
            eframe = EncodedFrame(code, shapex, shapey, "I", self.frame_counter)
            return eframe, size
        else:
            assert self.reference_frame is not None
            # use p_index to compute which part to encode the I-frame
            c, h, w = frame.shape
            if w % self.w_step != 0 or h % self.h_step != 0:
                raise RuntimeError("w_step and h_step need to divide W and H")

            # torch.cuda.synchronize()
            # print("IPatch size is: ", self.h_step, self.w_step)
            # icode, shapex, shapey, isize = self.qmap_coder.encode(part_iframe)

            # encode P part
            # st = time.perf_counter()
            eframe = self.dvc_coder.encode(frame, self.reference_frame)
            # torch.cuda.synchronize()
            # ed = time.perf_counter()
            # print("self.dvc_coder.encode: ", (ed - st) * 1000)
            # encode I part
            # st = time.perf_counter()
            w_tot = w / self.w_step
            h_tot = h / self.h_step
            print(3)
            w_offset = int((self.p_index % w_tot) * self.w_step)
            h_offset = int(((self.p_index // w_tot) % h_tot) * self.h_step)
            print(f"P_index = {self.p_index}, w_offset = {w_offset}, h_offset = {h_offset}")
            part_iframe = frame[:, h_offset:h_offset+self.h_step, w_offset:w_offset+self.w_step]
            icode, shapex, shapey, isize = bpg_encode(part_iframe)
            # ed = time.perf_counter()
            # print("self.bpg_encode: ", (ed - st) * 1000)
            ipart = IPartFrame(icode, shapex, shapey, w_offset, h_offset)
            eframe.ipart = ipart
            eframe.isize = isize
            eframe.frame_type = "P"

            if no_index_referesh == False:
                self.p_index += 1
            # print(eframe.frame_type)
            return eframe, self.dvc_coder.entropy_encode(eframe) + isize

    def decode_frame(self, eframe:EncodedFrame):
        """
        Input:
            eframe: the encoded frame (EncodedFrame object)
        Output:
            frame: the decoded frame in torch.tensor (3,h,w) on GPU, which can be used as ref frame
        Note:
            this function will NOT update the reference
        """
        if eframe.frame_type == "I":
            # out = self.qmap_coder.decode(eframe.code, eframe.shapex, eframe.shapey)
            out = bpg_decode(eframe.code, eframe.shapex, eframe.shapey)
            return out
        else:
            assert self.reference_frame is not None
            #out = self.dvc_coder.decode(eframe.code, self.reference_frame, eframe.shapex, eframe.shapey)
            # st = time.perf_counter()
            out = self.dvc_coder.decode(eframe, self.reference_frame)
            # torch.cuda.synchronize()
            # ed = time.perf_counter()
            # print("self.dvc_coder.decode:", (ed - st) * 1000)
            if eframe.ipart is not None:
                ipart = eframe.ipart
                # idec = self.qmap_coder.decode(ipart.code, ipart.shapex, ipart.shapey)
                # st = time.perf_counter()
                idec = bpg_decode(ipart.code, ipart.shapex, ipart.shapey)
                # torch.cuda.synchronize()
                # ed = time.perf_counter()
                # print("self.bpg_decode:", (ed - st) * 1000)

                out[:, ipart.offset_height:ipart.offset_height+self.h_step, ipart.offset_width:ipart.offset_width+self.w_step] = idec

            return out


    def encode_video(self, frames, perfect_iframe=False, use_mpeg=True):
        """
        Input:
            frames: PIL images
        Output:
            list of METRIC_FUNC and list of BPP
        """
        import dvc.net
        dvc.net.DEBUG_USE_MPEG = True
        bpps = []
        psnrs = []
        test_iter = tqdm(frames)
        dec_frames = []
        for idx, frame in enumerate(test_iter):
            # encode the frame
            if idx % self.gop == 0:
                ''' I FRAME '''
                if perfect_iframe:
                    self.update_reference(to_tensor(frame))
                    bpps.append(0)
                    psnrs.append(99)

                    dec_frames.append(to_tensor(frame)) # for ffmpeg psnr calculation
                else:
                    eframe, size = self.encode_frame(frame, "I")
                    decoded = self.decode_frame(eframe)
                    self.update_reference(decoded)

                    dec_frames.append(decoded) # for ffmpeg psnr calculation

                    # compute bpp
                    w, h = frame.size
                    bpp = size * 8 / (w * h)
                    bpps.append(bpp)

                    # compute psnr
                    tframe = to_tensor(frame)
                    psnr = float(METRIC_FUNC(tframe, decoded))
                    psnrs.append(psnr)

                    print("IFRAME: bpp =", bpp, "PSNR =", psnr)

            else:
                # eframe, z = self.encode_frame(frame)
                eframe, tot_size = self.encode_frame(frame)

                # decode frame
                w, h = frame.size
                decoded = self.decode_frame(eframe)

                dec_frames.append(to_tensor(frame)) # for ffmpeg psnr calculation
                self.update_reference(decoded)

                # compute psnr
                tframe = to_tensor(frame)
                psnr = float(METRIC_FUNC(tframe, decoded))
                psnrs.append(psnr)


                # compute bpp
                ''' whole frame compression '''
                # bs, tot_size = self.entropy_coder.entropy_encode(eframe.code, \
                                        # eframe.shapex, eframe.shapey, z)
                # tot_size =
                w, h = frame.size
                tot_size += eframe.isize
                bpp = tot_size * 8 / (w * h)
                print("Frame id = {}, P bpp = {}, I part bpp = {}".format(idx, (tot_size - eframe.isize) * 8 / (w * h), eframe.isize * 8 / (w * h)))
                bpps.append(bpp)

            test_iter.set_description(f"bpp:{np.mean(bpps):.4f}, psnr:{np.mean(psnrs):.4f}")

        assert len(dec_frames) == len(frames)
        #FFMPEG_PSNR(dec_frames, [to_tensor(_) for _ in frames], "/datamirror/yihua98/projects/aecodec_largescale/sim_db/temp")
        return psnrs, bpps



    def update_reference(self, ref_frame):
        """
        Input:
            ref_frame: reference frame in torch.tensor with size (3,h,w). On GPU
        """
        self.reference_frame = ref_frame

    def fit_frame(self, frame):
        """
        set the h_step and w_step for the encoder
        frame is a PIL image
        """
        w, h = frame.size
        self.h_step, self.w_step = set_hw_step(h, w)

    def get_avg_freeze_psnr(self, frames):
        res = []
        for idx, frame in enumerate(frames[2:]):
            img1 = to_tensor(frame)
            img2 = to_tensor(frames[idx-2])
            res.append(METRIC_FUNC(img1, img2))
        return float(np.mean(res))




def init_ae_model(qmap_quality=1):
    qmap_config_template = {
            "N": 192,
            "M": 192,
            "sft_ks": 3,
            "name": "default",
            "path": "/dataheart/autoencoder_dataset/datamirror/autoencoder_dataset/snapshot/qmap_pretrained.pt",
            "quality": qmap_quality,
        }
    qmap_coder = None # QmapModel(qmap_config_template)

    GRACE_MODEL = "models/grace"
    models = {
            "64": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/64_freeze.model"}, scale_factor=0.25)),
            "128": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/128_freeze.model"}, scale_factor=0.5)),
            "256": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/256_freeze.model"}, scale_factor=0.5)),
            "512": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/512_freeze.model"}, scale_factor=0.5)),
            "1024": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/1024_freeze.model"}, scale_factor=0.5)),
            "2048": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/2048_freeze.model"})),
            "4096": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/4096_freeze.model"})),
            "6144": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/6144_freeze.model"})),
            "8192": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/8192_freeze.model"})),
            "12288": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/12288_freeze.model"})),
            "16384": AEModel(qmap_coder, DVCInterface({"path": f"{GRACE_MODEL}/16384_freeze.model"})),
            }

    return models


def profile_psnr_bpp(cur_frame_id):
    print("Profiling the frame sizes...")
    global models, frames_origin, avgbpp_map
    # avgbpp_map['128'] = 0.065
    # avgbpp_map['256'] = 0.073
    # avgbpp_map['512'] = 0.085
    # avgbpp_map['1024'] = 0.095
    # avgbpp_map['2048'] = 0.11
    # avgbpp_map['4096'] = 0.12
    # if(cur_frame_id >= 100):
    #     avgbpp_map['128'] = 0.054*0.8
    #     avgbpp_map['256'] = 0.059*0.9
    #     avgbpp_map['512'] = 0.066*0.9
    #     avgbpp_map['1024'] = 0.07
    #     avgbpp_map['2048'] = 0.074
    #     avgbpp_map['4096'] = 0.09
    # elif(cur_frame_id<50):
    #     avgbpp_map['128'] = 0.07
    #     avgbpp_map["256"] = 0.083
    #     avgbpp_map["512"] = 0.095
    #     avgbpp_map["1024"] = 0.12
    #     avgbpp_map['2048'] = 0.17
    #     avgbpp_map["4096"] = 0.22

    # return
    for key in models.keys():
        model = models[key]
        psnrs, bpps = model.encode_video(frames_origin[cur_frame_id:cur_frame_id+11])
        mean_bpp = np.mean(bpps[1:])
        avgbpp_map[key] = mean_bpp

    print("\033[32mProfile result: ",  avgbpp_map, "\033[0m")

def get_ae_model_id(target_size_in_byte, w, h):
    global models
    target_bpp = target_size_in_byte * 8 / (w * h)
    print("\033[32mTarget bpp is: ",  target_bpp, "\033[0m")
    result = list(models.keys())[0]
    for model_id in models.keys():
        if avgbpp_map[model_id] > target_bpp:
            if(avgbpp_map[result] *0.5 + avgbpp_map[model_id]*0.5 < target_bpp):
                return model_id
            else:
                return result
        else:
            result = model_id
    return result

entropy_times = []
def encode_frame(ae_model: AEModel, is_iframe, ref_frame, new_frame, no_index_referesh=False):
    """
    ref_frame: torch tensor C, H, W
    new_frame: PIL image

    returns:
        size in bytes
        the eframe
    """
    if ref_frame is not None:
        ae_model.update_reference(ref_frame)
    else:
        if not is_iframe:
            raise RuntimeError("Cannot encode a P-frame without reference frame")

    eframe, size = ae_model.encode_frame(new_frame, is_iframe)
    return size, eframe
    #if is_iframe:
    #    eframe, size = ae_model.encode_frame(new_frame, True)
    #    return size, eframe
    #else:
    #    eframe = ae_model.encode_frame(new_frame, False, no_index_referesh=no_index_referesh)

    #    #global entropy_times
    #    #tmp = time.time()
    #    #bs, tot_size = ae_model.entropy_coder.entropy_encode(eframe.code, \
    #    #                                eframe.shapex, eframe.shapey, z, use_estimation=True)
    #    #end = time.time()
    #    #entropy_times += [end - tmp]
    #    return tot_size + eframe.isize, eframe

def decode_frame(ae_model: AEModel, eframe: EncodedFrame, ref_frame, loss):
    """
    ref_frame: the tensor frame in 3, h, w

    returns:
        decoded frame
    """
    if ref_frame is not None:
        ae_model.update_reference(ref_frame)
    else:
        if not eframe.frame_type == "I":
            raise RuntimeError("Cannot decode a P-frame without reference frame")

    if eframe.frame_type == "I":
        if loss > 0:
            print("Error! Cannot add loss on I frame, it will cause huge error!")
        decoded = ae_model.decode_frame(eframe)
        return decoded
    else:
        eframe.apply_loss(loss, 1)
        ae_model.update_reference(ref_frame)
        decoded = ae_model.decode_frame(eframe)
        return decoded


def decode_fix(ae_model: AEModel, decoded, gt_frame):
    # for bug fix: if one block have a very bad psnr (<15), fix it with a qmap encoding
    W,H = gt_frame.size
    tot_psnr = PSNR(decoded, to_tensor(gt_frame))
    if tot_psnr >= 30:
        return decoded

    print(f"\033[31mFound bad decoded image, trying to figure out where it is!\033[0m")
    for w in range(0, W, 128):
        for h in range(0, H, 128):
            ws, we = w, w + 128
            hs, he = h, h + 128
            if we > W:
                ws, we = W-128, W
            if he > H:
                hs, he = H-128, H
            dec_crop = decoded[:, hs:he, ws:we]
            gt_crop = to_tensor(gt_frame)[:, hs:he, ws:we]
            psnr = PSNR(dec_crop, gt_crop)
            if psnr < 5:
                print(f"\033[31mFound an bad crop at: {ws}:{hs}! Adding a patch to it!\033[0m")
                eframe, sz = ae_model.encode_frame(gt_frame.crop((ws, hs, we, he)), True, True)
                dec_frame = ae_model.decode_frame(eframe)
                decoded[:, hs:he, ws:we] = dec_frame

    return decoded

def update_profile_with_encode(model_id, size, w, h):
    global avgbpp_map
    bpp = size * 8 / (w * h)
    ratio_map = {}
    for key in models.keys():
        ratio_map[key] = avgbpp_map[key] / avgbpp_map[model_id]

    for key in models.keys():
        avgbpp_map[key] = (ratio_map[key] * bpp) * 0.5 + avgbpp_map[key] * 0.5

def get_cur_profile_with_table(ae_model_id, size, w, h):
    bpp = size * 8 / (w * h)
    ratio_map = {}
    new_profile_map = {}
    for key in models.keys():
        ratio_map[key] = avgbpp_map[key] / avgbpp_map[ae_model_id]
        new_profile_map[key] = (ratio_map[key] * bpp)
    return new_profile_map

def wrapped_encode(target_size_in_byte, cur_frame_id,
                    local = True, is_iframe = False):
    start = time.time()
    # print("YIHUA: wrapped_encode ", target_size_in_byte, cur_frame_id, ref_frame_id, ref_frame_sent, ref_frame_dropped, local, is_iframe)
    if (cur_frame_id % 30 == 0):
        torch.cuda.empty_cache()
    total_frame_number = len(frames_origin)

    global next_profile, frames_decoded_receiver, frames_decoded_sender, encode_up, encode_down
    # print("\033[32mProfile result: ",  avgbpp_map, "\033[0m")
    w, h = frames_origin[cur_frame_id % total_frame_number].size
    ae_model_id = get_ae_model_id(target_size_in_byte, w, h)
    keep_encode_flag = True      #it turns false if no need to encode
    have_already_encoded = False
    target_bpp = target_size_in_byte * 8 /w /h
    while(keep_encode_flag):
        print("\033[32m Encoding cur_frame_id: ", cur_frame_id, " ref_id: ", cur_frame_id - 1, " Selected model: ",  ae_model_id, "\033[0m")
        ae_model =models[ae_model_id]

        used_model_ids[cur_frame_id] = ae_model_id
        frame = frames_origin[cur_frame_id % total_frame_number]

        if cur_frame_id > next_profile:
            profile_psnr_bpp(cur_frame_id)
            next_profile += 60

        if cur_frame_id == 0 or is_iframe:
            size, eframe = encode_frame(ae_model, True, None, frame)
            decoded = decode_frame(ae_model, eframe, None, 0)
            codes[cur_frame_id] = eframe
            frames_decoded_sender = decoded
            return size

        """ now, only P frames are here """
        if local:
            ref_frame = frames_decoded_sender
        else:
            ref_frame = frames_decoded_receiver

        if ref_frame is None:
            raise RuntimeError(f"Reference frame not found for local mode = {local}")

        cur_frame = frames_origin[cur_frame_id % total_frame_number]

        size, eframe = encode_frame(ae_model, False, ref_frame, cur_frame)
        decoded = decode_frame(ae_model, eframe, ref_frame, 0)
        decoded = torch.clamp(decoded, min = 0, max = 1)

        if (not have_already_encoded):
                update_profile_with_encode(ae_model_id, size, w, h)
        print(f"\033[32mNew Profiling table is:\033[0m")
        print(avgbpp_map)
        cur_profile = get_cur_profile_with_table(ae_model_id, size, w, h)
        ''' update internal state '''
        codes[cur_frame_id] = eframe

        print(f"\033[32mEncoded bytes = {size}, bpp = {size * 8 / w / h}\033[0m")
        print("Have already encoded flag is: ", have_already_encoded)
        torch.cuda.empty_cache()

        previous_model = ae_model_id
        if((size <= target_size_in_byte * 1 and size > target_size_in_byte* 0.8) or have_already_encoded):
            print(size, target_size_in_byte)
            keep_encode_flag = False
        elif (size > target_size_in_byte * 1 and ae_model_id != "64"):
            ae_model_id = "64"

            print(cur_profile)
            for model_id in models.keys():
                if cur_profile[model_id] < target_bpp:
                    ae_model_id = model_id
            have_already_encoded = True
            if(ae_model_id == previous_model):
                print("real_size is:",size, "target size is:",target_size_in_byte)
                keep_encode_flag = False
            else:
                encode_down += 1
        elif (size < 0.8 * target_size_in_byte and ae_model_id != "16384"):
            ae_model_id = str(int(int(ae_model_id) * 2))

            for model_id in models.keys():
                if cur_profile[model_id] < target_bpp * 0.95:
                    ae_model_id = model_id
            have_already_encoded = True
            if(ae_model_id == previous_model):
                print("real_size is:",size, "target size is:",target_size_in_byte)
                keep_encode_flag = False
            else:
                encode_up += 1
        else:
            print("real_size is:",size, "target size is:",target_size_in_byte)
            keep_encode_flag = False

    frames_decoded_sender = decoded
    print("\033[32m cur_frame_id: ", cur_frame_id, " ref_id: ", cur_frame_id - 1, " Selected model: ",  ae_model_id, "\033[0m")
    end = time.time()
    print("\033[31mencoding used time =", end - start, "\033[0m")
    # if (ae_model_id == "64" and size > target_size_in_byte):
    #     size = max(2500, target_size_in_byte)

    if (cur_frame_id == 1123):
        with open(os.path.dirname(image_path)+"/second_encode_time.txt", "w") as writer:
            writer.write("encode_up: "+ str(encode_up)+' encode_down: '+str(encode_down))

    global max_encoded_frame_id
    max_encoded_frame_id = cur_frame_id
    return size


image_save_buffer = []
def my_save_image(image, name):
    image_save_buffer.append((image, name))
    if len(image_save_buffer) > 10:
        print("SAVING 10 IMAGES")
        for image, name in image_save_buffer:
            save_image(image, name)
        image_save_buffer.clear()


def wrapped_decode(cur_frame_id, loss_rate, save_img_flag,
                    is_iframe = False):
    start = time.time()
    recorded_losses[cur_frame_id] = loss_rate
    # cur_frame_dropped = 0
    #print("YIHUA: wrapped_decode ", cur_frame_id, cur_frame_sent, cur_frame_dropped, ref_frame_id, is_iframe)
    total_frame_number = len(frames_origin)
    global frames_decoded_receiver
    model_id = used_model_ids[cur_frame_id]
    ae_model = models[model_id]
    eframe = codes[cur_frame_id]
    #codes[cur_frame_id] = 0

    if is_iframe and eframe.frame_type == "P":
        raise RuntimeError("Frame encoded with P-frame but want to decode with I frame")

    ref_frame = frames_decoded_receiver
    decoded = decode_frame(ae_model, eframe, ref_frame, loss_rate)
    decoded = torch.clamp(decoded, min = 0, max = 1)

    global max_decoded_frame_id
    global decoder_ref_cache
    max_decoded_frame_id = cur_frame_id
    decoder_ref_cache[max_decoded_frame_id] = decoded
    # decoded = decode_fix(ae_model, decoded, frames_origin[cur_frame_id])

    # save_image(decoded, f"/dataheart/autoencoder_dataset/datamirror/autoencoder_dataset/yihua-ae-for-sim/debughc/dec-{cur_frame_id}.png")
    #frames_origin[cur_frame_id].save(f"debug/orig-{cur_frame_id}.png")

    ''' compute psnr and update internal states '''
    if (save_img_flag == 1):
        frames_origin[cur_frame_id % total_frame_number].save(f"{image_path}/orig-{str(cur_frame_id)}.png")
        #save_image(decoded, f"{image_path}/dec-{str(cur_frame_id)}.png")
        my_save_image(decoded, f"{image_path}/dec-{str(cur_frame_id)}.png")

    psnr = metric_all_in_one(to_tensor(frames_origin[cur_frame_id % total_frame_number]), decoded)
    #psnr = float(psnrJJ)
    # frames_origin[cur_frame_id] = 0
    frames_decoded_receiver = decoded
    print("-------psnr is: ", psnr)
    torch.cuda.empty_cache()
    end = time.time()
    print("\033[31mdecoding used time =", end - start, "\033[0m")
    return psnr

def on_decoder_feedback(frame_id):
    global synced_frame_id
    global recorded_losses
    global decoder_ref_cache
    global max_decoded_frame_id
    global frames_decoded_sender
    if recorded_losses[frame_id] > 0 and frame_id > synced_frame_id:
        #import pdb
        #pdb.set_trace()
        print("OnDecoderFeedback: updating the encoder reference frame", frame_id, synced_frame_id)
        ''' get the latest decoded frame '''
        ref_frame = decoder_ref_cache[frame_id]

        ''' update the encoder ref '''
        for idx, eframe in enumerate(codes[frame_id+1:max_encoded_frame_id+1]):
            temp_fid = frame_id + idx + 1
            ae_model = models[used_model_ids[temp_fid]]
            decoded = decode_frame(ae_model, eframe, ref_frame, 0)
            decoded = torch.clamp(decoded, min = 0, max = 1)
            ref_frame = decoded

        frames_decoded_sender = decoded
        synced_frame_id = frame_id

    keys = list(decoder_ref_cache.keys())
    for fid in keys:
        if fid <= frame_id:
            del decoder_ref_cache[fid]
            codes[fid] = 0

    torch.cuda.empty_cache()

def reset_everything(video_path, img_path):
    global image_path, frames_origin, frames_decoded_sender, frames_decoded_receiver, codes, used_model_ids
    image_path = img_path
    os.system("rm -rf "+ img_path)
    os.makedirs(img_path, exist_ok=True)

    print(f"Loading the video {video_path}... ")
    frames_origin = read_video_into_frames(video_path)
    codes = [None] * len(frames_origin)
    used_model_ids = [None] * len(frames_origin)
    frames_decoded_receiver = frames_origin[0]
    frames_decoded_sender = frames_origin[0]

    print("Adjusting the internal parameters by frame sizes ...")

    # [model.fit_frame(frames_origin[0]) for model in models.values()]
    # breakpoint()
    [model.set_gop(60) for model in models.values()]

    #bppfilename = "/dataheart/autoencoder_dataset/datamirror/autoencoder_dataset/yihua-ae-for-sim/avgbpp.json"
    bppfilename = "avgbpp-grace.json"
    global avgbpp_map
    if os.path.exists(bppfilename):
        with open(bppfilename, "r") as fin:
            avgbpp_map = json.load(fin)
    else:
        print("profiling the bpp ...")
        profile_psnr_bpp(0)
        with open(bppfilename, "w") as fout:
            print(json.dumps(avgbpp_map), file=fout)
    print(avgbpp_map)

    wrapped_encode(50000, 0)
    tuple = wrapped_decode(0, 0, 0)
    print(tuple[1])
    return 0


def test():
    reset_everything("/dataheart/autoencoder_dataset/yihua-share/new-segment_49y_ANuMQfI_1280x768.y4m", "Fake")
    losses = np.zeros(900)

    psnrs = []
    for idx, loss in enumerate(losses):
        # size = wrapped_encode(10000, idx, is_iframe= True)
        size = wrapped_encode(100000, idx, is_iframe= False)
        if idx - 1 >= 0:
            if((idx>=330 and idx <360) or (idx >= 420 and idx<450) or (idx >= 690 and idx<720) or (idx>=780 and idx<810)):
                psnr = wrapped_decode(idx-1, 0.4, True)
            else:
                psnr = wrapped_decode(idx-1, 0, True)
            psnrs.append(psnr)
        if idx - 5 >= 0:
            on_decoder_feedback(idx - 5)

def test_psnr_loss(loss):
    reset_everything("/dataheart/autoencoder_dataset/yihua-share/new-segment_49y_ANuMQfI_1280x768.y4m", "no_path")
    losses = np.zeros(10)
    losses[5] = loss

    psnrs = []
    for idx, loss in enumerate(losses):
        size = wrapped_encode(10000, idx)
        #if idx - 2 >= 0:
        psnr = wrapped_decode(idx, loss, False)
        psnrs.append(psnr)

    for idx, v in enumerate(psnrs):
        print(idx, v[0])
    print(np.mean(list(zip(*psnrs))[0]))
    return psnrs[5]

#values = list(map(test_psnr_loss, np.arange(0, 0.85, 0.1)))
#for p, s, _, _ in values:
#    print(p, s)


# test()
# import cProfile, pstats, io
# from pstats import SortKey
# pr = cProfile.Profile()

# pr.enable()
# test()
# pr.disable()
# s = io.StringIO()
# sortby = SortKey.CUMULATIVE
# ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
# ps.print_stats()
# print(s.getvalue())


frames_origin = []
frames_decoded_receiver = 0
frames_decoded_sender = 0
decoder_ref_cache = {}
max_decoded_frame_id = 0
max_encoded_frame_id = 0
codes = []
used_model_ids = []
recorded_losses = {}
synced_frame_id = 0
avgbpp_map = {}
image_path = ""
# next_profile = 60
next_profile = 10000000
encode_up = 0
encode_down = 0
torch.use_deterministic_algorithms(True)
models = init_ae_model()

reset_everything("'../../data/videos/autoencoder_dataset/GAM/game-0.mp4'", "my_img_path")
