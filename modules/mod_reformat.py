import os
import re
import json
from operator import itemgetter
import copy

ccmodule = {
    "description": "Reformat FancySubs",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to convert",
        "dst": "Destination file"
    },
    "outputs": {
        "dst": "Output fancusub file"
    },
    "defaults": {
        "priority": 50,  # Normal
        "runOn": "success"
    },
    "status": {
        "progress": "Progress 0-100%",
        "state": "Current state of processing"
    }
}


class SubParser:
    """Parse VTT/SRT files."""

    def __init__(self):
        self.items = []

    @staticmethod
    def time2sec(t):
        ms = t.split(",")[1]
        t = t[:-len(ms) - 1]
        if t.count(":") == 2:
            h, m, s = t.split(":")
        else:
            m, s = t.split(":")
            h = 0
        ts = int(h) * 3600 + int(m) * 60 + int(s) + (int(ms) / 1000.)
        return ts

    def load_srt(self, filename, default_who=None):
        with open(filename, "rb") as f:

            start = end = None
            text = ""

            for line in f.readlines():
                line = line.decode("utf-8").strip()
                if text and line.startswith("-"):
                    # print("Continuation", line)
                    s = {
                        "start": SubParser.time2sec(start) + 0.01,
                        "end": SubParser.time2sec(end),
                        "text": line[1::].strip()}
                    if default_who:
                        s["who"] = default_who
                    self.items.append(s)
                    # text = ""
                    continue
                elif line.startswith("-"):
                    line = line[1:]

                if line.strip() == "":
                    # print("End of comment", text)
                    # End of comment
                    if text and start and end:
                        s = {
                            "start": SubParser.time2sec(start),
                            "end": SubParser.time2sec(end),
                            "text": text
                        }
                        if default_who:
                            s["who"] = default_who

                        self.items.append(s)
                    start = end = None
                    text = ""
                    continue
                if re.match("^\d+$", line):
                    # Just the index, we don't care
                    continue

                m = re.match("(\d+:\d+:\d+,\d+) --> (\d+:\d+:\d+,\d+)", line.replace(".", ","))
                if not m:
                    m = re.match("(\d+:\d+,\d+) --> (\d+:\d+,\d+)", line.replace(".", ","))
                if m:
                    start, end = m.groups()
                    continue

                # print("TEXT", text, "LINE", line)
                if text and text[-1] != "-":
                    text += "<br>"
                    text += line
                else:
                    text = text[:-1] + line  # word has been divided

        return self.items


def balance(lines):
    """
    Ensure that the lines are of similar length
    """
    if not lines:
        return lines

    if len(lines) <= 1:
        return lines

    if len(lines) > 2:
        raise Exception("Must have at most two lines", len(lines))

    if lines[0][-1] == ".":
        return lines

    text = lines[0] + " " + lines[1]
    text = text.replace("  ", " ")

    mid_point = int(len(text) / 2.0)
    # Find the space before the mid point
    pos = text.rfind(" ", 0, mid_point)
    if pos > -1:
        lines[0] = trim(text[:pos])
        lines[1] = trim(text[pos:])
    return lines


def calculate_new_endts(item, position):
    txt = item["text"].replace("<br>", " ")
    time_pr_char = (item["end"] - item["start"]) / float(len(txt))
    return item["start"] + (position * time_pr_char)


def trim(s):
    # Remove additional spaces, also spaces in front of punctuation
    import re

    while True:
        m = re.search("(\s[\W\s])", s)
        if not m:
            break
        s = s[:m.span()[0]] + s[m.span()[0] + 1:]
    return s.strip()


def reformat(items, min_length=2, max_length=42, max_additional=5, max_next_line=10):
    """
    Reformat - min_length is minium time a sub will be on screen
    """

    new_subs = []

    # Need to have items sorted by start time
    items.sort(key=itemgetter("start"))

    for idx, item in enumerate(items):
        sstart = 0
        send = max_length

        if idx < len(items) - 1:
            next_item = items[idx + 1]

        else:
            next_item = None

        txt = trim(item["text"].replace("<br>", " ") + " ")

        print("*", txt)

        # print(item["text"].replace("<br>", "\n") + "\n---")
        # If we've got a "." early in the next sub, merge them.
        if idx < len(items) - 1:
            print("-->", next_item["text"])
            i2 = next_item["text"].find(".", 0, max_next_line)

            print("Early next stop", i2)
            if i2 > -1:
                txt += " " + next_item["text"][0:i2 + 1]
                next_item["text"] = next_item["text"][i2 + 1:]

        # print(item["text"].replace("<br>", "\n"))
        # split at
        lines = []
        while sstart < len(txt):
            split_at = txt.find(".", sstart, send) + 1
            if split_at <= 0:
                split_at = txt.rfind(",", sstart, send) + 1
            if split_at <= 0:
                split_at = txt.rfind(" ", sstart, send)
            if split_at <= 0:
                split_at = len(txt)

            if len(txt) - split_at < max_additional and txt[-1] not in [".", ",", "!", "?"]:
                split_at = len(txt)

            print("SPLITTING AT", sstart, split_at, "'%s'" % txt[sstart:split_at])
            lines.append(txt[sstart:split_at])
            sstart = split_at + 1
            send = sstart + max_length

        if len(lines) > 2:
            pos = len(lines[0]) + len(lines[1]) + 1
            old_end = item["end"]
            item["end"] = calculate_new_endts(item, pos)

            # Is the next item soon?
            if next_item and next_item["start"] - old_end < 2.0:
                next_item["start"] = item["end"]
                next_item["text"] = trim("<br>".join(lines[2:])) + " " + next_item["text"]
            else:
                new_item = copy.copy(item)
                new_item["start"] = item["end"]
                new_item["end"] = old_end
                new_item["text"] = trim("<br>".join(lines[2:]))
                items.insert(idx + 1, new_item)
            lines = lines[:2]

        item["text"] = "<br>".join(balance(lines))
        # Fake
        new_subs.append(item)

        print("\n".join(balance(lines[:2])) + "\n")

    # Sanity
    for s in new_subs:
        if s["end"] < s["start"]:
            print("BAD SUB - Ends before start, reversing!", s)
            f = s["start"]
            s["start"] = s["end"]
            s["end"] = f

        if s["end"] - s["start"] < min_length:
            s["end"] = s["start"] + min_length

    return new_subs


def process_task(cc, task):
    args = task["args"]

    if os.path.splitext(args["src"])[1] in [".vtt", ".srt"]:
        parser = SubParser()
        parser.load_srt(args["src"])
        items = parser.items
    else:
        with open(args["src"], "r") as f:
            items = json.load(f)

    max_length = args.get("max_length", 68)
    max_additional = args.get("max_additional", 20)
    max_next_line = args.get("max_next_line", 15)
    items = reformat(items,
                     max_length=max_length,
                     max_additional=max_additional,
                     max_next_line=max_next_line)

    target = args["dst"]
    if target.endswith(".json"):
        with open(target, "w") as f:
            json.dump(items, f, indent=" ")
    else:
        parser.write_vtt(target, items)

    return 100, {"result": "ok", "dst": target}
