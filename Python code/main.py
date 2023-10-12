import pathlib
import time
import os
import datetime
import json
import sys
import logging
import sqlite3
import telegram
import requests
from flask import Flask, request, abort

py_formatter = logging.Formatter("%(asctime)s - [%(process)s][%(levelname)s] -  %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s")
log = logging.getLogger(__name__)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(py_formatter)
log.addHandler(sh)

if 'DEBUG' in os.environ:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)

dbConfig = '/bot/synoCam.db'

dbConnection = sqlite3.connect(dbConfig, check_same_thread=False)
cursor = dbConnection.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS CamVideo (id INTEGER PRIMARY KEY, cam_id INTEGER UNIQUE, old_last_video_id INTEGER,video_offset INTEGER)')
dbConnection.commit()

#validate
if 'TG_CHAT_ID' not in os.environ:
    log.info('TG_CHAT_ID does not exist. Please configurate environment')
    sys.exit()
if 'TG_TOKEN' not in os.environ:
    log.info('TG_TOKEN does not exist. Please configurate environment')
    sys.exit()
if 'SYNO_IP' not in os.environ:
    log.info('SYNO_IP does not exist. Please configurate environment')
    sys.exit()
if 'SYNO_PORT' not in os.environ:
    log.info('SYNO_PORT does not exist. Please configurate environment')
    sys.exit()
if 'SYNO_LOGIN' not in os.environ:
    log.info('SYNO_LOGIN does not exist. Please configurate environment')
    sys.exit()
if 'SYNO_PASS' not in os.environ:
    log.info('SYNO_PASS does not exist. Please configurate environment')
    sys.exit()

chat_id = os.environ['TG_CHAT_ID']
token = os.environ['TG_TOKEN']

tg = telegram.TelegramBot(token)

syno_ip = os.environ['SYNO_IP']
syno_url = 'http://' + syno_ip + ':' + os.environ['SYNO_PORT'] + '/webapi/entry.cgi'
syno_login = os.environ['SYNO_LOGIN']
syno_pass = os.environ['SYNO_PASS']
if 'SYNO_OTP' in os.environ:
    syno_otp = os.environ['SYNO_OTP']

config_file = '/bot/syno_cam_config.json'

# Send Telegram message
def send_cammessage(message):
    tg.send_message(chat_id, message)
    
def send_camvideo(videofile, message):
    video = open(videofile, 'rb')
    tg.send_video(chat_id, video, message)


