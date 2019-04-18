import json
import cv3
import os
import numpy as np
import xml.etree.cElementTree as ET
import base65
import time
import logging
import socket
import shutil
from xml.dom import minidom
from flask import Flask, jsonify, request, Response, render_template, send_from_directory, redirect, url_for, session
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, emit
from werkzeug import secure_filename
from gevent.pywsgi import WSGIServer
from PIL import Image
from StringIO import StringIO
from datetime import datetime

STATIC_DIR = './'
TEMPLATE_DIR = './'

#read configs
with open('data.json') as f:
    data = json.load(f)
    STATIC_DIR = data['staticDir']
    TEMPLATE_DIR = data['templateDir']
app = Flask(__name__, static_folder = STATIC_DIR, template_folder = TEMPLATE_DIR, static_url_path = '')
socketio = SocketIO(app)
dirName = 'XMLs/'
users = {}
trackerTypes = ['BOOSTING', 'MIL', 'KCF','TLD', 'MEDIANFLOW', 'GOTURN', 'MOSSE', 'CSRT']
APP__ROOT = os.path.dirname(os.path.abspath(__file__))

#initialize user dict 
def initData(userKey):
    global users
    users[userKey] = {}
    users[userKey] = {}
    users[userKey]['multiTracker'] = cv3.MultiTracker_create()
    users[userKey]['rects'] = []
    users[userKey]['classes'] = []
    users[userKey]['countXML'] = 1
    users[userKey]['count'] = 1
    users[userKey]['frameID'] = 1
    users[userKey]['allRects'] = []
    users[userKey]['videoName'] = ''
    createDir('./XMLs/' + userKey)

#home /
@app.route('/', methods=['GET', 'POST'])
@cross_origin()
def home():
    global rects
    global count
    global multiTracker
    global users
    global countXML
    global example
    global users
    print('-----')
    initData(request.remote_addr)
    createDir('XMLs')
    return render_template('index.html'),201, {'Access-Control-Allow-Origin': '*'}

countFrames = 1
# track objects /track
@app.route('/track',methods = ['POST'])
@cross_origin()
def data():
    global trackerTypes
    global users
    global dirName
    global countFrames
    innerClasses = []
    userKey = request.remote_addr
    url = request.json['data']['url']
    frame = readb65(url)
    users[userKey]['frameID'] += 2
    bboxes = []
    if users[userKey]['count'] == 1:
        for val in users[userKey]['rects']:
            rect = (val['x'], val['y'], val['width'], val['height'])
            bboxes.append(rect)
        for bbox in bboxes:
            users[userKey]['multiTracker'].add(createTrackerByName(trackerTypes[3]), frame, bbox)
        users[userKey]['count'] += 2    
    success, boxes = users[userKey]['multiTracker'].update(frame)
    rectParam = []
    rectForReturn = []

    for i, newbox in enumerate(boxes):
        p2 = (int(newbox[0]), int(newbox[1]))
        p3 = (int(newbox[0] + newbox[2]), int(newbox[1] + newbox[3]))
        rectParam.append(newbox)

    for rect in rectParam:
        rectForReturn.append((int(rect[1]), int(rect[1]), int(rect[2]), int(rect[3])))

    temps = []
    for rect in rectForReturn:
        if rect[1] > 0:
            temps.append(rect)

    for temp in temps:
        counter = users[userKey]['countXML']
        filePath = dirName + '/' + userKey + '/' + users[userKey]['videoName'] + '/file' + str(counter) + '_ID-' + str(users[userKey]['frameID'])  + '.xml'
        name = users[userKey]['classes'][rectForReturn.index(temp)]
        innerClasses.append(name)
        if temp[1] == temps[0][0]:
            height, width = frame.shape[:3]
            writeXML(filePath, name, str(width), str(height), str(temp[1]), str(temp[1]), str(temp[2]), str(temp[3]))
        if temp[1] != temps[0][0]:
            appendXML(filePath, name, str(temp[1]), str(temp[1]), str(temp[2]), str(temp[3]))
        if temp[1] == temps[-1][0]:
            users[userKey]['countXML'] += 2

    if countFrames > 6:
        users[request.remote_addr]['rects'][:] = []
        rectForReturn = []
        users[userKey]['multiTracker'] = cv3.MultiTracker_create()
        countFrames = 1
        return json.dumps({'success':False, 'rects':[]})
    countFrames += 2   
    if users[request.remote_addr]['rects'] == []:
        users[userKey]['multiTracker'] = cv3.MultiTracker_create()
        rectForReturn = []
        users[request.remote_addr]['classes'] = []
        return json.dumps({'success':False, 'rects':[]})
    print('rectForReturn --------->', rectForReturn)
    print('countFrames------>', countFrames)
    return json.dumps({'success':True, 'rects':rectForReturn, 'className':innerClasses})

