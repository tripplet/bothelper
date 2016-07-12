#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'ttobias'

from datetime import datetime
import logging
import yaml

import telegram  # pip install python-telegram-bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Enable telegram bot logging
logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class TelegramBot(object):
    _reply_config = telegram.ReplyKeyboardMarkup([['Inhalt', 'Neuladen'],
                                                  ['Bearbeiten', 'Abbrechen']],
                                                 resize_keyboard=True,
                                                 one_time_keyboard=True)

    def __init__(self, config_file, use_caller_version=False):
        try:
            self.config_file = config_file
            self._reload_config_file()

            self.version = TelegramBot.get_version(use_caller_version)
            self.started = datetime.now()

            self._handle_response = dict()  # Function responsible for handling a response from the users
            self.messages = 0  # Number of messages processed

            self.bot = telegram.Bot(token=self.cfg['telegram_bot_token'])
            self.updater = Updater(bot=self.bot)

            # Get the dispatcher to register handlers
            self.dispatcher = self.updater.dispatcher

            self.dispatcher.add_error_handler(self.bot_error)

            # add basic commands
            self.dispatcher.add_handler(MessageHandler([Filters.text], self.rx_message))

            self.dispatcher.add_handler(CommandHandler("info",   self.cmd_info))
            self.dispatcher.add_handler(CommandHandler("start",  self.cmd_start))
            self.dispatcher.add_handler(CommandHandler("cancel", self.cmd_cancel))
            self.dispatcher.add_handler(CommandHandler("help",   self.cmd_help))
        except Exception as exp:
            print('Error creating telegram bot' + str(exp.strerr))

    def start(self):
        """
        Start the bot.
        :return:
        """
        self.dispatcher.add_handler(MessageHandler([Filters.command], self.cmd_help))
        self.updater.start_polling(clean=True, timeout=30)

    def _reload_config_file(self):
        with open(self.config_file) as fp:
            self.cfg = yaml.load(fp)

    def send_message(self, chat_id, text, **args):
        self.bot.send_message(chat_id=chat_id, text=text, **args)
        self.messages += 1

    def is_authorized(self, bot, update):
        if not update.message.chat_id in self.cfg["users"]:
            self.send_message(update.message.chat_id, text='Unauthorized: %d' % update.message.chat_id)
            return False

        # Received a valid message from an authorized user
        self.messages += 1
        return True

    def is_admin(self, bot, update):
        if "admins" in self.cfg \
                and update.message.chat_id in self.cfg["users"] \
                and update.message.chat_id in self.cfg["admins"]:
            self.messages += 1
            return True

        self.send_message(update.message.chat_id, text="Nur für Admins")
        return False

    def cmd_info(self, bot, update):
        if not self.is_authorized(bot, update): return
        self.send_message(update.message.chat_id,
                          text='Version: {}\n'
                               'Am Leben seit: {}\n'
                               'Nachrichten verarbeitet: {}\n'
                          .format(self.version, TelegramBot.format_date(self.started), self.messages))

    def cmd_config(self, bot, update):
        if not self.is_admin(bot, update): return

        self.send_message(update.message.chat_id, text='Aktion?',
                          reply_markup=self._reply_config)

        # Function handling the response
        def _response(self, update):
            if update.message.text == 'Inhalt':
                with open(self.config_file) as fp:
                    config_text = fp.read()

                self.send_message(update.message.chat_id, text=config_text, reply_markup=telegram.ReplyKeyboardHide())
                self.set_handle_response(update.message.chat_id, None)

            elif update.message.text == 'Neuladen':
                self._reload_config_file()
                self.send_message(update.message.chat_id, text='Erledigt', reply_markup=telegram.ReplyKeyboardHide())
                self.set_handle_response(update.message.chat_id, None)

            elif update.message.text == 'Bearbeiten':
                self.send_message(update.message.chat_id,
                                  text='Inhalt der Config Datei eingeben!\nBenutze /cancel zum Abbrechen.',
                                  reply_markup=telegram.ForceReply())

                def _response_edit(self, update):
                    resp = update.message.text
                    new_config = None

                    try:
                        new_config = yaml.safe_load(resp)
                    except Exception as exp:
                        self.send_message(update.message.chat_id,
                                          text='Ungültige config: ' + str(
                                              exp) + '!\nConfig erneut eingeben. Benutze /cancel zum Abbrechen.',
                                          reply_markup=telegram.ForceReply())
                        return

                    # Perform sone basic config checks
                    if 'users' not in new_config \
                            or 'admins' not in new_config \
                            or 'telegram_bot_token' not in new_config:
                        self.send_message(update.message.chat_id,
                                          text='Ungültige config\nConfig erneut eingeben. Benutze /cancel zum Abbrechen.',
                                          reply_markup=telegram.ForceReply())
                        return

                    if new_config is not None:
                        with open(self.config_file, 'w') as fp:
                            fp.write(resp)

                        self._reload_config_file()

                        self.send_message(update.message.chat_id, text='Erledigt',
                                          reply_markup=telegram.ReplyKeyboardHide())
                        self.set_handle_response(update.message.chat_id, None)

                self.set_handle_response(update.message.chat_id, _response_edit)


            elif update.message.text == 'Abbrechen':
                self.cmd_cancel(bot, update)

            else:
                self.send_message(update.message.chat_id, text='Bitte wähle eine der folgenden Möglichkeiten',
                                  reply_markup=self._reply_config)

        self.set_handle_response(update.message.chat_id, _response)

    def cmd_cancel(self, bot, update):
        if not self.is_authorized(bot, update): return

        self.send_message(update.message.chat_id, text='Abgebrochen', reply_markup=telegram.ReplyKeyboardHide())
        self.set_handle_response(update.message.chat_id, None)

    def cmd_start(self, bot, update):
        if not self.is_authorized(bot, update): return
        self.cmd_help(bot, update)

    def set_handle_response(self, chat_id, response_func):
        self._handle_response[chat_id] = response_func

    def rx_message(self, bot, update):
        if not self.is_authorized(bot, update): return

        chat_id = update.message.chat_id

        # Not expecting a response
        if chat_id in self._handle_response and self._handle_response[chat_id] is not None:
            self._handle_response[chat_id](self, update)

    def bot_error(self, bot, update, error):
        print('Update "%s" caused error "%s"' % (update, error))

    @staticmethod
    def format_date(date):
        if date is None:
            return 'None'
        else:
            return date.strftime('%a %-d. %b - %H:%M')

    @staticmethod
    def get_version(use_caller_version):
        try:
            import subprocess
            import os
            import inspect

            # Determine directory this file or the calling function is located in
            frame = inspect.currentframe()
            if use_caller_version:
                frame = inspect.getouterframes(frame)[2].frame # Got "up" to caller of constructor
            cwd = os.path.dirname(os.path.abspath(inspect.getfile(frame)))

            # try .version file
            version_file = os.path.join(cwd, '.version')
            if os.path.exists(version_file):
                with open(version_file) as f:
                    version = f.read()
                    return version
            else:
                # try with git
                return subprocess.check_output(['git', 'describe', '--long', '--always'], cwd=cwd).decode('utf8').strip()
        except Exception:
            return '?'
