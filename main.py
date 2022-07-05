import functools
import nextcord
from nextcord.ext import commands
import youtube_dl
from pytube import YouTube, exceptions
import requests
import random
import json
import os
from dotenv import load_dotenv
import asyncio
import time

load_dotenv(".env")
intents = nextcord.Intents.all()
client = commands.Bot(command_prefix="-", intents=intents, case_insensitive=True)

ydl_opts = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'youtube_include_dash_manifest': False,
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

queue = []
start_task = False
current_track = 0
stream_errors = 0
loop_type = 0
ref_time = time.time()
pause_time = 0
seek_time = 0
embed_icon = "https://music.youtube.com/img/favicon_144.png"
embed_colour = 0xff0000
version = "Alpha-Danielle V0.1.0.5"
stream = ()


@client.event
async def on_ready():
    print("\033[0m Bot is ready...")
    await client.change_presence(activity=nextcord.Game(name=version))


@client.event
async def on_voice_state_update(member, before, after):
    vc_connection = nextcord.utils.get(client.voice_clients, guild=member.guild)

    global seek_time, current_track, stream_errors, pause_time
    if before.channel is not None and before.channel != after.channel:
        if member == client.user:
            if pause_time:
                seek_time = pause_time - ref_time - 1
            else:
                seek_time = time.time() - ref_time - 1
                pause_time = time.time() - 1
            stream_errors = -2
            if seek_time < 0 or not queue:
                seek_time = 0
                pause_time = 0
            await client.change_presence(activity=nextcord.Game(name=version))
        elif member != client.user and vc_connection:
            if before.channel == vc_connection.channel and len(vc_connection.channel.members) == 1:
                seek_time = time.time() - ref_time
                if pause_time:
                    seek_time = pause_time - ref_time - 1
                else:
                    seek_time = time.time() - ref_time - 1
                    pause_time = time.time() -1
                stream_errors = -2
                if seek_time < 0 or not queue:
                    seek_time = 0
                    pause_time = 0
                await vc_connection.disconnect(force=True)
                await client.change_presence(activity=nextcord.Game(name=version))


async def check_voice(ctx):
    if ctx.author.voice:
        vc = ctx.author.voice.channel
    else:
        return await ctx.reply("You must be in a voice channel to use music commands")

    # Connect to requester's VC, unless already connected
    try:
        vc_connection = await vc.connect()
    except nextcord.errors.ClientException:
        vc_connection = nextcord.utils.get(client.voice_clients, guild=ctx.guild)

    # Check if requester in different VC and if there are other users in the original
    if vc_connection.channel != vc:
        if len(vc_connection.channel.members) <= 1:
            await vc_connection.move_to(ctx.author.voice.channel)
        else:
            return await ctx.reply("You must be in MY voice channel, where everyone is at to use music commands")

    return vc_connection


async def vc_manners(ctx, vc_connection):
    if nextcord.utils.get(ctx.guild.roles, name="DJ") in ctx.author.roles:
        return True

    if current_track >= len(queue) or current_track < 0:
        return True
    requester = queue[current_track]["Requester"]
    if requester == ctx.author.mention:
        return True
    elif len(vc_connection.channel.members) <= 2:
        return True

    return False


