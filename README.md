# mic2etherpad
Voice dictation to Etherpad using VOSK microphone speech recognition

## Usage

```
usage: mic2ether.py [-h] [-a] [-x OUTTXT] [-m MODEL_PATH] [-d DEVICE]
                    [-r SAMPLERATE] [-l LANGUAGE] [-t TOKEN] [-u URL]
                    [-k APIKEY] [-p PADID] [-s SHORTCUTS]

optional arguments:
  -h, --help            show this help message and exit
  -a, --list-audio-devices
                        show list of audio devices and exit
  -x OUTTXT, --outtxt OUTTXT
                        text file to store transcription to
  -m MODEL_PATH, --model MODEL_PATH
                        Path to the model
  -d DEVICE, --device DEVICE
                        input device (numeric ID or substring)
  -r SAMPLERATE, --samplerate SAMPLERATE
                        sampling rate
  -l LANGUAGE, --language LANGUAGE
                        language code ['en', 'ca', 'tr', 'es']
  -t TOKEN, --token TOKEN
                        PunkProse token if sending to remote API
  -u URL, --url URL     Etherpad base URL (default: http://localhost:9001)
  -k APIKEY, --apikey APIKEY
                        Etherpad API key (default: myapikey)
  -p PADID, --padid PADID
                        Etherpad pad ID to write to (default: MIC2ETHER)
  -s SHORTCUTS, --shortcuts SHORTCUTS
                        Path to shortcuts JSON file
```

## Setup

1. Install and run [Etherpad](https://github.com/ether/etherpad-lite)
2. Note down the URL it's running (e.g. http://localhost:9001)
3. Note down the API key stored inside `APIKEY.txt` (or change it if you like)
4. Clone this repository: `git clone https://github.com/collectivat/mic2etherpad.git`
5. Enter in the directory: `cd mic2etherpad`
6. Install required python modules: `pip install -r requirements.txt`
7. (Optional) Obtain a PunkProseAPI token for punctuation

## Run

Simple run will download the model specified by language code and start microphone recognition to write to pad `http://0.0.0.0:9001/p/MIC2ETHER`

```
python mic2ether.py -l en 
```

You can download a [VOSK model](https://alphacephei.com/vosk/models) and specify its path instead of language code

```
python mic2ether.py -m my-vosk-model-path 
```

You can specify Etherpad URL, PadID and API key

```
python mic2ether.py -l en -u http://localhost:8080 -k my_secret_api_key -p my_awesome_pad
```

You can enable punctuation by specifying a PunkProseAPI key
```
python mic2ether.py -l en -t <my-punkprose-token>
```

## Voice shortcuts

You can specify key phrases that do specific actions in a JSON format shortcut file:

- `NEWLINE`: Key phrase for passing to a new line
- `END`: Key phrase to end recognition

To enable voice shortcuts, just specify the path to the json file:
```
python mic2ether.py -l en -s etc/shortcuts_en.json
```
