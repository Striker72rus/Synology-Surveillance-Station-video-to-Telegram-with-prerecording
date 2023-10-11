import pathlib
import time
import os
import json
import subprocess
import sys
import logging
import sqlite3
#import telegram

py_formatter = logging.Formatter("%(asctime)s - [%(process)s][%(levelname)s] -  %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s")
log = logging.getLogger(__name__)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(py_formatter)
log.addHandler(sh)
log.setLevel(logging.DEBUG)

# Auto pip install ----------------------------------------------------------------------------------------
try:
    import telebot
    log.info('The telebot module is installed')
except ModuleNotFoundError:
    log.info('The telebot module is NOT installed')
    log.info('The telebot module is Installing...')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'telebot'], stdout=subprocess.DEVNULL)
finally:
    import telebot
#----------
try:
    from flask import Flask, request, abort
    log.info('The flask module is installed')
except ModuleNotFoundError:
    log.info('The flask module is NOT installed')
    log.info('The flask module is Installing...')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'flask'], stdout=subprocess.DEVNULL)
finally:
    from flask import Flask, request, abort
#----------
try:
    import requests
    log.info('The requests module is installed')
except ModuleNotFoundError:
    log.info('The requests module is NOT installed')
    log.info('The requests module is Installing...')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'], stdout=subprocess.DEVNULL)
finally:
    import requests
#----------------------------------------------------------------------------------------------------------
dbConfig = '/bot/synoCam.db'

#if not pathlib.Path(dbConfig).is_file():
dbConnection = sqlite3.connect(dbConfig)
cursor = dbConnection.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS CamVideo (id INTEGER PRIMARY KEY, cam_id INTEGER UNIQUE, old_last_video_id INTEGER,video_offset INTEGER)')
dbConnection.commit()
#else:
#    dbConnection = sqlite3.connect(dbConfig)
#    cursor = dbConnection.cursor()


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

#tg = telegram.TelegramBot(token)

tg_bot = telebot.TeleBot(token)

syno_ip = os.environ['SYNO_IP']
syno_url = 'http://' + syno_ip + ':' + os.environ['SYNO_PORT'] + '/webapi/entry.cgi'
syno_login = os.environ['SYNO_LOGIN']
syno_pass = os.environ['SYNO_PASS']
if 'SYNO_OTP' in os.environ:
    syno_otp = os.environ['SYNO_OTP']

config_file = '/bot/syno_cam_config.json'

# Send Telegram message
def send_cammessage(message):
    tg_bot.send_message(chat_id, message)
    
def send_camvideo(videofile, cam_id, debug):
    mycaption = "Camera " + str(cam_load[cam_id]['SynoName'] + " DEBUG_ID: " + debug)
    video = open(videofile, 'rb')
    tg_bot.send_video(chat_id, video, None, None, None, None, mycaption)


def firstStart():
    # With OTP code
    if 'SYNO_OTP' in os.environ:
        try:
            response = requests.get(syno_url,
                params={'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
                        'account': syno_login, 'passwd': syno_pass, 'otp_code': syno_otp,
                        'session': 'SurveillanceStation', 'format': 'cookie12'})
        except requests.exceptions.HTTPError as errh:
            print ("Http Error:",errh)
        except requests.exceptions.ConnectionError as errc:
            print ("Error Connecting:",errc)
        except requests.exceptions.Timeout as errt:
            print ("Timeout Error:",errt)
        except requests.exceptions.RequestException as err:
            print ("OOps: Something Else",err)
    # Without OTP code
    else:
        try:
            response = requests.get(syno_url,
                params={'api': 'SYNO.API.Auth', 'version': '7', 'method': 'login',
                        'account': syno_login, 'passwd': syno_pass,
                        'session': 'SurveillanceStation', 'format': 'cookie12'})
        except requests.exceptions.HTTPError as err:
            log.info('Login or Password is wrong. Please configurate environment')
            sys.exit()

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
        log.debug("INSERT")
    else:
        log.debug(data)
        if data[0] > 0:
            cursor.execute('UPDATE CamVideo SET old_last_video_id = ?, video_offset = ? WHERE cam_id = ?', (0, 0, i))
            dbConnection.commit()
            log.debug("UPDATE")
    
def get_last_id_video(cam_id):
    take_video_id = requests.get(syno_url,
        params={'version': '6', 'cameraIds': cam_id, 'api': 'SYNO.SurveillanceStation.Recording',
                'toTime': '0', 'offset': '0', 'limit': '1', 'fromTime': '0', 'method': 'List', '_sid': syno_sid}).json()['data']['recordings'][0]['id']
    return take_video_id

def get_last_video(cam_id, video_id, offset):
    download = requests.get(syno_url + '/temp.mp4',
        params={'id': video_id, 'version': '6', 'mountId': '0', 'api': 'SYNO.SurveillanceStation.Recording',
                'method': 'Download', 'offsetTimeMs': offset, 'playTimeMs': '10000','_sid': syno_sid}, allow_redirects=True)
    open('/bot/'+str(cam_id)+'_'+str(video_id)+'.mp4', 'wb').write(download.content)
    return 

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
       log.info("Received IDCam: "+ cam_id + ', '+ time.strftime("%d.%m.%Y, %H:%M:%S", time.localtime()))
       time.sleep(5)
       last_video_id = get_last_id_video(cam_id)
       cursor.execute('SELECT old_last_video_id FROM CamVideo WHERE cam_id = ?', (cam_id,))
       old_last_video_id = cursor.fetchone()[0]
       if last_video_id != old_last_video_id:
           get_last_video(cam_id, last_video_id, '0')
           cursor.execute('UPDATE CamVideo SET old_last_video_id = ?, video_offset = ? WHERE cam_id = ?', (last_video_id, 0, cam_id))
           dbConnection.commit()
       else:
           cursor.execute('UPDATE CamVideo SET video_offset = video_offset + 10000 WHERE cam_id = ?', (cam_id))
           dbConnection.commit()
           cursor.execute('SELECT video_offset FROM CamVideo WHERE cam_id = ?', (cam_id,))
           video_offset = cursor.fetchone()[0]

           get_last_video(cam_id, last_video_id, video_offset)
       send_camvideo('/bot/'+str(cam_id) +'_'+str(last_video_id)+'.mp4',cam_id, str(last_video_id)+' offset: ' + str(video_offset))
       os.remove('/bot/'+str(cam_id) +'_'+str(last_video_id)+'.mp4')

       return 'success', 200
    else:
       abort(400)