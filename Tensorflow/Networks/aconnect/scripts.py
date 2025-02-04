import numpy as np
import tensorflow as tf
import os
import gc
from memory_profiler import profile
#Function to make the monte carlo simulation. To see more please go to the original file in Scripts
def MonteCarlo(net=None,Xtest=None,Ytest=None,M=100,Wstd=0,Bstd=0,errDistr="normal",
        force="no",Derr=0,net_name="Network",custom_objects=None,dtype='float32',
        optimizer=tf.keras.optimizers.SGD(learning_rate=0.1,momentum=0.9),
        loss=['sparse_categorical_crossentropy'],
        metrics=['accuracy'],top5=False,run_model_eagerly=False,evaluate_batch_size=None):
        """
        Input Parameters:
        net: Name of the network model you want to test (it must be saved in the folder Models)
        Xtest and Ytest: Validation/Testing dataset
        M: Number of samples for the Monte Carlo
        Wstd and Bstd: Weights and Bias error for the simulation. It must be a float between 0-1
        force: String, should be "yes" or "no" when you want to use a Wstd or Bstd different from the used during training i.e.
                If you trained A-Connect with 50% and you want to test it with an error of 70% you must define force="yes"
        errDistr: String. Options: "normal" or "lognormal". States the distribution applied over the error matrices (noise)
        Derr: If you want to introduce a deterministic error when you are using BW in the network. Float between 0-1
        net_name = String with the name you want to use to save the simulation results
        custom_objects: Python dictionary with the name of all the custom elements that you used in your model i.e. If you use an A-Connect model with Conv and FC A-Connect custom_objects should be
        custom_objects= {'ConvAConnect':ConvAConnect.ConvAConnect,'AConnect':AConnect.AConnect}
        SRAMsz: Matrix dimension for the static error matrix that you want to generate. It is depend on the dimension of the layer weights
        SRAMBsz: Vector dimension for the static error vector that you want to generate. It is depend on the dimension of the layer weights
        optimizer,loss,metrics: The values that you used during the training
        run_model_eagerly: Set to True to run the noisy model eagerly, can help to increase the performance in certain cases
        evaluate_batch_size: Batch size used when evaluating the model, higher values increase performance at the expense of a higher memory usage
        This function returns the noisy accuracy values and the mean of this values
        """

        ### Script to change the error matrix during inference or introduce the error to the layer weights
        ### HOw to
        """
        Input Parameters
        net: Loaded model
        Wstd: Weights standard deviation for simulation
        Bstd: Bias standard deviation for simulation
        force: When you want to use the training deviation or the simulation deviation
        Derr: Deterministic error
        SRAMsz: ERror matrix size
        SRAMBsz: Error vector size
        This function returns a NoisyNet and the values of Wstd and Bstd used
        """
        def add_Wnoise(net,Wstd,Bstd,errDistr,force,Derr,dtype='float32'):
                layers = net.layers #Get the list of layers used in the model
                Nlayers = np.size(layers) #Get the number of layers

                #Merr_aux0 = np.random.randn(100000).astype(dtype)
                #Iterate over the number of layers
                for i in range(Nlayers): 
                        #If the layer does not have training parameters it is omitted
                        if layers[i].count_params() != 0: 
                                #Does the layer have weights or kernel?
                                if hasattr(layers[i],'kernel') or hasattr(layers[i],'W'):  
                                        Wsz = np.shape(layers[i].weights[0]) #Takes the weights/kernel size
                                        Wsize = np.prod(Wsz)
                                        Bsz = np.shape(layers[i].weights[1]) #Takes the bias size
                                        MBerr_aux = np.random.randn(Bsz[0])

                                        #If the layer have the attribute strides means that it is a convolutional layer
                                        if hasattr(layers[i],'strides'): 
                                                Merr_aux = np.random.randn(Wsz[0],Wsz[1],Wsz[2],Wsz[3]).astype(dtype)
                                                #Merr_aux = np.reshape(Merr_aux0[:Wsize],(Wsz[0],Wsz[1],Wsz[2],Wsz[3]))
                                        else:
                                                Merr_aux = np.random.randn(Wsz[0], Wsz[1]).astype(dtype) 
                                                #Merr_aux  = np.reshape(Merr_aux0[:Wsize],(Wsz[0],Wsz[1]))
                                        
                                        #Does the layer have Wstd? if it is true is an A-Connect or DropConnect network
                                        if hasattr(layers[i], 'Wstd'):
                                                #IF the value it is different from zero, the layer is working with the algorithm
                                                if(layers[i].Wstd != 0 and layers[i].errDistr=="lognormal"): 
                                                        Wstd_layer = layers[i].Wstd
                                                        if force == "no": #Do you want to take the training or simulation Wstd value?
                                                                Wstd = Wstd_layer
                                                        else:
                                                                Wstd = Wstd
                                                else: #If it is false, it means that is working as a normal FC layer
                                                        Wstd_layer = 0
                                                        Wstd = Wstd
                                        else:
                                                Wstd = Wstd #If it is false, is a FC layers
                                                Wstd_layer = 0
                                        if hasattr(layers[i], 'Bstd'): #The same logic is applied for Bstd
                                                if(layers[i].Bstd != 0 and layers[i].errDistr=="lognormal"):
                                                        Bstd_layer = layers[i].Bstd
                                                        if force == "no":
                                                                Bstd = Bstd_layer
                                                        else:
                                                                Bstd = Bstd
                                                else:
                                                        Bstd = Bstd
                                                        Bstd_layer = 0
                                        else:
                                                Bstd = Bstd
                                                Bstd_layer = 0

                                        #Create the error matrix taking into account the Wstd and Bstd
                                        Werr = Merr_distr(Merr_aux,Wstd,Wstd_layer,errDistr)
                                        Berr = Merr_distr(MBerr_aux,Bstd,Bstd_layer,errDistr)
                                        #Now if the layer have Werr or Berr is an A-Conenct or DropConnect layer
                                        if hasattr(layers[i],'Werr') or hasattr(layers[i],'Berr') or hasattr(layers[i],'infWerr') or hasattr(layers[i],'infBerr'):
                                                #print(i)#

                                                if(layers[i].isQuant[0] == 'yes'): 
                                                        if(Derr != 0): #Introduce the deterministic error when BW are used
                                                                weights = layers[i].weights[0]
                                                                wp = weights > 0
                                                                wn = weights <= 0
                                                                wn = wn.numpy()
                                                                wp = wp.numpy()
                                                                Werr = Derr*wn*Werr + Werr*wp
                                                if hasattr(layers[i], 'Wstd'):
                                                        if(layers[i].Wstd != 0):
                                                                layers[i].infWerr = Werr #Change the inference error matrix
                                                        else:
                                                                #print(layers[i].Werr)
                                                                layers[i].Werr = Werr
                                                else:
                                                                layers[i].Werr = Werr
                                                if hasattr(layers[i], 'Bstd'):
                                                        if(layers[i].Bstd != 0):
                                                                layers[i].infBerr = Berr #Change the inference error matrix
                                                        else:
                                                                layers[i].Berr = Berr
                                                else:
                                                        layers[i].Berr = Berr
                                        #if the layer is not A-Conenct or DropCOnnect the error must be introduced to the weights because it is a normal FC or normal Conv layer
                                        else:
                                                weights = layers[i].weights[0]*Werr #Introduce the mismatch to the weights
                                                bias = layers[i].weights[1]*Berr #Introduce the mismatch to the bias
                                                local_weights = [weights,bias] #Create the tuple of modified values
                                                layers[i].set_weights(local_weights) #Update the values of the weights

                if net.name=='sequential':
                    NoisyNet = tf.keras.Sequential(layers)
                else:
                    NoisyNet = tf.keras.Model(layers[0].input,layers[-1].output)
                del layers,Werr,Berr

                return NoisyNet,Wstd,Bstd

        def get_top_n_score(target, prediction, n):
            #ordeno los indices de menor a mayor probabilidad
            pre_sort_index = np.argsort(prediction)
            #ordeno de mayor probabilidad a menor
            pre_sort_index = pre_sort_index[:,::-1]
            #cojo las n-top predicciones
            pre_top_n = pre_sort_index[:,:n]
            #obtengo el conteo de acierto
            precision = [1 if target[i] in pre_top_n[i] else 0 for i in range(target.shape[0])]
            #se retorna la precision
            return np.mean(precision)
        
        def classify(net,Xtest,Ytest,top5):#,ev_batch_size=None):
                #_, accuracy, top5acc = net.evaluate(Xtest,Ytest,verbose=0,batch_size=ev_batch_size)
                #XtestIn = tf.convert_to_tensor(Xtest) 
                #y_predict = net(XtestIn,training=False)
                #y_predict = net(Xtest,training=False)
                y_predict = net.predict(Xtest,verbose=0)#,batch_size=ev_batch_size)
                accuracy = get_top_n_score(Ytest, y_predict, 1)
                if top5:
                    acc_top5 = get_top_n_score(Ytest, y_predict, 5)
                    return accuracy, acc_top5
                else:
                    return accuracy
        
        #@profile
        def MCsim(net=net,Xtest=Xtest,Ytest=Ytest,M=M,Wstd=Wstd,Bstd=Bstd,errDistr=errDistr,
                force=force,Derr=Derr,net_name=net_name,custom_objects=custom_objects,dtype=dtype,
                optimizer=optimizer,loss=loss,metrics=metrics,top5=top5):

                #Initilize the variable where im going to save the noisy accuracy
                acc_noisy = np.zeros((M,1)) 
                acc_noisy_top5 = np.zeros((M,1))

                #Load the trained model
                local_net = tf.keras.models.load_model(net,custom_objects = custom_objects) 
                #Save the weights. It is used to optimize the script RAM consumption
                #local_net.save_weights(filepath=(net_name+'_weights.h5')) 
                #print(local_net.summary()) #Print the network summary
                if top5:
                    print('Simulation Nr.\t | \tWstd\t | \tBstd\t | \tAccuracy | \tTop-5 Accuracy\n')
                    print('------------------------------------------------------------------------------------')
                else:
                    print('Simulation Nr.\t | \tWstd\t | \tBstd\t | \tAccuracy\n')
                    print('------------------------------------------------------------------------------------')

                for i in range(M): #Iterate over M samples
                    #Function that adds the new noisy matrices to the layers
                    [NetNoisy,Wstdn,Bstdn] = add_Wnoise(local_net,Wstd,Bstd,errDistr,force,Derr,dtype=dtype) 
                    #Compile the model. It is necessary to use the model.evaluate
                    #NetNoisy.compile(optimizer,loss,metrics,run_eagerly=run_model_eagerly) 
                    
                    if top5:
                        #Get the accuracy of the network    
                        acc_noisy[i],acc_noisy_top5[i] = classify(NetNoisy,Xtest,Ytest,top5)
                        acc_noisy_top5[i] = 100*acc_noisy_top5[i]
                        acc_noisy[i] = 100*acc_noisy[i]
                        print('\t%i\t | \t%.1f\t | \t%.1f\t | \t%.2f | \t%.2f\n' %(i,Wstd*100,Bstd*100,acc_noisy[i],acc_noisy_top5[i]))
                    else:
                        #Get the accuracy of the network
                        acc_noisy[i] = classify(NetNoisy,Xtest,Ytest,top5)
                        acc_noisy[i] = 100*acc_noisy[i]
                        print('\t%i\t | \t%.1f\t | \t%.1f\t | \t%.2f\n' %(i,Wstd*100,Bstd*100,acc_noisy[i]))
                    del NetNoisy
                    gc.collect()
                    tf.keras.backend.clear_session()
                    tf.compat.v1.reset_default_graph()
                    #Takes the original weights value.
                    #local_net.load_weights(filepath=(net_name+'_weights.h5')) 

                media = np.median(acc_noisy)
                Xmin = np.amin(acc_noisy)
                Xmax = np.amax(acc_noisy)
                IQR = np.percentile(acc_noisy,75) - np.percentile(acc_noisy,25)
                stats = [media,IQR,Xmax,Xmin]
                print('---------------------------------------------------------------------------------------')
                print('Median: %.2f%%\n' % media)
                print('IQR Accuracy: %.2f%%\n' % IQR)
                print('Min. Accuracy: %.2f%%\n' % Xmin)
                print('Max. Accuracy: %.2f%%\n'% Xmax)
                if top5:
                    media_top5 = np.median(acc_noisy_top5)
                    Xmin_top5 = np.amin(acc_noisy_top5)
                    Xmax_top5 = np.amax(acc_noisy_top5)
                    IQR_top5 = np.percentile(acc_noisy_top5,75) - np.percentile(acc_noisy_top5,25)
                    stats_top5 = [media_top5,IQR_top5,Xmax_top5,Xmin_top5]
                    print('---------------------------------------------------------------------------------------')
                    print('Median (Top-5): %.2f%%\n' % media_top5)
                    print('IQR Accuracy (Top-5): %.2f%%\n' % IQR_top5)
                    print('Min. Accuracy (Top-5): %.2f%%\n' % Xmin_top5)
                    print('Max. Accuracy (Top-5): %.2f%%\n'% Xmax_top5)

                del local_net
                if top5:
                    return acc_noisy,acc_noisy_top5,stats,stats_top5
                else:
                    return acc_noisy,stats

        return  MCsim(net=net,Xtest=Xtest,Ytest=Ytest,M=M,Wstd=Wstd,Bstd=Bstd,errDistr=errDistr,
                force=force,Derr=Derr,net_name=net_name,custom_objects=custom_objects,dtype=dtype,
                optimizer=optimizer,loss=loss,metrics=metrics,top5=top5)

