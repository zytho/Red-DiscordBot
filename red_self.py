from discord.ext import commands
from discord.ext.commands.bot import _get_variable
import discord
from cogs.utils.settings import Settings
from cogs.utils.dataIO import dataIO
from cogs.utils.chat_formatting import inline
import asyncio
import os
import time
import sys
import logging
import logging.handlers
import shutil
import traceback
import functools
from getpass import getpass

#
#  Red, a Discord bot by Twentysix, based on discord.py and its command extension
#                   https://github.com/Twentysix26/
#
#
# red.py and cogs/utils/checks.py both contain some modified functions originally made by Rapptz
#             https://github.com/Rapptz/RoboDanny/tree/async
#

DEFAULT_PREFIX = []
DELETE_PREFIX = 'd'  # Prepend prefix with this to delete trigger message
APPEND_PREFIX = 'a'  # prepend prefix with this to leave trigger message
EDIT_PREFIX = 's'  # default behavior, used in short

selfs = ['self,', 'self, ']
short_prefix = '!'
for pp in (DELETE_PREFIX, APPEND_PREFIX, EDIT_PREFIX):
    for p in selfs:
        if not p.startswith(pp):
            p = pp + p
        DEFAULT_PREFIX.append(p)
    DEFAULT_PREFIX.append(pp + short_prefix)


description = ("Red Selfbot - A multifunction Discord bot by Twentysix, "
               "modified by CalebJ to be run as a self-bot.")

formatter = commands.HelpFormatter(show_check_failure=False)

def inject_context(ctx, coro):
    @functools.wraps(coro)
    @asyncio.coroutine
    def wrapped(*args, **kwargs):
        _internal_channel = ctx.message.channel
        _internal_author = ctx.message.author
        _internal_context = ctx  # necessary modification

        try:
            ret = yield from coro(*args, **kwargs)
        except Exception as e:
            raise CommandInvokeError(e) from e
        return ret
    return wrapped

# Override inject_context function to pass full ctx
commands.core.inject_context = inject_context

class selfBot(commands.Bot):
    def say(self, content, *args, **kwargs):
        ctx = _get_variable('_internal_context')
        author = ctx.message.author
        destination = ctx.message.channel

        extensions = ('delete_after','delete_before')
        params = {k: kwargs.pop(k, None) for k in extensions}

        selfedit = (not ctx.prefix.startswith(APPEND_PREFIX) and
                    not ctx.message.edited_timestamp)
        selfdel = ctx.prefix.startswith(DELETE_PREFIX)

        if selfedit or selfdel:
            if selfdel:
                coro = asyncio.sleep(0)
                params['delete_before'] = ctx.message
            else:
                coro = self.edit_message(ctx.message, content)
        else:
            coro = self.send_message(destination, content, *args, **kwargs)
        return self._augmented_msg(coro, **params)

    # We can't reply to anyone but ourselves
    reply = say

    def upload(self, *args, **kwargs):
        ctx = _get_variable('_internal_context')
        author = ctx.message.author
        destination = ctx.message.channel

        extensions = ('delete_after','delete_before')
        params = {k: kwargs.pop(k, None) for k in extensions}

        selfedit = (not ctx.prefix.startswith(APPEND_PREFIX) and 
                    not ctx.message.edited_timestamp)
        selfdel = ctx.prefix.startswith(DELETE_PREFIX)

        if selfedit or selfdel:
            # can't edit when uploading, delete old instead
            params['delete_before'] = ctx.message
            if selfdel:
                # Why are we using delete on an upload? Hell if I know.
                coro = asyncio.sleep(0)
            else:
                coro = self.send_file(destination, *args, **kwargs)
        return self._augmented_msg(coro, **params)

    @asyncio.coroutine
    def _augmented_msg(self, coro, **kwargs):

        delete_before = kwargs.get('delete_before')
        if delete_before:
            yield from self.delete_message(delete_before)

        msg = yield from coro

        delete_after = kwargs.get('delete_after')
        if delete_after is not None:
            @asyncio.coroutine
            def delete():
                yield from asyncio.sleep(delete_after)
                yield from self.delete_message(msg)

            discord.compat.create_task(delete(), loop=self.loop)

        return msg

