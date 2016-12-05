import asyncio
import os
import time
import sys
import logging
import logging.handlers
import shutil
import traceback
import datetime

try:
    assert sys.version_info >= (3, 5)
    from discord.ext import commands
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
# Red, a Discord bot by Twentysix, based on discord.py and its command
#                             extension.
#
#                   https://github.com/Twentysix26/
#
#
# red.py and cogs/utils/checks.py both contain some modified functions
#                     originally made by Rapptz.
#
#                 https://github.com/Rapptz/RoboDanny/
#

description = "Red - A multifunction Discord bot by Twentysix"


class RedBot(commands.Bot):
    def __init__(self, *args, **kwargs):

        def prefix_manager(bot, message):
            """
            Returns prefixes of the message's server if set.
            If none are set or if the message's server is None
            it will return the global prefixes instead.

            Requires a Bot instance and a Message object to be
            passed as arguments.
            """
            return bot.settings.get_prefixes(message.server)

        self.counter = Counter()
        self.uptime = datetime.datetime.now()
        self._message_modifiers = []
        self.settings = Settings()

        super().__init__(*args, command_prefix=prefix_manager, **kwargs)

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
            pages = self.formatter.format_help_for(ctx, ctx.invoked_subcommand)
            for page in pages:
                await self.send_message(ctx.message.channel, page)
        else:
            pages = self.formatter.format_help_for(ctx, ctx.command)
            for page in pages:
                await self.send_message(ctx.message.channel, page)

    def user_allowed(self, message):
        author = message.author

        if author.bot or author == self.user:
            return False

        mod = self.get_cog('Mod')

        if mod is not None:
            if self.settings.owner == author.id:
                return True
            if not message.channel.is_private:
                server = message.server
                names = (self.settings.get_server_admin(
                    server), self.settings.get_server_mod(server))
                results = map(
                    lambda name: discord.utils.get(author.roles, name=name),
                    names)
                for r in results:
                    if r is not None:
                        return True

            if author.id in mod.blacklist_list:
                return False

            if mod.whitelist_list:
                if author.id not in mod.whitelist_list:
                    return False

            if not message.channel.is_private:
                if message.server.id in mod.ignore_list["SERVERS"]:
                    return False

                if message.channel.id in mod.ignore_list["CHANNELS"]:
                    return False
            return True
        else:
            return True


class RedFormatter(commands.HelpFormatter):
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


class RedCore:
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger

    async def on_ready(self):
        owner_cog = self.bot.get_cog('Owner')
        loaded_cogs = len([c for c in self.bot.cogs if c != 'RedCore'])
        total_cogs = len(owner_cog._list_cogs())
        users = len(set(self.bot.get_all_members()))
        servers = len(self.bot.servers)
        channels = len([c for c in self.bot.get_all_channels()])

        if self.bot.settings.login_type == "token" \
                and self.bot.settings.owner == "id_here":
            await self._set_bot_owner()

        print('------')
        print("{} is now online.".format(self.bot.user.name))
        print('------')
        print("Connected to:")
        print("{} servers".format(servers))
        print("{} channels".format(channels))
        print("{} users".format(users))
        print("\n{}/{} active cogs with {} commands".format(
              loaded_cogs, total_cogs, len(self.bot.commands)))
        prefixes = self.bot.settings.prefixes
        prefix_label = "Prefixes:" if len(prefixes) > 1 else "Prefix:"
        print("{} {}\n".format(prefix_label, " ".join(prefixes)))

        if self.bot.settings.login_type == "token":
            print("------")
            print("Use this url to bring your bot to a server:")
            url = await self._get_oauth_url()
            self.bot.oauth_url = url
            print(url)
            print("------")
        await self.bot.get_cog('Owner').disable_commands()

    async def on_command(self, command, ctx):
        self.bot.counter["processed_commands"] += 1

    async def on_message(self, message):
        self.bot.counter["messages_read"] += 1

    async def on_command_error(self, error, ctx):
        channel = ctx.message.channel
        if isinstance(error, commands.MissingRequiredArgument):
            await self.bot.send_cmd_help(ctx)

        elif isinstance(error, commands.BadArgument):
            await self.bot.send_cmd_help(ctx)

        elif isinstance(error, commands.DisabledCommand):
            await self.bot.send_message(channel, "That command is disabled.")

        elif isinstance(error, commands.CommandInvokeError):
            self.logger.exception("Exception in command '{}'".format(
                ctx.command.qualified_name), exc_info=error.original)
            oneliner = "Error in command '{}' - {}: {}".format(
                ctx.command.qualified_name, type(error.original).__name__,
                str(error.original))
            await self.bot.send_message(channel, inline(oneliner))

        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        elif isinstance(error, commands.NoPrivateMessage):
            await self.bot.send_message(channel, "That command is not "
                                        "available in DMs.")
        else:
            self.logger.exception(type(error).__name__, exc_info=error)

    async def _get_oauth_url(self):
        try:
            data = await self.bot.application_info()
        except Exception as e:
            return "Couldn't retrieve invite link.Error: {}".format(e)
        return discord.utils.oauth_url(data.id)

    async def _set_bot_owner(self):
        try:
            data = await self.bot.application_info()
            self.bot.settings.owner = data.owner.id
        except Exception as e:
            print("Couldn't retrieve owner's ID. Error: {}".format(e))
            return
        print("{} has been recognized and set as owner.".format(data.owner))


