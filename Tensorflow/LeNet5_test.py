import tensorflow as tf
import numpy as np
import time
from Networks import LeNet5
from Scripts import load_ds
from datetime import datetime
from Scripts import MCsim
from Layers import AConnect
from Layers import ConvAConnect
identifier = [False,True]
Sim_err = [0, 0.3, 0.7, 0.5]
(x_train, y_train), (x_test, y_test) = load_ds.load_ds()
_,_,x_test=LeNet5.LeNet5(x_train,x_test)
x_test = np.float32(x_test)
"""
for i in range(len(identifier)):
    #print(type(x_test))
    isAConnect = identifier[i]
    model,x_train,x_test=LeNet5.LeNet5(x_train,x_test,isAConnect=isAConnect,Wstd=0.5,Bstd=0.5,isBin="no")
    optimizer = tf.keras.optimizers.SGD(learning_rate=0.1,momentum=0.9)
    model.compile(optimizer=optimizer,loss=['sparse_categorical_crossentropy'],metrics=['accuracy'])
    print(model.summary())
    history = model.fit(x_train,y_train,validation_split=0.2,epochs = 20,batch_size=256)
    acc = history.history['accuracy']
    val_acc = history.history['val_accuracy']
    if isAConnect:
        string = './Models/'+'AConnect_LeNet5'+'.h5'
        name = 'AConnect_LeNet5'
        model.save(string,include_optimizer=True)
        np.savetxt('./Models/Training data/'+'AConnect_LeNet5'+'_acc'+'.txt',acc,fmt="%.2f")
        np.savetxt('./Models/Training data/'+'AConnect_LeNet5'+'_val_acc'+'.txt',val_acc,fmt="%.2f")    
        
    else:
        string = './Models/'+'LeNet5'+'.h5'
        name = 'LeNet5'
        model.save(string,include_optimizer=True)
        np.savetxt('./Models/Training data/'+'LeNet5'+'_acc'+'.txt',acc,fmt="%.2f")
        np.savetxt('./Models/Training data/'+'LeNet5'+'_val_acc'+'.txt',val_acc,fmt="%.2f") """     
for k in range(len(identifier)):
    isAConnect = identifier[k]
    if isAConnect:       
        string = './Models/'+'AConnect_LeNet5'+'.h5'
        name = 'AConnect_LeNet5'
        custom_objects = {'ConvAConnect':ConvAConnect.ConvAConnect,'AConnect':AConnect.AConnect}    
    else:      
        string = './Models/'+'LeNet5'+'.h5'
        name = 'LeNet5'
        custom_objects = None

    for j in range(len(Sim_err)):
        Err = Sim_err[j]
        if Err != 0.5:
            force = "yes"
        else:
            force = "no"
        if Err == 0:
            N = 1
        else:
            N = 1000
        now = datetime.now()
        starttime = now.time()
        #####
        print('\n\n*******************************************************************************************\n\n')
        print('TESTING NETWORK: ', name)
        print('With simulation error: ', Err)
        print('\n\n*******************************************************************************************')
        acc_noisy, media = MCsim.MCsim(string,x_test,y_test,N,Err,Err,force,0,name,custom_objects,SRAMsz=[1024,1024],SRAMBsz=[1024])
        #####
        now = datetime.now()
        endtime = now.time()

        print('\n\n*******************************************************************************************')
        print('\n Simulation started at: ',starttime)
        print('Simulation finished at: ', endtime)