bot = selfBot(command_prefix=DEFAULT_PREFIX, formatter=formatter,
                   description=description, pm_help=False, self_bot=True, max_messages=32768)

settings = Settings()


@bot.event
async def on_ready():
    owner_cog = bot.get_cog('Owner')
    total_cogs = len(owner_cog._list_cogs())
    users = len(set(bot.get_all_members()))
    servers = len(bot.servers)
    channels = len([c for c in bot.get_all_channels()])
    if not hasattr(bot, "uptime"):
        bot.uptime = int(time.perf_counter())
    if settings.owner == "id_here":
        settings.owner = bot.user.id
    print('------')
    print("{}'s selfbot is now online.".format(bot.user.name))
    print('------')
    print("Connected to:")
    print("{} servers".format(servers))
    print("{} channels".format(channels))
    print("{} users".format(users))
    print("\n{}/{} active cogs with {} commands".format(
        len(bot.cogs), total_cogs, len(bot.commands)))
    prefix_label = "Prefixes:" if len(bot.command_prefix) > 1 else "Prefix:"
    print("{} {}\n".format(prefix_label, " ".join(bot.command_prefix)))
    await bot.get_cog('Owner').disable_commands()


@bot.event
async def on_command(command, ctx):
    pass

@bot.event
async def on_message(message):
    if user_allowed(message):
        await bot.process_commands(message)

@bot.event
async def on_command_error(error, ctx):
    if isinstance(error, commands.MissingRequiredArgument):
        await send_cmd_help(ctx)
    elif isinstance(error, commands.BadArgument):
        await send_cmd_help(ctx)
    elif isinstance(error, commands.DisabledCommand):
        await bot.send_message(ctx.message.channel,
            "That command is disabled.")
    elif isinstance(error, commands.CommandInvokeError):
        logger.exception("Exception in command '{}'".format(
            ctx.command.qualified_name), exc_info=error.original)
        oneliner = "Error in command '{}' - {}: {}".format(
            ctx.command.qualified_name, type(error.original).__name__,
            str(error.original))
        await ctx.bot.send_message(ctx.message.channel, inline(oneliner))
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        logger.exception(type(error).__name__, exc_info=error)

async def send_cmd_help(ctx):
    if ctx.invoked_subcommand:
        pages = bot.formatter.format_help_for(ctx, ctx.invoked_subcommand)
        for page in pages:
            await bot.send_message(ctx.message.channel, page)
    else:
        pages = bot.formatter.format_help_for(ctx, ctx.command)
        for page in pages:
            await bot.send_message(ctx.message.channel, page)


def user_allowed(message):
    return message.author.id == bot.user.id


def check_folders():
    folders = ("data", "data/red", "cogs", "cogs/utils")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_configs():
    if settings.bot_settings == settings.default_settings:
        print("Red selfbot - First run configuration\n")
        print("\nInsert your email or user session token:")

        choice = input("> ")

        if "@" not in choice and len(choice) >= 50:  # Assuming token
            settings.login_type = "token"
            settings.email = choice
        elif "@" in choice:
            settings.login_type = "email"
            settings.email = choice
            settings.password = getpass()
        else:
            os.remove('data/red/settings.json')
            input("Invalid input. Restart Red and repeat the configuration "
                  "process.")
            exit(1)

        #print("\Choose your prefix:")
        #confirmation = False
        #while confirmation is False:
            #new_prefix = ensure_reply("\nPrefix> ").strip()
            #print("\nAre you sure you want {0} as your prefix?\nYou "
                  #"will be able to issue commands like this: {0}help"
                  #"\nType yes to confirm or no to change it".format(new_prefix))
            #confirmation = get_answer()

        settings.prefixes = DEFAULT_PREFIX
        settings.owner = "id_here"

        print("\nThe configuration is done. Leave this window always open to keep "
              "Red online.\nAll commands will have to be issued through Discord's "
              "chat, *this window will now be read only*.")

    if not os.path.isfile("data/red/cogs.json"):
        print("Creating new cogs.json...")
        dataIO.save_json("data/red/cogs.json", {})

