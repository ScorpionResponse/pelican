import os
import re
import sys
import time
import logging
import argparse

from pelican.generators import (ArticlesGenerator, PagesGenerator,
        StaticGenerator, PdfGenerator)
from pelican.log import init
from pelican.settings import read_settings, _DEFAULT_CONFIG
from pelican.utils import clean_output_dir, files_changed
from pelican.writers import Writer

__major__ = 3
__minor__ = 0
__version__ = "{0}.{1}".format(__major__, __minor__)


logger = logging.getLogger(__name__)


class Pelican(object):
    def __init__(self, settings=None, path=None, theme=None, output_path=None,
            markup=None, delete_outputdir=False):
        """Read the settings, and performs some checks on the environment
        before doing anything else.
        """
        if settings is None:
            settings = _DEFAULT_CONFIG

        self.path = path or settings['PATH']
        if not self.path:
            raise Exception('You need to specify a path containing the content'
                    ' (see pelican --help for more information)')

        if self.path.endswith('/'):
            self.path = self.path[:-1]

        # define the default settings
        self.settings = settings

        self._handle_deprecation()

        self.theme = theme or settings['THEME']
        output_path = output_path or settings['OUTPUT_PATH']
        self.output_path = os.path.realpath(output_path)
        self.markup = markup or settings['MARKUP']
        self.delete_outputdir = delete_outputdir \
                                    or settings['DELETE_OUTPUT_DIRECTORY']

        # find the theme in pelican.theme if the given one does not exists
        if not os.path.exists(self.theme):
            theme_path = os.sep.join([os.path.dirname(
                os.path.abspath(__file__)), "themes/%s" % self.theme])
            if os.path.exists(theme_path):
                self.theme = theme_path
            else:
                raise Exception("Impossible to find the theme %s" % theme)

    def _handle_deprecation(self):

        if self.settings.get('CLEAN_URLS', False):
            logger.warning('Found deprecated `CLEAN_URLS` in settings. Modifing'
                        ' the following settings for the same behaviour.')

            self.settings['ARTICLE_URL'] = '{slug}/'
            self.settings['ARTICLE_LANG_URL'] = '{slug}-{lang}/'
            self.settings['PAGE_URL'] = 'pages/{slug}/'
            self.settings['PAGE_LANG_URL'] = 'pages/{slug}-{lang}/'

            for setting in ('ARTICLE_URL', 'ARTICLE_LANG_URL', 'PAGE_URL',
                            'PAGE_LANG_URL'):
                logger.warning("%s = '%s'" % (setting, self.settings[setting]))

        if self.settings.get('ARTICLE_PERMALINK_STRUCTURE', False):
            logger.warning('Found deprecated `ARTICLE_PERMALINK_STRUCTURE` in'
                        ' settings.  Modifing the following settings for'
                        ' the same behaviour.')

            structure = self.settings['ARTICLE_PERMALINK_STRUCTURE']

            # Convert %(variable) into {variable}.
            structure = re.sub('%\((\w+)\)s', '{\g<1>}', structure)

            # Convert %x into {date:%x} for strftime
            structure = re.sub('(%[A-z])', '{date:\g<1>}', structure)

            # Strip a / prefix
            structure = re.sub('^/', '', structure)

            for setting in ('ARTICLE_URL', 'ARTICLE_LANG_URL', 'PAGE_URL',
                            'PAGE_LANG_URL', 'ARTICLE_SAVE_AS',
                            'ARTICLE_LANG_SAVE_AS', 'PAGE_SAVE_AS',
                            'PAGE_LANG_SAVE_AS'):
                self.settings[setting] = os.path.join(structure,
                                                      self.settings[setting])
                logger.warning("%s = '%s'" % (setting, self.settings[setting]))

    def run(self):
        """Run the generators and return"""

        context = self.settings.copy()
        generators = [
            cls(
                context,
                self.settings,
                self.path,
                self.theme,
                self.output_path,
                self.markup,
                self.delete_outputdir
            ) for cls in self.get_generator_classes()
        ]

        for p in generators:
            if hasattr(p, 'generate_context'):
                p.generate_context()

        # erase the directory if it is not the source and if that's
        # explicitely asked
        if (self.delete_outputdir and not
                os.path.realpath(self.path).startswith(self.output_path)):
            clean_output_dir(self.output_path)

        writer = self.get_writer()

        for p in generators:
            if hasattr(p, 'generate_output'):
                p.generate_output(writer)

    def get_generator_classes(self):
        generators = [ArticlesGenerator, PagesGenerator, StaticGenerator]
        if self.settings['PDF_GENERATOR']:
            generators.append(PdfGenerator)
        return generators

    def get_writer(self):
        return Writer(self.output_path, settings=self.settings)


def parse_arguments():
    parser = argparse.ArgumentParser(description="""A tool to generate a
    static blog, with restructured text input files.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(dest='path', nargs='?',
        help='Path where to find the content files.',
        default=None)

    parser.add_argument('-t', '--theme-path', dest='theme',
        help='Path where to find the theme templates. If not specified, it'
             'will use the default one included with pelican.')

    parser.add_argument('-o', '--output', dest='output',
        help='Where to output the generated files. If not specified, a '
             'directory will be created, named "output" in the current path.')

    parser.add_argument('-m', '--markup', dest='markup',
        help='The list of markup language to use (rst or md). Please indicate '
             'them separated by commas.')

    parser.add_argument('-s', '--settings', dest='settings',
        help='The settings of the application.')

    parser.add_argument('-d', '--delete-output-directory',
        dest='delete_outputdir',
        action='store_true', help='Delete the output directory.')

    parser.add_argument('-v', '--verbose', action='store_const',
        const=logging.INFO, dest='verbosity',
        help='Show all messages.')

    parser.add_argument('-q', '--quiet', action='store_const',
        const=logging.CRITICAL, dest='verbosity',
        help='Show only critical errors.')

    parser.add_argument('-D', '--debug', action='store_const',
        const=logging.DEBUG, dest='verbosity',
        help='Show all message, including debug messages.')

    parser.add_argument('--version', action='version', version=__version__,
        help='Print the pelican version and exit.')

    parser.add_argument('-r', '--autoreload', dest='autoreload',
        action='store_true',
        help="Relaunch pelican each time a modification occurs"
                             " on the content files.")
    return parser.parse_args()


def main():
    args = parse_arguments()
    init(args.verbosity)
    # Split the markup languages only if some have been given. Otherwise,
    # populate the variable with None.
    markup = [a.strip().lower() for a in args.markup.split(',')]\
              if args.markup else None

    settings = read_settings(args.settings)

    cls = settings.get('PELICAN_CLASS')
    if isinstance(cls, basestring):
        module, cls_name = cls.rsplit('.', 1)
        module = __import__(module)
        cls = getattr(module, cls_name)

    try:
        pelican = cls(settings, args.path, args.theme, args.output, markup,
                args.delete_outputdir)
        if args.autoreload:
            while True:
                try:
                    # Check source dir for changed files ending with the given
                    # extension in the settings. In the theme dir is no such
                    # restriction; all files are recursively checked if they
                    # have changed, no matter what extension the filenames
                    # have.
                    if files_changed(pelican.path, pelican.markup) or \
                            files_changed(pelican.theme, ['']):
                        pelican.run()
                    time.sleep(.5)  # sleep to avoid cpu load
                except KeyboardInterrupt:
                    break
        else:
            pelican.run()
    except Exception, e:
        logger.critical(unicode(e))

        if (args.verbosity == logging.DEBUG):
            raise
        else:
            sys.exit(getattr(e, 'exitcode', 1))
