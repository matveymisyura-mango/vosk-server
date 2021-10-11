#!/usr/bin/env python3

import json
import audioop
import os
import sys
import asyncio
import pathlib
import websockets
import concurrent.futures
import logging
from vosk import Model, SpkModel, KaldiRecognizer
from datetime import datetime


def process_chunk(rec, message):
    startsentese = False
    endsentese = False
    
    if message == '{"eof" : 1}':
        endsentese = True
        rec.FinalResult()
        return '{"partial":""}', startsentese, endsentese, True
    elif rec.AcceptWaveform(message):
        partsentense =  json.loads(rec.Result())
        if len(partsentense['text']) > 1:
            startsentese = True
            endsentese = True
        return '{"partial":""}', startsentese, endsentese, False
        #return rec.Result(), startsentese, endsentese, False
    else:
        partsentense =  json.loads(rec.PartialResult())
        if len(partsentense['partial']) < 1:
            return '{"partial":""}', startsentese, endsentese, False
        else:
            print('start sentence')
            startsentese = True
            return '{"partial":""}', startsentese, endsentese,False
		
		
		
async def recognize(websocket, path):
    global model
    global spk_model
    global args
    global loop
    global pool

    rec = None
    recfinal = None
    phrase_list = None
    sample_rate = args.sample_rate
    show_words = args.show_words
    max_alternatives = args.max_alternatives
    frames=[]
    logging.info('Connection from %s', websocket.remote_address);

    while True:

        message = await websocket.recv()

        # Load configuration if provided
        if isinstance(message, str) and 'config' in message:
            jobj = json.loads(message)['config']
            logging.info("Config %s", jobj)
            if 'phrase_list' in jobj:
                phrase_list = jobj['phrase_list']
            if 'sample_rate' in jobj:
                sample_rate = float(jobj['sample_rate'])
            if 'words' in jobj:
                show_words = bool(jobj['words'])
            if 'max_alternatives' in jobj:
                max_alternatives = int(jobj['max_alternatives'])
            continue

        # Create the recognizer, word list is temporary disabled since not every model supports it
        if not rec:
            if phrase_list:
                rec = KaldiRecognizer(model, sample_rate, json.dumps(phrase_list, ensure_ascii=False))
            else:
                rec = KaldiRecognizer(model, sample_rate)
            rec.SetWords(show_words)
            rec.SetMaxAlternatives(max_alternatives)
            if spk_model:
                rec.SetSpkModel(spk_model)
        # Create the recognizer, word list is temporary disabled since not every model supports it
        if not recfinal:
            if phrase_list:
                recfinal = KaldiRecognizer(model, sample_rate, json.dumps(phrase_list, ensure_ascii=False))
            else:
                recfinal = KaldiRecognizer(model, sample_rate)
            recfinal.SetWords(show_words)
            recfinal.SetMaxAlternatives(max_alternatives)
            if spk_model:
                recfinal.SetSpkModel(spk_model)

        

        if message != '{"eof" : 1}':
            # left channel
            leftchaneldata = audioop.tomono(message, 2, 1, 0)
            # right channel
            #newaudiodata = audioop.tomono(message, 2, 0, 1)
        
        response, startsentese, endsentese, stop = await loop.run_in_executor(pool, process_chunk, rec, leftchaneldata)

        frames.append(leftchaneldata)

            
        #await websocket.send(response)
        if endsentese == True:
            logging.info('Start recognition frase ' + str(datetime.now()));
            audiodata = b''.join(frames)
            if recfinal.AcceptWaveform(audiodata):
                result = recfinal.Result()
            else:
                result = recfinal.FinalResult()
            await websocket.send(result)
            recfinal.Reset()
            frames.clear()
            logging.info('End recognition frase ' + str(datetime.now())); 
            logging.info('Recognition result ' + str(json.loads(result)['text']));  
        else:
            await websocket.send(response)

        #if startsentese == False:
        #    frames.clear()
          
        # if end the streem stop recognition streem
        if stop:
            break




def start():

    global model
    global spk_model
    global args
    global loop
    global pool

    # Enable loging if needed
    #
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logging.basicConfig(level=logging.INFO,
                    handlers=[logging.FileHandler("ASR_local.log", encoding='utf-8', mode='w'), stream_handler])

    args = type('', (), {})()

    args.interface = os.environ.get('VOSK_SERVER_INTERFACE', '0.0.0.0')
    args.port = int(os.environ.get('VOSK_SERVER_PORT', 2701))
    args.model_path = os.environ.get('VOSK_MODEL_PATH', 'model')
    args.spk_model_path = os.environ.get('VOSK_SPK_MODEL_PATH')
    args.sample_rate = float(os.environ.get('VOSK_SAMPLE_RATE', 8000))
    args.max_alternatives = int(os.environ.get('VOSK_ALTERNATIVES', 0))
    args.show_words = bool(os.environ.get('VOSK_SHOW_WORDS', True))

    if len(sys.argv) > 1:
       args.model_path = sys.argv[1]

    # Gpu part, uncomment if vosk-api has gpu support
    #
    # from vosk import GpuInit, GpuInstantiate
    # GpuInit()
    # def thread_init():
    #     GpuInstantiate()
    # pool = concurrent.futures.ThreadPoolExecutor(initializer=thread_init)

    model = Model(args.model_path)
    spk_model = SpkModel(args.spk_model_path) if args.spk_model_path else None

    pool = concurrent.futures.ThreadPoolExecutor((os.cpu_count() or 1))
    loop = asyncio.get_event_loop()

    start_server = websockets.serve(
        recognize, args.interface, args.port)

    logging.info("Listening on %s:%d", args.interface, args.port)
    loop.run_until_complete(start_server)
    loop.run_forever()


if __name__ == '__main__':
    start()