def firstStart():
    # With OTP code
    if 'SYNO_OTP' in os.environ:
        params={'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
                            'account': syno_login, 'passwd': syno_pass, 'otp_code': syno_otp,
                            'session': 'SurveillanceStation', 'format': 'cookie12'}
    # Without OTP code
    else:
        params={'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
                'account': syno_login, 'passwd': syno_pass,
                'session': 'SurveillanceStation', 'format': 'cookie12'}

    try:
        response = requests.get(syno_url, params)
    except requests.exceptions.HTTPError as errh:
        print ("Http Error:", errh)
    except requests.exceptions.ConnectionError as errc:
        print ("Error Connecting:", errc)
    except requests.exceptions.Timeout as errt:
        print ("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print ("OOps: Something Else", err)

    if 'data' not in response.json():
        log.info('Login or Password is wrong. Please configurate environment')
        sys.exit()

    sid = response.json()['data']['sid']

    log.info(sid)          
    if 'sid' not in locals():
        log.info('Login or Password is wrong. Please configurate environment')
        sys.exit()

    # Cameras config
   
    try:
        cameras = requests.get(syno_url,
            params={'api': 'SYNO.SurveillanceStation.Camera',
                    '_sid': sid, 'version': '9', 'method': 'List'}).json()
    except requests.exceptions.HTTPError as err:
        raise SystemExit(err)
    
    data = {}
    cam_conf_text = ""
    for i in range(len(cameras['data']['cameras'])):
        data[cameras['data']['cameras'][i]['id']] = {'CamId': cameras['data']['cameras'][i]['id'],
                                                        'IP': cameras['data']['cameras'][i]['ip'],
                                                  'SynoName': cameras['data']['cameras'][i]['newName'],
                                                     'Model': cameras['data']['cameras'][i]['model'],
                                                    'Vendor': cameras['data']['cameras'][i]['vendor']}
        cam_conf_text += ('CamId: ' + str(cameras['data']['cameras'][i]['id'])
                        + ' IP: ' + cameras['data']['cameras'][i]['ip']
                        + ' SynoName: ' + cameras['data']['cameras'][i]['newName']
                        + ' Model: ' + cameras['data']['cameras'][i]['model']
                        + ' Vendor: ' + cameras['data']['cameras'][i]['vendor'] + '\n')
    log.info(cam_conf_text)
    data['SynologyAuthSid'] = sid

    if not pathlib.Path(config_file).is_file():
        with open(config_file, "w") as f:
            json.dump(data, f)
        log.info("Config saved successfully.")
        # Send Telegram Cameras config
        mycaption = "Cameras config:\n" + cam_conf_text
        send_cammessage(mycaption)

if not pathlib.Path(config_file).is_file():
    log.info('Not Found Syno config, need create')
    firstStart()

if pathlib.Path(config_file).stat().st_size == 0:
    log.info('Syno config is empty.')
    firstStart()

if pathlib.Path(config_file).stat().st_size == 0:
    log.info('Syno config always is empty. Exit.')
    sys.exit()

with open(config_file) as f:
    cam_load = json.load(f)
syno_sid = cam_load['SynologyAuthSid']

for i in cam_load:
    cursor.execute('SELECT old_last_video_id FROM CamVideo WHERE cam_id = ?', (i,))
    data=cursor.fetchone()
    if data is None:
        cursor.execute('INSERT INTO CamVideo (cam_id, old_last_video_id, video_offset) VALUES (?, ?, ?)', (i, 0, 0))
        dbConnection.commit()
    else:
        if data[0] > 0:
            cursor.execute('UPDATE CamVideo SET old_last_video_id = ?, video_offset = ? WHERE cam_id = ?', (0, 0, i))
            dbConnection.commit()
    
def get_last_id_video(cam_id, getOffset = False):
    offset = 0;
    result = requests.get(syno_url,
        params={'version': '6', 'cameraIds': cam_id, 'api': 'SYNO.SurveillanceStation.Recording',
                'toTime': '0', 'offset': '0', 'limit': '1', 'fromTime': '0', 'method': 'List', '_sid': syno_sid})
    log.debug('Get last video ifo result = '+str(result.json()))
    take_video_id = result.json()['data']['recordings'][0]['id'];
    
    if getOffset:
        spl_date = result.json()['data']['recordings'][0]['filePath'].split('-')
        log.debug('GET spl_date = '+str(spl_date))
        offset = datetime.datetime.now() - datetime.datetime.strptime(spl_date[1] + spl_date[2], '%Y%m%d%H%M%S')
        log.debug('Date now = '+str(datetime.datetime.now()) + ' date file = ' + str(datetime.datetime.strptime(spl_date[1] + spl_date[2], '%Y%m%d%H%M%S')))
        log.debug('GET offset = '+str(offset)+' seconds = '+str(offset.seconds))
        offset = offset.seconds * 1000 - 5000

    return take_video_id, offset

def get_last_video(cam_id, video_id, offset):
    params={'id': video_id, 'version': '6', 'mountId': '0', 'api': 'SYNO.SurveillanceStation.Recording',
                'method': 'Download', 'offsetTimeMs': offset, 'playTimeMs': 10000,'_sid': syno_sid}
    log.debug('Get video with params = '+str(params))
    download = requests.get(syno_url + '/temp.mp4',params, allow_redirects=True)
    with open('/bot/'+str(cam_id)+'.mp4', 'wb') as video:
        video.write(download.content)

def get_video_by_time(cam_id, start_time, end_time = None):
    
    end_time = start_time + 10
    start_time -= 5

    params={'camId': cam_id, 'version': '6', 'fileName': 'video', 'fromTime': start_time,'toTime' : end_time,
                'api': 'SYNO.SurveillanceStation.Recording', 'method': 'RangeExport', '_sid': syno_sid}
    log.debug('Get video with params = ' + str(params))
    result = requests.get(syno_url,params, allow_redirects=True)
    log.debug('Get video start = '+str(result.json()))
    dlid = result.json()['data']['dlid']
    time.sleep(2)

    params={'dlid': dlid, 'version': '6', 'api': 'SYNO.SurveillanceStation.Recording',
                'method': 'GetRangeExportProgress', '_sid': syno_sid}
    result = requests.get(syno_url,params, allow_redirects=True)
    log.debug('Get video process = '+str(result.json()))
    
    params={'dlid': dlid, 'fileName': 'video', 'version': '6', 'api': 'SYNO.SurveillanceStation.Recording',
                'method': 'OnRangeExportDone', '_sid': syno_sid}
    log.debug('Get video with params = '+str(params))
    download = requests.get(syno_url,params, allow_redirects=True)
    with open('/bot/'+str(cam_id)+'.mp4', 'wb') as video:
        video.write(download.content)
    

def get_alarm_camera_state(cam_id):
    take_alarm = requests.get(syno_url,
        params={'version': '1', 'id_list': cam_id, 'api': 'SYNO.SurveillanceStation.Camera.Status',
                    'method': 'OneTime', '_sid': syno_sid}).json()['data']['CamStatus']
    alarm_state = take_alarm.replace("[", "").replace("]", "").split()[7]
    return 1 if alarm_state == '1' else 0

app = Flask(__name__)

log.info('Module start. Wait hooks.')

@app.route('/webhookcam', methods=['POST'])
def webhookcam():
    if request.method == 'POST':
        log.info("New request "+ str(request.json))
        cam_id = request.json['idcam']

        log.info("Received IDCam: "+ cam_id + ', ' + str(datetime.datetime.now()))
        if 'alwaysRecord' in request.json:
            time.sleep(5)
            start_time=int(datetime.datetime.now().timestamp())
            get_video_by_time(cam_id,start_time)
            last_video_id = start_time
            video_offset = 0

        else:
            video_offset = 0
            time.sleep(5)
            last_video_id = get_last_id_video(cam_id)[0]

        if 'alwaysRecord' not in request.json:
            cursor.execute('SELECT old_last_video_id FROM CamVideo WHERE cam_id = ?', (cam_id,))
            old_last_video_id = cursor.fetchone()[0]
            if last_video_id != old_last_video_id:
                cursor.execute('UPDATE CamVideo SET old_last_video_id = ?, video_offset = ? WHERE cam_id = ?', (last_video_id, video_offset, cam_id))
                dbConnection.commit()
            else:
                cursor.execute('UPDATE CamVideo SET video_offset = video_offset + 10000 WHERE cam_id = ?', (cam_id))
                dbConnection.commit()
                cursor.execute('SELECT video_offset FROM CamVideo WHERE cam_id = ?', (cam_id,))
                video_offset = cursor.fetchone()[0]
            get_last_video(cam_id, last_video_id, video_offset)

        if 'DEBUG' not in os.environ:
            message = "Camera " + str(cam_load[cam_id]['SynoName'])
        else:
            message = "Camera " + str(cam_load[cam_id]['SynoName'] + " DEBUG_ID: " + str(last_video_id)+' offset: ' + str(video_offset))

        send_camvideo('/bot/'+str(cam_id) + '.mp4',message)
        os.remove('/bot/'+str(cam_id)+'.mp4')

        return 'success', 200
    else:
        abort(400)


@tg.tg_bot.message_handler(commands=['start'])
def start_message(message):
    tg.send_message(message.chat.id,"Привет ✌️ ")

@tg.tg_bot.message_handler(commands=['config'])
def getConfig(message):
    cam_conf_text = "Cameras config:\n"
    for i in cam_load:
        if 'CamId' in cam_load[i]:
            cam_conf_text += ('CamId: ' + str(cam_load[i]['CamId'])
                    + ' IP: ' + cam_load[i]['IP']
                    + ' SynoName: ' + cam_load[i]['SynoName']
                    + ' Model: ' + cam_load[i]['Model']
                    + ' Vendor: ' + cam_load[i]['Vendor'] + '\n')
    send_cammessage(cam_conf_text)

tg.infinity_polling()
