import tensorflow as tf
from tensorflow.keras.layers import Dense, Conv2D, BatchNormalization, Activation,RandomTranslation,ZeroPadding2D,RandomCrop
from tensorflow.keras.layers import AveragePooling2D, Input, Flatten, RandomFlip, RandomZoom, Softmax
from tensorflow.keras.regularizers import l2
from tensorflow.keras.models import Model
from aconnect.layers import Conv_AConnect, FC_AConnect

def resnet_layer(inputs,num_filters=16,kernel_size=(3,3),
                strides=1,activation='relu',batch_normalization=True,
                conv_first=True,isAConnect=True,
                **AConnect_args):
    
    
    """2D Convolution-Batch Normalization-Activation stack builder

    # Arguments
        inputs (tensor): input tensor from input image or previous layer
        num_filters (int): Conv2D number of filters
        kernel_size (int): Conv2D square kernel dimensions
        strides (int): Conv2D square stride dimensions
        activation (string): activation name
        batch_normalization (bool): whether to include batch normalization
        conv_first (bool): conv-bn-activation (True) or
            bn-activation-conv (False)

    # Returns
        x (tensor): tensor as input to the next layer
    """
    if isAConnect:
        conv = Conv_AConnect(num_filters,kernel_size,
                            strides=strides,padding="SAME",
                            kernel_regularizer=l2(1e-4),
                            **AConnect_args)
    else:
        conv = Conv2D(num_filters,
                      kernel_size=kernel_size,
                      strides=strides,
                      padding='same',
                      kernel_initializer='glorot_uniform',
                      kernel_regularizer=l2(1e-4))

    x = inputs
    if conv_first:
        x = conv(x)
        if batch_normalization:
            x = BatchNormalization()(x)
        if activation is not None:
            x = Activation(activation)(x)
    else:
        if batch_normalization:
            x = BatchNormalization()(x)
        if activation is not None:
            x = Activation(activation)(x)
        x = conv(x)
    return x


def resnet_v1(input_shape, depth, num_classes=10, 
                isAConnect=True,Wstd=0,Bstd=0,
                Conv_pool=2,FC_pool=2,errDistr="normal",
                isQuant=['no','no'],bw=[8,8],
                bwErrProp=True,**kwargs):
    
    AConnect_args = {"isAConnect": isAConnect,
                "Wstd": Wstd,
                "Bstd": Bstd,
                "isQuant": isQuant,
                "bw": bw,
                "errDistr": errDistr,
                "bwErrProp": bwErrProp,
                "d_type": tf.dtypes.float16}
    """ResNet Version 1 Model builder [a]

    Stacks of 2 x (3 x 3) Conv2D-BN-ReLU
    Last ReLU is after the shortcut connection.
    At the beginning of each stage, the feature map size is halved (downsampled)
    by a convolutional layer with strides=2, while the number of filters is
    doubled. Within each stage, the layers have the same number filters and the
    same number of filters.
    Features maps sizes:
    stage 0: 32x32, 16
    stage 1: 16x16, 32
    stage 2:  8x8,  64
    The Number of parameters is approx the same as Table 6 of [a]:
    ResNet20 0.27M
    ResNet32 0.46M
    ResNet44 0.66M
    ResNet56 0.85M
    ResNet110 1.7M

    # Arguments
        input_shape (tensor): shape of input image tensor
        depth (int): number of core convolutional layers
        num_classes (int): number of classes (CIFAR10 has 10)

    # Returns
        model (Model): Keras model instance
    """
    if (depth - 2) % 6 != 0:
        raise ValueError('depth should be 6n+2 (eg 20, 32, 44 in [a])')
    # Start model definition.
    num_filters = 16
    num_res_blocks = int((depth - 2) / 6)

    inputs = Input(shape=input_shape)
    if isAConnect and Wstd!=0:
        x = RandomZoom(0.0)(inputs)
        x = RandomTranslation(0.0,0.0)(x)
        x = RandomZoom(0.0)(x)
    elif isAConnect and Wstd==0:
        Flip = RandomFlip("horizontal")
        x = Flip(inputs)
        x = RandomTranslation(0.1,0.1)(x)
        x = RandomZoom(0.2)(x)
    else:
        Flip = RandomFlip("horizontal")
        x = Flip(inputs)
        x = RandomTranslation(0.1,0.1)(x)
        x = RandomZoom(0.2)(x)
    x = resnet_layer(inputs=x,
                    pool=Conv_pool,
                    **AConnect_args)

    # Instantiate the stack of residual units
    for stack in range(3):
        for res_block in range(num_res_blocks):
            strides = 1
            if stack > 0 and res_block == 0:  # first layer but not first stack
                strides = 2  # downsample
            y = resnet_layer(inputs=x,
                            num_filters=num_filters,
                            strides=strides,
                            pool=Conv_pool,
                            **AConnect_args)
            y = resnet_layer(inputs=y,
                            num_filters=num_filters,
                            activation=None,
                            batch_normalization=False, # Added by Luis E. Rueda G. (testing)
                            pool=Conv_pool,
                            **AConnect_args)
            if stack > 0 and res_block == 0:  # first layer but not first stack
                # linear projection residual shortcut connection to match
                # changed dims
                x = resnet_layer(inputs=x,
                                num_filters=num_filters,
                                kernel_size=(1,1),
                                strides=strides,
                                activation=None,
                                batch_normalization=False,
                                pool=Conv_pool,
                                **AConnect_args)
            x = tf.keras.layers.add([x, y])
            x = BatchNormalization()(x) # Added by Luis E. Rueda G. (testing)
            x = Activation('relu')(x)
        num_filters *= 2

    # Add classifier on top.
    # v1 does not use BN after last shortcut connection-ReLU
    x = AveragePooling2D(pool_size=8)(x)
    y = Flatten()(x)
    
    if isAConnect:
        y = FC_AConnect(num_classes,pool=FC_pool,**AConnect_args)(y)
        outputs = Softmax()(y)
    else:
        outputs = Dense(num_classes,
                        activation='softmax',
                        kernel_initializer='glorot_uniform')(y)

    # Instantiate model.
    model = Model(inputs=inputs, outputs=outputs)
    return model


