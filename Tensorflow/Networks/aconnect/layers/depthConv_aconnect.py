import tensorflow as tf
import numpy as np
import math
from .scripts import Merr_distr,mult_custom,Quant_custom

###########################################################################################################3
"""
DepthWise-Convolutional layer with A-Connect
INPUT ARGUMENTS:
-kernel_size: List with the dimension of the filter. e.g. [3,3]. It must be less than the input data size
-Wstd and Bstd: Weights and bias standard deviation for training
-pool: Number of error matrices that you want to use.
-bwErrProp: True or False flag to enable/disable backward propagation of error matrices
-isBin: string yes or no, whenever you want binary weights
-strides: Number of strides (or steps) that the filter moves during the convolution
-padding: "SAME" or "VALID". If you want to keep the same size or reduce it.
-d_type: Type of the parameters that the layers will create. Supports fp16, fp32 and fp64
"""

class DepthWiseConv_AConnect(tf.keras.layers.Layer):
        def __init__(self,
                kernel_size=(3, 3),
                strides=(1, 1),
                padding="VALID",
                data_format='channels_last',
                depth_multiplier=1 , in_channels=None,
                Wstd=0,
                Bstd=0,
                errDistr="normal",
                pool=0,
                isQuant=['no','no'],
                bw=[1,1],
                bwErrProp = True,
                d_type=tf.dtypes.float16,
                use_bias=True,
                kernel_initializer=tf.keras.initializers.GlorotUniform(),
                bias_initializer=tf.keras.initializers.Constant(0.),
                kernel_regularizer=None,
                bias_regularizer=None,
                **kwargs):
                #dilation_rate=(1, 1),

                super(DepthWiseConv_AConnect, self).__init__()
                self.kernel_size = kernel_size
                self.strides = self._strides = strides
                self.padding = padding
                self.data_format=data_format
                #self.dilation_rate=dilation_rate,
                self.depth_multiplier=depth_multiplier
                self.in_channels=in_channels
                self.Wstd = Wstd
                self.Bstd = Bstd
                self.errDistr = errDistr
                self.pool = pool
                self.isQuant = isQuant
                self.bw = bw
                self.bwErrProp = bwErrProp
                self.d_type = d_type
                self.use_bias = use_bias
                self.kernel_initializer = kernel_initializer 
                self.bias_initializer = bias_initializer
                self.kernel_regularizer = kernel_regularizer 
                self.bias_regularizer = bias_regularizer
                self.kwargs = kwargs
                self.validate_init()
        
        def build(self,input_shape):
                if self.data_format == 'channels_last':
                    self.data_format = 'NHWC'
                    if self.in_channels is None:
                        self.in_channels = input_shape[-1]
                    self._strides = [1,self._strides[0],self._strides[1],1]
                    #self._dilation_rate = [1,self._dilation_rate[0],self._dilation_rate[1],1]
                elif self.data_format == 'channels_first':
                    self.data_format = 'NCHW'
                    if self.in_channels is None:
                        self.in_channels = input_shape[1]      
                    self._strides = [1,1,self._strides[0],self._strides[1]]
                    #self._dilation_rate = [1,1,self._dilation_rate[0],self._dilation_rate[1]]
                else:
                    raise Exception("data_format should be either channels_last or channels_first")
                
                ### Compute the shape of the weights. Input shape could be
                ### [H,W,Ch,depth_mult] RGB
                if type(self.kernel_size) is int:
                    kernel_size = self.kernel_size,
                else:
                    kernel_size = self.kernel_size
                kernel_size = list(kernel_size)
                if len(kernel_size) > 1:
                    self.filter_shape = kernel_size + list((self.in_channels,self.depth_multiplier))
                else:
                    self.filter_shape = kernel_size + kernel_size + list((self.in_channels,self.depth_multiplier))
                #self.filter_shape = [self.kernel_size[0],self.kernel_size[1],self.in_channels, self.depth_multiplier]

                self.W = self.add_weight('kernel',
                                          shape = self.filter_shape,
                                          initializer = self.kernel_initializer,
                                          regularizer = self.kernel_regularizer,
                                          dtype=self.d_type,
                                          trainable=True)
                if self.use_bias:
                    self.bias_shape = self.in_channels*self.depth_multiplier
                    self.bias = self.add_weight('bias',
                                                shape=self.bias_shape,
                                                initializer = self.bias_initializer,
                                                regularizer = self.bias_regularizer,
                                                dtype=self.d_type,
                                                trainable=True)
                #If the layer will take into account the standard deviation of the weights or the std of 
                #the bias or both
                if(self.Wstd != 0 or self.Bstd != 0): 
                    if self.use_bias:
                        if(self.Bstd != 0):
                            self.infBerr = Merr_distr([self.bias_shape,],self.Bstd,self.d_type,self.errDistr)
                            #It is necessary to convert the tensor to a numpy array.Tensors are constants 
                            #and cannot be changed. Necessary to change the error matrix/array when 
                            #Monte Carlo is running.
                            self.infBerr = self.infBerr.numpy()  
                        else:
                            self.Berr = tf.constant(1,dtype=self.d_type)
                    if(self.Wstd !=0):
                        self.infWerr = Merr_distr(self.filter_shape,self.Wstd,self.d_type,self.errDistr)
                        self.infWerr = self.infWerr.numpy()
                    else:
                        self.Werr = tf.constant(1,dtype=self.d_type)
                else:
                    self.Werr = tf.constant(1,dtype=self.d_type) #We need to define the number 1 as a float32.
                    if self.use_bias:
                        self.Berr = tf.constant(1,dtype=self.d_type)
                super(DepthWiseConv_AConnect, self).build(input_shape)
        def call(self,X,training):
                self.X = tf.cast(X, dtype=self.d_type)
                self.batch_size = tf.shape(self.X)[0]
                
                #Quantize the weights
                if(self.isQuant[0]=="yes"):
                    weights = self.LQuant(self.W)    
                else:
                    weights = self.W
                #Quantize the biases
                if self.use_bias:
                    if(self.isQuant[1]=="yes"):
                        bias = self.LQuant(self.bias)
                    else:
                        bias = self.bias
                
                if(training):
                    if(self.Wstd != 0 or self.Bstd != 0):
                        if(self.Wstd != 0):
                            werr_shape = [self.pool]+self.filter_shape
                            Werr = Merr_distr(werr_shape,self.Wstd,self.d_type,self.errDistr)
                        else:
                            Werr = self.Werr

                        if self.use_bias:
                            if(self.Bstd != 0):
                                berr_shape = [self.pool,self.bias_shape]
                                Berr = Merr_distr(berr_shape,self.Bstd,self.d_type,self.errDistr)
                            else:
                                Berr = self.Berr

                        newBatch = tf.cast(tf.floor(tf.cast(self.batch_size/self.pool,dtype=tf.float16)),dtype=tf.int32)
                        for i in range(self.pool):
                            werr_aux = self.custom_mult(weights,Werr[i])
                            Z1 = tf.nn.depthwise_conv2d(input=self.X[(i)*newBatch:(i+1)*newBatch],
                                                        filter=werr_aux,
                                                        strides=self._strides,
                                                        padding=self.padding,
                                                        data_format=self.data_format)
                            if self.use_bias:
                                berr_aux = self.custom_mult(bias,Berr[i])
                                Z1 = tf.add(Z1,berr_aux)
                            if i==0:
                                Z = Z1
                            else: 
                                Z = tf.concat([Z,Z1],axis=0)
                    else:
                        #Custom Conv layer operation
                        w = weights*self.Werr
                        Z = tf.nn.depthwise_conv2d(input=self.X,
                                                    filter=w,
                                                    strides=self._strides,
                                                    padding=self.padding,
                                                    data_format=self.data_format)
                        if self.use_bias:
                            b = bias*self.Berr
                            Z=Z+b
                else:
                    if(self.Wstd != 0 or self.Bstd !=0):
                        if(self.Wstd !=0):
                                Werr = self.infWerr
                        else:
                                Werr = self.Werr
                        if self.use_bias:
                            if(self.Bstd != 0):
                                    Berr = self.infBerr
                            else:
                                    Berr = self.Berr
                    else:
                        Werr = self.Werr
                        if self.use_bias:
                            Berr = self.Berr
                    
                    #Custom Conv layer operation
                    w = weights*Werr
                    Z = tf.nn.depthwise_conv2d(input=self.X,
                                                filter=w,
                                                strides=self._strides,
                                                padding=self.padding,
                                                data_format=self.data_format)
                    if self.use_bias:
                        b = bias*Berr
                        Z=Z+b
                
                Z = self.LQuant(Z)
                return Z
        
        def validate_init(self):
                if self.Wstd > 1 or self.Wstd < 0:
                    raise ValueError('Wstd must be a number between 0 and 1. \n' 'Found %d' %(self.Wstd,))
                if self.Bstd > 1 or self.Bstd < 0:
                    raise ValueError('Bstd must be a number between 0 and 1. \n' 'Found %d' %(self.Bstd,))
                if not isinstance(self.errDistr, str):
                    raise TypeError('errDistr must be a string. Only two distributions supported: "normal", "lognormal"'
                            'Found %s' %(type(self.errDistr),))
                if not isinstance(self.isQuant, list):
                    raise TypeError('isQuant must be a list, ["yes","yes"] , ["yes","no"], ["no","yes"] or ["no","no"]. ' 'Found %s' %(type(self.isQuant),))
                if self.pool is not None and not isinstance(self.pool, int):
                    raise TypeError('pool must be a integer. ' 'Found %s' %(type(self.pool),))
        def get_config(self):
                config = super(DepthWiseConv_AConnect, self).get_config()
                config.update({
                        'kernel_size': self.kernel_size,
                        'strides': self.strides,
                        'padding': self.padding,
                        'data_format': self.data_format,
                        'use_bias': self.use_bias,
                        'Wstd': self.Wstd,
                        'Bstd': self.Bstd,
                        'errDistr': self.errDistr,
                        'pool': self.pool,
                        'isQuant': self.isQuant,
                        'bw': self.bw,
                        'd_type': self.d_type,
                        'depth_multiplier': self.data_multiplier})
                return config
        
        @tf.custom_gradient
        def LQuant(self,x):      # Gradient function for weights quantization
            y, grad = Quant_custom(x,self)
            return y,grad
        
        @tf.custom_gradient
        def custom_mult(self,x,xerr):      # Gradient function for weights quantization
            y,grad = mult_custom(x,xerr,self.bwErrProp)
            return y,grad

###########################################################################################################3

