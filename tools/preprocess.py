import sys
from typing import TextIO, Callable, Match
from typing_extensions import TypedDict
import re

from lxml import etree
from lxml.cssselect import CSSSelector
from io import StringIO

import logging

logging.basicConfig(format='%(levelname)s: %(message)s' ,stream=sys.stderr, level=logging.DEBUG)
logger = logging.getLogger('preprocess')

##########################################

COMMAND_RE = re.compile(r"\{\{(.+):(.+)\}\}")

HeadingTypeAtomic = TypedDict("HeadingTypeAtomic", {
    "name": str, "href": str, "children": list["HeadingTypeAtomic"]
})

landmarks: list[HeadingTypeAtomic] = []

####### commands #########################

def _include(m: Match) -> str:
    global logger
    params = m.group(2).strip()
    with open(params, "r") as includedfile:
        logger.debug("Inserting file %s" % params)
        return replacer(includedfile.read())

def _tableofcontents(m: Match) -> str:
    global landmarks
    writeable_string = StringIO()
    writeable_string.write('<ol class="tableofcontents">')
    landmarks2toc(writeable_string, landmarks, 0)
    writeable_string.write('</ol>')
    writeable_string.seek(0)
    return writeable_string.read()

######## map commands to text ############

CommandTable = dict[str, Callable[[Match], str]]

commands: CommandTable = {
    "include": _include
}

commands_after: CommandTable = {
    "tableofcontents": _tableofcontents
}

##########################################

def landmarks2toc(content: StringIO, landmarks: list[HeadingTypeAtomic], level: int):
    levels = [
        "chapter", # h2
        "schapter", # h3
        "sschapter", # h4
        "ssschapter", # h5
        "sssschapter", # h6
    ]

    for h in landmarks:
        content.write(
            '<li><a href="%s" class="_%s">%s</a>' % (
                h["href"] if h["href"] else "#",
                levels[level],
                h["name"]
            )
        )
        if len(h["children"]) > 0:
            content.write('<ol>')
            landmarks2toc(content, h["children"], level+1)
            content.write('</ol>')
        content.write('</li>')

def doc2landmarks(xml: str):
    global landmarks

    parser = etree.HTMLParser()
    content = etree.parse(StringIO(xml), parser)

    root = content.getroot()

    for heading in root.xpath(
        CSSSelector('h2,h3,h4,h5,h6').path
    ):
        tag = heading.tag.lower()

        if tag == "h2":
            append_target = landmarks
        elif tag == "h3":
            append_target = landmarks[-1]["children"]
        elif tag == "h4":
            append_target = landmarks[-1]["children"][-1]["children"]
        elif tag == "h5":
            append_target = landmarks[-1]["children"][-1]["children"][-1]["children"]
        elif tag == "h6":
            append_target = landmarks[-1]["children"][-1]["children"][-1]["children"][-1]["children"]
        else:
            logger.debug("Heading level %s not allowed" % tag)
            continue

        headingtxt = (
            heading.text + ''.join([etree.tostring(e).decode('utf-8') for e in heading])
        ).strip()

        logger.debug("Found heading of %s: %s" % (tag, headingtxt))

        append_target.append({
            "name": headingtxt,
            "href": heading.attrib.get("id", None),
            "children": []
        })

def dispatch_commands_common(m: Match, which_table: CommandTable) -> str:
    command, args = (
        m.group(1).strip(),
        m.group(2).strip()
    )

    try:
        logger.debug("Dispatching command %s" % command)
        return which_table[command](m)
    except:
        logger.debug("Command %s not found at this stage, leaving intact" % command)
        return m.group(0)

def dispatch_commands(m: Match) -> str:
    global commands
    return dispatch_commands_common(m, commands)

def dispatch_commands_after(m: Match) -> str:
    global commands_after
    return dispatch_commands_common(m, commands_after)

def replacer(text: str) -> str:
    global COMMAND_RE
    global logger

    logger.debug("Hit replacer function")
    return (
        re.sub(
            COMMAND_RE, dispatch_commands, text
        )
    )

def replacer_after(text: str) -> str:
    global COMMAND_RE
    global logger

    logger.debug("Hit post-replacer function")
    return (
        re.sub(
            COMMAND_RE, dispatch_commands_after, text
        )
    )

def process_file(content: str) -> str:
    global logger

    logger.info("Phase 1: processing")
    content = replacer(content)

    logger.info("Creating landmarks")
    doc2landmarks(content)

    logger.info("Phase 2: post-processing")
    content = replacer_after(content)
    return content

if __name__ == "__main__":
    with open(sys.argv[1], "r") as infile:
        print(process_file(infile.read()))