def resnet_v2(input_shape, depth, num_classes=10,
                isAConnect=False,Wstd=0,Bstd=0,
                Conv_pool=2,FC_pool=2,errDistr="normal",
                isQuant=['no','no'],bw=[8,8],bwErrProp=True,**kwargs):
    
    AConnect_args = {"isAConnect": isAConnect,
                "Wstd": Wstd,
                "Bstd": Bstd,
                "isQuant": isQuant,
                "bw": bw,
                "errDistr": errDistr,
                "bwErrProp": bwErrProp,
                "d_type": tf.dtypes.float16}
    """ResNet Version 2 Model builder [b]

    Stacks of (1 x 1)-(3 x 3)-(1 x 1) BN-ReLU-Conv2D or also known as
    bottleneck layer
    First shortcut connection per layer is 1 x 1 Conv2D.
    Second and onwards shortcut connection is identity.
    At the beginning of each stage, the feature map size is halved (downsampled)
    by a convolutional layer with strides=2, while the number of filter maps is
    doubled. Within each stage, the layers have the same number filters and the
    same filter map sizes.
    Features maps sizes:
    conv1  : 32x32,  16
    stage 0: 32x32,  64
    stage 1: 16x16, 128
    stage 2:  8x8,  256

    # Arguments
        input_shape (tensor): shape of input image tensor
        depth (int): number of core convolutional layers
        num_classes (int): number of classes (CIFAR10 has 10)

    # Returns
        model (Model): Keras model instance
    """
    if (depth - 2) % 9 != 0:
        raise ValueError('depth should be 9n+2 (eg 56 or 110 in [b])')
    # Start model definition.
    num_filters_in = 16
    num_res_blocks = int((depth - 2) / 9)

    inputs = Input(shape=input_shape)
    if isAConnect and Wstd!=0:
        x = RandomZoom(0.0)(inputs)
        x = RandomTranslation(0.0,0.0)(x)
        x = RandomZoom(0.0)(x)
    else:
        Flip = RandomFlip("horizontal")
        x = Flip(inputs)
        x = RandomTranslation(0.1,0.1)(x)
        x = RandomZoom(0.2)(x)
    # v2 performs Conv2D with BN-ReLU on input before splitting into 2 paths
    x = resnet_layer(inputs=x,
                    num_filters=num_filters_in,
                    #conv_first=True,
                    pool=Conv_pool,
                    **AConnect_args)

    # Instantiate the stack of residual units
    for stage in range(3):
        for res_block in range(num_res_blocks):
            activation = 'relu'
            batch_normalization = True
            strides = 1
            if stage == 0:
                num_filters_out = num_filters_in * 4
                if res_block == 0:  # first layer and first stage
                    activation = None
                    batch_normalization = False
            else:
                num_filters_out = num_filters_in * 2
                if res_block == 0:  # first layer but not first stage
                    strides = 2    # downsample

            # bottleneck residual unit
            y = resnet_layer(inputs=x,
                            num_filters=num_filters_in,
                            kernel_size=(1,1),
                            strides=strides,
                            activation=activation,
                            batch_normalization=batch_normalization,
                            #conv_first=False,           # Removed by Luis Rueda
                            pool=Conv_pool,
                            **AConnect_args)
            y = resnet_layer(inputs=y,
                            num_filters=num_filters_in,
                            #conv_first=False,           # Removed by Luis Rueda
                            pool=Conv_pool,
                            **AConnect_args)
            y = resnet_layer(inputs=y,
                            num_filters=num_filters_out,
                            kernel_size=(1,1),
                            #conv_first=False,           # Removed by Luis Rueda
                            activation=None,            # Added by Luis Rueda
                            batch_normalization=False,  # Added by Luis Rueda
                            pool=Conv_pool,
                            **AConnect_args)
            if res_block == 0:
                # linear projection residual shortcut connection to match
                # changed dims
                x = resnet_layer(inputs=x,
                                num_filters=num_filters_out,
                                kernel_size=(1,1),
                                strides=strides,
                                activation=None,
                                batch_normalization=False,
                                pool=Conv_pool,
                                **AConnect_args)
            x = tf.keras.layers.add([x, y])
            x = BatchNormalization()(x) # Added by Luis Rueda
            x = Activation('relu')(x)   # Added by Luis Rueda

        num_filters_in = num_filters_out

    # Add classifier on top.
    # v2 has BN-ReLU before Pooling (removed by Luis Rueda since it was added
    # in the previous blocks)
    #x = BatchNormalization()(x)
    #x = Activation('relu')(x)
    x = AveragePooling2D(pool_size=8)(x)
    y = Flatten()(x)
    
    if isAConnect:
        y = FC_AConnect(num_classes,pool=FC_pool,**AConnect_args)(y)
        outputs = Softmax()(y)
    else:
        outputs = Dense(num_classes,
                        activation='softmax',
                        kernel_initializer='he_normal')(y)

    # Instantiate model.
    model = Model(inputs=inputs, outputs=outputs)
    return model