def check_folders():
    folders = ("data", "data/red", "cogs", "cogs/utils")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def setup_wizard(settings):
    print("Red - First run configuration\n")
    print("If you haven't already, create a new account:\n"
          "https://twentysix26.github.io/Red-Docs/red_guide_bot_accounts/"
          "#creating-a-new-bot-account")
    print("and obtain your bot's token like described.")
    print("\nInsert your bot's token:")

    choice = input("> ")

    if "@" not in choice and len(choice) >= 50:  # Assuming token
        settings.login_type = "token"
        settings.email = choice
    elif "@" in choice:
        settings.login_type = "email"
        settings.email = choice
        settings.password = input("\nPassword> ")
    else:
        os.remove('data/red/settings.json')
        input("Invalid input. Restart Red and repeat the configuration "
              "process.")
        exit(1)

    print("\nChoose a prefix. A prefix is what you type before a command."
          "\nA typical prefix would be the exclamation mark.\n"
          "Can be multiple characters. You will be able to change it "
          "later and add more of them.\nChoose your prefix:")
    confirmation = False
    while confirmation is False:
        new_prefix = ensure_reply("\nPrefix> ").strip()
        print("\nAre you sure you want {0} as your prefix?\nYou "
              "will be able to issue commands like this: {0}help"
              "\nType yes to confirm or no to change it".format(
                new_prefix))
        confirmation = get_answer()

    settings.prefixes = [new_prefix]
    if settings.login_type == "email":
        print("\nOnce you're done with the configuration, you will have to"
              " type '{}set owner' *in Discord's chat*\nto set yourself as"
              " owner.\nPress enter to continue".format(new_prefix))
        settings.owner = input("")  # Shh, they will never know it's here
        if settings.owner == "":
            settings.owner = "id_here"
        if not settings.owner.isdigit() or len(settings.owner) < 17:
            if settings.owner != "id_here":
                print("\nERROR: What you entered is not a valid ID. Set "
                      "yourself as owner later with {}set owner".format(
                          new_prefix))
            settings.owner = "id_here"
    else:
        settings.owner = "id_here"

    print("\nInput the admin role's name. Anyone with this role in Discord"
          " will be able to use the bot's admin commands")
    print("Leave blank for default name (Transistor)")
    settings.default_admin = input("\nAdmin role> ")
    if settings.default_admin == "":
        settings.default_admin = "Transistor"

    print("\nInput the moderator role's name. Anyone with this role in"
          " Discord will be able to use the bot's mod commands")
    print("Leave blank for default name (Process)")
    settings.default_mod = input("\nModerator role> ")
    if settings.default_mod == "":
        settings.default_mod = "Process"

    print("\nThe configuration is done. Leave this window always open to"
          " keep Red online.\nAll commands will have to be issued through"
          " Discord's chat, *this window will now be read only*.\nPress"
          " enter to continue")
    input("\n")


def get_logger():
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
    return logger


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


def load_cogs(bot, logger, prompt=False):
    try:
        registry = dataIO.load_json("data/red/cogs.json")
    except:
        registry = {}

    bot.load_extension('cogs.owner')
    owner_cog = bot.get_cog('Owner')
    if owner_cog is None:
        print("You got rid of the damn OWNER cog, it has special functions"
              " that I require to run.\n\n"
              "I can't start without it!\n")
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
            if not prompt:
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


def login(bot):
    settings = bot.settings
    if settings.login_type == "token":
        yield from bot.login(settings.email)
    else:
        yield from bot.login(settings.email, settings.password)
    yield from bot.connect()


def start_bot(loop, bot, logger, login=login):
    error = False
    try:
        loop.run_until_complete(login(bot))
    except discord.LoginFailure:
        error = True
        logger.error(traceback.format_exc())
        choice = input("Invalid login credentials. "
                       "If they worked before Discord might be having "
                       "temporary technical issues.\nIn this case, press "
                       "enter and try again later.\nOtherwise you can type "
                       "'reset' to delete the current configuration and redo "
                       "the setup process again the next start.\n> ")
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
    loop = asyncio.get_event_loop()

    prompt = "--no-prompt" not in sys.argv[1:]

    formatter = RedFormatter(show_check_failure=False)

    bot = RedBot(formatter=formatter, description=description, pm_help=None)

    bot.add_check(lambda ctx: bot.user_allowed(ctx.message))

    send_cmd_help = bot.send_cmd_help  # Backwards
    user_allowed = bot.user_allowed    # compatibility
    settings = bot.settings            # bullshit

    check_folders()
    logger = get_logger()

    if settings.bot_settings == settings.default_settings:
        setup_wizard(bot.settings)

    redcore = RedCore(bot, logger)
    bot.add_cog(redcore)
    owner_cog = load_cogs(bot, logger, prompt)

    # Prefix sanity check
    if settings.prefixes == []:
        print("No prefix set. Defaulting to !")
        settings.prefixes = ["!"]
        if settings.owner != "id_here":
            print("Use !set prefix to set it.")
        else:
            print("Once you're owner use !set prefix to set it.")

    # Owner sanity check
    if settings.owner == "id_here" and settings.login_type == "email":
        print("Owner has not been set yet. Do '{}set owner' in chat to set "
              "yourself as owner.".format(settings.prefixes[0]))
    else:
        owner_cog.owner.hidden = True  # Hides the set owner command from help

    print("-- Logging in.. --")
    if os.name == "nt" and os.path.isfile("update.bat"):
        print("Make sure to keep your bot updated by running the file "
              "update.bat")
    else:
        print("Make sure to keep your bot updated by using: git pull")
        print("and: pip3 install -U git+https://github.com/Rapptz/"
              "discord.py@master#egg=discord.py[voice]")
    print("Official server: https://discord.me/Red-DiscordBot")

    start_bot(loop, bot, logger)
