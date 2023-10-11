import sys
from typing import TextIO, Callable, Match
from typing_extensions import TypedDict
import re

from lxml import etree
from lxml.cssselect import CSSSelector
from io import StringIO

import logging

logging.basicConfig(format='%(levelname)s: %(message)s' ,stream=sys.stderr, level=logging.INFO)

##########################################

# regex used for matching commands.
COMMAND_RE = re.compile(r"\{\{(.+?):(.+)\}\}")

# type of landmark elements
HeadingTypeAtomic = TypedDict("HeadingTypeAtomic", {
    "name": str, "href": str, "children": list["HeadingTypeAtomic"]
})

######## used globals ####################

logger = logging.getLogger('preprocess')
landmarks: list[HeadingTypeAtomic] = []

####### commands #########################

# commands must conform to this
CommandFunction = Callable[[Match], str]

def _include(m: Match) -> str:
    """
    Includes a document within another document
    """
    global logger
    params = m.group(2).strip()

    if params == "":
        raise Exception("Missing file path!")

    with open(params, "r") as includedfile:
        logger.info("Inserting file %s" % params)
        return replacer(includedfile.read())

def _tableofcontents(m: Match) -> str:
    """
    Writes a <ol> table of contents in the page based
    on the currently noted landmarks (that is, headings)
    """
    global landmarks
    writeable_string = StringIO()
    writeable_string.write('<ol class="tableofcontents">')
    landmarks2toc(writeable_string, landmarks, 0)
    writeable_string.write('</ol>')
    writeable_string.seek(0)
    return writeable_string.read()

def _verbatim_keep_command(m: Match) -> str:
    """
    Pastes some text verbatim in the document.
    Used in the 1st stage, returns the raw match.
    """
    return m.group(0).strip()

def _verbatim(m: Match) -> str:
    """
    Pastes some text verbatim in the document.
    Used in the 2nd stage, returns just the arguments.
    """
    return m.group(2).strip()

######## map commands to text ############

CommandTable = dict[str, CommandFunction]

commands: CommandTable = { # 1st stage
    "include": _include,
    "verbatim": _verbatim_keep_command
}

commands_after: CommandTable = { # 2nd stage
    "table of contents": _tableofcontents,
    "verbatim": _verbatim
}

##########################################

def landmarks2toc(content: StringIO, landmarks: list[HeadingTypeAtomic], level: int):
    """
    Writes directly to `content`. Returns nothing.
    """
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
    """
    Extracts headings from a document and places it in
    the global landmarks variable.
    """
    global landmarks

    parser = etree.HTMLParser()
    content = etree.parse(StringIO(xml), parser)

    root = content.getroot()

    last_heading_tag = None
    last_heading_text = None
    tag = None
    htext = None

    for heading in root.xpath(
        CSSSelector('h2,h3,h4,h5,h6').path
    ):
        last_heading_tag = tag
        last_heading_text = htext

        tag = heading.tag.lower()
        htext = (
            heading.text + ''.join([etree.tostring(e).decode('utf-8') for e in heading])
        ).strip()

        # "h4" > "h3"
        if (last_heading_tag) is not None and (tag > last_heading_tag): 
            if (int(tag[-1]) - int(last_heading_tag[-1]) > 1):
                raise Exception("Skipping heading levels is not allowed (from %s:%s to %s:%s)" % (last_heading_tag, last_heading_text, tag, htext))

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

        logger.debug("Found heading of %s: %s" % (tag, htext))

        append_target.append({
            "name": htext,
            "href": heading.attrib.get("id", None),
            "children": []
        })

def dispatch_commands_common(m: Match, which_table: CommandTable) -> str:
    """
    Dispatches commands based on a table
    """
    command, args = (
        m.group(1).strip(),
        m.group(2).strip()
    )

    try:
        logger.debug("Dispatching command %s" % command)
        return which_table[command](m)
    except KeyError:
        logger.warning("Command '%s' not found at this stage, leaving intact" % command)
        return m.group(0)
    except Exception as e:
        logger.error("Command '%s' seems malformed, leaving intact: %s" % (command, e.__str__()))
        return m.group(0)

def dispatch_commands(m: Match) -> str:
    """
    Dispatches commands for the 1st stage.
    """
    global commands
    return dispatch_commands_common(m, commands)

def dispatch_commands_after(m: Match) -> str:
    """
    Dispatches commands for the 2nd stage.
    """
    global commands_after
    return dispatch_commands_common(m, commands_after)

def replacer(text: str) -> str:
    """
    1st stage text replacement.
    """
    global COMMAND_RE
    global logger

    logger.debug("Hit replacer function")
    return (
        re.sub(
            COMMAND_RE, dispatch_commands, text
        )
    )

def replacer_after(text: str) -> str:
    """
    2nd stage text replacement.
    """
    global COMMAND_RE
    global logger

    logger.debug("Hit post-replacer function")
    return (
        re.sub(
            COMMAND_RE, dispatch_commands_after, text
        )
    )

def process_file(content: str) -> str:
    """
    The entire text replacement process.
    """
    global logger

    logger.info("Stage 1: processing")
    content = replacer(content)

    logger.info("Creating landmarks")
    doc2landmarks(content)

    logger.info("Stage 2: post-processing")
    content = replacer_after(content)
    return content

if __name__ == "__main__":
    with open(sys.argv[1], "r") as infile:
        print(process_file(infile.read()))