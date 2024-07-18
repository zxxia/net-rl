from .basics import *
# import pickle
# import os
# import codecs

class Bitparm(nn.Module):
    '''
    save params
    '''
    def __init__(self, channel, final=False):
        super(Bitparm, self).__init__()
        self.final = final
        self.h = nn.Parameter(torch.nn.init.normal_(torch.empty(channel).view(1, -1, 1, 1), 0, 0.01))
        self.b = nn.Parameter(torch.nn.init.normal_(torch.empty(channel).view(1, -1, 1, 1), 0, 0.01))
        if not final:
            self.a = nn.Parameter(torch.nn.init.normal_(torch.empty(channel).view(1, -1, 1, 1), 0, 0.01))
        else:
            self.a = None

    def forward(self, x):
        if self.final:
            return F.sigmoid(x * F.softplus(self.h) + self.b)
        else:
            x = x * F.softplus(self.h) + self.b
            return x + F.tanh(x) * F.tanh(self.a)

class BitEstimator(nn.Module):
    '''
    Estimate bit
    '''
    def __init__(self, channel, channel_new):
        super(BitEstimator, self).__init__()
        self.f1 = Bitparm(channel)
        self.f2 = Bitparm(channel)
        self.f3 = Bitparm(channel)
        self.f4 = Bitparm(channel, True)
        self.e1 = Bitparm(channel_new)
        self.e2 = Bitparm(channel_new)
        self.e3 = Bitparm(channel_new)
        self.e4 = Bitparm(channel_new, True)
        
    def forward(self, x, use_new = False):
        # if not use_new:
        x = self.f1(x)
        x = self.f2(x)
        x = self.f3(x)
        return self.f4(x)
        # else:
        #     x = self.e1(x)
        #     x = self.e2(x)
        #     x = self.e3(x)
        #     return self.e4(x)