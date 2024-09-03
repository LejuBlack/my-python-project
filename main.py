import discord
from discord.ext import commands
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Updated FFMPEG options to reduce lag
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn -c:a libopus -b:a 128k -f opus'
}

YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist': True}

# Spotify credentials (replace with your own client ID and secret)
SPOTIFY_CLIENT_ID = "350af28d36534383b7554d5d453fafd0"
SPOTIFY_CLIENT_SECRET = "21bfc613e74d475ba8cafa37cac77bad"

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))

class MusicBot(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.queue = []
        self.loop = False
        self.current = None
        self.paused = False
        self.suggest = False
        self.base_track = None  # To track the base track for suggestions

    @commands.command(name='W', aliases=['w'])
    async def play(self, ctx, *, arg=None):
        if not arg:
            return await ctx.send("Please provide a song name, YouTube URL, 'pause', 'play', 'stop', 'loop', 'suggest', 'next', or a Spotify track link.")

        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return await ctx.send("You're not in a voice channel!")

        if not ctx.voice_client:
            try:
                await voice_channel.connect()
            except discord.ClientException:
                return await ctx.send("Already connected to a voice channel!")

        lower_arg = arg.lower()

        if lower_arg == "pause":
            await self.pause(ctx)
        elif lower_arg == "play":
            await self.resume(ctx)
        elif lower_arg == "stop":
            await self.stop(ctx)
        elif lower_arg == "loop":
            self.loop = not self.loop
            status = "enabled" if self.loop else "disabled"
            await ctx.send(f"Looping {status} 🔁")
        elif lower_arg == "suggest":
            self.suggest = not self.suggest
            status = "enabled" if self.suggest else "disabled"
            await ctx.send(f"Suggestions {status} 🎵")
        elif lower_arg == "next":
            await self.skip(ctx)
        elif "youtube.com" in lower_arg or "youtu.be" in lower_arg:
            await self.play_url(ctx, arg)
        elif "spotify.com" in lower_arg:
            await self.play_spotify(ctx, arg)
        else:
            await self.play_spotify_search(ctx, arg)

    async def play_url(self, ctx, url):
        async with ctx.typing():
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if 'entries' in info:
                        info = info['entries'][0]
                    title = info['title']
                    artist = info.get('artist', 'Unknown Artist')
                    url = info['url']
                    self.queue.append((url, title, artist))
                    
                    # Set the base track if this is the first track
                    if not self.current:
                        self.base_track = title
                    
                    await ctx.send(f"🎵 Added to queue: **{title}** by **{artist}**")
                    
                    # Send YouTube GIF
                    youtube_gif_path = 'YouTube-Logo-Animation.gif'
                    if os.path.isfile(youtube_gif_path):
                        await ctx.send(file=discord.File(youtube_gif_path))
                    else:
                        await ctx.send("YouTube GIF file not found.")
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

        if not ctx.voice_client.is_playing():
            await self.play_next(ctx)

    async def play_spotify_search(self, ctx, search_query):
        async with ctx.typing():
            try:
                result = sp.search(q=search_query, type='track', limit=1)
                if result['tracks']['items']:
                    track = result['tracks']['items'][0]
                    track_name = track['name']
                    artist_name = track['artists'][0]['name']
                    preview_url = track.get('preview_url')
                    
                    if preview_url:
                        self.queue.append((preview_url, track_name, artist_name))
                        await ctx.send(f"🎵 Added to queue: **{track_name}** by **{artist_name}**")
                    else:
                        await ctx.send(f"No preview available for **{track_name}** by **{artist_name}** on Spotify.")
                    
                    # Send Spotify GIF
                    spotify_gif_path = 'Spotify-Logo-Animation.gif'
                    if os.path.isfile(spotify_gif_path):
                        await ctx.send(file=discord.File(spotify_gif_path))
                    else:
                        await ctx.send("Spotify GIF file not found.")
                    
                    if not ctx.voice_client.is_playing():
                        await self.play_next(ctx)
                else:
                    await ctx.send(f"No matching track found on Spotify for: {search_query}")
            except Exception as e:
                await ctx.send(f"An error occurred while searching for the track on Spotify: {e}")

    async def play_spotify(self, ctx, url):
        async with ctx.typing():
            try:
                result = sp.track(url)
                track_name = result['name']
                artist_name = result['artists'][0]['name']
                preview_url = result.get('preview_url')

                if preview_url:
                    self.queue.append((preview_url, track_name, artist_name))
                    await ctx.send(f"🎵 Added to queue: **{track_name}** by **{artist_name}**")
                    
                    # Send Spotify GIF
                    spotify_gif_path = 'Spotify-Logo-Animation.gif'
                    if os.path.isfile(spotify_gif_path):
                        await ctx.send(file=discord.File(spotify_gif_path))
                    else:
                        await ctx.send("Spotify GIF file not found.")
                else:
                    await ctx.send(f"No preview available for **{track_name}** by **{artist_name}** on Spotify.")

                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
            except Exception as e:
                await ctx.send(f"An error occurred while trying to play the track: {e}")

    async def play_next(self, ctx):
        try:
            if self.loop and self.current:
                url, title, artist = self.current
            else:
                if not self.queue:
                    await ctx.send("Queue is empty!")
                    if self.suggest:
                        await self.suggest_and_play(ctx)
                    return
                url, title, artist = self.queue.pop(0)
                self.current = (url, title, artist)
                
            source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
            
            if not ctx.voice_client:
                return
            
            ctx.voice_client.play(source, after=lambda _: self.client.loop.create_task(self.play_next(ctx)))
            await ctx.send(f"🎵 Now playing: **{title}** by **{artist}**")
        except Exception as e:
            print(f"Error playing next track: {e}")
            await ctx.send(f"An error occurred while trying to play the next track: {e}")

    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            self.paused = True
            await ctx.send("Paused ⏸")
        else:
            await ctx.send("Nothing is playing to pause!")

    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            self.paused = False
            await ctx.send("Resumed ▶️")
        else:
            await ctx.send("Nothing paused to resume!")

    async def stop(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            self.queue.clear()
            self.loop = False
            self.current = None
            self.base_track = None
            await ctx.voice_client.disconnect()
            await ctx.send("Stopped and disconnected from the voice channel ⏹")
        else:
            await ctx.send("I'm not connected to a voice channel!")

    async def clear_queue_and_disconnect(self, ctx):
        self.queue.clear()
        self.loop = False
        self.current = None
        self.base_track = None
        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()

    async def suggest_and_play(self, ctx):
        if not self.base_track:
            await ctx.send("No base track to generate suggestions.")
            return

        try:
            results = sp.search(q=self.base_track, type='track', limit=1)
            if results['tracks']['items']:
                track_id = results['tracks']['items'][0]['id']
                recommendations = sp.recommendations(seed_tracks=[track_id], limit=5)
                for track in recommendations['tracks']:
                    track_name = track['name']
                    artist_name = track['artists'][0]['name']
                    search_query = f"{track_name} {artist_name}"
                    await self.play_spotify_search(ctx, search_query)
        except Exception as e:
            await ctx.send(f"Failed to fetch or play suggestions: {e}")

    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped ⏭")
        else:
            await ctx.send("Nothing is playing to skip!")

client = commands.Bot(command_prefix="!", intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}!')
    activity = discord.Streaming(name="WSmrt-Inf", url="https://twitch.tv/streamer")
    await client.change_presence(activity=activity)

@client.event
async def on_disconnect():
    print('Bot disconnected.')
    for guild in client.guilds:
        voice_client = guild.voice_client
        if voice_client:
            music_bot = client.get_cog('MusicBot')
            if music_bot:
                ctx = await client.get_context(guild.text_channels[0])
                await music_bot.clear_queue_and_disconnect(ctx)

@client.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        print(f"{member} connected to {after.channel}")
    elif before.channel is not None and after.channel is None:
        print(f"{member} disconnected from {before.channel}")
        if member == client.user:
            music_bot = client.get_cog('MusicBot')
            if music_bot:
                ctx = await client.get_context(before.channel.guild.text_channels[0])
                await music_bot.clear_queue_and_disconnect(ctx)

async def main():
    try:
        await client.add_cog(MusicBot(client))
        await client.start("MTI2MDE3OTY2OTA5ODAzNzI0OQ.G0OvKf.zV9bGomPSG_9CrmZRXoqLQA-5q_NKlFldP4T5Q")
    except discord.errors.HTTPException as e:
        if e.status == 429:
            retry_after = int(e.response.headers.get('Retry-After', 0))
            print(f"Rate limited. Retrying after {retry_after} seconds.")
            await asyncio.sleep(retry_after)
            await main()
    except Exception as e:
        print(f"Unexpected error: {e}")
        await asyncio.sleep(5)
        await main()

asyncio.run(main())
