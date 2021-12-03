#!/usr/bin/env python3

import argparse
import os
import queue
import sounddevice as sd
import vosk
import sys
import json
from etherpad_lite import EtherpadLiteClient

MODEL_DIR = 'models'
MODEL_PATH_DICT = { 'en':'models/vosk-model-small-en-us-0.15', 
                    'tr':'models/vosk-model-small-tr-0.3', 
                    'ca':'models/vosk-model-small-ca-0.4', 
                    'es':'models/vosk-model-small-es-0.3'}

MODEL_URL_DICT = {'en': 'http://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip', 
                  'ca': 'https://alphacephei.com/vosk/models/vosk-model-small-ca-0.4.zip', 
                  'tr': 'https://alphacephei.com/vosk/models/vosk-model-small-tr-0.3.zip',
                  'es': 'https://alphacephei.com/vosk/models/vosk-model-small-es-0.3.zip'}

DEFAULT_ETHERPAD_API_KEY = 'myapikey'
DEFAULT_ETHERPAD_URL = 'http://localhost:9001'
ETHERPAD_API_VERSION = '1.2.13'
DEFAULT_PAD_ID = 'MIC2ETHER'

q = queue.Queue()

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text

def callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


parser = argparse.ArgumentParser(description="Dictation with Etherpad", add_help=False)
parser.add_argument('-a', '--list-audio-devices', action='store_true', help='show list of audio devices and exit')
args, remaining = parser.parse_known_args()
if args.list_audio_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser])
parser.add_argument('-w', '--outwav', type=str, help='audio file to store recording to')
parser.add_argument('-x', '--outtxt', type=str, help='text file to store transcription to')
parser.add_argument('-m', '--model', type=str, metavar='MODEL_PATH', help='Path to the model')
parser.add_argument('-d', '--device', type=int_or_str, help='input device (numeric ID or substring)')
parser.add_argument('-r', '--samplerate', type=int, help='sampling rate')
parser.add_argument('-l', '--language', type=str, help='language code %s'%list(MODEL_URL_DICT.keys()))
parser.add_argument('-t', '--token', type=str, help='PunkProse token if sending to remote API')
parser.add_argument('-u', '--url', type=str, help='Etherpad base URL (default: %s)'%DEFAULT_ETHERPAD_URL, default=DEFAULT_ETHERPAD_URL)
parser.add_argument('-k', '--apikey', type=str, help='Etherpad API key (default: %s)'%DEFAULT_ETHERPAD_API_KEY, default=DEFAULT_ETHERPAD_API_KEY)
parser.add_argument('-p', '--padid', type=str, help='Etherpad pad ID to write to (default: %s)'%DEFAULT_PAD_ID, default=DEFAULT_PAD_ID)

if __name__ == "__main__":    
    args = parser.parse_args(remaining)

    model_path = args.model
    token = args.token
    lang = args.language
    out_wav = args.outwav
    out_txt = args.outtxt
    etherpad_api_key = args.apikey
    etherpad_api_url = args.url + '/api'
    pad_id = args.padid

    if not model_path:
        if not lang:
            print("ERROR: Neither model path nor language code given.")
            sys.exit()
        if lang and lang in MODEL_PATH_DICT:
            model_path = MODEL_PATH_DICT[lang]
            if not os.path.exists(model_path):
                print("Model for language %s not found. I will download it."%lang)
                if not os.path.exists(MODEL_DIR):
                    os.mkdir(MODEL_DIR)

                #Download model
                import requests
                import zipfile
                path_to_zip_file = model_path + '.zip'
                if not os.path.exists(path_to_zip_file):
                    print("Model URL:", MODEL_URL_DICT[lang])
                    r = requests.get(MODEL_URL_DICT[lang])
                    if r.status_code == 200:
                        with open(path_to_zip_file, 'wb') as f:
                            f.write(r.content)

                with zipfile.ZipFile(path_to_zip_file, 'r') as zip_ref:
                    zip_ref.extractall(MODEL_DIR)
        else:
            print("ERROR: Language %s not in MODEL_PATH_DICT. Either add there or manually specify model directory (-m)."%lang)
            sys.exit()

    if not lang:
        print("WARNING: Language not specified (-l). Will skip punctuation.")

    if not token:
        print("WARNING: No PunkProse API token (-t) specified. If service is not found locally, punctuation will be skipped.")

    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        # soundfile expects an int, sounddevice provides a float:
        args.samplerate = int(device_info['default_samplerate'])


    try:
        c = EtherpadLiteClient(base_params={'apikey':etherpad_api_key}, api_version=ETHERPAD_API_VERSION, base_url=etherpad_api_url)
        if pad_id in c.listAllPads()['padIDs']:
            print("WARNING: Deleting content of pad with padID %s"%pad_id)
            c.setText(padID=pad_id, text='')
        else:
            print("Creating Pad with PadID %s"%pad_id)
            c.createPad(padID=pad_id, text='')

    except Exception as e:
        print("Error connecting to Etherpad")
        parser.exit(type(e).__name__ + ': ' + str(e))

    #Start recognition
    try:
        model = vosk.Model(model_path)

        if out_wav:
            dump_fn = open(out_wav, "wb")
        else:
            dump_fn = None

        with sd.RawInputStream(samplerate=args.samplerate, blocksize = 8000, device=args.device, dtype='int16',
                                channels=1, callback=callback):
            print('#' * 80)
            print('Press Ctrl+C to stop the recording')
            print('#' * 80)

            rec = vosk.KaldiRecognizer(model, args.samplerate)

            in_paragraph = False
            while True:
                data = q.get()
                if rec.AcceptWaveform(data):
                    # print(rec.Result())
                    segment_result = json.loads(rec.Result())
                    if segment_result['text']:
                        print(segment_result['text'])
                        c.appendText(padID=pad_id, text=segment_result['text'] + " ")
                        in_paragraph=True
                    elif in_paragraph:
                        print("")
                        c.appendText(padID=pad_id, text="\n")
                        in_paragraph=False

                # else:
                #     print(rec.PartialResult())
                if dump_fn is not None:
                    dump_fn.write(data)

    except KeyboardInterrupt:
        print('\nDone')
        parser.exit(0)
    except Exception as e:
        parser.exit(type(e).__name__ + ': ' + str(e))
