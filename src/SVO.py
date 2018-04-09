import numpy as np
import cv2
import sys
from matplotlib import pyplot as plt
from scipy.optimize import least_squares
from math import cos, sin

def genEulerZXZMatrix(psi, theta, sigma):
    # ref http://www.u.arizona.edu/~pen/ame553/Notes/Lesson%2008-A.pdf
    mat = np.zeros((3,3))
    mat[0,0] = cos(psi) * cos(sigma) - sin(psi) * cos(theta) * sin(sigma)
    mat[0,1] = -cos(psi) * sin(sigma) - sin(psi) * cos(theta) * cos(sigma)
    mat[0,2] = sin(psi) * sin(theta)

    mat[1,0] = sin(psi) * cos(sigma) + cos(psi) * cos(theta) * sin(sigma)
    mat[1,1] = -sin(psi) * sin(sigma) + cos(psi) * cos(theta) * cos(sigma)
    mat[1,2] = -cos(psi) * sin(theta)

    mat[2,0] = sin(theta) * sin(sigma)
    mat[2,1] = sin(theta) * cos(sigma)
    mat[2,2] = cos(theta)

    return mat

def minimizeReprojection(dof,d2dPoints1, d2dPoints2, d3dPoints1, d3dPoints2, w2cMatrix):
    Rmat = genEulerZXZMatrix(dof[0], dof[1], dof[2])
    translationArray = np.array([[dof[3]], [dof[4]], [dof[5]]])
    temp = np.hstack((Rmat, translationArray))
    perspectiveProj = np.vstack((temp, [0, 0, 0, 1]))
    #print (perspectiveProj)

    numPoints = d2dPoints1.shape[0]
    errorA = np.zeros((numPoints,3))
    errorB = np.zeros((numPoints,3))

    forwardProjection = np.matmul(w2cMatrix, perspectiveProj)
    backwardProjection = np.matmul(w2cMatrix, np.linalg.inv(perspectiveProj))
    for i in range(numPoints):
        Ja = np.ones((3))
        Jb = np.ones((3))
        Wa = np.ones((4))
        Wb = np.ones((4))

        Ja[0:2] = d2dPoints1[i,:]
        Jb[0:2] = d2dPoints2[i,:]
        Wa[0:3] = d3dPoints1[i,:]
        Wb[0:3] = d3dPoints2[i,:]

        JaPred = np.matmul(forwardProjection, Wb)
        JaPred /= JaPred[-1]
        e1 = Ja - JaPred

        JbPred = np.matmul(backwardProjection, Wa)
        JbPred /= JbPred[-1]
        e2 = Jb - JbPred

        errorA[i,:] = e1
        errorB[i,:] = e2

    residual = np.vstack((errorA,errorB))
    return residual.flatten()

