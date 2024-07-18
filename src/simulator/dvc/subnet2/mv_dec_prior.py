#!/Library/Frameworks/Python.framework/Versions/3.5/bin/python3.5  
from .basics import *
# import pickle
# import os
# import codecs
# from .analysis import Analysis_net
# from .analysis_prior import Analysis_prior_net
# from .synthesis import Synthesis_net


class Mv_dec_prior_net(nn.Module):
    '''
    Decode residual prior
    '''
    def __init__(self):
        super(Mv_dec_prior_net, self).__init__()
        self.deconv1 = nn.ConvTranspose2d(out_channel_mv_z, out_channel_mv_z, 5, stride=2, padding=2, output_padding=1)
        torch.nn.init.xavier_normal_(self.deconv1.weight.data, math.sqrt(2 * 1))
        torch.nn.init.constant_(self.deconv1.bias.data, 0.01)
        self.relu1 = nn.ReLU()
        self.deconv2 = nn.ConvTranspose2d(out_channel_mv_z, out_channel_mv_z, 5, stride=2, padding=2, output_padding=1)
        torch.nn.init.xavier_normal_(self.deconv2.weight.data, math.sqrt(2 * 1))
        torch.nn.init.constant_(self.deconv2.bias.data, 0.01)
        self.relu2 = nn.ReLU()
        self.deconv3 = nn.ConvTranspose2d(out_channel_mv_z, out_channel_mv_new, 3, stride=1, padding=1)
        torch.nn.init.xavier_normal_(self.deconv3.weight.data, (math.sqrt(2 * 1 * (out_channel_mv + out_channel_mv_z) / (out_channel_mv_z + out_channel_mv_z))))
        torch.nn.init.constant_(self.deconv3.bias.data, 0.01)


    def forward(self, x):
        x = self.relu1(self.deconv1(x))
        x = self.relu2(self.deconv2(x))
        return torch.exp(self.deconv3(x))
