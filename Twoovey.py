import asyncio
from subprocess import call
import time
import discord
import os
os.add_dll_directory(r'C:\Program Files\VideoLAN\VLC')
import youtube_dl
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import urllib.parse as p
import pickle
from queue import PriorityQueue

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
YOUTUBE_PREFIX="https://www.youtube.com/watch?v="

from discord import message

class CustomClient(discord.Client):
    def __init__(self):
        super().__init__()
        self.queue_buffer = 100000
        self.queue_current = 0
        self.music_queue = PriorityQueue()
        self.playing = False
        self.voice_channel = None
        self.voice_connection = None
        self.now_playing = None
        self.youtube_credential_cache = None
    
    async def play(self, voice_connection):
        # 1 because the 0 is the weight of the value
        self.now_playing = self.music_queue.get()[1]
        filename = await YTDLSource.from_url(self.now_playing[0])
        voice_connection.play(discord.FFmpegPCMAudio(executable="C:/ffmpeg/bin/ffmpeg.exe", source=filename))
        if not voice_connection.is_playing():
            self.playing = False
            await self.play(self, voice_connection)

    def add_to_queue(self, entry):
        self.music_queue.put((self.queue_buffer - self.queue_current, entry))
        self.queue_current = self.queue_current+1

    def list_queue(self):
        result = ""
        dupe_queue = self.music_queue
        i=1
        if self.now_playing is not None:
            result = result + 'Now playing: {0}\n'.format(self.now_playing[1])
        while not dupe_queue.empty():
            next_item = dupe_queue.get()
            result = result + '{0} | {1}\n'.format(i, next_item[1][1])
            i = i+1
        return result

    async def join_voice(self, message):
        voice = message.author.voice
        if voice is None:
            await message.send(str(message.author.name) + " is not in a voice chat!")
            return None
        caller = voice.channel
        self.voice_channel = caller
        if self.voice_channel is not None and self.voice_channel != caller:
            await message.send("I'm already in another chat!")
        elif self.voice_channel is not None and self.voice_channel == caller:
            if self.voice_connection is None:
                self.voice_connection = await self.voice_channel.connect()
            return self.voice_connection

    async def on_ready(self):
        print('We have logged in as {0.user}'.format(super()))

    async def on_message(self, message):
        if message.author == self.user:
            return #ignore self

        voice_connection = await self.join_voice(message)
        if voice_connection is None:
            return

        print('Currently playing? {0}'.format(self.playing))
        if message.content.strip()=='-q':
            song_list = self.list_queue() or 'No songs queued!'
            await message.channel.send(song_list)

        if message.content.startswith('-q '):
            user_query = message.content[2:]
            data = get_youtube_data_from_query(user_query)
            self.youtube_credential_cache = data[2]
            self.add_to_queue(data[0:1])
            await message.channel.send('Adding a new song to the queue: {0}'.format(data[1]))
            if not self.playing:
                self.playing = True
                await self.play(voice_connection)
            await message.channel.send(data[1])

        if message.content.startswith('-skip'):
            self.voice_connection.stop()
            await self.play(voice_connection=voice_connection)


youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
        filename = data['title'] if stream else ytdl.prepare_filename(data)
        return filename

def get_youtube_data_from_query(query, cached_youtube_credential = None):
    youtube = cached_youtube_credential or youtube_authenticate()
    data = search(youtube, q=query, maxResults=1).get("items")[0]
    videoId = data["id"]["videoId"]
    print(videoId)
    title = data["snippet"]["title"]
    youtube_url = YOUTUBE_PREFIX + videoId

    return youtube_url, title, youtube

# TODO: this is eating my API limit for the day, need to refactor instead of reauthing every single fucking time
def youtube_authenticate():
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "youtube.json"
    creds = None
    # the file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    # if there are no (valid) credentials availablle, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)
        # save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build(api_service_name, api_version, credentials=creds)

def search(youtube, **kwargs):
    return youtube.search().list(
        part="snippet",
        **kwargs
    ).execute()

client = CustomClient()

client.run(os.getenv("DISCORD_TOKEN"))
