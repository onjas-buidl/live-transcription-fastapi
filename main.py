from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Callable
from deepgram import Deepgram
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

dg_client = Deepgram(os.getenv('DEEPGRAM_API_KEY'))

templates = Jinja2Templates(directory="templates")

async def process_audio(fast_socket: WebSocket):
    def process_raw_output(data: dict) -> str:
        """
        Process raw output from Deepgram API to add speaker information.
        It should already be speech detected

        -------
        example output (with speaker):
        my_dict = {
        'type': 'Results',
        'channel_index': [0, 1],
        'duration': 1.3100004,
        'start': 9.04,
        'is_final': True,
        'speech_final': True,
        'channel': {
            'alternatives': [
                {
                    'transcript': "Hey How's it going?",
                    'confidence': 0.98657423,
                    'words': [
                        {'word': 'hey', 'start': 9.154706, 'end': 9.307647, 'confidence': 0.88753504, 'speaker': 0, 'punctuated_word': 'Hey'},
                        {'word': "how's", 'start': 9.384118, 'end': 9.537059, 'confidence': 0.9859679, 'speaker': 0, 'punctuated_word': "How's"},
                        {'word': 'it', 'start': 9.537059, 'end': 9.69, 'confidence': 0.98657423, 'speaker': 0, 'punctuated_word': 'it'},
                        {'word': 'going', 'start': 9.69, 'end': 9.842941, 'confidence': 0.99444866, 'speaker': 0, 'punctuated_word': 'going?'}
                    ]
                }
            ]
        },
        'metadata': {
            'request_id': '1bc06137-f685-45d4-95b1-72e30a3f6cc1',
            'model_info': {
                'name': 'general',
                'version': '2023-02-22.3',
                'arch': 'base'
            },
            'model_uuid': '96a295ec-6336-43d5-b1cb-1e48b5e6d9a4'
        }
    }

        """
        speakers_involved = [word['speaker'] for word in data['channel']['alternatives'][0]['words']]
        speaker_count = Counter(speakers_involved)
        top_speaker = speaker_count.most_common(1)[0][0]
        return f' [Speaker {top_speaker}] ' + data['channel']['alternatives'][0]['transcript']

    async def get_transcript(data: Dict) -> None:
        if 'channel' in data:
            # print(data)
            print(type(data))
            transcript = data['channel']['alternatives'][0]['transcript']
        
            if transcript:
                await fast_socket.send_text(process_raw_output(data))

    deepgram_socket = await connect_to_deepgram(get_transcript)

    return deepgram_socket


async def connect_to_deepgram(transcript_received_handler: Callable[[Dict], None]):
    try:
        socket = await dg_client.transcription.live({'punctuate': True, 'diarize': True, 'interim_results': False})
        socket.registerHandler(socket.event.CLOSE, lambda c: print(f'Connection closed with code {c}.'))
        socket.registerHandler(socket.event.TRANSCRIPT_RECEIVED, transcript_received_handler)
        
        return socket
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')
 
@app.get("/", response_class=HTMLResponse)
def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/listen")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        deepgram_socket = await process_audio(websocket) 

        while True:
            data = await websocket.receive_bytes()
            deepgram_socket.send(data)
    except Exception as e:
        raise Exception(f'Could not process audio: {e}')
    finally:
        await websocket.close()
