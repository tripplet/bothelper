#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import logging

import telegram  # pip install python-telegram-bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.utils.request import Request

__author__ = 'ttobias'


class TelegramBot(object):
    __version = None
    _today_str = "Heute"
    _yesterday_str = "Gestern"

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

            self._bot = telegram.Bot(token=self.cfg['telegram_bot_token'], request=Request(con_pool_size=8))
            self._updater = Updater(bot=self._bot)

            # Get the dispatcher to register handlers
            self.dispatcher = self._updater.dispatcher

            self.dispatcher.add_error_handler(TelegramBot.bot_error)

            # add basic commands
            self.dispatcher.add_handler(MessageHandler(Filters.text, self.rx_message))

            self.dispatcher.add_handler(CommandHandler("info", self.cmd_info))
            self.dispatcher.add_handler(CommandHandler("start", self.cmd_start))
            self.dispatcher.add_handler(CommandHandler("cancel", self.cmd_cancel))
            self.dispatcher.add_handler(CommandHandler("help", self.cmd_help))
        except Exception as exp:
            logging.error('Error creating telegram bot' + str(exp))

    def start(self):
        """Start the bot."""
        self.dispatcher.add_handler(MessageHandler(Filters.command, self.cmd_help))
        logging.info('Telegram bot active')
        self._updater.start_polling(drop_pending_updates=True, timeout=30)

    def idle(self):
        """Execute idle loop"""
        self._updater.idle()

    def send_message(self, chat_id, text, **args):
        self._bot.send_message(chat_id=chat_id, text=text, **args)
        self.messages += 1

    def send_typing(self, chat_id):
        self._bot.send_chat_action(chat_id = chat_id, action=telegram.ChatAction.TYPING)

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
                                       reply_markup=telegram.ReplyKeyboardRemove())
                resp_self.set_handle_response(resp_update.message.chat_id, None)

            elif resp_update.message.text == 'Neuladen':
                self._reload_config()
                resp_self.send_message(resp_update.message.chat_id,
                                       text='Erledigt',
                                       reply_markup=telegram.ReplyKeyboardRemove())
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
                                               reply_markup=telegram.ReplyKeyboardRemove())
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

        self.send_message(update.message.chat_id, text='Abgebrochen', reply_markup=telegram.ReplyKeyboardRemove())
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

    @classmethod
    def format_date(cls, date):
        if date is None:
            return 'None'
        else:
            today = datetime.today().date()
            if date.date() == today:
                format_str = '{} %H:%M'.format(cls._today_str)
            elif date.date() == today + timedelta(days=-1):
                format_str = '{} %H:%M'.format(cls._yesterday_str)
            else:
                format_str = '%a %d. %b - %H:%M'
            return date.strftime(format_str)

    @staticmethod
    def get_version():
        if TelegramBot.__version is not None:
            return TelegramBot.__version

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
                    TelegramBot.__version = f.read().strip()
            else:
                # try with git
                git_commit = subprocess.check_output(
                    ['git', 'describe', '--long', '--always', '--tags'], cwd=cwd).decode('utf8').strip()
                git_commit_date = subprocess.check_output(
                    ['git', 'show', '-s', '--format=%ci', '--date=local'], cwd=cwd).decode('utf8').strip()[:19]
                TelegramBot.__version = '{} ({})'.format(git_commit, git_commit_date)
        except Exception:
            TelegramBot.__version = '?'

        return TelegramBot.__version
