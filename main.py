import discord
from discord.ext import commands
import youtube_dl
import requests
import random
import json
import os
from dotenv import load_dotenv
import asyncio
import time

load_dotenv(".env")
intents = discord.Intents.all()
client = commands.Bot(command_prefix="-", intents=intents, case_insensitive=True)

ydl_opts_flat = {
    'extract_flat': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'cachedir': False,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
    'force-ipv4': True
}

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'm4a',
        'preferredquality': '192', }],
    'extractaudio': True,
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'cachedir': False,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
    'force-ipv4': True
}

FFMPEG_opts = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': f'-vn -ss 0',
    }

queue = []
current_track = 0
loop_song = False
loop_list = False
ref_time = 0
seek_time = 0


@client.event
async def on_ready():
    print("\033[0m Bot is ready...")


def courtesy(ctx):
    requester = queue[current_track]["Requester"]
    if requester == ctx.author.mention:
        return True
    else:
        return False


def time_convert(seconds):
    mins = seconds // 60
    secs = seconds % 60
    if secs < 10:
        secs = f"0{secs}"
    if mins >= 60:
        hours = mins // 60
        mins = mins % 60
        return f"{hours}:{mins}:{secs}"
    else:
        return f"{mins}:{secs}"


@client.listen()
async def on_message(msg):
    if not msg.author.bot:
        if ("matl" in msg.content.lower() or "material" in msg.content.lower()) and msg.author.voice:
            # Connect the bot to VC
            try:
                vc = msg.author.voice.channel
                vc_connection = await vc.connect()
            except discord.errors.ClientException:
                vc_connection = discord.utils.get(client.voice_clients, guild=msg.guild)

            if not vc_connection.is_playing():
                vc_connection.play(discord.FFmpegPCMAudio(
                    source="MATLS.mp3"),
                    after=lambda e: asyncio.run_coroutine_threadsafe(vc_connection.disconnect(), client.loop))


@client.command(aliases=["play shuffle", "play next", "play now"])
async def play(ctx, *, search=""):
    # Check if requesting user in VC
    if not ctx.author.voice:
        await ctx.reply("I don't wanna enter VC alone... :'(")
        return

    # Connect the bot to VC
    try:
        vc = ctx.author.voice.channel
        vc_connection = await vc.connect()
    except discord.errors.ClientException:
        vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)

    global current_track
    if search:
        # Extract Meta Data
        with youtube_dl.YoutubeDL(ydl_opts_flat) as ydl:
            try:
                meta = ydl.extract_info(search, download=False)
                await ctx.reply(f":white_check_mark: Exact Match Found For: `{search}`")
            except youtube_dl.utils.DownloadError:
                await ctx.reply(f":mag: Searching For: `{search}` ")
                meta = ydl.extract_info(f"ytsearch:{search}", download=False)['entries'][0]

        # Enqueue Songs
        try:
            if meta["_type"] == "playlist":
                for entry in meta["entries"]:
                    entry["Requester"] = ctx.author.mention
                    entry["Thumbnail URL"] = f"https://i.ytimg.com/vi/{entry['id']}/hqdefault.jpg"
                queue.extend(meta["entries"])

                # Special Playlist Thumbnail Handler
                req = requests.get(f"https://music.youtube.com/playlist?list={meta['id']}", "html.parser")
                source = req.text
                marker = source.find("https://yt3.ggpht.com/") + 22
                if marker != -1:
                    nq_thumbnail_url = f"https://yt3.ggpht.com/{source[marker:marker + 75]}"
                else:
                    nq_thumbnail_url = f"https://i.ytimg.com/vi/{meta['entries'][0]['id']}/hqdefault.jpg"

                # Embed
                nq_embed = discord.Embed(description=
                                         f'[**{meta["title"]}**](https://www.youtube.com/playlist?list={meta["id"]})\n'
                                         f'\n**Total Enqueued:** {len(meta["entries"])}\n'
                                         f'**Track #s:** {len(queue)-len(meta["entries"])} - {len(queue)-1}\n'
                                         f'**Songs Ahead:** {len(queue)-len(meta["entries"])-current_track}')
                nq_embed.set_author(name="➕ Adding Playlist to Queue ➕",
                                    icon_url="https://music.youtube.com/img/favicon_144.png")
            else:
                raise KeyError
        except KeyError:
            meta["Requester"] = ctx.author.mention
            meta["Thumbnail URL"] = f"https://i.ytimg.com/vi/{meta['id']}/hqdefault.jpg"
            queue.append(meta)
            nq_thumbnail_url = meta["Thumbnail URL"]

            # Embed
            nq_embed = discord.Embed(description=
                                     f'[**{meta["title"]}**](https://www.youtube.com/watch?v={meta["id"]})\n\n'
                                     f'**Track #:** {len(queue) - 1}\n'
                                     f'**Songs Ahead:** {len(queue)-1 - current_track}')
            nq_embed.set_author(name="➕ Adding Song to Queue ➕",
                                icon_url="https://music.youtube.com/img/favicon_144.png")

        nq_embed.set_thumbnail(url=nq_thumbnail_url)
        await ctx.send(embed=nq_embed)

    # Play songs now, unless already playing
    if not vc_connection.is_playing():
        if current_track > len(queue)-1:
            current_track = 0
        await filter_formats(ctx, vc_connection)


