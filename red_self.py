import asyncio
import os
import time
import sys
import logging
import logging.handlers
import shutil
import traceback
import datetime
import functools
from getpass import getpass

try:
    assert sys.version_info >= (3, 5)
    from discord.ext import commands
    from discord.ext.commands.bot import _get_variable
    from discord.ext.commands.errors import CommandInvokeError
    import discord
except ImportError:
    print("Discord.py is not installed.\n"
          "Consult the guide for your operating system "
          "and do ALL the steps in order.\n"
          "https://twentysix26.github.io/Red-Docs/\n")
    sys.exit()
except AssertionError:
    print("Red needs Python 3.5 or superior.\n"
          "Consult the guide for your operating system "
          "and do ALL the steps in order.\n"
          "https://twentysix26.github.io/Red-Docs/\n")
    sys.exit()

from cogs.utils.settings import Settings
from cogs.utils.dataIO import dataIO
from cogs.utils.chat_formatting import inline
from collections import Counter


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
EDIT_PREFIX = 's'    # default behavior, used in short

selfs = ['self,', 'self, ']
short_prefix = '!'
for pp in (DELETE_PREFIX, APPEND_PREFIX, EDIT_PREFIX):
    for p in selfs:
        if not p.startswith(pp):
            p = pp + p
        DEFAULT_PREFIX.append(p)
    DEFAULT_PREFIX.append(pp + short_prefix)
DEFAULT_PREFIX = sorted(DEFAULT_PREFIX, reverse=True)


description = ("Red Selfbot - A multifunction Discord bot by Twentysix, "
               "modified by CalebJ to be run as a selfbot.")


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
    def __init__(self, *args, **kwargs):
        self.counter = Counter()
        self.uptime = datetime.datetime.now()
        self._message_modifiers = []
        self.settings = Settings()
        super().__init__(*args, **kwargs)

    def say(self, content=None, *args, **kwargs):
        ctx = _get_variable('_internal_context')
        destination = ctx.message.channel

        extensions = ('delete_after', 'delete_before')
        params = {k: kwargs.pop(k, None) for k in extensions}

        selfedit = (not ctx.prefix.startswith(APPEND_PREFIX) and
                    not ctx.message.edited_timestamp)
        selfdel = ctx.prefix.startswith(DELETE_PREFIX)

        if selfedit or selfdel:
            if selfdel:
                coro = asyncio.sleep(0)
                params['delete_before'] = ctx.message
            else:
                coro = self.edit_message(ctx.message, new_content=content,
                                         *args, **kwargs)
        else:
            coro = self.send_message(destination, content, *args, **kwargs)
        return self._augmented_msg(coro, **params)

    # We can't reply to anyone but ourselves
    reply = say

    def upload(self, *args, **kwargs):
        ctx = _get_variable('_internal_context')
        destination = ctx.message.channel

        extensions = ('delete_after', 'delete_before')
        params = {k: kwargs.pop(k, None) for k in extensions}

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

    async def send_message(self, *args, **kwargs):
        if self._message_modifiers:
            if "content" in kwargs:
                pass
            elif len(args) == 2:
                args = list(args)
                kwargs["content"] = args.pop()
            else:
                return await super().send_message(*args, **kwargs)

            content = kwargs['content']
            for m in self._message_modifiers:
                try:
                    content = str(m(content))
                except:   # Faulty modifiers should not
                    pass  # break send_message
            kwargs['content'] = content

        return await super().send_message(*args, **kwargs)

    def add_message_modifier(self, func):
        """
        Adds a message modifier to the bot

        A message modifier is a callable that accepts a message's
        content as the first positional argument.
        Before a message gets sent, func will get called with
        the message's content as the only argument. The message's
        content will then be modified to be the func's return
        value.
        Exceptions thrown by the callable will be catched and
        silenced.
        """
        if not callable(func):
            raise TypeError("The message modifier function "
                            "must be a callable.")

        self._message_modifiers.append(func)

    def remove_message_modifier(self, func):
        """Removes a message modifier from the bot"""
        if func not in self._message_modifiers:
            raise RuntimeError("Function not present in the message "
                               "modifiers.")

        self._message_modifiers.remove(func)

    def clear_message_modifiers(self):
        """Removes all message modifiers from the bot"""
        self._message_modifiers.clear()

    async def send_cmd_help(self, ctx):
        if ctx.invoked_subcommand:
            pages = bot.formatter.format_help_for(ctx, ctx.invoked_subcommand)
            for page in pages:
                await bot.send_message(ctx.message.channel, page)
        else:
            pages = bot.formatter.format_help_for(ctx, ctx.command)
            for page in pages:
                await bot.send_message(ctx.message.channel, page)

    def user_allowed(self, message):
        return message.author.id == bot.user.id


class Formatter(commands.HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _add_subcommands_to_page(self, max_width, commands):
        for name, command in sorted(commands, key=lambda t: t[0]):
            if name in command.aliases:
                # skip aliases
                continue

            entry = '  {0:<{width}} {1}'.format(name, command.short_doc,
                                                width=max_width)
            shortened = self.shorten(entry)
            self._paginator.add_line(shortened)


def prefix_manager(bot, message):
    """
    Returns prefixes of the message's server if set.
    If none are set or if the message's server is None
    it will return the global prefixes instead.

    Requires a Bot instance and a Message object to be
    passed as arguments.
    """
    return bot.settings.get_prefixes(message.server)


formatter = Formatter(show_check_failure=False)

bot = selfBot(command_prefix=prefix_manager, formatter=formatter,
              description=description, pm_help=False, self_bot=True, max_messages=8192)

send_cmd_help = bot.send_cmd_help  # Backwards
user_allowed = bot.user_allowed    # compatibility

settings = bot.settings


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
    prefix_label = "Prefixes:" if len(settings.prefixes) > 1 else "Prefix:"
    print("{} {}\n".format(prefix_label, " ".join(settings.prefixes)))
    await bot.get_cog('Owner').disable_commands()


@bot.event
async def on_command(command, ctx):
    bot.counter["processed_commands"] += 1


@bot.event
async def on_message(message):
    bot.counter["messages_read"] += 1
    if bot.user_allowed(message):
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


def run():
    global settings

    check_folders()
    check_configs()
    set_logger()
    owner_cog = load_cogs()
    if settings.prefixes == []:
        print("No prefix set. Defaulting to " + short_prefix)
        settings.prefixes = [short_prefix]
        print("Use !set prefix to set it.")
        owner_cog.owner.hidden = True  # Hides the set owner command from help
    print("-- Logging in.. --")
    if settings.login_type == "token":
        yield from bot.login(settings.email, bot=False)
    else:
        yield from bot.login(settings.email, settings.password)
    yield from bot.connect()


def main():
    error = False
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run())
    except discord.LoginFailure:
        error = True
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
    except KeyboardInterrupt:
        loop.run_until_complete(bot.logout())
    except:
        error = True
        logger.error(traceback.format_exc())
        loop.run_until_complete(bot.logout())
    finally:
        loop.close()
        if error:
            exit(1)


if __name__ == '__main__':
    main()
