#!/usr/bin/env python3

import argparse
import os
import queue
import sounddevice as sd
import vosk
import sys
import httpx
import requests
import json
from etherpad_lite import EtherpadLiteClient


MODEL_DIR = 'models'
MODEL_URL_JSON_PATH = 'etc/model_urls.json'
DEFAULT_ETHERPAD_API_KEY = 'myapikey'
DEFAULT_ETHERPAD_URL = 'http://localhost:9001'
ETHERPAD_API_VERSION = '1.2.13'
DEFAULT_PAD_ID = 'MIC2ETHER'
API_PUNKPROSE_URL = "http://api.collectivat.cat/punkProse"
NEWLINE_AFTER_EACH_RECOGNITION = False

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

def punctuate(text, lang, token):
    json_data = {'source':text,
                 'type':'text',
                 'lang':lang,
                 'recase':True,
                 'token':token}

    service_url = API_PUNKPROSE_URL
    result = text
    punctuation_successful = False

    try:
        r = httpx.post(service_url, json=json_data, timeout=None)
        if r.status_code == 200:
            punkProseResponse = r.json()
            result = punkProseResponse['result']
            punctuation_successful = True
        else:
            error = r

            print("Error while processing punctuation request.")
            print(error)
            try:
                print(r.json()['detail'])
            except:
                pass

    except httpx.HTTPError as exc:
        print(f"Error while requesting {exc.request.url!r}.")
        print(exc)

    return result, punctuation_successful

def translate(text, mt_translator, source_lang, target_lang):
    return mt_translator.translate(text,src=source_lang,dest=target_lang).text

def get_sentence_end_index(mystr, sentence_enders = ['.', '?']):
    end_indices = []
    for ender in sentence_enders:
        try:
            end_indices.append(mystr.rindex(ender))
        except:
            pass
    if not end_indices:
        return 0
    else:
        return max(end_indices)+1



parser = argparse.ArgumentParser(description="Dictation with Etherpad", add_help=False)
parser.add_argument('-a', '--list-audio-devices', action='store_true', help='show list of audio devices and exit')
args, remaining = parser.parse_known_args()
if args.list_audio_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser])
parser.add_argument('-x', '--outtxt', type=str, help='text file to store transcription to')
parser.add_argument('-m', '--model', type=str, metavar='MODEL_PATH', help='Path to the model')
parser.add_argument('-d', '--device', type=int_or_str, help='input device (numeric ID or substring)')
parser.add_argument('-r', '--samplerate', type=int, help='sampling rate')
parser.add_argument('-l', '--language', type=str, help='source language code')
parser.add_argument('-f', '--translatelang', type=str, help='translation language code')
parser.add_argument('-t', '--token', type=str, help='PunkProse token if sending to remote API')
parser.add_argument('-u', '--url', type=str, help='Etherpad base URL (default: %s)'%DEFAULT_ETHERPAD_URL, default=DEFAULT_ETHERPAD_URL)
parser.add_argument('-k', '--apikey', type=str, help='Etherpad API key (default: %s)'%DEFAULT_ETHERPAD_API_KEY, default=DEFAULT_ETHERPAD_API_KEY)
parser.add_argument('-p', '--padid', type=str, help='Etherpad pad ID to write to (default: %s)'%DEFAULT_PAD_ID, default=DEFAULT_PAD_ID)
parser.add_argument('-s', '--shortcuts', type=str, help='Path to shortcuts JSON file')