def set_logger():
    global logger
    logger = logging.getLogger("discord")
    logger.setLevel(logging.WARNING)
    handler = logging.FileHandler(
        filename='data/red/discord.log', encoding='utf-8', mode='a')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]"))
    logger.addHandler(handler)

    logger = logging.getLogger("red")
    logger.setLevel(logging.INFO)

    red_format = logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(red_format)
    stdout_handler.setLevel(logging.INFO)

    fhandler = logging.handlers.RotatingFileHandler(
        filename='data/red/red.log', encoding='utf-8', mode='a',
        maxBytes=10**7, backupCount=5)
    fhandler.setFormatter(red_format)

    logger.addHandler(fhandler)
    logger.addHandler(stdout_handler)

def ensure_reply(msg):
    choice = ""
    while choice == "":
        choice = input(msg)
    return choice

def get_answer():
    choices = ("yes", "y", "no", "n")
    c = ""
    while c not in choices:
        c = input(">").lower()
    if c.startswith("y"):
        return True
    else:
        return False

def set_cog(cog, value):
    data = dataIO.load_json("data/red/cogs.json")
    data[cog] = value
    dataIO.save_json("data/red/cogs.json", data)

def load_cogs():
    try:
        if sys.argv[1] == "--no-prompt":
            no_prompt = True
        else:
            no_prompt = False
    except:
        no_prompt = False

    try:
        registry = dataIO.load_json("data/red/cogs.json")
    except:
        registry = {}

    bot.load_extension('cogs.owner')
    owner_cog = bot.get_cog('Owner')
    if owner_cog is None:
        print("You got rid of the damn OWNER cog, it has special functions"
              " that I require to run.\n\n"
              "I can't start without it!")
        print()
        print("Go here to find a new copy:\n{}".format(
            "https://github.com/Twentysix26/Red-DiscordBot"))
        exit(1)

    failed = []
    extensions = owner_cog._list_cogs()
    for extension in extensions:
        if extension.lower() == "cogs.owner":
            continue
        in_reg = extension in registry
        if in_reg is False:
            if no_prompt is True:
                registry[extension] = False
                continue
            print("\nNew extension: {}".format(extension))
            print("Load it?(y/n)")
            if not get_answer():
                registry[extension] = False
                continue
            registry[extension] = True
        if not registry[extension]:
            continue
        try:
            owner_cog._load_cog(extension)
        except Exception as e:
            print("{}: {}".format(e.__class__.__name__, str(e)))
            logger.exception(e)
            failed.append(extension)
            registry[extension] = False

    if extensions:
        dataIO.save_json("data/red/cogs.json", registry)

    if failed:
        print("\nFailed to load: ", end="")
        for m in failed:
            print(m + " ", end="")
        print("\n")

    return owner_cog

def main():
    global settings

    check_folders()
    check_configs()
    set_logger()
    owner_cog = load_cogs()
    if settings.prefixes != []:
        bot.command_prefix = settings.prefixes
    else:
        print("No prefix set. Defaulting to " + short_prefix)
        bot.command_prefix = [short_prefix]
        print("Use !set prefix to set it.")
        owner_cog.owner.hidden = True  # Hides the set owner command from help
    print("-- Logging in.. --")
    if settings.login_type == "token":
        yield from bot.login(settings.email, bot = False)
    else:
        yield from bot.login(settings.email, settings.password)
    yield from bot.connect()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except discord.LoginFailure:
        logger.error(traceback.format_exc())
        choice = input("Invalid login credentials. "
            "If they worked before Discord might be having temporary "
            "technical issues.\nIn this case, press enter and "
            "try again later.\nOtherwise you can type 'reset' to "
            "delete the current configuration and redo the setup process "
            "again the next start.\n> ")
        if choice.strip() == "reset":
            shutil.copy('data/red/settings.json',
                        'data/red/settings-{}.bak'.format(int(time.time())))
            os.remove('data/red/settings.json')
    except:
        logger.error(traceback.format_exc())
        loop.run_until_complete(bot.logout())
    finally:
        loop.close()