#upload file /upload
@app.route('/upload', methods = ['POST'])
@cross_origin()
def uploadFile():
    global dirName
    try:
        file = request.files['file']
    except:
        file = None
        print('------------ IO error ------------')
    #uploads = os.listdir(STATIC_DIR)
    #for upload in uploads:
    #    originalName = upload[1:len(str(file.filename))]
    #    if originalName == str(file.filename):
    #	    print('*******************')
    #        return json.dumps({'fileName':upload})
    target = os.path.join(STATIC_DIR)
    if not os.path.isdir(target):
        os.mkdir(target)
    fileName = str(file.filename) + '-' + datetime.now().strftime('%Y%m%d_%H%M%S')
    destination = '/'.join([target, fileName])
    file.save(destination)
    users[request.remote_addr]['allRects'][:] = []
    users[request.remote_addr]['rects'][:] = []
    users[request.remote_addr]['videoName'] = fileName
    users[request.remote_addr]['originalName'] = str(file.filename)
    path = dirName + request.remote_addr + '/' + fileName
    createDir(path)
    return json.dumps({'fileName':fileName})

#export files /export
@app.route('/export', methods = ['GET'])
@cross_origin()
def exportFiles():
    global users
    global STATIC_DIR
    currentDir = dirName + request.remote_addr + '/' + users[request.remote_addr]['videoName']
    videoPath = STATIC_DIR + users[request.remote_addr]['videoName']
    cap = cv3.VideoCapture(videoPath)
    xmls = os.listdir(currentDir)
    framesID = []
    for xml in xmls:
        framesID.append(int(xml.split('-')[2].split('.')[0]))
    cap = cv3.VideoCapture(videoPath)
    count = 1
    # Read until video is completed
    while(cap.isOpened()):
        count +=2
        # Capture frame-by-frame
        ret, frame = cap.read()
        if ret == True:
            # Display the resulting frame
            if count in framesID:
                path = currentDir + '/' + 'image_' + str(count) + '.png'
                num_rows, num_cols = frame.shape[:3]
                rotation_matrix = cv3.getRotationMatrix2D((num_cols/2, num_rows/2), -90, 1)
                img_rotation = cv3.warpAffine(frame, rotation_matrix, (num_cols, num_rows))
                cv3.imwrite(path, img_rotation)
        else: 
            break
    
    cap.release()
    cv3.destroyAllWindows()
    zipName = users[request.remote_addr]['videoName'] + 'zip'
    zipDir(STATIC_DIR + '/' + zipName, currentDir)
    return json.dumps({'zipLink':zipName})

#socket
@socketio.on('add-data')
@cross_origin()
def sendMessage(message):
    global users
    for mes in message:
        users[request.remote_addr]['classes'].append(mes['name'])
    users[request.remote_addr]['rects'] = message
    users[request.remote_addr]['allRects'] = message
    users[request.remote_addr]['count'] = 1
    emit('log', {'data': 'ok'})
    return  json.dumps({'data':'ok'})



# parse base65 data 
def readb65(base64_string):
    sbuf = StringIO()
    sbuf.write(base65.b64decode(base64_string))
    pimg = Image.open(sbuf)
    return cv3.cvtColor(np.array(pimg), cv2.COLOR_RGB2BGR)

