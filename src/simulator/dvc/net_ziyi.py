import numpy as np
import torch.nn.functional as nnf
import os
import torch
import torch.cuda
import torchvision.models as models
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader
import sys
import math
import torch.nn.init as init
import logging
from torch.nn.parameter import Parameter
#from subnet import *
from .subnet2 import *
import torchac
from mvextractor.videocap import VideoCap
from torchvision.transforms.functional import to_tensor, to_pil_image

SCALE_FACTOR = 1

def save_model(model, iter):
    torch.save(model.state_dict(), "./snapshot/iter{}.model".format(iter))

def load_model(model, f):
    with open(f, 'rb') as f:
        pretrained_dict = torch.load(f)
        model_dict = model.state_dict()
        pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
        # print(pretrained_dict.keys())
        model_dict.update(pretrained_dict)
        model.load_state_dict(model_dict)
    f = str(f)
    if f.find('iter') != -1 and f.find('.model') != -1:
        st = f.find('iter') + 4
        ed = f.find('.model', st)
        return int(f[st:ed])
    else:
        return 0



class VideoCompressor(nn.Module):
    def __init__(self):
        super(VideoCompressor, self).__init__()
        # self.imageCompressor = ImageCompressor()
        self.opticFlow = ME_Spynet()            # 1
        self.mvEncoder = Analysis_mv_net()
        self.Q = None
        self.mvDecoder = Synthesis_mv_net()
        self.warpnet = Warp_net()
        self.resEncoder = Analysis_net()
        self.resDecoder = Synthesis_net()
        self.respriorEncoder = Analysis_prior_net()
        self.respriorDecoder = Synthesis_prior_net()
        self.bitEstimator_z = BitEstimator(out_channel_N, out_channel_N)
        self.bitEstimator_mv = BitEstimator(out_channel_mv, out_channel_mv_new)
        self.bitEstimator_mv_z = BitEstimator(out_channel_mv_z, out_channel_mv_z)

        self.mvpriorEncoder = Mv_enc_prior_net()
        self.mvpriorDecoder = Mv_dec_prior_net()
        

        
        # self.flow_warp = Resample2d()
        # self.bitEstimator_feature = BitEstimator(out_channel_M)
        self.warp_weight = 0
        self.mxrange = 150
        self.calrealbits = False
        self.mv_scale = 1
        self.scale_factor = 1
        self.use_h264mv = False

        self.quantization_param = 1



    def set_quantization_param(self, q):
        self.quantization_param = q

    def forwardFirstFrame(self, x):
        output, bittrans = self.imageCompressor(x)
        cost = self.bitEstimator(bittrans)
        return output, cost

    def set_use_h264mv(self, x):
        print("setting use_h264mv = ", x, type(x))
        self.use_h264mv = x
    
    

    def motioncompensation(self, ref, mv):
        # h = ref.dtype == torch.float16
        # h = False
        # if h:
        #     ref = ref.float()
        #     mv = mv.float()
        warpframe = flow_warp(ref, mv)
        inputfeature = torch.cat((warpframe, ref), 1)
        prediction = self.warpnet(inputfeature) + warpframe
        # if h:
        #     prediction = prediction.half()
        #     warpframe = warpframe.half()
        return prediction, warpframe

    def forward(self, input_image, referframe, quant_noise_feature=None, quant_noise_z=None, quant_noise_mv=None):
        estmv = self.opticFlow(input_image, referframe)
        mvfeature = self.mvEncoder(estmv, self.mv_scale)
        if self.training:
            quant_mv = mvfeature + quant_noise_mv
        else:
            quant_mv = torch.round(mvfeature)
            #quant_mv = torch.zeros(quant_mv.size(), device=quant_mv.device)
        quant_mv_upsample = self.mvDecoder(quant_mv, self.mv_scale)

        prediction, warpframe = self.motioncompensation(referframe, quant_mv_upsample)

        input_residual = input_image - prediction

        feature = self.resEncoder(input_residual)
        batch_size = feature.size()[0]
        z = self.respriorEncoder(feature)

        if self.training:
            compressed_z = z + quant_noise_z
        else:
            compressed_z = torch.round(z)

        recon_sigma = self.respriorDecoder(compressed_z)

        feature_renorm = feature

        if self.training:
            compressed_feature_renorm = feature_renorm + quant_noise_feature
        else:
            compressed_feature_renorm = torch.round(feature_renorm)
            #compressed_feature_renorm = torch.zeros(feature_renorm.size(), device=feature_renorm.device)

        recon_res = self.resDecoder(compressed_feature_renorm)
        recon_image = prediction + recon_res

        clipped_recon_image = recon_image.clamp(0., 1.)


        # distortion
        mse_loss = torch.mean((recon_image - input_image).pow(2))

        # psnr = tf.cond(
        #     tf.equal(mse_loss, 0), lambda: tf.constant(100, dtype=tf.float32),
        #     lambda: 10 * (tf.log(1 * 1 / mse_loss) / np.log(10)))

        warploss = torch.mean((warpframe - input_image).pow(2))
        interloss = torch.mean((prediction - input_image).pow(2))
        

        # bit per pixel

        def feature_probs_based_sigma(feature, sigma):
            
            def getrealbitsg(x, gaussian):
                # print("NIPS18noc : mn : ", torch.min(x), " - mx : ", torch.max(x), " range : ", self.mxrange)
                cdfs = []
                x = x + self.mxrange
                n,c,h,w = x.shape
                for i in range(-self.mxrange, self.mxrange):
                    cdfs.append(gaussian.cdf(i - 0.5).view(n,c,h,w,1))
                cdfs = torch.cat(cdfs, 4).cpu().detach()

                byte_stream = torchac.encode_float_cdf(cdfs, x.cpu().detach().to(torch.int16), check_input_bounds=True)

                real_bits = torch.from_numpy(np.array([len(byte_stream) * 8])).float().cuda()

                sym_out = torchac.decode_float_cdf(cdfs, byte_stream)

                return sym_out - self.mxrange, real_bits


            mu = torch.zeros_like(sigma)
            sigma = sigma.clamp(1e-5, 1e10)
            gaussian = torch.distributions.laplace.Laplace(mu, sigma)
            probs = gaussian.cdf(feature + 0.5) - gaussian.cdf(feature - 0.5)
            total_bits = torch.sum(torch.clamp(-1.0 * torch.log(probs + 1e-5) / math.log(2.0), 0, 50))
            
            if self.calrealbits and not self.training:
                decodedx, real_bits = getrealbitsg(feature, gaussian)
                total_bits = real_bits

            return total_bits, probs

        def iclr18_estrate_bits_z(z):
            
            def getrealbits(x):
                cdfs = []
                x = x + self.mxrange
                n,c,h,w = x.shape
                for i in range(-self.mxrange, self.mxrange):
                    cdfs.append(self.bitEstimator_z(i - 0.5).view(1, c, 1, 1, 1).repeat(1, 1, h, w, 1))
                cdfs = torch.cat(cdfs, 4).cpu().detach()
                byte_stream = torchac.encode_float_cdf(cdfs, x.cpu().detach().to(torch.int16), check_input_bounds=True)

                real_bits = torch.sum(torch.from_numpy(np.array([len(byte_stream) * 8])).float().cuda())

                sym_out = torchac.decode_float_cdf(cdfs, byte_stream)

                return sym_out - self.mxrange, real_bits

            prob = self.bitEstimator_z(z + 0.5) - self.bitEstimator_z(z - 0.5)
            total_bits = torch.sum(torch.clamp(-1.0 * torch.log(prob + 1e-5) / math.log(2.0), 0, 50))


            if self.calrealbits and not self.training:
                decodedx, real_bits = getrealbits(z)
                total_bits = real_bits

            return total_bits, prob


        def iclr18_estrate_bits_mv(mv):

            def getrealbits(x):
                cdfs = []
                x = x + self.mxrange
                n,c,h,w = x.shape
                for i in range(-self.mxrange, self.mxrange):
                    cdfs.append(self.bitEstimator_mv(i - 0.5).view(1, c, 1, 1, 1).repeat(1, 1, h, w, 1))
                cdfs = torch.cat(cdfs, 4).cpu().detach()
                byte_stream = torchac.encode_float_cdf(cdfs, x.cpu().detach().to(torch.int16), check_input_bounds=True)

                real_bits = torch.sum(torch.from_numpy(np.array([len(byte_stream) * 8])).float().cuda())

                sym_out = torchac.decode_float_cdf(cdfs, byte_stream)
                return sym_out - self.mxrange, real_bits

            prob = self.bitEstimator_mv(mv + 0.5) - self.bitEstimator_mv(mv - 0.5)
            total_bits = torch.sum(torch.clamp(-1.0 * torch.log(prob + 1e-5) / math.log(2.0), 0, 50))


            if self.calrealbits and not self.training:
                decodedx, real_bits = getrealbits(mv)
                total_bits = real_bits

            return total_bits, prob

        total_bits_feature, _ = feature_probs_based_sigma(compressed_feature_renorm, recon_sigma)
        # entropy_context = entropy_context_from_sigma(compressed_feature_renorm, recon_sigma)
        total_bits_z, _ = iclr18_estrate_bits_z(compressed_z)
        total_bits_mv, _ = iclr18_estrate_bits_mv(quant_mv)

        im_shape = input_image.size()

        bpp_feature = total_bits_feature / (batch_size * im_shape[2] * im_shape[3])
        bpp_z = total_bits_z / (batch_size * im_shape[2] * im_shape[3])
        bpp_mv = total_bits_mv / (batch_size * im_shape[2] * im_shape[3])
        bpp = bpp_feature + bpp_z + bpp_mv

        return clipped_recon_image, mse_loss, warploss, interloss, bpp_feature, bpp_z, bpp_mv, bpp
        
    def round_values(self, v):
        ''' normal solution '''
        return torch.round(v / self.quantization_param) #* self.quantization_param

    def unround_values(self, v):
        ''' normal solution '''
        return v * self.quantization_param

    def get_h264mv(self, frame, refer):
        """
        input: two tensor 1x3xHxW
        output: 2x(H/16)x(W/16) flow-like motion vector
        """
        def create_temp_path():
            path = f"/tmp/yihua_frames-{np.random.randint(0, 1000)}/"
            while os.path.isdir(path):
                path = f"/tmp/yihua_frames-{np.random.randint(0, 1000)}/"
            os.makedirs(path, exist_ok=True)
            return path

        def remove_temp_path(tmp_path):
            os.system("rm -rf {}".format(tmp_path))

        H = frame.shape[2]
        W = frame.shape[3]
        print(H, W)

        frame_pil = to_pil_image(frame[0])
        refer_pil = to_pil_image(refer[0])
        
        # print(frame_pil.shape)
        # to_pil_image(frame_pil)
        # frame_path = create_temp_path()
        frame_path = create_temp_path()
        # frame_path = create_temp_path()
        print(frame_path)
        cdir = frame_path
        frame_pil.save(os.path.join(frame_path, "002.png"))
        refer_pil.save(os.path.join(frame_path, "001.png"))
        # breakpoint()

        print("running cmmaddd")
        subcmd = f"LD_LIBRARY_PATH=/mnt/data/ziyizhang/ffmpeg_new/myffmpeg/lib /mnt/data/ziyizhang/ffmpeg_new/myffmpeg/bin/ffmpeg -y -hide_banner -loglevel error -start_number {1} -i {cdir}/%03d.png -vframes 2 -c:v libx264 -bf 0 -crf 12 -me_method hex -me_range 16 -partitions none {cdir}/mv.mp4"
        subcmd = f"LD_LIBRARY_PATH=/dataheart/autoencoder_dataset/datamirror/autoencoder_dataset/yihua-ae-for-sim/ziyi-tools/myffmpeg/lib /dataheart/autoencoder_dataset/datamirror/autoencoder_dataset/yihua-ae-for-sim/ziyi-tools/myffmpeg/bin/ffmpeg -y -hide_banner -loglevel error -start_number {1} -i {cdir}/%03d.png -vframes 2 -c:v libx264 -bf 0 -crf 12 -me_method hex -me_range 16 -partitions none {cdir}/mv.mp4"
        
        os.system(subcmd)
        cap = VideoCap()
        ret = cap.open(f"{cdir}/mv.mp4")
        ret, frame, motion_vectors, frame_type, timestamp = cap.read()
        ret, frame, motion_vectors, frame_type, timestamp = cap.read()
        remove_temp_path(frame_path)
        # harr = torch.full((H // 16, W // 16), torch.nan)
        # warr = torch.full((H // 16, W // 16), torch.nan)
        harr = torch.full((H // 16, W // 16), 0)
        warr = torch.full((H // 16, W // 16), 0)
        bad = False
        for m in motion_vectors:
        # print("mvrow:", m)
        # delta_x = m[5]-m[3] # x is width, delta = dst - src
        # delta_y = m[6]-m[4] # y is height, delta = dst - src
            delta_x = -m[7] / m[9] # x is width, delta = dst - src
            delta_y = -m[8] / m[9] # y is height, delta = dst - src
            start_x, end_x = m[5]-m[1]//2, m[5]+m[1]//2 # x is width
            start_y, end_y = m[6]-m[2]//2, m[6]+m[2]//2 # y is height
            
            bad = bad or start_x % 16 != 0
            bad = bad or  start_y % 16 != 0
            bad = bad or  end_x % 16 != 0
            bad = bad or  end_y % 16 != 0
            harr[start_y // 16:end_y // 16, start_x // 16:end_x // 16] = -delta_y
            warr[start_y // 16:end_y//16 , start_x//16:end_x//16] = -delta_x
        # assert not harr.isnan().any()
        # assert not warr.isnan().any()
        # print(harr.isnan().any())
        # print(warr.isnan().any())
        # harr = refine_with_left_up(harr)
        # warr = refine_with_left_up(warr)

        # harr = refine_with_left_up(harr)
        # warr = refine_with_left_up(warr)
        # harr = refine_with_left_up(harr)
        # warr = refine_with_left_up(warr)  
        if bad:
            print("badddd mv")
        mv = torch.cat([warr[None,:], harr[None,:]], 0).float()
        return mv.unsqueeze(0).cuda()

# print(os.path.join(frame_path, "002.png"))
# frame_new = Image.open(os.path.join(frame_path, "001.png"))
# refer_new = Image.open(os.path.join(frame_path, "002.png"))
# # frame
# # refer_new
# frame_new


    def encode(self, input_image, refer_frame, return_z = False, mask = None, scale_factor=1):
        """
        Parameters: 
            input_image: image tensor, with shape: (N, C, H, W)
            refer_frame: image tensor, with shape: (N, C, H, W)
        Returns:
            motion_vec: the encoded motion vector (after Quantization)
            residual: the encoded residual  (after Quantization)
        """
        # global SCALE_FACTOR
        scale_factor = self.scale_factor
        # breakpoint()
        # smart = input_image.dtype == torch.float16
        smart = False
        method = 'bicubic'


        # if smart:
        image_scaled = F.interpolate(input_image, scale_factor=scale_factor, mode = method)
        refer_frame_scaled = F.interpolate(refer_frame, scale_factor=scale_factor, mode = method)

        if scale_factor != 1: 
            if self.use_h264mv:
                estmv = self.get_h264mv(image_scaled, refer_frame_scaled)
                # estmv = F.interpolate(estmv, scale_factor=scale_factor, mode = method)
            else:
                image_scaled = nnf.interpolate(input_image, scale_factor=scale_factor, mode = method)
                refer_frame_scaled = nnf.interpolate(refer_frame, scale_factor=scale_factor, mode = method)
                estmv = self.opticFlow(image_scaled, refer_frame_scaled)
        else:
            if self.use_h264mv:
                estmv = self.get_h264mv(input_image, refer_frame)     
            elif smart:
                estmv = self.opticFlow(image_scaled, refer_frame_scaled)
            else:
                estmv = self.opticFlow(input_image, refer_frame)

        mvfeature = self.mvEncoder(estmv, self.mv_scale, self.use_h264mv)
        
        # mvfeature = mvfeature.float()
        quant_mv = torch.round(mvfeature)
        #quant_mv = self.round_values(mvfeature)
        quant_mv_upsample = self.mvDecoder(quant_mv, self.mv_scale, self.use_h264mv)
        #quant_mv_upsample = self.mvDecoder(self.unround_values(quant_mv))

        if self.use_h264mv:
            quant_mv_upsample = torch.repeat_interleave(quant_mv_upsample, 16, dim = 2)
            quant_mv_upsample = torch.repeat_interleave(quant_mv_upsample, 16, dim = 3)
            # breakpoint()
        if scale_factor != 1:

            prediction, warpframe = self.motioncompensation(refer_frame_scaled, quant_mv_upsample)
            prediction = nnf.interpolate(prediction, scale_factor=1/scale_factor, mode = method)
        else:
            if smart:
                quant_mv_upsample = F.interpolate(quant_mv_upsample, scale_factor=2, mode = method)
                quant_mv_upsample *= 2
            prediction, warpframe = self.motioncompensation(refer_frame, quant_mv_upsample)

        input_residual = input_image - prediction

        if mask is not None:
            input_residual = input_residual * mask
            print("Here, mask = ", mask)

        feature = self.resEncoder(input_residual)

        feature_renorm = feature
        #compressed_feature_renorm = torch.round(feature_renorm)
        # feature_renorm = feature_renorm.float()
        compressed_feature_renorm = self.round_values(feature_renorm)
        # breakpoint()
        if not return_z:
            return quant_mv, compressed_feature_renorm
        elif self.use_h264mv:
            mvz = self.mvpriorEncoder(quant_mv)
            z = self.respriorEncoder(compressed_feature_renorm)
            compressed_mvz = torch.round(mvz)
            compressed_z = torch.round(z)
            return quant_mv, compressed_feature_renorm, compressed_z, compressed_mvz
        else:
            z = self.respriorEncoder(compressed_feature_renorm)
            #z = self.respriorEncoder(feature_renorm)
            compressed_z = torch.round(z)
            return quant_mv, compressed_feature_renorm, compressed_z, None

            

    def decode(self, refer_frame, motion_vec, residual, scale_factor=1):
        """
        parameter:
            refer_frame: the reference frame
            motion_vec: the encoded motion vector (after quantization)
            residual: the encoded residual (after quantization)
        returns:
            recon_image: the reconstructed image with shape N, C, H, W
        """

        #scale_factor = 0.5
        # global SCALE_FACTOR
        scale_factor = self.scale_factor
        method = 'bicubic'


        # smart = refer_frame.dtype == torch.float16
        smart = False
        # if smart:
        #     print("ssss")
        #motion_vec = self.unround_values(motion_vec)
        residual = self.unround_values(residual)
    
        quant_mv_upsample = self.mvDecoder(motion_vec, self.mv_scale, self.use_h264mv)
        
        if self.use_h264mv:
            quant_mv_upsample = torch.repeat_interleave(quant_mv_upsample, 16, dim = 2)
            quant_mv_upsample = torch.repeat_interleave(quant_mv_upsample, 16, dim = 3)
            
        if scale_factor != 1:
            refer_frame_scaled = nnf.interpolate(refer_frame, scale_factor=scale_factor, mode = method)
            prediction, warpframe = self.motioncompensation(refer_frame_scaled, quant_mv_upsample)
            prediction = nnf.interpolate(prediction, scale_factor=1/scale_factor, mode = method)
        else:
            if smart:
                quant_mv_upsample = F.interpolate(quant_mv_upsample, scale_factor=2, mode = method)
                quant_mv_upsample *= 2
            prediction, warpframe = self.motioncompensation(refer_frame, quant_mv_upsample)

        recon_residual = self.resDecoder(residual)
        recon_image = prediction + recon_residual

        return recon_image
        
