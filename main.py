import functools

import discord
from discord.ext import commands, tasks
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

ydl_opts = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'extract_flat': False,
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'cachedir': False,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
    'force-ipv4': True,
}

queue = []
start_task = False
current_track = 0
loop_track = False
loop_list = False
ref_time = 0
pause_time = 0
seek_time = 0
embed_icon = "https://music.youtube.com/img/favicon_144.png"
embed_colour = 0xff0000


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
        return await ctx.reply("I don't wanna enter VC alone... :'(")

    # Connect the bot to VC
    try:
        vc = ctx.author.voice.channel
        vc_connection = await vc.connect()
    except discord.errors.ClientException:
        vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)

    global current_track
    if search:
        # Extract Meta Data
        ydl_opts["extract_flat"] = True
        current_loop = asyncio.get_running_loop()
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                partial = functools.partial(
                    ydl.extract_info, search, download=False)
                meta = await current_loop.run_in_executor(None, partial)
                await ctx.reply(f":white_check_mark: Exact Match Found For: `{search}`")
            except youtube_dl.utils.DownloadError:
                await ctx.reply(f":mag: Searching For: `{search}` ")
                partial = functools.partial(
                    ydl.extract_info, f"ytsearch:{search}", download=False)
                meta = await current_loop.run_in_executor(None, partial)
                meta = meta['entries'][0]

        # Enqueue tracks
        len_q_old = len(queue)
        try:
            if meta["_type"] == "playlist":
                queue.extend(meta["entries"])
            else:
                raise KeyError
        # Not Playlist
        except KeyError:
            queue.append(meta)

        # Play tracks now, unless already playing
        if not vc_connection.is_playing() and not vc_connection.is_paused():
            if current_track > len(queue) - 1:
                current_track = 0
            await filter_formats(current_track)
            load_track(ctx, vc_connection, current_track)

        # Post Processing. Notice it comes after playing the track? EFFICIENCY
        for track in range(len_q_old, len(queue)):
            queue[track]["Requester"] = ctx.author.mention
            queue[track]["Thumbnail URL"] = f"https://i.ytimg.com/vi/{queue[track]['id']}/hqdefault.jpg"

        nq_thumb_url = queue[len_q_old]["Thumbnail URL"]
        try:
            if meta["_type"] == "playlist":
                # Embed
                nq_embed = discord.Embed(
                    description=f'[**{meta["title"]}**](https://www.youtube.com/playlist?list={meta["id"]})\n'
                                f'**Track #{len(queue) - len(meta["entries"])} - {len(queue) - 1}**\n'
                                f'\n**Total Enqueued:** {len(meta["entries"])}\n'
                                f'**tracks Ahead:** {len(queue) - len(meta["entries"]) - current_track}',
                                colour=embed_colour)
                nq_embed.set_author(name="➕ Adding Playlist to Queue ➕",
                                    icon_url=embed_icon)
                req = requests.get(f"https://music.youtube.com/playlist?list={meta['id']}", "html.parser")
                source = req.text
                marker = source.find("https://yt3.ggpht.com/") + 22
                if marker != 21:
                    nq_thumb_url = f"https://yt3.ggpht.com/{source[marker:marker + 75]}"
            else:
                raise KeyError
        # Not playlist
        except KeyError:
            # Embed
            nq_embed = discord.Embed(
                description=f'[**{meta["title"]}**](https://www.youtube.com/watch?v={meta["id"]})\n\n'
                            f'**Track #{len(queue) - 1}**\n'
                            f'**tracks Ahead:** {len(queue) - 1 - current_track}',
                            colour=embed_colour)
            nq_embed.set_author(name="➕ Adding track to Queue ➕",
                                icon_url=embed_icon)

        nq_embed.set_thumbnail(url=nq_thumb_url)
        await ctx.send(embed=nq_embed)

        await asyncio.sleep(2)
        # Start caching future tracks
        for track in range(len_q_old, len(queue)):
            await filter_formats(track)

    else:
        if not vc_connection.is_playing() and not vc_connection.is_paused():
            if current_track > len(queue) - 1:
                current_track = 0
            await filter_formats(current_track)
            load_track(ctx, vc_connection, current_track)
        else:
            await pause(ctx)