if __name__ == "__main__":
    args = parser.parse_args(remaining)

    model_path = args.model
    token = args.token
    lang = args.language
    translate_lang = args.translatelang
    out_txt = args.outtxt
    etherpad_api_key = args.apikey
    etherpad_api_url = args.url + '/api'
    pad_id = args.padid
    shortcuts_json_path = args.shortcuts

    try:
        MODEL_URL_DICT = json.load(open(MODEL_URL_JSON_PATH, 'r'))
    except Exception as e:
        print(e)
        print("ERROR: Couldn't read model url json at %s"%MODEL_URL_JSON_PATH)
        sys.exit()

    if not model_path:
        if not lang:
            print("ERROR: Neither model path nor language code given.")
            sys.exit()
        if lang and lang in MODEL_URL_DICT:
            model_path = os.path.join(MODEL_DIR, os.path.splitext(MODEL_URL_DICT[lang].split("/")[-1])[0])
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

    inverted_shortcuts = {}
    if args.shortcuts:
        try:
            with open(args.shortcuts, "r") as jsonfile:
                shortcuts_data = json.load(jsonfile)
            inverted_shortcuts = {v: k for k, v in shortcuts_data.items()}
            print(inverted_shortcuts)
        except Exception as e:
            print("ERROR: Couldn't read shortcuts file", args.shortcuts)
            print(e)

    if translate_lang:
        from googletrans import Translator
        mt_translator = Translator()

        translate_pad_id = pad_id + "_" + translate_lang

    try:
        print("PAD URL:", args.url + "/p/" + pad_id)
        c = EtherpadLiteClient(base_params={'apikey':etherpad_api_key}, api_version=ETHERPAD_API_VERSION, base_url=etherpad_api_url)
        if pad_id in c.listAllPads()['padIDs']:
            print("WARNING: Deleting content of pad with padID %s"%pad_id)
            c.setText(padID=pad_id, text='')
        else:
            print("Creating Pad with PadID %s"%pad_id)
            c.createPad(padID=pad_id, text='')

        if translate_lang:
            if translate_pad_id in c.listAllPads()['padIDs']:
                print("WARNING: Deleting content of pad with padID %s"%translate_pad_id)
                c.setText(padID=translate_pad_id, text='')
            else:
                print("Creating Pad for translation with PadID %s"%translate_pad_id)
                c.createPad(padID=translate_pad_id, text='')
    except Exception as e:
        print("Error connecting to Etherpad")
        parser.exit(type(e).__name__ + ': ' + str(e))

    #Start recognition
    try:
        model = vosk.Model(model_path)

        if out_txt:
            dump_fn = open(out_txt, "w")
        else:
            dump_fn = None

        with sd.RawInputStream(samplerate=args.samplerate, blocksize = 8000, device=args.device, dtype='int16',
                                channels=1, callback=callback):
            print('#' * 80)
            print('Press Ctrl+C to stop the recording')
            print('#' * 80)

            rec = vosk.KaldiRecognizer(model, args.samplerate)

            paragraph_over = False
            end=False
            curr_paragraph = []
            all_paragraphs = []
            while True:
                data = q.get()
                if rec.AcceptWaveform(data):
                    # print(rec.Result())
                    segment_result = json.loads(rec.Result())
                    if segment_result['text']:
                        #Check if it's a shortcut
                        if segment_result['text'] in inverted_shortcuts:
                            print('<' + inverted_shortcuts[segment_result['text']] + '>')

                            #Process command
                            if inverted_shortcuts[segment_result['text']] == 'NEWLINE':
                                c.appendText(padID=pad_id, text="\n")
                                paragraph_over=True
                                print("paragraph_over for NEWLINE")
                            elif inverted_shortcuts[segment_result['text']] == 'END':
                                paragraph_over=True
                                end=True
                        else:
                            print(segment_result['text'])
                            c.appendText(padID=pad_id, text=segment_result['text'])
                            if NEWLINE_AFTER_EACH_RECOGNITION:
                                c.appendText(padID=pad_id, text="\n")
                            else:
                                c.appendText(padID=pad_id, text=" ")
                            curr_paragraph.append(segment_result['text'])
                    elif curr_paragraph and not paragraph_over:
                        paragraph_over=True
                        print("paragraph_over cuz text empty")
                        print(curr_paragraph)

                    if token and paragraph_over and curr_paragraph:
                        #get the text as it is from the pad
                        all_text = c.getText(padID=pad_id)['text']
                        sentence_ends_at = get_sentence_end_index(all_text)
                        already_punctuated = all_text[0:sentence_ends_at]
                        yet_to_punctuate = all_text[sentence_ends_at:]

                        #punctuate current paragraph
                        to_punc = ' '.join(yet_to_punctuate.split('\n'))
                        print("Sending to punc:", to_punc)
                        punctuated_paragraph_plain, status = punctuate(to_punc, lang, token)
                        plain_token_index = 0

                        #set the whole pad to all_paragraphs
                        text_to_set = ''
                        if already_punctuated:
                            text_to_set += already_punctuated + '\n'
                        text_to_set += punctuated_paragraph_plain + '\n\n'
                        c.setText(padID=pad_id, text=text_to_set)

                        #translate current paragraph
                        if translate_lang:
                            all_translated_text = c.getText(padID=translate_pad_id)['text'].strip()

                            translated_paragraph_plain = translate(punctuated_paragraph_plain, mt_translator, lang, translate_lang)
                            text_to_set = ''
                            if all_translated_text:
                                text_to_set += all_translated_text + '\n'
                            text_to_set += translated_paragraph_plain + '\n\n'
                            c.setText(padID=translate_pad_id, text=text_to_set)

                        paragraph_over = False
                        curr_paragraph = []
                    if end:
                        break

            if dump_fn is not None:
                dump_fn.write('\n'.join(all_paragraphs))
                dump_fn.close()

    except KeyboardInterrupt:
        print('\nDone')
        parser.exit(0)
    except Exception as e:
        parser.exit(type(e).__name__ + ': ' + str(e))
