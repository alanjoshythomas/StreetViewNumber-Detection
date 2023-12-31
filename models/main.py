import cv2
import numpy as np
import keras
from keras.models import load_model
import os
import matplotlib.pyplot as ply
import h5py
import pickle


def runDetection(img, imgName =None):
    bwU = imageLocalization(img)
    CNNmodel = loadModel()
    dm = img.shape
    orig = np.float64(np.copy(img))

    for i in range(0,3,1):
       orig[:,:,i]-= np.mean(orig[:,:,i].flatten())

    with open('required/BGRnorm.pickle', 'rb') as handle:
        norm = pickle.load(handle)
        M = norm["mean"]
        SD = norm["std"]

    sz = 48
    Ohs, Ows = dm[0],dm[1]
    hs = np.copy(Ohs)
    ws = np.copy(Ows)
    imgS  = []
    maskS = []
    hVec  = []
    wVec  = []
    imgS.append(orig)
    maskS.append(bwU)
    hVec.append(np.int16(np.round(np.linspace(0, Ohs - 1, hs))))
    wVec.append(np.int16(np.round(np.linspace(0, Ows - 1, ws))))

    for i in range(0,10,1):
        if ((hs < 3*sz) | (ws < 3*sz)):
            break

        hs = np.int(np.round(hs * 0.8))
        ws = np.int(np.round(ws * 0.8))
        newIm = cv2.resize(imgS[i],  (ws, hs), interpolation=cv2.INTER_AREA)
        newMs = cv2.resize(maskS[i], (ws, hs), interpolation=cv2.INTER_AREA)
        imgS.append(newIm)
        maskS.append(newMs)
        hVec.append(np.int16(np.round(np.linspace(0, Ohs-1, hs))))
        wVec.append(np.int16(np.round(np.linspace(0, Ows-1, ws))))

    loc,dPrb,dVal = [], [], []
    pSz = np.int16(np.round(sz/2.))
    steps =  5 #np.int16(np.round(pSz/4))
    numPx = 500
    numPyr = imgS.__len__()

    for lvl in range(0,numPyr,1):
        currMk = maskS[lvl]
        currIm = imgS[lvl]
        currWv = wVec[lvl]
        currHv = hVec[lvl]
        h,w,c = currIm.shape
        if lvl > 3:
            steps = 4
            numPx = 150
        elif lvl > 5:
            steps = 2
            numPx = 100

        for i in range(0, h-sz, steps):
            h1 = np.max([0, i-pSz])
            h2 = np.min([h, i+pSz])
            if not np.any(currMk[h1:h2, :]):
                continue

            for j in range(0, w-sz, steps):
                w1 = np.max([0,j-pSz])
                w2 = np.min([w,j+pSz])

                if (h2-h1 < sz) | (w2-w1 < sz):
                    continue

                currWindow = currMk[h1:h2, w1: w2]
                numPix = np.count_nonzero(currWindow)
                if numPix< numPx:
                    continue

                cropIm = currIm[h1:h2, w1:w2, :].astype('float64')
                cropIm = cropIm - M
                cropIm = cropIm / SD
                im = np.reshape(cropIm,(1,sz,sz,c))
                yOut = CNNmodel.predict(im)  # predicting digits
                ndig = np.array(yOut[0].squeeze())
                digs = np.array(yOut[1:5]).squeeze()
                bwdig = np.array(yOut[5].squeeze())
                numDig = np.argmax(ndig)
                print ([j,i,lvl])

                nMask = (bwdig[1]>0.9) & (numDig >0)
                if np.any(nMask):
                    vals = np.argmax(digs,axis=1)
                    dV = np.hstack((numDig, np.argmax(digs,axis=1)))
                    dP = np.hstack((ndig[numDig],
                                    digs[0,vals[0]],digs[1,vals[1]],
                                    digs[2,vals[1]],digs[3,vals[1]]))
                    if np.sum(dP) > 3.5:
                        bbox = np.array([currWv[w1], currHv[h1], currWv[w2], currHv[h2]],dtype = 'int16')
                        loc.append(bbox)
                        dVal.append(dV)
                        dPrb.append(dP)

    boxes = np.asarray(loc)
    vals  = np.asarray(dVal).squeeze()
    probs = np.asarray(dPrb).squeeze()

    probMask = np.zeros((Ohs,Ows),dtype= 'float64')
    for idx in range(0,len(boxes),1):
        b = boxes[idx]
        blank = np.zeros_like(img,dtype ='uint8')
        bw = np.zeros_like(probMask, dtype='float64')
        cv2.rectangle(blank, (b[0], b[1]), (b[2], b[3]), (255, 255, 255), -1)
        bw = np.float64(blank[:,:,1])/255.
        probMask = probMask + (bw *np.sum(probs[idx]))

    pbw = probMask > np.max(probMask)*.15 #200
    pbw = cv2.morphologyEx(np.uint8(pbw), cv2.MORPH_CLOSE, np.ones((3, 3)),iterations= 2)
    contours, _ = cv2.findContours(np.uint8(pbw), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    bbox = []
    for Cnt in contours:
        cB = cv2.boundingRect(Cnt)
        cbox = [cB[0], cB[1], cB[0]+cB[2],cB[1]+cB[3]]
        bbox.append(cbox)

    maybeBox = []
    prds = []
    for idx in range(0,len(bbox),1):
        b = bbox[idx]
        currbw = bwU[b[1]:b[3], b[0]:b[2]]
        currbw = cv2.morphologyEx(currbw, cv2.MORPH_CLOSE, np.ones((5, 5)),iterations= 5)
        bwcontours, tree = cv2.findContours(np.uint8(currbw), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        tmpbox = []
        for Cnt in bwcontours:
            cB = cv2.boundingRect(Cnt)
            cbox = np.add([cB[0], cB[1], cB[0]+cB[2], cB[1]+cB[3]] ,
                          [b[0] , b[1], b[0] , b[1]])
            tmpbox.append(cbox)
        if not tmpbox:
            continue
        cbox = np.asarray(tmpbox)
        mbox = [np.min(cbox[:,0]), np.min(cbox[:,1]), np.max(cbox[:,2]), np.max(cbox[:,3])]
        tmp = np.asarray(mbox)
        nmbox = [tmp[0] - 0 , tmp[1]-0, tmp[2]+0, tmp[3]+0]
        # maybe = np.int16(np.round(nmbox))
        maybe = np.int16(np.round(np.mean([mbox, b], axis=0)))
        maybeBox.append(maybe)

        patch = cv2.resize(orig[maybe[1]:maybe[3], maybe[0]:maybe[2],:],(sz,sz))
        patch = (patch - M)/SD
        y0 = CNNmodel.predict(np.reshape(patch,(1,sz,sz,c)))
        prds.append(y0)

    finalBox = np.asarray(maybeBox)
    outIm = drawBoundingBox(finalBox, prds, img, imgName)

    return outIm

# Create images with predcitions plotted
def drawBoundingBox(maybeBox,prds,img,name = 'test1'):

    oIm = np.copy(img)
    font = cv2.FONT_HERSHEY_SIMPLEX

    for ix in range(0,len(maybeBox),1):
        nDig = np.argmax(prds[ix][0])
        if nDig == 0:
            continue # not a sequence

        nDigProb = np.max(prds[ix][0])
        tmp = np.asarray(prds[ix][1:5]).squeeze()
        seq = np.argmax(tmp, axis=1)
        seqProb = np.max(tmp, axis=1)
        confidence = (np.sum(seqProb) + nDigProb)/5.

        if (nDigProb < 0.85) | (confidence < 0.8):
            continue

        b = maybeBox[ix]
        cv2.rectangle(oIm, (b[0], b[1]), (b[2], b[3]), (0,255,255), 2)
        sequence = seq[seq!=10]

        text1 = str(sequence)
        conf = confidence*100
        text2 = 'confidence:' + str(('%2.3f'%conf)) + '%'
        org1 = (b[0], b[1] - 5)
        org2 = (b[0], b[3] + 5)

        cv2.putText(oIm, text1, org1, font,fontScale = 2, color =  (0, 255, 0),lineType = 3,thickness=3)
        cv2.putText(oIm, text2, org2, font, fontScale =.75, color=(255, 255, 255),lineType =2,thickness=2)

        cv2.imwrite('graded_images/' + name + '.png', oIm)

    return oIm

# removes contents of the image without any significant gradient changes
def imageLocalization(img):
    origImg = np.copy(img)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    imb = cv2.morphologyEx(img,cv2.MORPH_OPEN,np.ones((3,3)))
    tmp = np.uint8(cv2.dilate(imb,np.ones((2,2))))
    blurred = cv2.GaussianBlur(tmp, (15, 15), 0)

    img2 = np.float64(np.copy(blurred))
    sobelx = cv2.Sobel(img, cv2.CV_64F, 1, 0, ksize=15)
    sobely = cv2.Sobel(img, cv2.CV_64F, 0, 1, ksize=15)

    mag = np.sqrt(np.square(sobelx) + np.square(sobely))
    BW = mag > 0.2 * np.max(mag)

    bwU = np.uint8(BW.copy())
    bwU = cv2.morphologyEx(bwU, cv2.MORPH_CLOSE, np.ones((3, 3)))
    bwU = cv2.morphologyEx(bwU, cv2.MORPH_OPEN, np.ones((5, 5)))
    contours,_ = cv2.findContours(bwU, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    area,bbox = [],[]
    for Cnt in contours:
        area.append(cv2.contourArea(Cnt))
        bbox.append(cv2.boundingRect(Cnt))

    bb = np.asarray(bbox,dtype = 'float64')
    aspectRatio = bb[:,2].flatten()/bb[:,3].flatten()
    ar = np.asarray(area)

    filter = (ar > 200) & (aspectRatio<3) & (aspectRatio > 0.25) #& (ar < 6000)
    conts = np.asarray(contours)
    conts = conts[filter]

    mask = np.ones(bwU.shape[:2],dtype = 'uint8') * 255
    for ix in range(0,len(filter),1):
        if filter[ix] == False:
           cv2.drawContours(mask,[contours[ix]],-1,0,-1)

    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, np.ones((2, 2)))
    bwU = cv2.bitwise_and(bwU,mask)
    bwU = cv2.morphologyEx(bwU, cv2.MORPH_OPEN, np.ones((2, 2)))
    return bwU

def loadModel():
    return load_model('required/VGGPreTrained.classifier.hdf5')

def loadAndDetectImages(): 
    imName = "image"
    Img = cv2.imread("image.jpg")
    runDetection(Img, imgName = imName)

if __name__ == "__main__":
    loadAndDetectImages()