def time_convert(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if secs < 10:
        secs = f"0{int(secs)}"
    if mins >= 60:
        hours = int(mins // 60)
        mins = int(mins % 60)
        if mins < 10:
            mins = f"0{int(mins)}"
        return f"{hours}:{mins}:{secs}"
    else:
        return f"{mins}:{secs}"


def loop_gui():
    if loop_type == 1:
        return "🔂 | "
    elif loop_type == 2:
        return "🔁 | "
    else:
        return ""


@client.listen()
async def on_message(msg):
    if not msg.author.bot:
        if ("matl" in msg.content.lower() or "material" in msg.content.lower()) and msg.author.voice:
            # Connect the bot to VC
            try:
                vc = msg.author.voice.channel
                vc_connection = await vc.connect()
            except nextcord.errors.ClientException:
                vc_connection = nextcord.utils.get(client.voice_clients, guild=msg.guild)

            if not vc_connection.is_playing():
                vc_connection.play(nextcord.FFmpegPCMAudio(
                    source="MATLS.mp3"))


@client.command()
async def play(ctx, *, search=""):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return

    global current_track

    current_loop = asyncio.get_running_loop()
    if search:
        # Extract Playlist Meta Data
        ydl_opts["extract_flat"] = True
        if "list=" in search and "youtube.com/" in search:
            await ctx.reply(f":globe_with_meridians: Getting URL For: `{search}`")
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    partial = functools.partial(ydl.extract_info, search, download=False)
                    meta = await current_loop.run_in_executor(None, partial)
                if "title" not in meta:
                    raise youtube_dl.DownloadError
                elif "_type" in meta and meta["_type"] == "url":
                    return await ctx.reply("**InvalidPlaylist:** This autogenerated playlist is not supported")
            except youtube_dl.DownloadError:
                return await ctx.reply(f"**InvalidPlaylist:** Check your URL")

        # Extract Video Meta Data
        elif "youtube.com/watch?v=" in search:
            # For partial to work
            def get_meta(vid):
                return {'id': vid.video_id, 'title': vid.title, 'duration': vid.length}
            try:
                yt = YouTube(search)
                await ctx.reply(f":globe_with_meridians: Getting URL For: `{search}`")
                partial = functools.partial(get_meta, yt)
                meta = await current_loop.run_in_executor(None, partial)
            except exceptions.RegexMatchError:
                return await ctx.reply(f"**InvalidPlaylist:** Check your URL ")
        # Extract Search Meta Data
        else:
            # For partial to work
            await ctx.reply(f":mag: Searching For: `{search}`")
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                partial = functools.partial(ydl.extract_info, f"ytsearch:{search}", download=False)
                meta = await current_loop.run_in_executor(None, partial)
                meta = meta['entries'][0]

        # Queue tracks
        len_q_old = len(queue)
        try:
            if meta["_type"] == "playlist":
                queue.extend(meta["entries"])
            else:
                raise KeyError
        # Not Playlist
        except KeyError:
            queue.append(meta)

        # Add additional Information
        for track in range(len_q_old, len(queue)):
            queue[track]["Requester"] = ctx.author.mention
            queue[track]["Thumbnail URL"] = f"https://i.ytimg.com/vi/{queue[track]['id']}/hqdefault.jpg"

        # Play tracks now, unless already playing
        if vc_connection.is_connected() and not vc_connection.is_playing() and not vc_connection.is_paused():
            if current_track > len(queue) - 1:
                current_track = 0
            await filter_formats(current_track)
            await load_track(ctx, vc_connection, current_track)

        # Post Processing. Notice it comes after playing the track? EFFICIENCY
        nq_thumb_url = queue[len_q_old]["Thumbnail URL"]
        try:
            if meta["_type"] == "playlist":
                # Embed
                nq_embed = nextcord.Embed(
                    description=f'{loop_gui()}**[{meta["title"]}](https://www.youtube.com/playlist?list={meta["id"]})**'
                                f'\n**Track #{len(queue) - len(meta["entries"])} - {len(queue) - 1}**\n'
                                f'\n**Total Queued:** {len(meta["entries"])}\n'
                                f'**Tracks Ahead:** {len(queue) - len(meta["entries"]) - current_track}',
                                colour=embed_colour)
                nq_embed.set_author(name=f"➕ Adding Playlist to Queue ➕",
                                    icon_url=embed_icon)
                partial = functools.partial(requests.get, f"https://music.youtube.com/playlist?list={meta['id']}")
                source = await current_loop.run_in_executor(None, partial)
                source = source.text
                marker = source.find("https://yt3.ggpht.com/") + 22
                if marker != 21:
                    nq_thumb_url = f"https://yt3.ggpht.com/{source[marker:marker + 100]}"
                    nq_thumb_url = nq_thumb_url[:nq_thumb_url.find('=')]
            else:
                raise KeyError
        # Not playlist
        except KeyError:
            # Embed
            nq_embed = nextcord.Embed(
                description=f'{loop_gui()}**[{meta["title"]}](https://www.youtube.com/watch?v={meta["id"]})**\n\n'
                            f'**Track #{len(queue) - 1}**\n'
                            f'**Tracks Ahead:** {len(queue) - 1 - current_track}',
                            colour=embed_colour)
            nq_embed.set_author(name="➕ Adding track to Queue ➕",
                                icon_url=embed_icon)

        nq_embed.set_thumbnail(url=nq_thumb_url)
        await ctx.send(embed=nq_embed)

        # await asyncio.sleep(2)
        # Start caching future tracks
        # for track in range(len_q_old, len(queue)):
        #    await filter_formats(track)

    elif queue:
        # Attempted error correction for the psychos who manually disconnects bot often
        if not vc_connection.is_connected():
            await vc_connection.disconnect(force=True)
            vc_connection = await check_voice(ctx)
        # Allows easy replay access
        if not vc_connection.is_playing() and not vc_connection.is_paused():
            if current_track > len(queue) - 1:
                current_track = 0
            await auto_next(ctx)
        else:
            await pause(ctx)


async def filter_formats(track: int):
    ydl_opts["extract_flat"] = False
    if "formats" not in str(queue[track]):
        current_loop = asyncio.get_running_loop()
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            partial = functools.partial(
                ydl.extract_info, f"https://www.youtube.com/watch?v={queue[track]['id']}", download=False)
            track_meta = await current_loop.run_in_executor(None, partial)
            queue[track]["formats"] = track_meta["formats"]

    if isinstance((queue[track]["formats"]), list):
        index = 0
        for i, formats in enumerate(queue[track]["formats"]):
            if formats["ext"] == "m4a":
                index = i
                break
        queue[track]["formats"] = queue[track]["formats"][index]["url"]


async def load_track(ctx, vc_connection, track: int):
    global ref_time, stream_errors, pause_time, stream

    stream_link = queue[track]["formats"]
    ffmpeg_opts = {"before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_time}"}
    vc_connection.play(nextcord.FFmpegPCMAudio(source=stream_link, **ffmpeg_opts),
                       after=lambda e: print(e) if e else asyncio.run_coroutine_threadsafe(auto_next(ctx), client.loop))

    if stream_errors == -2:
        ref_time = time.time() - pause_time + ref_time
        pause_time = 0
        stream_errors = 0
        if queue:
            await ctx.send(":floppy_disk: Attempting to load previous session...")
            await now(ctx)
    else:
        ref_time = time.time() - seek_time

    stream = (queue[track]['title'], f"https://www.youtube.com/watch?v={queue[track]['id']})")
    await client.change_presence(activity=nextcord.Streaming(
        name=stream[0], url=stream[1]))

    # TEST
    with open("test.json", "w") as file:
        json.dump(queue, file, indent=4)


async def auto_next(ctx):
    vc_connection = nextcord.utils.get(client.voice_clients, guild=ctx.guild)
    global current_track, stream_errors, seek_time

    # Detect Errors Pass 1
    if stream_errors == -2 or stream_errors == -1:
        pass
    elif time.time() - ref_time < queue[current_track]["duration"] - 1:
        stream_errors += 1
    else:
        stream_errors = 0

    if stream_errors == 0:
        seek_time = 0

    # Detect Errors Pass 2
    if stream_errors == -1:
        stream_errors = 0
    elif time.time() - ref_time < queue[current_track]["duration"]-1 or stream_errors == -2:
        pass

    if stream_errors > 2:
        current_track += 1
        await filter_formats(current_track)
        await load_track(ctx, vc_connection, current_track)
        return await ctx.send(f"Track failed to play. Count = {stream_errors} times.")
    elif stream_errors > 0:
        queue[current_track].pop("formats")
        print("Probably Error 403: Expired Links")
        await filter_formats(current_track)
        await load_track(ctx, vc_connection, current_track)
        # Remove future tracks' links
        if current_track + 1 < len(queue):
            for track in range(current_track + 1, len(queue)):
                if "formats" in queue[track]:
                    queue[track].pop("formats")
            return

    # No Errors
    if loop_type != 1 and stream_errors != -2 and not seek_time:
        await skip(ctx)
    if current_track + 1 <= len(queue):
        await filter_formats(current_track)
        await load_track(ctx, vc_connection, current_track)
    elif loop_type == 2:
        current_track = 0
        await filter_formats(current_track)
        await load_track(ctx, vc_connection, current_track)
    else:
        await client.change_presence(activity=nextcord.Game(name=version))


@client.command(aliases=["dc", "disconnect", "kys"])
async def leave(ctx):
    vc_connection = nextcord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc_connection:
        if len(vc_connection.channel.members) <= 1:
            pass
        elif vc_connection.channel != ctx.author.voice.channel:
            return await ctx.reply("You must be in MY voice channel where everyone is at to use music commands")
        await ctx.reply("Sayonara!")
        global current_track, stream_errors
        stream_errors = -2
        await vc_connection.disconnect(force=True)
    else:
        await ctx.reply("I already left >:(")


@client.command(aliases=["resume"])
async def pause(ctx):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return

    global ref_time, pause_time, current_track
    if not vc_connection.is_playing() and not vc_connection.is_paused():
        if current_track > len(queue) - 1:
            current_track = 0
        await filter_formats(current_track)
        await load_track(ctx, vc_connection, current_track)
        return

    if vc_connection.is_paused():
        await ctx.reply(":arrow_forward: Resumed!")
        ref_time = time.time() - pause_time + ref_time
        pause_time = 0
        await client.change_presence(activity=nextcord.Streaming(
            name=stream[0], url=stream[1]))
        vc_connection.resume()
    elif not queue:
        await ctx.reply(":x: Nothing to pause.")
    else:
        await ctx.reply(":pause_button: Paused!")
        pause_time = time.time()
        await client.change_presence(activity=nextcord.Game(name=version))
        vc_connection.pause()


@client.command(aliases=["next"])
async def skip(ctx):
    command = ctx.invoked_with
    global current_track, stream_errors, seek_time
    if command == "next" or command == "skip":
        vc_connection = await check_voice(ctx)
        if isinstance(vc_connection, nextcord.message.Message):
            return
        if not await vc_manners(ctx, vc_connection):
            return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

        if current_track + 1 >= len(queue):
            await ctx.reply("No more tracks in queue.")
        else:
            track_info = queue[current_track + 1]
            await ctx.reply(f":fast_forward: Skipping track to `Track #{current_track + 1}` | "
                            f"[{track_info['title']}]")
            # (https://www.youtube.com/watch?v={track_info['id']})
        if loop_type == 1:
            current_track += 1
        stream_errors = -1
        vc_connection.stop()
    elif current_track < len(queue):
        current_track += 1
    seek_time = 0


@client.command(aliases=["queue"])
async def q(ctx):
    if current_track+1 > len(queue)-1:
        return await ctx.reply("Nothing in queue")

    # Embed Description
    next10 = current_track+11
    q_desc = f''
    if next10 > len(queue):
        next10 = len(queue)
    for index, track_info in enumerate(queue[current_track+1:next10]):
        q_desc += f'**Track #{index+current_track+1}** | '\
                 f'[{track_info["title"]}](https://www.youtube.com/watch?v={track_info["id"]})\n'\
                 f'... `Requested By:` {track_info["Requester"]}\n\n'

    q_embed = nextcord.Embed(description=q_desc, colour=embed_colour)
    q_embed.set_author(name=f"🎶 Next 10 in Queue 🎶")

    # Embed Total Duration as Footer
    if pause_time:
        duration = pause_time - ref_time
    else:
        duration = time.time() - ref_time
    for track_info in queue[current_track+1:len(queue)]:
        duration += track_info["duration"]
    duration = time_convert(duration)
    q_embed.set_footer(text=f'Track #{current_track} / {len(queue)-1}'
                            f' | Tracks Left: {len(queue) - current_track} | Playtime Left: {duration}')
    await ctx.send(embed=q_embed)


@client.command()
async def clearq(ctx):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return
    if not await vc_manners(ctx, vc_connection):
        return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

    global current_track, seek_time
    await ctx.reply(":dvd: Clearing All Tracks!")
    queue.clear()
    current_track = 0
    seek_time = 0
    global stream_errors
    stream_errors = -1
    vc_connection.stop()
    await client.change_presence(activity=nextcord.Game(name=version))


@client.command()
async def prev(ctx):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return
    if not await vc_manners(ctx, vc_connection):
        return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

    global current_track, stream_errors, seek_time
    if current_track == 0:
        await ctx.reply("Nothing to backtrack.")
    else:
        track_info = queue[current_track - 1]
        await ctx.reply(f":rewind: Backtracking track to `Track #{current_track - 1}` | "
                        f"[{track_info['title']}]")
        # (https://www.youtube.com/watch?v={track_info['id']})
        stream_errors = -1
        current_track -= 2
        seek_time = 0
        if loop_type == 1:
            current_track += 1
        if vc_connection.is_playing():
            vc_connection.stop()
        else:
            await auto_next(ctx)


@client.command()
async def shuffle(ctx):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return
    if not await vc_manners(ctx, vc_connection):
        return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

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
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return
    if not await vc_manners(ctx, vc_connection):
        return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

    if not num:
        await ctx.reply("**Missing Argument:** `Track Number (int)`")
        return
    elif not num.isnumeric() and not (num.startswith("-") and num[1:].isnumeric()):
        await ctx.reply("**Unexpected Argument:** Expecting `Track Number (int)`")
        return

    num = int(num)
    global current_track, stream_errors, seek_time
    if num == current_track and queue:
        await ctx.reply("I'm playing that Track right now.")
    elif num > len(queue) - 1 or num < 0 or not queue:
        await ctx.reply("**OutOfBounds Argument:** The given `Track Number (int)` is out of range")
    else:
        track_info = queue[num]
        await ctx.reply(f"Switching to `Track #{num}` | "
                        f"[{track_info['title']}]")
        # (https: // www.youtube.com / watch?v={track_info['id']})
        current_track = num - 1
        stream_errors = -1
        seek_time = 0
        if vc_connection.is_playing():
            vc_connection.stop()
        else:
            await auto_next(ctx)


@client.command()
async def loop(ctx):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return

    global loop_type
    loop_type += 1
    if loop_type == 1:
        await ctx.reply(":repeat_one: Single tracks will be looped.")
    elif loop_type == 2:
        await ctx.reply(":repeat: Playlist will be looped.")
    if loop_type > 2:
        loop_type = 0
        await ctx.reply(":x: Loops turned off.")


@client.command(aliases=["np"])
async def now(ctx):
    vc_connection = nextcord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc_connection and (vc_connection.is_playing() or vc_connection.is_paused()):
        track_info = queue[current_track]
        duration = time_convert(round(track_info["duration"]))
        if pause_time:
            time_passed = time_convert(round(pause_time - ref_time))
            status_gui = "⏸️ Paused ⏸️"
        else:
            time_passed = time_convert(round(time.time() - ref_time))
            status_gui = "🎶 Now Playing 🎶"

        # Get Next track
        if current_track + 1 >= len(queue):
            next_track = "N/A"
        else:
            next_track = f'[{queue[current_track + 1]["title"]}](https://www.youtube.com/watch?v=' \
                         f'{queue[current_track + 1]["id"]})'

        # Embed
        np_embed = nextcord.Embed(
            description=f'{loop_gui()}**[{track_info["title"]}](https://www.youtube.com/watch?v={track_info["id"]})**\n'
                        f'**Track #{current_track}** | '
                        f'`{time_passed} / {duration}`\n\n**Requested By:** {track_info["Requester"]}\n'
                        f'**Up Next:** {next_track}', colour=embed_colour)
        np_embed.set_author(name=status_gui, icon_url=embed_icon)
        np_embed.set_thumbnail(url=track_info["Thumbnail URL"])
        await ctx.send(embed=np_embed)
    else:
        await ctx.reply("I'm not playing anything.")


@client.command()
async def remove(ctx, num=f""):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return
    if not await vc_manners(ctx, vc_connection):
        return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

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
                        f"[{track_info['title']}]")
        # (https://www.youtube.com/watch?v={track_info['id']})
        queue.pop(num)
        if num == current_track:
            global stream_errors
            stream_errors = -1
            vc_connection.stop()


@client.command()
async def seek(ctx, seek_t=""):
    vc_connection = await check_voice(ctx)
    if isinstance(vc_connection, nextcord.message.Message):
        return
    if not await vc_manners(ctx, vc_connection):
        return await ctx.reply("Your role is not a `DJ`, so let others enjoy the music too.")

    if not vc_connection.is_playing() and not vc_connection.is_paused():
        return await ctx.reply("Cannot seek without a video")

    global current_track, seek_time, stream_errors
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
    seek_time = secs
    stream_errors = -1
    vc_connection.stop()


@client.command()
async def load_test_case(ctx):
    global queue, current_track, seek_time, stream_errors
    with open("test2.json", "r") as file:
        queue = json.load(file)
    current_track = 1
    stream_errors = 0
    seek_time = 0

client.run(os.getenv("DISCORD_TOKEN"))