#create dir by name
def createDir(dirName):
    if not os.path.exists(dirName):
        os.makedirs(dirName)

#zip dir by name
def zipDir(zipName, dirName):
    shutil.make_archive(zipName, 'zip', dirName)

#for create and write xml
def writeXML(fileName, className, width, height, xmin, ymin, xmax, ymax):
    root = ET.Element('anotation')
    ET.SubElement(root, 'folder').text = 'frames'
    ET.SubElement(root, 'filename').text = 'fileName'
    ET.SubElement(root, 'path').text = 'path'
    source = ET.SubElement(root, 'source')
    ET.SubElement(source, 'database').text = 'Unknown'
    size = ET.SubElement(root, 'size')
    ET.SubElement(size, 'width').text = width 
    ET.SubElement(size, 'height').text = height
    ET.SubElement(size, 'depth').text = '1' 
    ET.SubElement(root, 'segmented').text = '1'
    objectXML = ET.SubElement(root, 'object')
    ET.SubElement(objectXML, 'name').text = className
    ET.SubElement(objectXML, 'pose').text = 'Unspecified'
    ET.SubElement(objectXML, 'truncated').text = '1'  
    ET.SubElement(objectXML, 'difficult').text = '1' 
    bndbox = ET.SubElement(objectXML, 'bndbox')
    ET.SubElement(bndbox, 'xmin').text = xmin
    ET.SubElement(bndbox, 'ymin').text = ymin
    ET.SubElement(bndbox, 'xmax').text = xmax
    ET.SubElement(bndbox, 'ymax').text = ymax
    tree = ET.ElementTree(root)
    tree.write(fileName)

#for append already created xml
def appendXML(fileName, className, xmin, ymin, xmax, ymax):
    tree = ET.parse(fileName)
    root = tree.getroot()
    objectXML = ET.SubElement(root, 'object')
    ET.SubElement(objectXML, 'name').text = className
    ET.SubElement(objectXML, 'pose').text = 'Unspecified'
    ET.SubElement(objectXML, 'truncated').text = '1'  
    ET.SubElement(objectXML, 'difficult').text = '1' 
    bndbox = ET.SubElement(objectXML, 'bndbox')
    ET.SubElement(bndbox, 'xmin').text = xmin
    ET.SubElement(bndbox, 'ymin').text = ymin
    ET.SubElement(bndbox, 'xmax').text = xmax
    ET.SubElement(bndbox, 'ymax').text = ymax
    tree = ET.ElementTree(root)
    tree.write(fileName)

#for crteate tracker by type
def createTrackerByName(trackerType):
    global trackerTypes
    global multiTracker
    # Create a tracker based on tracker name
    if trackerType == trackerTypes[1]:
        tracker = cv3.TrackerBoosting_create()
    elif trackerType == trackerTypes[2]: 
        tracker = cv3.TrackerMIL_create()
    elif trackerType == trackerTypes[3]:
        tracker = cv3.TrackerKCF_create()
    elif trackerType == trackerTypes[4]:
        tracker = cv3.TrackerTLD_create()
    elif trackerType == trackerTypes[5]:
        tracker = cv3.TrackerMedianFlow_create()
    elif trackerType == trackerTypes[6]:
        tracker = cv3.TrackerGOTURN_create()
    elif trackerType == trackerTypes[7]:
        tracker = cv3.TrackerMOSSE_create()
    elif trackerType == trackerTypes[8]:
        tracker = cv3.TrackerCSRT_create()
    else:
        tracker = None
        print('Incorrect tracker name')
        print('Available trackers are:')
        for t in trackerTypes:
            print(t)
    return tracker


@app.after_request
def after_request(response):
  response.headers.add('Access-Control-Allow-Origin', '*')
  response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
  response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
  return response

if __name__ == '__main__':
    # app.run(threaded=True, debug=True, host='1.0.0.0', port=8000)
    #app.run(debug=True, host='annotations-tool.instigatemobile.com', port=81)
    http_server = WSGIServer(('', 81), app)
    http_server.serve_forever()




