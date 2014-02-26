#!/usr/bin/env python
# encoding: utf-8

"""Parsing of snippet files."""

from collections import defaultdict
import glob
import os

from UltiSnips import _vim
from UltiSnips.snippet.definition import UltiSnipsSnippetDefinition
from UltiSnips.snippet.source.file._base import SnippetFileSource
from UltiSnips.snippet.source.file._common import handle_extends
from UltiSnips.text import LineIterator, head_tail


def _plugin_dir():
    """Calculates the plugin directory for UltiSnips."""
    directory = __file__
    for _ in range(10):
        directory = os.path.dirname(directory)
        if (os.path.isdir(os.path.join(directory, "plugin")) and
            os.path.isdir(os.path.join(directory, "doc"))):
            return directory
    raise Exception("Unable to find the plugin directory.")

def base_snippet_files_for(ft, default=True):
    """Returns a list of snippet files matching the given filetype (ft).
    If default is set to false, it doesn't include shipped files.

    Searches through each path in 'runtimepath' in reverse order,
    in each of these, it searches each directory name listed in
    'g:UltiSnipsSnippetDirectories' in order, then looks for files in these
    directories called 'ft.snippets' or '*_ft.snippets' replacing ft with
    the filetype.
    """
    if _vim.eval("exists('b:UltiSnipsSnippetDirectories')") == "1":
        snippet_dirs = _vim.eval("b:UltiSnipsSnippetDirectories")
    else:
        snippet_dirs = _vim.eval("g:UltiSnipsSnippetDirectories")

    base_snippets = os.path.realpath(os.path.join(_plugin_dir(), "UltiSnips"))
    ret = []
    for rtp in _vim.eval("&runtimepath").split(','):
        for snippet_dir in snippet_dirs:
            pth = os.path.realpath(os.path.expanduser(
                os.path.join(rtp, snippet_dir)))
            patterns = ["%s.snippets", "%s_*.snippets", os.path.join("%s", "*")]
            if not default and pth == base_snippets:
                patterns.remove("%s.snippets")

            for pattern in patterns:
                for fn in glob.glob(os.path.join(pth, pattern % ft)):
                    if fn not in ret:
                        ret.append(fn)
    return ret

def _handle_snippet_or_global(line, lines, python_globals, priority):
    """Parses the snippet that begins at the current line."""
    descr = ""
    opts = ""

    # Ensure this is a snippet
    snip = line.split()[0]

    # Get and strip options if they exist
    remain = line[len(snip):].strip()
    words = remain.split()
    if len(words) > 2:
        # second to last word ends with a quote
        if '"' not in words[-1] and words[-2][-1] == '"':
            opts = words[-1]
            remain = remain[:-len(opts) - 1].rstrip()

    # Get and strip description if it exists
    remain = remain.strip()
    if len(remain.split()) > 1 and remain[-1] == '"':
        left = remain[:-1].rfind('"')
        if left != -1 and left != 0:
            descr, remain = remain[left:], remain[:left]

    # The rest is the trigger
    trig = remain.strip()
    if len(trig.split()) > 1 or "r" in opts:
        if trig[0] != trig[-1]:
            return "error", ("Invalid multiword trigger: '%s'" % trig,
                    lines.line_index)
        trig = trig[1:-1]
    end = "end" + snip
    content = ""

    found_end = False
    for line in lines:
        if line.rstrip() == end:
            content = content[:-1]  # Chomp the last newline
            found_end = True
            break
        content += line

    if not found_end:
        return "error", ("Missing 'endsnippet' for %r" % trig, lines.line_index)

    if snip == "global":
        python_globals[trig].append(content)
    elif snip == "snippet":
        return "snippet", (UltiSnipsSnippetDefinition(priority, trig, content,
            descr, opts, python_globals),)
    else:
        return "error", ("Invalid snippet type: '%s'" % snip, lines.line_index)

def _parse_snippets_file(data):
    """Parse 'data' assuming it is a snippet file. Yields events in the
    file."""

    python_globals = defaultdict(list)
    lines = LineIterator(data)
    current_priority = 0
    for line in lines:
        if not line.strip():
            continue

        head, tail = head_tail(line)
        if head in ("snippet", "global"):
            snippet = _handle_snippet_or_global(line, lines,
                    python_globals, current_priority)
            if snippet is not None:
                yield snippet
        elif head == "extends":
            yield handle_extends(tail, lines.line_index)
        elif head == "clearsnippets":
            yield "clearsnippets", (tail.split(),)
        elif head == "priority":
            try:
                current_priority = int(tail.split()[0])
            except (ValueError, IndexError):
                yield "error", ("Invalid priority %r" % tail, lines.line_index)
        elif head and not head.startswith('#'):
            yield "error", ("Invalid line %r" % line.rstrip(), lines.line_index)

class UltiSnipsFileSource(SnippetFileSource):
    """Manages all snippets definitions found in rtp for ultisnips."""

    def _get_all_snippet_files_for(self, ft):
        return set(base_snippet_files_for(ft))

    def _parse_snippet_file(self, filedata, filename):
        for event, data in _parse_snippets_file(filedata):
            yield event, data