async def filter_formats(track: int):
    print(track)
    ydl_opts["extract_flat"] = False
    if "formats" not in str(queue[track]):
        current_loop = asyncio.get_running_loop()
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            partial = functools.partial(
                ydl.extract_info, f"https://www.youtube.com/watch?v={queue[track]['id']}", download=False)
            track_meta = await current_loop.run_in_executor(None, partial)
            queue[track]["formats"] = track_meta["formats"]

    if isinstance((queue[track]["formats"]), list):
        for i, formats in enumerate(queue[track]["formats"]):
            if formats["ext"] == "m4a" and "manifest" not in str(formats):
                index = i
                queue[track]["formats"] = queue[track]["formats"][index]["url"]
                break


def load_track(ctx, vc_connection, track: int):
    global ref_time, seek_time
    stream_link = queue[track]["formats"]
    ffmpeg_opts = {"before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_time}"}
    vc_connection.play(discord.FFmpegPCMAudio(source=stream_link, **ffmpeg_opts),
                       after=lambda e: asyncio.run_coroutine_threadsafe(auto_next(ctx), client.loop))
    ref_time = time.time() - seek_time
    seek_time = 0


@client.command()
async def auto_next(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    global current_track, loop_track, loop_list

    if not loop_track:
        await skip(ctx)

    if current_track + 1 <= len(queue):
        await filter_formats(current_track)
        load_track(ctx, vc_connection, current_track)
    elif loop_list:
        current_track = 0
        await filter_formats(current_track)
        load_track(ctx, vc_connection, current_track)


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
    global ref_time, pause_time
    if vc_connection.is_paused():
        await ctx.reply(":arrow_forward: Resumed!")
        ref_time = time.time() - pause_time + ref_time
        pause_time = 0
        vc_connection.resume()
    else:
        await ctx.reply(":pause_button: Paused!")
        pause_time = time.time()
        vc_connection.pause()


@client.command(aliases=["next"])
async def skip(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    command = ctx.invoked_with.lower()
    global current_track
    if command == "next" or command == "skip":
        if current_track + 1 >= len(queue):
            await ctx.reply("No more tracks in queue.")
        else:
            track_info = queue[current_track + 1]
            await ctx.reply(f":fast_forward: Skipping track to `Track #{current_track + 1}` | "
                            f"[{track_info['title']}](https://www.youtube.com/watch?v={track_info['id']})")
        vc_connection.stop()
        if loop_track:
            current_track += 1
    elif current_track < len(queue):
        current_track += 1


@client.command()
async def q(ctx):
    # TEST
    print(current_track)
    with open("test.json", "w") as file:
        json.dump(queue, file, indent=4)
    await ctx.reply("In Development")


@client.command()
async def clearq(ctx):
    global current_track
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
        track_info = queue[current_track - 1]
        await ctx.reply(f":rewind: Backtracking track to `Track #{current_track - 1}` | "
                        f"[{track_info['title']}](https://www.youtube.com/watch?v={track_info['id']})")
        current_track -= 2
        if loop_track:
            current_track += 1
        if vc_connection.is_playing():
            vc_connection.stop()
        else:
            await auto_next(ctx)


@client.command()
async def shuffle(ctx):
    global queue
    if len(queue) - current_track + 1 >= 2:
        await ctx.reply(":twisted_rightwards_arrows: Queued tracks Shuffled!")
        queued_tracks = [queue[track] for track in range(current_track + 1, len(queue))]
        random.shuffle(queued_tracks)
        queue = queue[:current_track + 1]
        queue.extend(queued_tracks)
    else:
        await ctx.reply("Not enough stuff for a shuffle")


@client.command(aliases=["track"])
async def switch(ctx, num=""):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if not num:
        await ctx.reply("**Missing Argument:** `Track Number (int)`")
        return
    elif not num.isnumeric() and not (num.startswith("-") and num[1:].isnumeric()):
        await ctx.reply("**Unexpected Argument:** Expecting `Track Number (int)`")
        return

    num = int(num)
    global current_track
    if num == current_track:
        await ctx.reply("I'm playing that Track right now.")
    elif num > len(queue) - 1 or num < 0:
        await ctx.reply("**OutOfBounds Argument:** The given `Track Number (int)` is out of range")
    else:
        track_info = queue[num]
        await ctx.reply(f"Switching to `Track #{num}` | "
                        f"[{track_info['title']}](https://www.youtube.com/watch?v={track_info['id']})")
        current_track = num - 1
        vc_connection.stop()


@client.command()
async def loop(ctx, opt="track"):
    global loop_list, loop_track
    opt = opt.lower()
    if opt == "track":
        if loop_track:
            loop_track = False
            await ctx.reply(":repeat_one: Current track will not be looped :x:")
        else:
            loop_track = True
            await ctx.reply(":repeat_one: Current track will be looped :white_check_mark:")
    elif "list" in opt:
        if loop_list:
            loop_list = False
            await ctx.reply(":repeat: Playlist will not be looped :x:")
        else:
            loop_list = True
            await ctx.reply(":repeat: Playlist will be looped :white_check_mark:")
    else:
        await ctx.reply("I was expecting \"track\" or \"list\"")


@client.command(aliases=["np"])
async def now(ctx):
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc_connection.is_playing() or vc_connection.is_paused():
        track_info = queue[current_track]
        duration = time_convert(round(track_info["duration"]))
        time_passed = time_convert(round(time.time() - ref_time))

        # Get Next track
        if current_track + 1 >= len(queue):
            next_track = "N/A"
        else:
            next_track = f'[{queue[current_track + 1]["title"]}](https://www.youtube.com/watch?v=' \
                         f'{queue[current_track + 1]["id"]})'

        # Embed
        np_embed = discord.Embed(
            description=f'[**{track_info["title"]}**](https://www.youtube.com/watch?v={track_info["id"]})\n'
                        f'**Track #{current_track}** | '
                        f'`{time_passed} / {duration}`\n\n**Requested By:** {track_info["Requester"]}\n'
                        f'**Up Next:** {next_track}', colour=embed_colour)
        np_embed.set_author(name="🎶 Now Playing 🎶", icon_url=embed_icon)
        np_embed.set_thumbnail(url=track_info["Thumbnail URL"])
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
        track_info = queue[num]
        await ctx.reply(f"Removing `Track #{num}` | "
                        f"[{track_info['title']}](https://www.youtube.com/watch?v={track_info['id']})")
        queue.pop(num)
        if num == current_track:
            vc_connection.stop()


@client.command()
async def seek(ctx, seek_t=""):
    global current_track, seek_time
    vc_connection = discord.utils.get(client.voice_clients, guild=ctx.guild)

    time_decode = seek_t.split(":")
    multipliers = len(time_decode)
    for multiplier in range(multipliers):
        if not time_decode[multiplier].isnumeric():
            return await ctx.reply("**Unexpected Format:** Expecting `Seconds (int)` or `HH:MM:SS` or `MM:SS`")

    # Converts HH:MM:SS formats
    if multipliers == 1:
        secs = int(time_decode[0])
    elif multipliers == 2:
        secs = 60 * int(time_decode[0]) + int(time_decode[1])
    elif multipliers == 3:
        secs = 3600 * int(time_decode[0]) + 60 * int(time_decode[1]) + int(time_decode[2])
    else:
        return await ctx.reply("**Unexpected Format:** Expecting `Seconds (int)` or `HH:MM:SS` or `MM:SS`")

    await ctx.reply(f"Seeking to timestamp: `{seek_t}`")
    current_track -= 1
    seek_time = secs
    vc_connection.stop()


client.run(os.getenv("DISCORD_TOKEN"))
