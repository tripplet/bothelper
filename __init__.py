#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
import logging

import telegram  # pip install python-telegram-bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

__author__ = 'ttobias'


class TelegramBot(object):
    _reply_config = telegram.ReplyKeyboardMarkup([['Inhalt', 'Neuladen'],
                                                  ['Bearbeiten', 'Abbrechen']],
                                                 resize_keyboard=True,
                                                 one_time_keyboard=True)

    def __init__(self, config):
        try:
            self.dispatcher = None
            self.cfg = config

            self.version = TelegramBot.get_version()
            self.started = datetime.now()

            self._handle_response = dict()  # Function responsible for handling a response from the users
            self.messages = 0  # Number of messages processed

            self.bot = telegram.Bot(token=self.cfg['telegram_bot_token'])
            self.updater = Updater(bot=self.bot)

            # Get the dispatcher to register handlers
            self.dispatcher = self.updater.dispatcher

            self.dispatcher.add_error_handler(TelegramBot.bot_error)

            # add basic commands
            self.dispatcher.add_handler(MessageHandler([Filters.text], self.rx_message))

            self.dispatcher.add_handler(CommandHandler("info", self.cmd_info))
            self.dispatcher.add_handler(CommandHandler("start", self.cmd_start))
            self.dispatcher.add_handler(CommandHandler("cancel", self.cmd_cancel))
            self.dispatcher.add_handler(CommandHandler("help", self.cmd_help))
        except Exception as exp:
            logging.error('Error creating telegram bot' + str(exp))

    def start(self):
        """
        Start the bot.
        :return:
        """
        self.dispatcher.add_handler(MessageHandler([Filters.command], self.cmd_help))
        logging.info('Telegram bot active')
        self.updater.start_polling(clean=True, timeout=30)

    def send_message(self, chat_id, text, **args):
        self.bot.send_message(chat_id=chat_id, text=text, **args)
        self.messages += 1

    def is_authorized(self, bot, update):
        if update.message.chat_id not in self.cfg["users"]:
            self.send_message(update.message.chat_id, text='Unauthorized: %d' % update.message.chat_id)
            return False

        # Received a valid message from an authorized user
        self.messages += 1
        return True

    def is_admin(self, _, update):
        if "admins" in self.cfg \
                and update.message.chat_id in self.cfg["users"] \
                and update.message.chat_id in self.cfg["admins"]:
            self.messages += 1
            return True

        self.send_message(update.message.chat_id, text="Nur für Admins")
        return False

    def cmd_info(self, bot, update):
        if not self.is_authorized(bot, update):
            return
        self.send_message(update.message.chat_id,
                          text='Version: {}\n'
                               'Am Leben seit: {}\n'
                               'Nachrichten verarbeitet: {}\n'
                          .format(self.version, TelegramBot.format_date(self.started), self.messages))

    def _reload_config(self, content='', check_only=False):
        pass

    def cmd_config(self, bot, update):
        if not self.is_admin(bot, update):
            return

        self.send_message(update.message.chat_id, text='Aktion?',
                          reply_markup=self._reply_config)

        # Function handling the response
        def _response(resp_self, resp_update):
            if resp_update.message.text == 'Inhalt':
                with open(resp_self.config_file) as fp:
                    config_text = fp.read()

                resp_self.send_message(resp_update.message.chat_id,
                                       text=config_text,
                                       reply_markup=telegram.ReplyKeyboardHide())
                resp_self.set_handle_response(resp_update.message.chat_id, None)

            elif resp_update.message.text == 'Neuladen':
                self._reload_config()
                resp_self.send_message(resp_update.message.chat_id,
                                       text='Erledigt',
                                       reply_markup=telegram.ReplyKeyboardHide())
                resp_self.set_handle_response(resp_update.message.chat_id, None)

            elif resp_update.message.text == 'Bearbeiten':
                resp_self.send_message(resp_update.message.chat_id,
                                       text='Inhalt der Config Datei eingeben!\nBenutze /cancel zum Abbrechen.',
                                       reply_markup=telegram.ForceReply())

                def _response_edit(edit_self, edit_update):
                    resp = edit_update.message.text
                    new_config = None

                    try:
                        self._reload_config(content=resp, check_only=True)
                    except Exception as exp:
                        edit_self.send_message(edit_update.message.chat_id,
                                               text='Ungültige config: ' +
                                                    str(exp) +
                                                    '!\nConfig erneut eingeben. Benutze /cancel zum Abbrechen.',
                                               reply_markup=telegram.ForceReply())
                        return

                    if new_config is not None:
                        self._reload_config(content=resp)

                        edit_self.send_message(edit_update.message.chat_id, text='Erledigt',
                                               reply_markup=telegram.ReplyKeyboardHide())
                        edit_self.set_handle_response(edit_update.message.chat_id, None)

                resp_self.set_handle_response(resp_update.message.chat_id, _response_edit)

            elif resp_update.message.text == 'Abbrechen':
                resp_self.cmd_cancel(bot, resp_update)
            else:
                resp_self.send_message(resp_update.message.chat_id, text='Bitte wähle eine der folgenden Möglichkeiten',
                                       reply_markup=self._reply_config)

        self.set_handle_response(update.message.chat_id, _response)

    def cmd_cancel(self, bot, update):
        if not self.is_authorized(bot, update):
            return

        self.send_message(update.message.chat_id, text='Abgebrochen', reply_markup=telegram.ReplyKeyboardHide())
        self.set_handle_response(update.message.chat_id, None)

    def cmd_start(self, bot, update):
        if not self.is_authorized(bot, update):
            return
        self.cmd_help(bot, update)

    def cmd_help(self, bot, update):
        """
        Empty help function should be overridden in subclass
        """
        pass

    def set_handle_response(self, chat_id, response_func):
        self._handle_response[chat_id] = response_func

    def rx_message(self, bot, update):
        if not self.is_authorized(bot, update):
            return

        chat_id = update.message.chat_id

        # Not expecting a response
        if chat_id in self._handle_response and self._handle_response[chat_id] is not None:
            self._handle_response[chat_id](self, update)

    @staticmethod
    def bot_error(_, update, error):
        logging.error('Update "%s" caused error "%s"' % (update, error))

    @staticmethod
    def format_date(date):
        if date is None:
            return 'None'
        else:
            return date.strftime('%a %d. %b - %H:%M')

    @staticmethod
    def get_version():
        # noinspection PyBroadException
        try:
            import subprocess
            import os
            import inspect

            # Determine directory of the main script file
            frames = inspect.getouterframes(inspect.currentframe())
            frame = frames[len(frames)-1].frame
            cwd = os.path.dirname(os.path.abspath(inspect.getfile(frame)))

            # try .version file
            version_file = os.path.join(cwd, '.version')
            if os.path.exists(version_file):
                with open(version_file) as f:
                    version = f.read()
                    return version.strip()
            else:
                # try with git
                return subprocess.check_output(['git', 'describe', '--long', '--always', '--tags'], cwd=cwd).decode(
                    'utf8').strip()
        except Exception:
            return '?'
