import sys
from typing import TextIO, Callable, Match, Dict
import re

def _include(m: Match) -> str:
    params = m.group(2).strip()
    with open(params, "r") as includedfile:
        return includedfile.read()

COMMAND_RE = re.compile(r"\{\{(.+):(.+)\}\}")

commands: Dict[str, Callable[[Match], str]] = {
    "include": _include,
    #"tableofcontents": _tableofcontents
}

def dispatch_commands(m: Match) -> str:
    global commands

    command, args = (
        m.group(1).strip(),
        m.group(2).strip()
    )

    try:
        return commands[command](m)
    except KeyError:
        return '<div class="fatalError">No such command: %s</div>' % command
    except Exception as e:
        return '<div class="fatalError"><pre>%s</pre></div>' % e.__str__()

def replacer(text: str) -> str:
    global COMMAND_RE
    return (
        re.sub(
            COMMAND_RE, dispatch_commands, text
        )
    )

def process_file(infile: TextIO) -> str:
    content = infile.read()
    content = replacer(content)
    return content

if __name__ == "__main__":
    with open(sys.argv[1], "r") as infile:
        print(process_file(infile))