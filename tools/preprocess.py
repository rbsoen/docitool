import sys
from typing import TextIO, Callable, Match, Any, Tuple
from typing_extensions import TypedDict
import re

from lxml import etree
from lxml.cssselect import CSSSelector
from io import StringIO

import logging

import hashlib
import os

logging.basicConfig(format='%(levelname)s: %(message)s' ,stream=sys.stderr, level=logging.DEBUG)

##########################################

# regex used for matching commands.
COMMAND_RE = re.compile(r"\{\{(.+?):(.+)\}\}")

# type of landmark elements
HeadingTypeAtomic = TypedDict("HeadingTypeAtomic", {
    "name": str, "href": str, "children": list["HeadingTypeAtomic"]
})

# cache directory
CACHEDIR = ".docitool_cache"

######## used globals ####################

logger = logging.getLogger('preprocess')
landmarks: list[HeadingTypeAtomic] = []

# optional: citeproc
sources: Any = None
citations: list[Any] = []
cite_style: Any = None
bibliography: Any = None

# optional: katex
mdengine: Any = None

####### commands #########################

# commands must conform to this
CommandFunction = Callable[[Match], str]

########## core commands #########################

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
    Not needed, but useful for eliminating "invalid command" warnings
    """
    return m.group(0).strip()

def _verbatim(m: Match) -> str:
    """
    Pastes some text verbatim in the document.
    Used in the 2nd stage, returns just the arguments.
    """
    return m.group(2).strip()

########## optionals: citeproc #########################

def _addsourcesfrom(m: Match) -> str:
    """
    [citeproc-py; toml]

    Add Citeproc sources in TOML format  from a folder to the `sources` global.
    Returns a blank string.
    """
    import toml
    from citeproc.source.json import CiteProcJSON

    global sources
    global logger

    params = m.group(2).strip()

    if params == "":
        raise Exception("Which folder to add sources from?")
    
    logger.info("Adding sources from %s" % params)
    
    srcs: Any = []

    for i in os.walk(params):
        folder, subfolders, files = i
        logger.info ("in %s..." % folder)
        for f in files:
            logger.info("from file %s" % f)
            toml_content = toml.load(os.path.join(folder, f))
            srcs.append(toml_content)
            try:
                tmp_source = CiteProcJSON([toml_content])
            except Exception as e:
                logger.error("Error processing file %s!" % os.path.join(folder, f))
                raise e
    sources = CiteProcJSON(srcs)
    return ""

def _usecitestylefrom(m: Match) -> str:
    """
    [citeproc-py]

    Uses citation styles from a file. Requires the `sources` global to be
    defined first, e.g. by the "add sources from" command.
    Returns a blank string.
    """
    from citeproc import CitationStylesStyle, CitationStylesBibliography

    global sources, cite_style, bibliography
    global logger

    if cite_style is not None:
        logger.error("Citation style already set, cannot change.")
        return ""

    params = m.group(2).strip()

    if params == "":
        raise Exception("Which file to use styles from?")
    
    if sources is None:
        raise Exception("Use the \{\{ add sources from: <file> \}\} command first!")
    
    cite_style = CitationStylesStyle(params, validate=False)
    bibliography = CitationStylesBibliography(cite_style, sources)

    logger.info("Set citation style from '%s'" % params)
    return ""

def _tableofreferences(m: Match) -> str:
    """
    [citeproc-py]

    Writes a <ol> table of references in the page based
    on the bibliography.
    """
    global bibliography
    global logger

    selements: list[str] = []

    for i in bibliography.bibliography():
        html = str(i)
        selements.append("<li>%s</li>" % html)
    return '<ol id="tableofreferences">%s</ol>' % "\n".join(selements)

def _ref_keep_command(m: Match) -> str:
    """
    [citeproc-py]

    Registers a citation. Used in 1st stage, returns the raw match.
    """
    global bibliography, citations
    global logger
    from citeproc import CitationItem, Citation
    
    citation_array: list[Any] = [
        CitationItem(i.strip())
        for i in m.group(2).split(",")
    ]

    citations.append(Citation(citation_array))
    bibliography.register(citations[-1])
    bibliography.sort()

    logger.debug("Registered citation %s" % citations[-1])
    return m.group(0)

def _ref(m: Match) -> str:
    """
    [citeproc-py]

    Renders a citation to the document.
    Used in 2nd stage.
    """
    global bibliography, citations
    global logger

    def warn(cite_item):
        logger.warning('Reference with key "%s" not found in the bibliography.' % cite_item.key)
    
    main_citation = citations[-1]
    csl_cite = bibliography.cite(main_citation, warn)
    list_cite = main_citation['cites']
    logger.debug('Outputting citation %s' % csl_cite)
    if isinstance(csl_cite, str):
        return csl_cite
    else:
        return str(csl_cite)

########## optionals: plantuml #########################

def _uml(m: Match) -> str:
    """
    [plantuml]

    Returns a PlantUML-rendered SVG. Requires the external program
    `plantuml` to be accessible from path.
    """

    global logger

    import subprocess

    params = m.group(2).strip()

    logger.info("Inserting UML diagram from %s" % params)

    should_remake, cache_file = is_file_newer_than_cache(params)

    if should_remake:
        with open(params, "r") as puml_file:
            result = subprocess.run(
                    ["plantuml", "-Tsvg", "-pipe"],
                    stdout=subprocess.PIPE,
                    input=puml_file.read(),
                    encoding="utf-8"
            ).stdout
        with open(cache_file, "w") as cache:
            cache.write(result)
            return result

    with open(cache_file, "r") as cache:
        return cache.read()

########## optionals: katex #########################

def _formula(m: Match) -> str:
    global mdengine
    global logger

    import markdown
    from markdown_katex.extension import tex2html

    params = m.group(2).strip()

    logger.info("Inserting formula from %s" % params)

    should_remake, cache_file = is_file_newer_than_cache(params)
    
    if should_remake:
        if mdengine is None:
            mdengine = markdown.Markdown(
                extensions=["markdown_katex"],
                extension_configs={
                    "markdown_katex": {
                        "no_inline_svg": False,
                        "insert_fonts_css": False,
                    }
                }
            )
        with open(params, "r") as formula_file:
            result = mdengine.convert(
                "```math\n" + formula_file.read() + "\n```"
            )
        with open(cache_file, "w") as cache:
            cache.write(result)
            return result

    with open(cache_file, "r") as cache:
        return cache.read()

######## map commands to text ############

CommandTable = dict[str, CommandFunction]

commands: CommandTable = { # 1st stage
    "include": _include,
    "verbatim": _verbatim_keep_command,
# -------- optional ---------
# citeproc
    "add sources from": _addsourcesfrom,
    "use citation styles from": _usecitestylefrom,
    "ref": _ref_keep_command,
# plantuml
    "uml": _uml,
# katex
    "formula": _formula
}

commands_after: CommandTable = { # 2nd stage
    "table of contents": _tableofcontents,
    "verbatim": _verbatim,
# -------- optional ---------
# citeproc
    "table of references": _tableofreferences,
    "ref": _ref
}

##########################################

def is_file_newer_than_cache(filename: str) -> Tuple[bool, str]:
    """
    Returns a tuple:
        [1] (bool) if True: file is newer than cache and should
            be recreated.
        [2] (str) Filename for the cache.
    """
    global logger

    os.makedirs(CACHEDIR, exist_ok=True)

    cache_file = os.path.join(CACHEDIR,
        hashlib.sha1(filename.encode()).hexdigest() + '.cache'
    )
    if not os.path.exists(cache_file):
        logger.debug("Cache for %s nonexistent, creating", filename)
        return (True, cache_file)
    
    cache_stat = os.stat(cache_file)

    if (
        os.path.getmtime(filename) > os.path.getmtime(cache_file) \
        or cache_stat.st_size < 1
    ):
        logger.debug("Cache for %s outdated, recreating", filename)
        return (True, cache_file)
    
    logger.debug("Don't need to regenerate cache for %s", filename)
    return (False, cache_file)
    

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