#Function to load the MNIST dataset. THis function could load the standard 28x28 8 or 4 bits dataset, or 11x11 8 or 4 bits dataset.
def load_ds(imgSize=[28,28], Quant=8):
        (x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()
        if (imgSize != [28,28]):
                x_train, x_test = np.expand_dims(x_train,-1),np.expand_dims(x_test,-1) #Need an extra dimension to apply tf.image.resize
                x_train = tf.image.resize(x_train,[imgSize[0],imgSize[1]],method=tf.image.ResizeMethod.BILINEAR,antialias=True) #This function applies a resize similar to imresize in matlab
                x_test = tf.image.resize(x_test,[imgSize[0],imgSize[1]],method=tf.image.ResizeMethod.BILINEAR,antialias=True)
                x_train, x_test = np.squeeze(x_train,-1),np.squeeze(x_test,-1) #Remove the extra dimension
        x_train = tf.cast(x_train,tf.uint8)
        x_test = tf.cast(x_test,tf.uint8)
        if(Quant !=8):
                xlsb = 256/2**Quant
                x_train = np.floor(np.divide(x_train,xlsb))
                x_test = np.floor(np.divide(x_test,xlsb))
                x_train = tf.cast(x_train,tf.uint8)
                x_test = tf.cast(x_test,tf.uint8)
        return (x_train,y_train),(x_test,y_test)

#Function to plot the box chart
def plotBox(data,labels,legends,color,color_fill,path):
        import matplotlib.pyplot as plt
        """
        Script to plot and save a box chart with custom style.
        """

        def plotChart(ax,x,color=color,color_fill=color_fill,labels=labels): #Script that plots the box, needed in the script below
                boxprops = dict(linestyle='-', linewidth=3,facecolor=color_fill,color=color)
                whiskerprops = dict(color=color, linewidth=3)
                flierprops = dict(marker='.', markerfacecolor=color, markersize=6,
                              markeredgecolor=color)
                capprops = dict(color=color)
                medianprops = dict(color=color)
                b = ax.boxplot(x,notch=False,widths=0.2,labels=labels,patch_artist=True,
                            boxprops=boxprops,whiskerprops=whiskerprops,flierprops=flierprops,
                            capprops=capprops,medianprops=medianprops
                            )
                return b

        def plotBox(data,labels,legends,color,color_fill,path,figsize=(3,5)): #Top script  to plot the box with custom style
                """
                HOW TO:
                data: Data that you want to plot, should be a list or a list of list (maximum 3 list) i.e. data= [data1,data2,data3] where data1 = [x1,x2,...],
                data2=[y1,y2,...], data3=[z1,z2,...]
                labels: Labels for the x-axis. Must have the same dimension as the data that you are going to plot.
                legends: String. Legends for the plot. Must have the same dimension as the data parameter e.g. data = [data1,data2], legends=[legend1,legend2]
                color: Color for the lines. Should be a list of size 3 with RGB Color.
                color_fill: Color for filling the boxes. Should be a list of size 3 with RGB Color.
                path: String. Where you want to save the image and the name of the archive. By default you do not need to indicate a saving format. By default all
                the images are saved in png format."""
                font = {'family':'Arial','style':'normal','weight' : 'semibold',
                    'size'   : 14}
                plt.rc('font',**font)
                fig = plt.figure(figsize=figsize)
                ax = fig.add_axes([0.1,0.1,0.8,0.8])
                ax.set_xlabel("Simulation Error (%)",fontdict={'family':'Arial','style':'normal','weight' : 'semibold',
                    'size'   : 15})
                ax.set_ylabel("Validation Accuracy (%)",fontdict={'family':'Arial','style':'normal','weight' : 'semibold',
                    'size'   : 16})
                d_size = len(data)
                if d_size == 4:
                    b1 = plotChart(ax,data,color=color,color_fill=color_fill,labels=labels)
                    ax.legend([b1["boxes"][0]],legends, loc='lower left',prop={'family':'Arial','style':'normal','weight' : 'semibold',
                    'size'   : 12})
                elif d_size == 2:
                    b1 = plotChart(ax,data[0],color=color[0],color_fill=color_fill[0],labels=labels)
                    b2 = plotChart(ax,data[1],color=color[1],color_fill=color_fill[1],labels=labels)
                    ax.legend([b1["boxes"][0], b2["boxes"][0]],[legends[0], legends[1]], loc='lower left',prop={'family':'Arial','style':'normal','weight' : 'semibold',
                    'size'   : 12})
                elif d_size == 3:
                    b1 = plotChart(ax,data[0],color=color[0],color_fill=color_fill[0],labels=labels)
                    b2 = plotChart(ax,data[1],color=color[1],color_fill=color_fill[1],labels=labels)
                    b3 = plotChart(ax,data[2],color=color[2],color_fill=color_fill[2],labels=labels)
                    ax.legend([b1["boxes"][0], b2["boxes"][0],b3["boxes"][0]],[legends[0], legends[1], legends[2]], loc='lower left',prop={'family':'Arial','style':'normal','weight' : 'semibold',
                    'size'   : 12})
                else:
                    print("Not supported size")

                ax.spines['top'].set_linewidth(1.4)
                ax.spines['right'].set_linewidth(1.4)
                ax.spines['bottom'].set_linewidth(1.4)
                ax.spines['left'].set_linewidth(1.4)
                plt.savefig(path, bbox_inches='tight')
        return plotBox(data,labels,legends,color,color_fill,path)

def Merr_distr(Merr,stddev,stddev_layer,errDistr): #Used to reshape the output of the layer

    N = stddev*Merr

    if errDistr == "normal":
      Merr = np.abs(1+N)
      #Merr = 1+N
    elif errDistr == "lognormal":
        #stddev_layer1 = 0
        stddev_layer1 = stddev_layer
        Merr = np.exp(-N)*np.exp(0.5*(np.power(stddev_layer1,2)-np.power(stddev,2)))
        #Merr = np.exp(N)
    return Merr
