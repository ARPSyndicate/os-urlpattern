from __future__ import print_function

import argparse
import logging
import os
import sys
import time
from collections import Counter
from logging.config import dictConfig

from .compat import binary_stdin
from .definition import DEFAULT_ENCODING
from .exceptions import (InvalidCharException,
                         InvalidPatternException,
                         IrregularURLException)
from .formatter import FORMATTERS
from .pattern_maker import PatternMaker
from .pattern_matcher import PatternMatcher
from .utils import LogSpeedAdapter, load_obj


def _config_logging(log_level):
    dictConfig(_DEFAULT_LOGGING)
    if log_level == 'NOTSET':
        handler = logging.NullHandler()
    else:
        handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logging.root.setLevel(logging.NOTSET)
    handler.setFormatter(formatter)
    handler.setLevel(log_level)
    logging.root.addHandler(handler)


class Command(object):
    def __init__(self, config=None):
        self._config = config
        self._logger = logging.getLogger(self.__class__.__name__)

    def add_argument(self, parser):

        parser.add_argument('-f', '--file',
                            help='file to be processed (default: stdin)',
                            nargs='?',
                            type=argparse.FileType('rb'),
                            default=binary_stdin,
                            dest='file')

        parser.add_argument('-L', '--loglevel',
                            help='log level (default: NOTSET)',
                            default='NOTSET',
                            action='store',
                            dest='log_level',
                            choices=['NOTSET', 'DEBUG', 'INFO',
                                     'WARN', 'ERROR', 'FATAL'],
                            type=lambda s: s.upper())

    def process_args(self, args):
        _config_logging(args.log_level)

    def run(self, args):
        raise NotImplementedError


class MakePatternCommand(Command):

    def process_args(self, args):
        super(MakePatternCommand, self).process_args(args)
        if args.config:
            self._config.readfp(args.config)

    def add_argument(self, parser):
        super(MakePatternCommand, self).add_argument(parser)
        parser.add_argument('-c', '--config',
                            help='config file',
                            nargs='+',
                            type=argparse.FileType('r'),
                            action='store',
                            dest='config')

        parser.add_argument('-F', '--formatter',
                            help='output formatter (default: JSON)',
                            default='JSON',
                            action='store',
                            dest='formatter',
                            choices=FORMATTERS.keys(),
                            type=lambda s: s.upper(),
                            )

    def _load(self, pattern_maker, args):
        stats = Counter()
        speed_logger = LogSpeedAdapter(self._logger, 5000)
        for url in args.file:
            url = url.strip()
            stats['ALL'] += 1
            speed_logger.debug('[LOADING]')
            try:
                url = url.decode(DEFAULT_ENCODING)
                if pattern_maker.load(url):
                    stats['UNIQ'] += 1
                stats['VALID'] += 1
            except (InvalidPatternException,
                    IrregularURLException,
                    InvalidCharException,
                    UnicodeDecodeError) as e:
                self._logger.warn('%s, %s' % (str(e), url))
                stats['INVALID'] += 1
                continue
        self._logger.debug('[LOADED] %s' % str(stats))

    def _dump(self, pattern_maker, args):
        formatter = FORMATTERS[args.formatter](self._config)
        s = time.time()
        for pattern_tree in pattern_maker.process():
            e = time.time()
            self._logger.debug('[CLUSTER] %d %.2fs' %
                               (pattern_tree.root.count, e - s))
            formatter.format(pattern_tree)
            s = time.time()

    def _freeze_config(self):
        cluster_algorithm_method = load_obj(
            self._config.get('make', 'cluster_algorithm'))
        self._config.set('make', 'cluster_algorithm', cluster_algorithm_method)
        self._config.freeze()

    def run(self, args):
        self._freeze_config()

        pattern_maker = PatternMaker(self._config)

        self._load(pattern_maker, args)
        self._dump(pattern_maker, args)


class MatchPatternCommand(Command):
    def __init__(self):
        super(MatchPatternCommand, self).__init__()

    def add_argument(self, parser):
        super(MatchPatternCommand, self).add_argument(parser)
        parser.add_argument('-p', '--pattern-file',
                            help='pattern file to be loaded',
                            nargs='+',
                            type=argparse.FileType('r'),
                            required=True,
                            action='store',
                            dest='pattern_file')

    def run(self, args):
        pattern_matcher = PatternMatcher()


_DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'incremental': True,
}


def _execute(command, argv=None):
    argv = argv or sys.argv
    parser = argparse.ArgumentParser()
    command.add_argument(parser)
    args = parser.parse_args(argv[1:])
    command.process_args(args)
    command.run(args)


def _default_config():
    from . import config
    path = os.path.dirname(config.__file__)
    cfg = config.Config()
    cfg.read(os.path.join(path, 'default_config.cfg'))
    return cfg


def make(argv=None):
    _execute(MakePatternCommand(_default_config()), argv)


def match(argv=None):
    _execute(MatchPatternCommand(), argv)