if __name__ == "__main__":

    sequence = 00   #sys.argv[1]
    startFrame = 0 #sys.argv[2]
    endFrame = 1 #sys.argv[3]

    datapath = '../Data/' + '{0:02d}'.format(sequence)

    calibFileName = datapath + '/calib.txt'
    calibFile = open(calibFileName, 'r').readlines()
    P1Vals = calibFile[0].split()
    Proj1 = np.zeros((3,4))
    for row in range(3):
        for column in range(4):
            Proj1[row, column] = float(P1Vals[row*4 + column + 1])

    P2Vals = calibFile[1].split()
    Proj2 = np.zeros((3,4))
    for row in range(3):
        for column in range(4):
            Proj2[row, column] = float(P2Vals[row*4 + column + 1])

    leftImagePath = datapath + '/image_0/'
    rightImagePath = datapath + '/image_1/'

    for frm in range(startFrame+1, endFrame+1):

        # reuse T-1 data instead of reading again-again
        # same with feature computation - anything that can be reused
        imgPath = leftImagePath + '{0:06d}'.format(frm-1) + '.png';
        ImT1_L = cv2.imread(imgPath, 0)    #0 flag returns a grayscale image

        imgPath = rightImagePath + '{0:06d}'.format(frm-1) + '.png';
        ImT1_R = cv2.imread(imgPath, 0)

        imgPath = leftImagePath + '{0:06d}'.format(frm) + '.png';
        ImT2_L = cv2.imread(imgPath, 0)

        imgPath = rightImagePath + '{0:06d}'.format(frm) + '.png';
        ImT2_R = cv2.imread(imgPath, 0)

        # cv2.imshow('ImT1_L', ImT1_L)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()

        block = 15
        #emperical values from P1, P2 as suggested in Ocv documentation
        P1 = 0 #block * block * 8
        P2 = 0 #block * block * 32

        disparityEngine = cv2.StereoSGBM_create(minDisparity=0,numDisparities=16, blockSize=block, P1=P1, P2=P2)
        ImT1_disparity = disparityEngine.compute(ImT1_L, ImT1_R).astype(np.float32)
        #cv2.imwrite('disparity.png', ImT1_disparity)
        ImT1_disparityA = np.divide(ImT1_disparity, 16.0)

        ImT2_disparity = disparityEngine.compute(ImT2_L, ImT2_R).astype(np.float32)
        ImT2_disparityA = np.divide(ImT2_disparity, 16.0)

        TILE_H = 10
        TILE_W = 20
        fastFeatureEngine = cv2.FastFeatureDetector_create()

        # keypoints = fastFeatureEngine.detect(ImT1_L)
        # ftDebug = ImT1_L
        # ftDebug = cv2.drawKeypoints(ImT1_L, keypoints, ftDebug, color=(255,0,0))
        # cv2.imwrite('ftDebug.png', ftDebug)

        #20x10 (wxh) tiles for extracting less features from images
        H,W = ImT1_L.shape
        kp = []
        idx = 0
        for y in range(0, H, TILE_H):
            for x in range(0, W, TILE_W):
                imPatch = ImT1_L[y:y+TILE_H, x:x+TILE_W]
                keypoints = fastFeatureEngine.detect(imPatch)
                for pt in keypoints:
                    pt.pt = (pt.pt[0] + x, pt.pt[1] + y)

                if (len(keypoints) > 10):
                    keypoints = sorted(keypoints, key=lambda x: -x.response)
                    for kpt in keypoints[0:10]:
                        kp.append(kpt)
                else:
                    for kpt in keypoints:
                        kp.append(kpt)

        ftDebug = ImT1_L
        ftDebug = cv2.drawKeypoints(ImT1_L, kp, ftDebug, color=(255,0,0))
        cv2.imwrite('ftDebug.png', ftDebug)

        # pack keypoint 2-d coords into numpy array
        trackPoints1 = np.zeros((len(kp),1,2), dtype=np.float32)
        for i,kpt in enumerate(kp):
            trackPoints1[i,:,0] = kpt.pt[0]
            trackPoints1[i,:,1] = kpt.pt[1]

        # Parameters for lucas kanade optical flow
        lk_params = dict( winSize  = (15,15),
                          maxLevel = 3,
                          criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 0.03))

        trackPoints2, st, err = cv2.calcOpticalFlowPyrLK(ImT1_L, ImT2_L, trackPoints1, None, flags=cv2.MOTION_AFFINE, **lk_params)

        # separate points that were tracked successfully
        ptTrackable = np.where(st == 1, 1,0).astype(bool)
        trackPoints1_KLT = trackPoints1[ptTrackable, ...]
        trackPoints2_KLT_t = trackPoints2[ptTrackable, ...]
        trackPoints2_KLT = np.around(trackPoints2_KLT_t)

        # among tracked points take points within error measue
        error = 4
        errTrackablePoints = err[ptTrackable, ...]
        errThresholdedPoints = np.where(errTrackablePoints < error, 1, 0).astype(bool)
        trackPoints1_KLT = trackPoints1_KLT[errThresholdedPoints, ...]
        trackPoints2_KLT = trackPoints2_KLT[errThresholdedPoints, ...]

        # ftDebug = ImT1_L
        # ftDebug = cv2.cvtColor(ftDebug,cv2.COLOR_GRAY2RGB)
        # for points in trackPoints1_KLT:
        #     cv2.circle(ftDebug, (points[0], points[1]), 2, color=(0,0,255))
        # cv2.imwrite('ftDebug_trackedPoints1.png', ftDebug)


        # ftDebug = ImT2_L
        # ftDebug = cv2.cvtColor(ftDebug,cv2.COLOR_GRAY2RGB)
        # for points in trackPoints2_KLT:
        #     cv2.circle(ftDebug, (points[0], points[1]), 2, color=(0,255,0))
        # cv2.imwrite('ftDebug_trackedPoints2.png', ftDebug)

        #compute right image disparity displaced points
        trackPoints1_KLT_L = trackPoints1_KLT
        trackPoints2_KLT_L = trackPoints2_KLT

        trackPoints1_KLT_R = np.copy(trackPoints1_KLT_L)
        trackPoints2_KLT_R = np.copy(trackPoints2_KLT_L)
        selectedPointMap = np.zeros(trackPoints1_KLT_L.shape[0])

        disparityMinThres = 0.0
        disparityMaxThres = 100.0
        for i in range(trackPoints1_KLT_L.shape[0]):
            T1Disparity = ImT1_disparityA[int(trackPoints1_KLT_L[i,1]), int(trackPoints1_KLT_L[i,0])]
            T2Disparity = ImT2_disparityA[int(trackPoints2_KLT_L[i,1]), int(trackPoints2_KLT_L[i,0])]

            if (T1Disparity > disparityMinThres and T1Disparity < disparityMaxThres
                and T2Disparity > disparityMinThres and T2Disparity < disparityMaxThres):
                trackPoints1_KLT_R[i, 0] = trackPoints1_KLT_L[i, 0] - T1Disparity
                trackPoints2_KLT_R[i, 0] = trackPoints2_KLT_L[i, 0] - T2Disparity
                selectedPointMap[i] = 1

        selectedPointMap = selectedPointMap.astype(bool)
        trackPoints1_KLT_L_3d = trackPoints1_KLT_L[selectedPointMap, ...]
        trackPoints1_KLT_R_3d = trackPoints1_KLT_R[selectedPointMap, ...]
        trackPoints2_KLT_L_3d = trackPoints2_KLT_L[selectedPointMap, ...]
        trackPoints2_KLT_R_3d = trackPoints2_KLT_R[selectedPointMap, ...]

        # 3d point cloud triagulation

        numPoints = trackPoints1_KLT_L_3d.shape[0]
        d3dPointsT1 = np.ones((numPoints,3))
        d3dPointsT2 = np.ones((numPoints,3))

        for i in range(numPoints):
            #for i in range(1):
            pLeft = trackPoints1_KLT_L_3d[i,:]
            pRight = trackPoints1_KLT_R_3d[i,:]

            X = np.zeros((4,4))
            X[0,:] = pLeft[0] * Proj1[2,:] - Proj1[0,:]
            X[1,:] = pLeft[1] * Proj1[2,:] - Proj1[1,:]
            X[2,:] = pRight[0] * Proj2[2,:] - Proj2[0,:]
            X[3,:] = pRight[1] * Proj2[2,:] - Proj2[1,:]

            [u,s,v] = np.linalg.svd(X)
            v = v.transpose()
            vSmall = v[:,-1]
            vSmall /= vSmall[-1]

            d3dPointsT1[i, :] = vSmall[0:-1]
        #     print (X)
        #     print (vSmall)

        for i in range(numPoints):
            #for i in range(1):
            pLeft = trackPoints2_KLT_L_3d[i,:]
            pRight = trackPoints2_KLT_R_3d[i,:]

            X = np.zeros((4,4))
            X[0,:] = pLeft[0] * Proj1[2,:] - Proj1[0,:]
            X[1,:] = pLeft[1] * Proj1[2,:] - Proj1[1,:]
            X[2,:] = pRight[0] * Proj2[2,:] - Proj2[0,:]
            X[3,:] = pRight[1] * Proj2[2,:] - Proj2[1,:]

            [u,s,v] = np.linalg.svd(X)
            v = v.transpose()
            vSmall = v[:,-1]
            vSmall /= vSmall[-1]

            d3dPointsT2[i, :] = vSmall[0:-1]

        #tunable - def 0.01
        distDifference = 0.05

        # in-lier detection algorithm
        numPoints = d3dPointsT1.shape[0]
        W = np.zeros((numPoints, numPoints))

        # diff of pairwise euclidean distance between same points in T1 and T2
        for i in range(numPoints):
            for j in range(numPoints):
                T2Dist = np.linalg.norm(d3dPointsT2[i,:] - d3dPointsT2[j,:])
                T1Dist = np.linalg.norm(d3dPointsT1[i,:] - d3dPointsT1[j,:])
                if (abs(T2Dist - T1Dist) < distDifference):
                    W[i, j] = 1

        count = 0
        maxn = 0
        maxc = 0

        # Find point with maximum degree and store in maxn
        for i in range(numPoints):
            for j in range(numPoints):
                if W[i,j] == 1:
                    count = count+1
            if count > maxc:
                maxc = count
                maxn = i
            count=0

        clique = [maxn]
        isin = True

        while True:
            potentialnodes = list()
            # Find potential nodes which are connected to all nodes in the clique
            for i in range(numPoints):
                for j in range(len(clique)):
                    isin = isin & bool(W[i, clique[j]])
                if isin == True and i not in clique:
                    potentialnodes.append(i)
                isin=True

            count = 0
            maxn = 0
            maxc = 0
            # Find the node which is connected to the maximum number of potential nodes and store in maxn
            for i in range(len(potentialnodes)):
                for j in range(len(potentialnodes)):
                    if W[potentialnodes[i], potentialnodes[j]] == 1:
                        count = count+1
                if count > maxc:
                    maxc = count
                    maxn = potentialnodes[i]
                count = 0
            if maxc == 0:
                break
            clique.append(maxn)

        # pick up clique point 3D coords and features for optimization
        pointsInClique = len(clique)
        cliqued3dPointT1 = d3dPointsT1[clique]#np.zeros((pointsInClique, 3))
        cliqued3dPointT2 = d3dPointsT2[clique]

        # points = features
        trackedPoints1_KLT_L = trackPoints1_KLT_L_3d[clique]
        trackedPoints2_KLT_L = trackPoints2_KLT_L_3d[clique]

        ftDebug = ImT1_L
        ftDebug = cv2.cvtColor(ftDebug,cv2.COLOR_GRAY2RGB)
        for points in trackedPoints1_KLT_L:
            cv2.circle(ftDebug, (points[0], points[1]), 2, color=(0,255,0))

        cv2.imwrite('ftDebug_trackedPoints1_clique.png', ftDebug)

        dSeed = np.zeros(6)

        #minimizeReprojection(d, trackedPoints1_KLT_L, trackedPoints2_KLT_L, cliqued3dPointT1, cliqued3dPointT2, Proj1)
        optRes = least_squares(minimizeReprojection, dSeed, method='lm', max_nfev=2000,
                            args=(trackedPoints1_KLT_L, trackedPoints2_KLT_L, cliqued3dPointT1, cliqued3dPointT2, Proj1))

        error = optRes.fun
        pointsInClique = len(clique)
        e = error.reshape((pointsInClique*2, 3))
        errorThreshold = 1.0
        xRes1 = np.where(e[0:pointsInClique, 0] >= errorThreshold)
        yRes1 = np.where(e[0:pointsInClique, 1] >= errorThreshold)
        zRes1 = np.where(e[0:pointsInClique, 2] >= errorThreshold)
        xRes2 = np.where(e[pointsInClique:2*pointsInClique, 0] >= errorThreshold)
        yRes2 = np.where(e[pointsInClique:2*pointsInClique, 1] >= errorThreshold)
        zRes2 = np.where(e[pointsInClique:2*pointsInClique, 2] >= errorThreshold)

        pruneIdx = xRes1[0].tolist() + yRes1[0].tolist() + zRes1[0].tolist() + xRes2[0].tolist() + yRes2[0].tolist() +  zRes2[0].tolist()
        if (len(pruneIdx) > 0):
            uPruneIdx = list(set(pruneIdx))
            trackedPoints1_KLT_L = np.delete(trackedPoints1_KLT_L, uPruneIdx, axis=0)
            trackedPoints2_KLT_L = np.delete(trackedPoints2_KLT_L, uPruneIdx, axis=0)
            cliqued3dPointT1 = np.delete(cliqued3dPointT1, uPruneIdx, axis=0)
            cliqued3dPointT2 = np.delete(cliqued3dPointT2, uPruneIdx, axis=0)

            optRes = least_squares(minimizeReprojection, optRes.x, method='lm', max_nfev=2000,
                            args=(trackedPoints1_KLT_L, trackedPoints2_KLT_L, cliqued3dPointT1, cliqued3dPointT2, Proj1))

        #clique size check
        # reproj error check
        # r, t generation
        # plot on map vs ground truth