async def filter_formats(ctx, vc_connection):
    global ref_time, seek_time
    FFMPEG_opts[f'options'] = f'-vn -ss {seek_time}'
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        song_meta = ydl.extract_info(
            f"https://www.youtube.com/watch?v={queue[current_track]['id']}",
            download=False)
        index = 0
        for i, formats in enumerate(song_meta["formats"]):
            if formats["ext"] == "m4a":
                index = i
                break
        stream_link = song_meta["formats"][index]["url"]

        with open("test2.json", "w") as file:
            json.dump(song_meta, file, indent=4)
        await ctx.send(index)

    vc_connection.play(discord.FFmpegPCMAudio(source=stream_link, **FFMPEG_opts),
                       after=lambda e: asyncio.run_coroutine_threadsafe(auto_next(ctx), client.loop))
    ref_time = time.time()
    seek_time = 0


@client.command()
async def auto_next(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    global current_track, loop_song, loop_list

    if not loop_song:
        await next(ctx)

    if current_track+1 <= len(queue):
        await filter_formats(ctx, vc_connection)
    elif loop_list:
        current_track = 0
        await filter_formats(ctx, vc_connection)


@client.command()
async def leave(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc_connection.is_connected():
        await ctx.reply("Sayonara!")
        await vc_connection.disconnect()
    else:
        await ctx.reply("I already left >:(")


@client.command()
async def pause(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc_connection.is_paused():
        await ctx.reply(":arrow_forward: Resumed!")
        vc_connection.resume()
    else:
        await ctx.reply(":pause_button: Paused!")
        vc_connection.pause()


@client.command()
async def next(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    global current_track
    if ctx.invoked_with.lower() == "next":
        if current_track >= len(queue):
            await ctx.reply("No more songs in queue.")
        else:
            await ctx.reply(":fast_forward: Skipping Songs!")
        vc_connection.stop()
        if loop_song:
            current_track += 1
    elif current_track < len(queue):
        current_track += 1


@client.command()
async def q(ctx):
    # TEST
    print(current_track)
    with open("test.json", "w") as file:
        json.dump(queue, file, indent=4)


@client.command()
async def clearq(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    await ctx.reply(":dvd: Clearing All Tracks!")
    queue.clear()
    vc_connection.stop()


@client.command()
async def prev(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    global current_track
    if current_track == 0:
        await ctx.reply("Nothing to backtrack.")
    else:
        await ctx.reply(":rewind: Backtracking Songs!")
        current_track -= 2
        if loop_song:
            current_track += 1
        if vc_connection.is_playing():
            vc_connection.stop()
        else:
            await auto_next(ctx)


@client.command()
async def shuffle(ctx):
    global queue
    if len(queue) - current_track+1 >= 2:
        await ctx.reply(":twisted_rightwards_arrows: Queued Songs Shuffled!")
        queued_songs = [queue[track] for track in range(current_track+1, len(queue))]
        random.shuffle(queued_songs)
        queue = queue[:current_track+1]
        queue.extend(queued_songs)
    else:
        await ctx.reply("Not enough stuff for a shuffle")


@client.command()
async def track(ctx, num=""):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if not num:
        await ctx.reply("**Missing Argument:** `Track Number (int)`")
        return
    elif not num.isnumeric() and not (num.startswith("-") and num[1:].isnumeric()):
        await ctx.reply("**Unexpected Argument:** Expecting `Track Number (int)`")
        return

    num = int(num)

    if num > len(queue)-1 or num < 0:
        await ctx.reply("**OutOfBounds Argument:** The given `Track Number (int)` is out of range")
    else:
        await ctx.reply(f"Switching to Track Number: `{num}`")
        global current_track
        current_track = num-1
        vc_connection.stop()


@client.command()
async def loop(ctx, opt="song"):
    global loop_list, loop_song
    opt = opt.lower()
    if opt == "song":
        if loop_song:
            loop_song = False
            await ctx.reply(":repeat_one: Current song will not be looped :x:")
        else:
            loop_song = True
            await ctx.reply(":repeat_one: Current song will be looped :white_check_mark:")
    elif "list" in opt:
        if loop_list:
            loop_list = False
            await ctx.reply(":repeat: Playlist will not be looped :x:")
        else:
            loop_list = True
            await ctx.reply(":repeat: Playlist will be looped :white_check_mark:")
    else:
        await ctx.reply("I was expecting \"song\" or \"list\"")


@client.command(aliases=["np"])
async def now(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc_connection.is_playing():
        song_info = queue[current_track]
        duration = time_convert(round(song_info["duration"]))
        time_passed = time_convert(round(time.time() - ref_time))

        # Get Next Song
        if current_track+1 >= len(queue):
            next_song = "N/A"
        else:
            next_song = f'[{queue[current_track+1]["title"]}](https://www.youtube.com/watch?v=' \
                        f'{queue[current_track+1]["id"]})'

        # Embed
        np_embed = discord.Embed(
            description=f'[**{song_info["title"]}**](https://www.youtube.com/watch?v={song_info["id"]})\n'
                        f'`{time_passed} / {duration}`\n\nRequested By: {song_info["Requester"]}\n'
                        f'Up Next: {next_song}')
        np_embed.set_author(name="🎶 Now Playing 🎶", icon_url="https://music.youtube.com/img/favicon_144.png")
        np_embed.set_thumbnail(url=song_info["Thumbnail URL"])
        await ctx.send(embed=np_embed)
    else:
        await ctx.reply("I'm not playing anything.")


@client.command()
async def remove(ctx, num=f""):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)

    if not num:
        num = len(queue) - 1
    elif not num.isnumeric() and not (num.startswith("-") and num[1:].isnumeric()):
        await ctx.reply("**Unexpected Argument:** Expecting `Track Number (int)`")
        return

    num = int(num)
    if num > len(queue) - 1 or num < 0:
        await ctx.reply("**OutOfBounds Argument:** The given `Track Number (int)` is out of range")
    else:
        await ctx.reply(f"Removing Track Number: `{num}`")
        queue.pop(num)
        if num == current_track:
            vc_connection.stop()


@client.command()
async def seek(ctx, seek_t=0):
    global current_track, seek_time
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    current_track -= 1
    seek_time = seek_t
    vc_connection.stop()


client.run(os.getenv("DISCORD_TOKEN"))
