"""Beautiful Soup
Elixir and Tonic
"The Screen-Scraper's Friend"
http://www.crummy.com/software/BeautifulSoup/

Beautiful Soup uses a plug-in parser to parse a (possibly invalid) XML
or HTML document into a tree representation. The parser does the work
of building a parse tree, and Beautiful Soup provides provides methods
and Pythonic idioms that make it easy to navigate, search, and modify
the parse tree.

Beautiful Soup works with Python 2.5 and up. It works better if lxml
or html5lib is installed.

For more than you ever wanted to know about Beautiful Soup, see the
documentation:
http://www.crummy.com/software/BeautifulSoup/documentation.html
"""
from __future__ import generators

__author__ = "Leonard Richardson (leonardr@segfault.org)"
__version__ = "4.0.0a"
__copyright__ = "Copyright (c) 2004-2011 Leonard Richardson"
__license__ = "MIT"

__all__ = ['BeautifulSoup']

import re

from util import isList, buildSet
from builder import builder_registry
from dammit import UnicodeDammit
from element import DEFAULT_OUTPUT_ENCODING, NavigableString, Tag


class BeautifulSoup(Tag):
    """
    This class defines the basic interface called by the tree builders.

    These methods will be called by the parser:
      reset()
      feed(markup)

    The tree builder may call these methods from its feed() implementation:
      handle_starttag(name, attrs) # See note about return value
      handle_endtag(name)
      handle_data(data) # Appends to the current data node
      endData(containerClass=NavigableString) # Ends the current data node

    No matter how complicated the underlying parser is, you should be
    able to build a tree using 'start tag' events, 'end tag' events,
    'data' events, and "done with data" events.

    If you encounter an empty-element tag (aka a self-closing tag,
    like HTML's <br> tag), call handle_starttag and then
    handle_endtag.
    """
    ROOT_TAG_NAME = u'[document]'

    # If the end-user gives no indication which tree builder they
    # want, look for one with these features.
    DEFAULT_BUILDER_FEATURES = ['html']

    # Used when determining whether a text node is all whitespace and
    # can be replaced with a single space. A text node that contains
    # fancy Unicode spaces (usually non-breaking) should be left
    # alone.
    STRIP_ASCII_SPACES = { 9: None, 10: None, 12: None, 13: None, 32: None, }

    def __init__(self, markup="", features=None, builder=None,
                 parse_only=None, from_encoding=None):
        """The Soup object is initialized as the 'root tag', and the
        provided markup (which can be a string or a file-like object)
        is fed into the underlying parser."""

        if builder is None:
            if isinstance(features, basestring):
                features = [features]
            if features is None or len(features) == 0:
                features = self.DEFAULT_BUILDER_FEATURES
            builder_class = builder_registry.lookup(*features)
            if builder_class is None:
                raise ValueError(
                    "Couldn't find a tree builder with the features you "
                    "requested: %s. Do you need to install a parser library?"
                    % ",".join(features))
            builder = builder_class()
        self.builder = builder
        self.is_xml = builder.is_xml
        self.builder.soup = self

        self.parse_only = parse_only

        self.reset()

        if hasattr(markup, 'read'):        # It's a file-type object.
            markup = markup.read()
        self.markup, self.original_encoding, self.declared_html_encoding = (
            self.builder.prepare_markup(markup, from_encoding))

        try:
            self._feed()
        except StopParsing:
            pass

        # Clear out the markup and the builder so they can be CGed.
        self.markup = None
        self.builder.soup = None
        self.builder = None

    def _feed(self):
        # Convert the document to Unicode.
        self.builder.reset()

        self.builder.feed(self.markup)
        # Close out any unfinished strings and close all the open tags.
        self.endData()
        while self.currentTag.name != self.ROOT_TAG_NAME:
            self.popTag()

    def reset(self):
        Tag.__init__(self, self, self.builder, self.ROOT_TAG_NAME)
        self.hidden = 1
        self.builder.reset()
        self.currentData = []
        self.currentTag = None
        self.tagStack = []
        self.pushTag(self)

    def popTag(self):
        tag = self.tagStack.pop()
        #print "Pop", tag.name
        if self.tagStack:
            self.currentTag = self.tagStack[-1]
        return self.currentTag

    def pushTag(self, tag):
        #print "Push", tag.name
        if self.currentTag:
            self.currentTag.contents.append(tag)
        self.tagStack.append(tag)
        self.currentTag = self.tagStack[-1]

    def endData(self, containerClass=NavigableString):
        if self.currentData:
            currentData = u''.join(self.currentData)
            if (currentData.translate(self.STRIP_ASCII_SPACES) == '' and
                not buildSet([tag.name for tag in self.tagStack]).intersection(
                    self.builder.preserve_whitespace_tags)):
                if '\n' in currentData:
                    currentData = '\n'
                else:
                    currentData = ' '
            self.currentData = []
            if self.parse_only and len(self.tagStack) <= 1 and \
                   (not self.parse_only.text or \
                    not self.parse_only.search(currentData)):
                return
            o = containerClass(currentData)
            self.object_was_parsed(o)

    def object_was_parsed(self, o):
        """Add an object to the parse tree."""
        o.setup(self.currentTag, self.previous)
        if self.previous:
            self.previous.next = o
        self.previous = o
        self.currentTag.contents.append(o)


    def _popToTag(self, name, inclusivePop=True):
        """Pops the tag stack up to and including the most recent
        instance of the given tag. If inclusivePop is false, pops the tag
        stack up to but *not* including the most recent instqance of
        the given tag."""
        #print "Popping to %s" % name
        if name == self.ROOT_TAG_NAME:
            return

        numPops = 0
        mostRecentTag = None
        for i in range(len(self.tagStack)-1, 0, -1):
            if name == self.tagStack[i].name:
                numPops = len(self.tagStack)-i
                break
        if not inclusivePop:
            numPops = numPops - 1

        for i in range(0, numPops):
            mostRecentTag = self.popTag()
        return mostRecentTag

    def handle_starttag(self, name, attrs):
        """Push a start tag on to the stack.

        If this method returns None, the tag was rejected by the
        SoupStrainer. You should proceed as if the tag had not occured
        in the document. For instance, if this was a self-closing tag,
        don't call handle_endtag.
        """

        #print "Start tag %s: %s" % (name, attrs)
        self.endData()

        if (self.parse_only and len(self.tagStack) <= 1
            and (self.parse_only.text
                 or not self.parse_only.searchTag(name, attrs))):
            return None

        tag = Tag(self, self.builder, name, attrs, self.currentTag,
                  self.previous)
        if tag is None:
            return tag
        if self.previous:
            self.previous.next = tag
        self.previous = tag
        self.pushTag(tag)
        return tag


    def handle_endtag(self, name):
        #print "End tag: " + name
        self.endData()
        self._popToTag(name)

    def handle_data(self, data):
        self.currentData.append(data)

    def decode(self, pretty_print=False,
               eventual_encoding=DEFAULT_OUTPUT_ENCODING,
               substitute_html_entities=False):
        """Returns a string or Unicode representation of this document.
        To get Unicode, pass None for encoding."""
        if self.is_xml:
            # Print the XML declaration
            encoding_part = ''
            if eventual_encoding != None:
                encoding_part = ' encoding="%s"' % eventual_encoding
            prefix = u'<?xml version="1.0"%s>\n' % encoding_part
        else:
            prefix = u''
        if not pretty_print:
            indent_level = None
        else:
            indent_level = 0
        return prefix + super(BeautifulSoup, self).decode(
            indent_level, eventual_encoding,
            substitute_html_entities)


class StopParsing(Exception):
    pass


#By default, act as an HTML pretty-printer.
if __name__ == '__main__':
    import sys
    soup = BeautifulSoup(sys.stdin)
    print soup.prettify()
